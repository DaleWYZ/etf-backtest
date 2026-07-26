"""Flask 应用初始化"""

import os
import sys
import logging
from flask import Flask, send_from_directory, Response, request, stream_with_context

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

# 安装日志缓冲处理器（用于前端实时查看）
from engine.log_handler import install_handler, sse_generator
_log_handler = None


def _ensure_log_handler():
    global _log_handler
    if _log_handler is None:
        _log_handler = install_handler()


def create_app() -> Flask:
    """创建 Flask 应用"""
    _ensure_log_handler()

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

    # 日志 SSE 流
    @app.route("/api/logs/stream")
    def log_stream():
        last_id = request.headers.get("Last-Event-ID")
        if last_id:
            try:
                last_id = int(last_id)
            except ValueError:
                last_id = None
        return Response(
            stream_with_context(sse_generator(last_id)),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    # 退出程序（浏览器关闭时前端调用）
    @app.route("/api/shutdown", methods=["POST"])
    def shutdown():
        logger.info("收到浏览器关闭信号，程序退出")
        import threading
        def delayed_exit():
            import time
            time.sleep(0.5)
            os._exit(0)
        threading.Thread(target=delayed_exit, daemon=True).start()
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
