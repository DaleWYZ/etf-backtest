"""日志处理模块 — 内存日志缓冲 + SSE 流式推送 + 连接跟踪自动退出"""

import logging
import os
import threading
import time
from collections import deque
from datetime import datetime


class LogBuffer:
    """线程安全的内存日志缓冲区"""

    def __init__(self, max_size: int = 500):
        self._buffer = deque(maxlen=max_size)
        self._lock = threading.Lock()
        self._counter = 0

    def add(self, level: str, name: str, message: str):
        entry = {
            "id": self._counter,
            "time": datetime.now().strftime("%H:%M:%S"),
            "level": level,
            "name": name,
            "message": message,
        }
        with self._lock:
            self._buffer.append(entry)
            self._counter += 1

    def get_all(self) -> list[dict]:
        with self._lock:
            return list(self._buffer)

    def get_since(self, last_id: int) -> list[dict]:
        with self._lock:
            return [e for e in self._buffer if e["id"] > last_id]

    def get_latest_id(self) -> int:
        with self._lock:
            return self._counter - 1 if self._buffer else -1


# 全局日志缓冲区
log_buffer = LogBuffer()


class ConnectionTracker:
    """SSE 连接跟踪器 — 无客户端时自动退出进程"""

    def __init__(self, idle_timeout: float = 5.0):
        self._count = 0
        self._lock = threading.Lock()
        self._idle_timeout = idle_timeout
        self._shutdown_timer: threading.Timer | None = None

    def add_client(self):
        with self._lock:
            self._count += 1
            # 有新客户端连接，取消定时器
            if self._shutdown_timer:
                self._shutdown_timer.cancel()
                self._shutdown_timer = None

    def remove_client(self):
        with self._lock:
            self._count = max(0, self._count - 1)
            if self._count == 0:
                # 所有客户端断开，启动退出倒计时
                self._shutdown_timer = threading.Timer(self._idle_timeout, self._do_shutdown)
                self._shutdown_timer.daemon = True
                self._shutdown_timer.start()

    def _do_shutdown(self):
        """执行进程退出"""
        with self._lock:
            if self._count > 0:
                return  # 期间有客户端重连，取消退出
        logging.getLogger(__name__).info("所有浏览器已关闭，程序自动退出")
        # 延迟一下让最后的 SSE 响应写完
        time.sleep(0.3)
        os._exit(0)


# 全局连接跟踪器
connection_tracker = ConnectionTracker(idle_timeout=5.0)


class BufferHandler(logging.Handler):
    """自定义 logging handler，将日志写入 LogBuffer"""

    def __init__(self, buffer: LogBuffer):
        super().__init__()
        self.buffer = buffer
        self.setLevel(logging.DEBUG)
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record):
        try:
            name = record.name
            if name.startswith("engine."):
                name = name[7:]
            elif name.startswith("api."):
                name = name[4:]
            self.buffer.add(record.levelname, name, self.format(record))
        except Exception:
            self.handleError(record)


def install_handler():
    handler = BufferHandler(log_buffer)
    handler.setLevel(logging.DEBUG)
    logging.getLogger().addHandler(handler)
    return handler


def sse_generator(last_id: int | None = None, heartbeat_interval: float = 2.0):
    """
    SSE 事件生成器（用于 Flask 流式响应）
    客户端断开时自动触发连接跟踪器的 remove_client
    """
    connection_tracker.add_client()
    try:
        # 初始发送
        if last_id is not None:
            entries = log_buffer.get_since(int(last_id))
        else:
            entries = log_buffer.get_all()

        for entry in entries:
            yield f"id: {entry['id']}\ndata: {_format_entry(entry)}\n\n"

        # 监听新日志
        while True:
            latest = log_buffer.get_latest_id()
            if last_id is not None and latest > last_id:
                new_entries = log_buffer.get_since(last_id)
                for entry in new_entries:
                    yield f"id: {entry['id']}\ndata: {_format_entry(entry)}\n\n"
                    last_id = entry["id"]
            else:
                yield f": heartbeat {time.time()}\n\n"

            time.sleep(heartbeat_interval)
    finally:
        connection_tracker.remove_client()


def _format_entry(entry: dict) -> str:
    return f"[{entry['time']}] [{entry['level']}] [{entry['name']}] {entry['message']}"
