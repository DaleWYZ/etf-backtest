"""金融指标计算模块"""

import numpy as np
import pandas as pd
from scipy import optimize


def calculate_metrics(
    daily_values: pd.DataFrame,
    annual_details: list[dict],
    total_invested: float,
    final_value: float,
    risk_free_rate: float = 0.03,
) -> dict:
    """
    计算全部指标

    Args:
        daily_values: 每日数据 DataFrame，包含 value, cost 列
        annual_details: 年度明细列表
        total_invested: 总投入
        final_value: 最终市值
        risk_free_rate: 无风险利率（默认3%）

    Returns:
        指标字典
    """
    total_return = final_value - total_invested
    total_return_rate = total_return / total_invested if total_invested > 0 else 0

    # 年数
    if daily_values.empty:
        years = 0
    else:
        days = (daily_values.index[-1] - daily_values.index[0]).days
        years = max(days / 365.25, 0.01)

    # CAGR
    cagr = (final_value / total_invested) ** (1 / years) - 1 if total_invested > 0 and years > 0 else 0

    # 最大回撤
    max_drawdown = _calc_max_drawdown(daily_values["value"])

    # 年化波动率
    annual_volatility = _calc_annual_volatility(daily_values["value"])

    # 夏普比率
    sharpe = _calc_sharpe(cagr, annual_volatility, risk_free_rate)

    # 胜率
    win_rate = _calc_win_rate(daily_values)

    # XIRR
    xirr_val = _calc_xirr(daily_values)

    return {
        "total_invested": round(total_invested, 2),
        "final_value": round(final_value, 2),
        "total_return": round(total_return, 2),
        "total_return_rate": round(total_return_rate, 4),
        "cagr": round(cagr, 4),
        "max_drawdown": round(max_drawdown, 4),
        "annual_volatility": round(annual_volatility, 4),
        "sharpe_ratio": round(sharpe, 4),
        "win_rate": round(win_rate, 4),
        "xirr": round(xirr_val, 4),
        "years": round(years, 2),
        "annual_details": annual_details,
    }


def _calc_max_drawdown(daily_values: pd.Series) -> float:
    """计算最大回撤"""
    if daily_values.empty:
        return 0.0
    rolling_max = daily_values.expanding().max()
    drawdown = (daily_values - rolling_max) / rolling_max
    return float(drawdown.min())


def _calc_annual_volatility(daily_values: pd.Series) -> float:
    """计算年化波动率"""
    if len(daily_values) < 2:
        return 0.0
    daily_returns = daily_values.pct_change().dropna()
    if len(daily_returns) < 2:
        return 0.0
    return float(daily_returns.std() * np.sqrt(252))


def _calc_sharpe(cagr: float, annual_volatility: float, risk_free_rate: float = 0.03) -> float:
    """计算夏普比率"""
    if annual_volatility == 0:
        return 0.0
    return (cagr - risk_free_rate) / annual_volatility


def _calc_win_rate(daily_values: pd.DataFrame) -> float:
    """计算盈利交易日占比"""
    if len(daily_values) < 2:
        return 0.0
    if "value" not in daily_values.columns:
        return 0.0
    daily_returns = daily_values["value"].pct_change().dropna()
    if len(daily_returns) == 0:
        return 0.0
    return float((daily_returns > 0).sum() / len(daily_returns))


def _calc_xirr(daily_values: pd.DataFrame) -> float:
    """
    计算 XIRR（内部收益率）

    构建现金流：每个定投日对应一笔负现金流（投入），
    最后一天对应正现金流（市值）。
    使用 Newton 法求解 NPV=0 的折现率。
    """
    if daily_values.empty or "cost" not in daily_values.columns:
        return 0.0

    # 找出所有定投日（cost 有增加的日子）
    cost_series = daily_values["cost"]
    cost_diff = cost_series.diff().fillna(cost_series.iloc[0])

    # 过滤掉成本没有变化的交易日
    inv_dates_mask = cost_diff > 1e-6
    cash_flows = -cost_diff[inv_dates_mask].values  # 负号表示投入（流出）
    cf_dates = daily_values.index[inv_dates_mask]

    if len(cash_flows) == 0:
        return 0.0

    # 最后一天加入最终市值（正现金流，流入）
    final_value = daily_values["value"].iloc[-1]
    cash_flows = np.append(cash_flows, final_value)
    # 追加最终日期
    cf_date_list = list(cf_dates)
    cf_date_list.append(daily_values.index[-1])
    cf_dates = pd.DatetimeIndex(cf_date_list)

    # 计算每笔现金流距第一笔的天数（年化）
    t0 = cf_dates[0]
    times = np.array([(d - t0).days / 365.25 for d in cf_dates])

    def npv(rate):
        """NPV 函数"""
        if rate <= -1:
            return 1e10
        return float(np.sum(cash_flows / (1 + rate) ** times))

    # 初始猜测：总收益率 / 年数 的大致年化
    total_return = (final_value - (-cash_flows.sum())) / (-cash_flows.sum())
    guess = total_return / max(times[-1], 0.01) if times[-1] > 0 else 0.05
    guess = max(min(guess, 2.0), -0.5)  # 限制在合理范围

    try:
        result = optimize.newton(npv, guess, maxiter=100, tol=1e-6)
        if result <= -1:
            return 0.0
        return float(result)
    except (RuntimeError, OverflowError, ValueError):
        # 退化为简单 IRR 估算
        try:
            result = optimize.newton(npv, 0.05, maxiter=100, tol=1e-6)
            if result <= -1:
                return 0.0
            return float(result)
        except Exception:
            return 0.0


def build_annual_details(daily_values: pd.DataFrame) -> list[dict]:
    """构建按年度分解的收益详情"""
    if daily_values.empty:
        return []

    annual_list = []

    for year in range(daily_values.index[0].year, daily_values.index[-1].year + 1):
        year_data = daily_values[daily_values.index.year == year]

        if year_data.empty:
            continue

        # 当年投入
        if len(year_data) > 1:
            cost_diff = year_data["cost"].diff().fillna(0)
        else:
            cost_diff = year_data["cost"] - (
                daily_values["cost"].shift(1).loc[year_data.index[0]]
                if year_data.index[0] in daily_values.index
                and daily_values.index.get_loc(year_data.index[0]) > 0
                else year_data["cost"].iloc[0]
            )
            cost_diff = pd.Series([cost_diff], index=year_data.index)

        # 第一个定投日的cost变化 = 当日cost值（首次买入）
        if year == daily_values.index[0].year:
            first_idx = year_data.index[0]
            if first_idx == daily_values.index[0]:
                cost_diff.iloc[0] = year_data["cost"].iloc[0]

        invested = round(float(cost_diff[cost_diff > 0].sum()), 2)

        # 年初市值：取上一年最后一个交易日的市值
        if year == daily_values.index[0].year:
            start_value = 0.0
        else:
            prev_year_data = daily_values[daily_values.index.year == year - 1]
            if not prev_year_data.empty:
                start_value = float(prev_year_data["value"].iloc[-1])
            else:
                start_value = 0.0

        # 年末市值
        end_value = float(year_data["value"].iloc[-1])

        # 当年收益
        annual_return = end_value - start_value - invested

        # 当年收益率
        denominator = start_value + invested / 2
        if denominator > 0:
            return_rate = annual_return / denominator
        else:
            return_rate = 0.0

        annual_list.append(
            {
                "year": year,
                "invested": round(invested, 2),
                "start_value": round(start_value, 2),
                "end_value": round(end_value, 2),
                "return": round(annual_return, 2),
                "return_rate": round(return_rate, 4),
            }
        )

    return annual_list
