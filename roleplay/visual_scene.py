"""Supported visual-novel locations selected explicitly by the player."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VisualScene:
    id: str
    place: str
    time: str


SCENES: dict[str, VisualScene] = {
    "main_office": VisualScene("main_office", "夏莱办公室", "白天"),
    "main_office_sunset": VisualScene("main_office_sunset", "夏莱办公室", "黄昏"),
    "main_office_night": VisualScene("main_office_night", "夏莱办公室", "夜晚"),
    "game_dev_room": VisualScene("game_dev_room", "游戏开发部活动室", "白天"),
    "game_dev_room_night": VisualScene("game_dev_room_night", "游戏开发部活动室", "夜晚"),
    "rest_room": VisualScene("rest_room", "休息室", "白天"),
    "rest_room_night": VisualScene("rest_room_night", "休息室", "夜晚"),
    "resting_lounge": VisualScene("resting_lounge", "休息区", "白天"),
    "resting_lounge_night": VisualScene("resting_lounge_night", "休息区", "夜晚"),
}

DEFAULT_SCENE_ID = "main_office"


def normalize_scene_id(value: object) -> str:
    return value if isinstance(value, str) and value in SCENES else ""


def scene_prompt(scene_id: str) -> str:
    scene = SCENES[scene_id]
    return (
        f"当前视觉小说场地：{scene.place}；时间：{scene.time}。"
        "这是用户在界面中手动选定的当前场景，角色可以自然感知并据此回应。"
        "以界面中最新选择的场地为准；对话中提及其他地点不自动改变当前场地。"
        "不要把场景标签当作老师说出的台词。"
    )
