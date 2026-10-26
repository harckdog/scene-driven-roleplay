"""
summary/manager.py

负责管理 Conversation Summary。

职责：
    - 创建 Summary
    - 读取 Summary
    - 保存 Summary
    - 清空 Summary

不负责：
    - 判断是否更新
    - 调用 LLM
    - 生成 Summary
"""

import json
from copy import deepcopy
from pathlib import Path

from config import SUMMARY_DIR


DEFAULT_SUMMARY = {
    "summary": "",
    "last_index":0
}


def _summary_path(mode: str) -> Path:
    """
    返回指定模式对应的 Summary 文件路径。
    """
    return SUMMARY_DIR / f"{mode}.json"


def exists(mode: str) -> bool:
    """
    判断 Summary 是否存在。
    """
    return _summary_path(mode).exists()


def create(mode: str) -> None:
    """
    创建 Summary。
    """

    if exists(mode):
        return

    save(mode, deepcopy(DEFAULT_SUMMARY))


def load(mode: str) -> dict:
    """
    加载 Summary Record。
    """

    path = _summary_path(mode)

    if not path.exists():
        return deepcopy(DEFAULT_SUMMARY)

    try:
        with open(path, "r", encoding="utf-8") as f:
            record = json.load(f)
    except (OSError, json.JSONDecodeError):
        return deepcopy(DEFAULT_SUMMARY)

    if not isinstance(record, dict):
        return deepcopy(DEFAULT_SUMMARY)

    summary = record.get("summary", "")
    last_index = record.get("last_index", 0)
    return {
        "summary": summary if isinstance(summary, str) else "",
        "last_index": last_index if isinstance(last_index, int) and last_index >= 0 else 0,
    }


def save(mode: str, record: dict) -> None:
    """
    保存 Summary Record。
    """

    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    with open(_summary_path(mode), "w", encoding="utf-8") as f:
        json.dump(
            record,
            f,
            ensure_ascii=False,
            indent=4
        )


def clear(mode: str) -> None:
    """
    清空 Summary。
    """

    save(mode, deepcopy(DEFAULT_SUMMARY))
