"""ETF 定投回测工具 — 程序入口

双击运行此程序，自动启动 Web 服务并打开浏览器。
"""

import os
import sys
import threading
import webbrowser
import logging

logger = logging.getLogger(__name__)


def get_host_port() -> tuple[str, int]:
    """获取服务器 host 和 port"""
    host = "127.0.0.1"
    port = 5000
    # 尝试环境变量覆盖
    env_port = os.environ.get("ETF_BACKTEST_PORT", "")
    if env_port:
        try:
            port = int(env_port)
        except ValueError:
            pass
    return host, port


def open_browser(url: str):
    """延迟打开浏览器（等服务器就绪）"""
    import time

    time.sleep(1.5)
    try:
        webbrowser.open(url)
        logger.info(f"浏览器已打开: {url}")
    except Exception as e:
        logger.warning(f"无法自动打开浏览器: {e}")
        print(f"请手动打开浏览器访问: {url}")


def main():
    """主入口"""
    print("=" * 60)
    print("  ETF 定投回测工具 v1.0")
    print("=" * 60)
    print()

    from app import create_app

    app = create_app()
    host, port = get_host_port()
    url = f"http://{host}:{port}"

    # 在另一个线程中打开浏览器
    browser_thread = threading.Thread(target=open_browser, args=(url,), daemon=True)
    browser_thread.start()

    print(f"  服务已启动: {url}")
    print(f"  按 Ctrl+C 停止服务")
    print()

    # 启动 Flask（关闭 reloader，单进程模式）
    app.run(host=host, port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
