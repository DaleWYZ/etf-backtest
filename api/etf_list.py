"""ETF 预设列表 + 搜索 API"""

from flask import Blueprint, request, jsonify
from engine.data_fetcher import search_etf

etf_bp = Blueprint("etf", __name__)

# 预设 ETF 分组列表（国内可买到的常见 ETF）
PRESET_ETF_GROUPS = [
    {
        "name": "美股宽基",
        "etfs": [
            {"code": "513500", "name": "标普500ETF(博时)"},
            {"code": "159612", "name": "标普500ETF(国泰)"},
            {"code": "159660", "name": "标普500ETF基金"},
            {"code": "513100", "name": "纳指ETF(国泰)"},
            {"code": "159632", "name": "纳指ETF(景顺)"},
            {"code": "159501", "name": "纳斯达克ETF(易方达)"},
            {"code": "159941", "name": "纳指ETF(广发)"},
        ],
    },
    {
        "name": "红利类",
        "etfs": [
            {"code": "510880", "name": "红利ETF(上证红利)"},
            {"code": "159905", "name": "深红利ETF"},
            {"code": "515080", "name": "中证红利ETF"},
            {"code": "515180", "name": "红利ETF易方达"},
            {"code": "515450", "name": "红利低波ETF"},
        ],
    },
    {
        "name": "跨境其他",
        "etfs": [
            {"code": "513050", "name": "中概互联ETF"},
            {"code": "159920", "name": "恒生ETF"},
            {"code": "513520", "name": "日经ETF"},
            {"code": "513030", "name": "德国ETF"},
            {"code": "159866", "name": "印度基金LOF"},
        ],
    },
    {
        "name": "商品/债券",
        "etfs": [
            {"code": "518880", "name": "黄金ETF"},
            {"code": "511010", "name": "国债ETF"},
        ],
    },
    {
        "name": "宽基指数(A股)",
        "etfs": [
            {"code": "510300", "name": "沪深300ETF"},
            {"code": "510500", "name": "中证500ETF"},
            {"code": "510050", "name": "上证50ETF"},
            {"code": "159915", "name": "创业板ETF"},
            {"code": "588000", "name": "科创50ETF"},
        ],
    },
]


@etf_bp.route("/api/etf/presets", methods=["GET"])
def get_presets():
    """返回预设 ETF 分组列表"""
    return jsonify({"groups": PRESET_ETF_GROUPS})


@etf_bp.route("/api/etf/search", methods=["GET"])
def search():
    """搜索 ETF"""
    keyword = request.args.get("keyword", "").strip()
    if not keyword or len(keyword) < 2:
        return jsonify({"results": []})

    results = search_etf(keyword)
    return jsonify({"results": results})
