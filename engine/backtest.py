"""ETF 定投回测核心引擎"""

import logging
from datetime import datetime
import pandas as pd
import numpy as np

from .data_fetcher import get_etf_data, get_etf_name
from .metrics import calculate_metrics, build_annual_details

logger = logging.getLogger(__name__)


def run_backtest(
    etf_code: str,
    start_date: str,
    end_date: str,
    amount: float = 100.0,
    frequency: str = "daily",
    weekday: int = 1,
    month_day: int = 1,
    fee_rate: float = 0.00015,
) -> dict:
    """
    执行 ETF 定投回测

    Args:
        etf_code: ETF 代码
        start_date: 回测开始日期 "YYYY-MM-DD"
        end_date: 回测结束日期 "YYYY-MM-DD"
        amount: 每次定投金额（元）
        frequency: 定投频率 "daily" | "weekly" | "monthly"
        weekday: 周定投时的星期 (1=周一, 5=周五)
        month_day: 月定投时的日期 (1-28)
        fee_rate: 买入手续费率（默认万1.5 = 0.00015）

    Returns:
        回测结果字典
    """
    # 1. 获取数据
    df = get_etf_data(etf_code)
    if df is None or df.empty:
        raise ValueError(f"无法获取 ETF {etf_code} 的数据")

    # 2. 截取日期范围
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)

    # 扩展 start 往前一点，确保能找到第一个定投日
    lookback_start = start - pd.DateOffset(days=90)
    df_period = df[(df.index >= lookback_start) & (df.index <= end)].copy()

    if df_period.empty:
        raise ValueError(f"ETF {etf_code} 在 {start_date} ~ {end_date} 期间无数据")

    # 3. 确定定投日期
    investment_dates = _get_investment_dates(df_period, start, end, frequency, weekday, month_day)

    if not investment_dates:
        raise ValueError(f"在指定时间段内没有找到符合条件（{frequency}）的交易日")

    # 4. 模拟定投
    daily_values = _simulate_dca(df_period, investment_dates, start, end, amount, fee_rate)

    # 5. 计算指标
    total_invested = float(daily_values["cost"].iloc[-1])
    final_value = float(daily_values["value"].iloc[-1])

    # 年度明细
    annual_details = build_annual_details(daily_values)

    # 汇总指标
    metrics = calculate_metrics(daily_values, annual_details, total_invested, final_value)

    # 6. ETF 名称
    etf_name = get_etf_name(etf_code)

    # 7. 构建用于前端的每日数据（转换为可JSON序列化格式）
    daily_list = []
    # 只返回回测区间内的数据点（降采样，每天最多1个点）
    mask = (daily_values.index >= start) & (daily_values.index <= end)
    display_df = daily_values[mask]

    # 如果数据点太多，降采样（最多约500个点给前端画图）
    if len(display_df) > 500:
        step = len(display_df) // 500
        display_df = display_df.iloc[::step]

    for idx, row in display_df.iterrows():
        daily_list.append(
            {
                "date": idx.strftime("%Y-%m-%d"),
                "nav": round(float(row["nav"]), 4),
                "total_shares": round(float(row["total_shares"]), 4),
                "cost": round(float(row["cost"]), 2),
                "value": round(float(row["value"]), 2),
            }
        )

    return {
        "etf_code": etf_code,
        "etf_name": etf_name,
        **metrics,
        "daily_values": daily_list,
        "investment_count": len(investment_dates),
    }


def _get_investment_dates(
    df: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    frequency: str,
    weekday: int,
    month_day: int,
) -> list[pd.Timestamp]:
    """
    确定定投日期列表

    Args:
        df: 含所有交易日的 DataFrame
        start: 回测开始日期
        end: 回测结束日期
        frequency: "daily" | "weekly" | "monthly"
        weekday: 周定投的星期几 (1=Mon...5=Fri)
        month_day: 月定投的几号 (1-28)

    Returns:
        定投日期列表（必须是实际交易日）
    """
    # 在回测区间内的交易日
    mask = (df.index >= start) & (df.index <= end)
    trading_days = df[mask].index.sort_values()

    if frequency == "daily":
        return list(trading_days)

    elif frequency == "weekly":
        # 在回测区间内，找出指定 weekday 对应的交易日
        # 对于每个 week，找该周的指定 weekday 最近的交易日
        investment_dates = []
        target_weekday = weekday % 7  # 0=周日, 1=周一...

        # 按周分组
        trading_days_series = pd.Series(trading_days, index=trading_days)
        weekly_groups = trading_days_series.groupby(
            [trading_days_series.index.isocalendar().year, trading_days_series.index.isocalendar().week]
        )

        for (year, week), group in weekly_groups:
            # 该周中，找到 weekday 匹配的交易日，或最近的
            group_dates = group.index
            target_date = None

            # 尝试找 weekday 完全匹配的
            for d in group_dates:
                if d.day_of_week == target_weekday:
                    target_date = d
                    break

            # 如果没有精确匹配，找最接近的（偏后）
            if target_date is None:
                best_diff = 999
                for d in group_dates:
                    diff = abs(d.day_of_week - target_weekday)
                    if diff < best_diff:
                        best_diff = diff
                        target_date = d

            if target_date is not None:
                investment_dates.append(target_date)

        return sorted(investment_dates)

    elif frequency == "monthly":
        # 每月指定 day 号，找到最近交易日
        investment_dates = []

        # 按月份分组
        for month_start, group in trading_days.to_series().groupby(pd.Grouper(freq="MS")):
            if group.empty:
                continue
            group_dates = group.index
            year_month = month_start.strftime("%Y-%m")

            # 目标日期
            try:
                target = pd.Timestamp(f"{year_month}-{month_day:02d}")
            except (ValueError, OverflowError):
                continue

            # 找最接近的交易日（优先偏后，和定投逻辑一致）
            best_date = None
            best_diff = 999
            for d in group_dates:
                diff = abs((d - target).days)
                if diff < best_diff:
                    best_diff = diff
                    best_date = d

            if best_date is not None:
                investment_dates.append(best_date)

        return sorted(investment_dates)

    else:
        raise ValueError(f"不支持的定投频率: {frequency}")


def _simulate_dca(
    df: pd.DataFrame,
    investment_dates: list[pd.Timestamp],
    start: pd.Timestamp,
    end: pd.Timestamp,
    amount: float,
    fee_rate: float,
) -> pd.DataFrame:
    """
    模拟定投过程

    Returns:
        DataFrame，索引为日期，包含:
        - nav: 当日净值（收盘价）
        - total_shares: 累计份额
        - cost: 累计投入
        - value: 累计市值
    """
    # 构建包含所有交易日 + 定投标记的 DataFrame
    mask = (df.index >= start) & (df.index <= end)
    sim_df = df[mask][["close"]].copy()
    sim_df.rename(columns={"close": "nav"}, inplace=True)

    inv_set = set(investment_dates)

    total_shares = 0.0
    total_cost = 0.0

    shares_list = []
    cost_list = []
    value_list = []

    for idx in sim_df.index:
        nav = float(sim_df.at[idx, "nav"])

        if idx in inv_set:
            # 定投日：买入
            fee = amount * fee_rate
            net_amount = amount - fee
            shares_bought = net_amount / nav if nav > 0 else 0
            total_shares += shares_bought
            total_cost += amount

        shares_list.append(total_shares)
        cost_list.append(total_cost)
        value_list.append(total_shares * nav)

    sim_df["total_shares"] = shares_list
    sim_df["cost"] = cost_list
    sim_df["value"] = value_list

    return sim_df
