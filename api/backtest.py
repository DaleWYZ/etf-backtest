"""回测 API 端点"""

import logging
from flask import Blueprint, request, jsonify
from engine.backtest import run_backtest

logger = logging.getLogger(__name__)

backtest_bp = Blueprint("backtest", __name__)


@backtest_bp.route("/api/backtest", methods=["POST"])
def do_backtest():
    """
    执行回测

    POST body:
    {
        "etf_code": "513500",
        "start_date": "2020-01-01",
        "end_date": "2024-12-31",
        "amount": 100,
        "frequency": "daily",       // "daily" | "weekly" | "monthly"
        "weekday": 1,               // weekly: 1=周一 ~ 5=周五
        "month_day": 1,             // monthly: 1-28
        "fee_rate": 0.00015         // 默认万1.5
    }
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({"error": "请求体为空"}), 400

        etf_code = str(data.get("etf_code", "")).strip()
        if not etf_code:
            return jsonify({"error": "请提供 ETF 代码"}), 400

        start_date = str(data.get("start_date", "")).strip()
        end_date = str(data.get("end_date", "")).strip()
        if not start_date or not end_date:
            return jsonify({"error": "请提供回测起止日期"}), 400

        amount = float(data.get("amount", 100))
        if amount <= 0:
            return jsonify({"error": "定投金额必须大于0"}), 400

        frequency = str(data.get("frequency", "daily")).strip()
        if frequency not in ("daily", "weekly", "monthly"):
            return jsonify({"error": "定投频率必须为 daily/weekly/monthly"}), 400

        weekday = int(data.get("weekday", 1))
        weekday = max(1, min(5, weekday))

        month_day = int(data.get("month_day", 1))
        month_day = max(1, min(28, month_day))

        fee_rate = float(data.get("fee_rate", 0.00015))
        fee_rate = max(0, min(0.01, fee_rate))  # 手续费率 0~1%

        logger.info(
            f"回测请求: {etf_code} | {start_date} ~ {end_date} | "
            f"{amount}元 | {frequency} | 费率{fee_rate:.4%}"
        )

        result = run_backtest(
            etf_code=etf_code,
            start_date=start_date,
            end_date=end_date,
            amount=amount,
            frequency=frequency,
            weekday=weekday,
            month_day=month_day,
            fee_rate=fee_rate,
        )

        return jsonify(result)

    except ValueError as e:
        logger.warning(f"回测参数错误: {e}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"回测失败: {e}", exc_info=True)
        return jsonify({"error": f"回测失败: {str(e)}"}), 500
