"""日志处理模块 — 内存日志缓冲 + SSE 流式推送"""

import logging
import threading
import time
from collections import deque
from datetime import datetime


class LogBuffer:
    """线程安全的内存日志缓冲区"""

    def __init__(self, max_size: int = 500):
        self._buffer = deque(maxlen=max_size)
        self._lock = threading.Lock()
        self._counter = 0  # 每条日志的唯一 ID，SSE 客户端用 last_id 恢复

    def add(self, level: str, name: str, message: str):
        """添加一条日志"""
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
        """获取全部缓存日志"""
        with self._lock:
            return list(self._buffer)

    def get_since(self, last_id: int) -> list[dict]:
        """获取自 last_id 之后的新日志"""
        with self._lock:
            return [e for e in self._buffer if e["id"] > last_id]

    def get_latest_id(self) -> int:
        with self._lock:
            return self._counter - 1 if self._buffer else -1


# 全局日志缓冲区
log_buffer = LogBuffer()


class BufferHandler(logging.Handler):
    """自定义 logging handler，将日志写入 LogBuffer"""

    def __init__(self, buffer: LogBuffer):
        super().__init__()
        self.buffer = buffer
        self.setLevel(logging.DEBUG)
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record):
        try:
            # 缩短 name 便于显示
            name = record.name
            if name.startswith("engine."):
                name = name[7:]
            elif name.startswith("api."):
                name = name[4:]
            self.buffer.add(record.levelname, name, self.format(record))
        except Exception:
            self.handleError(record)


def install_handler():
    """将 BufferHandler 安装到根 logger"""
    handler = BufferHandler(log_buffer)
    handler.setLevel(logging.DEBUG)
    logging.getLogger().addHandler(handler)
    return handler


def sse_generator(last_id: int | None = None, heartbeat_interval: float = 2.0):
    """
    SSE 事件生成器（用于 Flask 流式响应）

    客户端连接后：
    1. 首先发送所有历史日志
    2. 然后每隔 heartbeat_interval 秒检查新日志并推送
    """
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
            # 发送心跳（SSE 注释，保持连接）
            yield f": heartbeat {time.time()}\n\n"

        time.sleep(heartbeat_interval)


def _format_entry(entry: dict) -> str:
    """格式化日志条目为单行文本"""
    return f"[{entry['time']}] [{entry['level']}] [{entry['name']}] {entry['message']}"
