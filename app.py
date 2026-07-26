"""Flask 应用初始化"""

import os
import sys
import logging
from flask import Flask, send_from_directory

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


def create_app() -> Flask:
    """创建 Flask 应用"""
    static_dir = get_static_dir()

    app = Flask(
        __name__,
        static_folder=static_dir,
        static_url_path="/static",
    )

    # 注册蓝图
    from api.etf_list import etf_bp
    from api.backtest import backtest_bp

    app.register_blueprint(etf_bp)
    app.register_blueprint(backtest_bp)

    # 首页路由
    @app.route("/")
    def index():
        return send_from_directory(static_dir, "index.html")

    # 健康检查
    @app.route("/api/health")
    def health():
        return {"status": "ok"}

    return app


def get_static_dir() -> str:
    """获取静态文件目录（兼容 PyInstaller 打包）"""
    if getattr(sys, "frozen", False):
        # PyInstaller 打包后
        base_path = sys._MEIPASS  # type: ignore
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))

    static_dir = os.path.join(base_path, "static")
    if not os.path.exists(static_dir):
        # 备用：当前目录
        static_dir = os.path.join(os.getcwd(), "static")
    return static_dir
