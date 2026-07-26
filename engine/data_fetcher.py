"""ETF 数据获取模块 — 从 akshare 拉取日线数据并缓存到 SQLite"""

import os
import sqlite3
import logging
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import patch
import pandas as pd

logger = logging.getLogger(__name__)

# 缓存数据库路径
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".etf_backtest")
CACHE_DB = os.path.join(CACHE_DIR, "etf_cache.db")
CACHE_TTL_HOURS = 24


@contextmanager
def _no_proxy_session():
    """
    临时让所有 requests.Session 忽略系统代理。
    不修改环境变量，不影响用户浏览器代理。
    """
    import requests as _requests

    OriginalSession = _requests.Session

    class _NoProxySession(OriginalSession):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.trust_env = False  # 不读取系统代理
            self.proxies.clear()

    with patch("requests.Session", _NoProxySession):
        yield


def _ensure_cache_dir():
    """确保缓存目录存在"""
    os.makedirs(CACHE_DIR, exist_ok=True)


def _get_connection():
    """获取 SQLite 连接，自动创建表"""
    _ensure_cache_dir()
    conn = sqlite3.connect(CACHE_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS etf_daily (
            code TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            PRIMARY KEY (code, date)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cache_meta (
            code TEXT PRIMARY KEY,
            last_update TEXT NOT NULL,
            data_start TEXT,
            data_end TEXT
        )
    """)
    conn.commit()
    return conn


def _is_cache_fresh(code: str) -> bool:
    """检查缓存是否在有效期内（24小时）"""
    conn = _get_connection()
    row = conn.execute(
        "SELECT last_update FROM cache_meta WHERE code = ?", (code,)
    ).fetchone()
    conn.close()
    if not row:
        return False
    last_update = datetime.fromisoformat(row[0])
    return (datetime.now() - last_update) < timedelta(hours=CACHE_TTL_HOURS)


def _get_cached_data(code: str) -> pd.DataFrame | None:
    """从 SQLite 缓存读取数据"""
    conn = _get_connection()
    df = pd.read_sql_query(
        "SELECT date, open, high, low, close, volume FROM etf_daily WHERE code = ? ORDER BY date",
        conn,
        params=(code,),
    )
    conn.close()
    if df.empty:
        return None
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)
    df.sort_index(inplace=True)
    return df


def _save_to_cache(code: str, df: pd.DataFrame):
    """将 DataFrame 写入 SQLite 缓存"""
    conn = _get_connection()
    df_to_save = df.reset_index()
    df_to_save["code"] = code
    df_to_save["date"] = df_to_save["date"].dt.strftime("%Y-%m-%d")

    # 批量插入 / 替换
    rows = []
    for _, row in df_to_save.iterrows():
        rows.append(
            (code, str(row["date"]), float(row["open"]), float(row["high"]),
             float(row["low"]), float(row["close"]), float(row["volume"]))
        )
    conn.executemany(
        """INSERT OR REPLACE INTO etf_daily (code, date, open, high, low, close, volume)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )

    data_start = df_to_save["date"].min()
    data_end = df_to_save["date"].max()
    conn.execute(
        """INSERT OR REPLACE INTO cache_meta (code, last_update, data_start, data_end)
           VALUES (?, ?, ?, ?)""",
        (code, datetime.now().isoformat(), data_start, data_end),
    )
    conn.commit()
    conn.close()


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """标准化 akshare 返回的 DataFrame 列名和格式"""
    col_map = {
        "日期": "date", "date": "date",
        "开盘": "open", "open": "open",
        "最高": "high", "high": "high",
        "最低": "low", "low": "low",
        "收盘": "close", "close": "close",
        "成交量": "volume", "volume": "volume", "成交数量": "volume",
    }
    df.rename(columns=col_map, inplace=True)
    df = df.loc[:, ~df.columns.duplicated()].copy()

    required_cols = ["date", "open", "high", "low", "close", "volume"]
    for c in required_cols:
        if c not in df.columns:
            if c == "volume":
                df[c] = 0.0
            else:
                raise ValueError(f"缺少必要列: {c}，实际列: {df.columns.tolist()}")

    df = df[required_cols].copy()
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)
    df.sort_index(inplace=True)
    df.dropna(subset=["close"], inplace=True)
    return df


def _fetch_from_akshare(code: str) -> pd.DataFrame:
    """从 akshare 拉取 ETF 日线数据（多数据源自动切换 + 重试）"""
    with _no_proxy_session():
        import akshare as ak

        # 数据源列表：按优先级依次尝试
        sources = [
            (
                "东方财富-ETF",
                lambda: ak.fund_etf_hist_em(symbol=code, period="daily", adjust="qfq"),
            ),
            (
                "东方财富-A股",
                lambda: ak.stock_zh_a_hist(
                    symbol=code, period="daily",
                    start_date="19700101", end_date="20991231",
                    adjust="qfq"
                ),
            ),
            (
                "新浪财经",
                lambda: ak.fund_etf_hist_sina(symbol=code),
            ),
        ]

        for src_name, fetch_fn in sources:
            last_error = None
            for attempt in range(2):
                try:
                    logger.info(f"正在获取 {code} 数据 (来源: {src_name})...")
                    df = fetch_fn()

                    if df is None or df.empty:
                        raise ValueError(f"{src_name} 未返回 {code} 的数据")

                    df = _normalize_df(df)
                    logger.info(f"成功获取 {code}，共 {len(df)} 条记录 (来源: {src_name})")
                    return df

                except Exception as e:
                    last_error = e
                    logger.warning(f"[{src_name}] 请求失败 (第{attempt+1}/2次): {type(e).__name__}: {e}")
                    if attempt < 1:
                        time.sleep(2)

            logger.warning(f"[{src_name}] 数据源失败，尝试下一个...")

        # 所有数据源都失败
        raise RuntimeError(
            f"无法获取 {code} 的数据，已尝试3个数据源均失败。\n"
            f"请确认: 1) 网络可正常访问互联网  2) ETF代码 {code} 正确\n"
            f"最后的错误: {type(last_error).__name__}: {last_error}"
        )


def get_etf_data(code: str, force_refresh: bool = False) -> pd.DataFrame:
    """
    获取 ETF 日线数据（优先从缓存读取）

    Args:
        code: ETF 代码，如 "513500"
        force_refresh: 是否强制刷新缓存

    Returns:
        DataFrame，索引为日期，包含 open/high/low/close/volume 列
    """
    code = str(code).strip()

    # 尝试从缓存读取
    if not force_refresh and _is_cache_fresh(code):
        cached = _get_cached_data(code)
        if cached is not None and not cached.empty:
            logger.info(f"使用缓存数据: {code} ({len(cached)} 条)")
            return cached

    # 检查是否需要增量更新
    if not force_refresh:
        cached = _get_cached_data(code)
        if cached is not None and not cached.empty:
            # 尝试增量拉取最近数据
            last_cached_date = cached.index.max()
            try:
                new_data = _fetch_from_akshare(code)
                if not new_data.empty:
                    _save_to_cache(code, new_data)
                    return new_data
            except Exception:
                pass  # 增量拉取失败，返回缓存数据
            return cached

    # 全量拉取
    df = _fetch_from_akshare(code)
    if df is not None and not df.empty:
        _save_to_cache(code, df)
    return df


def search_etf(keyword: str) -> list[dict]:
    """
    搜索 ETF
    """
    with _no_proxy_session():
        try:
            import akshare as ak

            df = ak.fund_etf_category_sina(symbol="ETF基金")
            if df is None or df.empty:
                return []

            keyword_lower = keyword.lower()
            mask = df["名称"].str.contains(keyword, case=False, na=False) | df["代码"].str.contains(
                keyword, case=False, na=False
            )
            matched = df[mask].head(20)

            results = []
            for _, row in matched.iterrows():
                results.append(
                    {
                        "code": str(row["代码"]),
                        "name": str(row["名称"]),
                    }
                )
            return results
        except Exception as e:
            logger.warning(f"ETF 搜索失败: {e}")
            return []


def get_etf_name(code: str) -> str:
    """获取 ETF 名称"""
    with _no_proxy_session():
        try:
            import akshare as ak

            df = ak.fund_etf_category_sina(symbol="ETF基金")
            if df is not None and not df.empty:
                row = df[df["代码"] == code]
                if not row.empty:
                    return str(row.iloc[0]["名称"])
        except Exception:
            pass
    return f"ETF {code}"
