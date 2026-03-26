# -*- coding: utf-8 -*-
"""
结构化日志配置
输出 JSON 格式，便于接入阿里云 SLS 等日志平台
"""

import logging
import sys
import json
import traceback
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """将日志记录序列化为单行 JSON"""

    def format(self, record: logging.LogRecord) -> str:
        log: dict = {
            "time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # 附加上下文字段（通过 extra= 传入）
        for key in ("request_id", "session_id", "job_id", "duration_ms"):
            if hasattr(record, key):
                log[key] = getattr(record, key)

        if record.exc_info:
            log["exc"] = traceback.format_exception(*record.exc_info)

        return json.dumps(log, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    """
    初始化全局日志配置，应在应用启动时调用一次。
    开发环境可传 level="DEBUG"。
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 清除已有 handler，避免重复输出
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)

    # 降低第三方库的噪音
    for noisy in ("uvicorn.access", "httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
