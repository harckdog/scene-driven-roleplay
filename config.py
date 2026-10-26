"""Application configuration."""

import os
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


load_dotenv()

API_KEY = os.getenv("LLM_API_KEY") or os.getenv("MOONSHOT_API_KEY")
BASE_URL = os.getenv("BASE_URL")
MODEL = os.getenv("MODEL")
LLM_API_FORMAT = os.getenv("LLM_API_FORMAT", "auto").strip().lower()
if LLM_API_FORMAT not in {"auto", "responses", "chat_completions"}:
    raise ValueError("LLM_API_FORMAT must be auto, responses, or chat_completions")
def default_vision_model(base_url: str | None, model: str | None) -> str | None:
    """Choose a vision model for known providers; use MODEL elsewhere."""
    host = (urlparse(base_url or "").hostname or "").lower()
    if host in {"open.bigmodel.cn", "api.z.ai"}:
        if (model or "").lower().startswith(("glm-5.3-flash", "glm-4.6v", "glm-4.5v", "glm-4.1v", "glm-4v")):
            return model
        return "glm-4.6v-flash"
    if host in {"api.deepseek.com", "api.deepseek.cn"}:
        return "deepseek-flash"
    return model


# Set VISION_MODEL explicitly when the chosen provider needs a different model.
VISION_MODEL = (os.getenv("VISION_MODEL") or default_vision_model(BASE_URL, MODEL) or "").strip()

DEBUG = os.getenv("DEBUG", "false").lower() == "true"
LLM_CACHE_METRICS = os.getenv("LLM_CACHE_METRICS", "false").lower() == "true"
ROLEPLAY_TIMING = os.getenv("ROLEPLAY_TIMING", "false").lower() == "true"
ROLEPLAY_SCENE_ONLY_TOP_K = int(os.getenv("ROLEPLAY_SCENE_ONLY_TOP_K", "10"))
if ROLEPLAY_SCENE_ONLY_TOP_K < 1:
    raise ValueError("ROLEPLAY_SCENE_ONLY_TOP_K must be positive")
ROLEPLAY_GENERATOR_MAX_OUTPUT_TOKENS = int(os.getenv("ROLEPLAY_GENERATOR_MAX_OUTPUT_TOKENS", "1024"))
if ROLEPLAY_GENERATOR_MAX_OUTPUT_TOKENS < 128:
    raise ValueError("ROLEPLAY_GENERATOR_MAX_OUTPUT_TOKENS must be at least 128")
ROLEPLAY_SCENE_RETRIEVER_MODE = os.getenv("ROLEPLAY_SCENE_RETRIEVER_MODE", "cosine").strip().lower()
if ROLEPLAY_SCENE_RETRIEVER_MODE not in {"cosine", "qwen"}:
    raise ValueError("ROLEPLAY_SCENE_RETRIEVER_MODE must be cosine or qwen")
# A reminder must still arrive promptly when the remote model is busy.  This
# only bounds the optional in-character wording; the fixed reminder fallback
# remains available afterwards.
REMINDER_MODEL_TIMEOUT_SECONDS = float(os.getenv("REMINDER_MODEL_TIMEOUT_SECONDS", "20"))

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
LOCAL_DATA_DIR = PROJECT_DIR / "local_data"
SESSION_DIR = DATA_DIR / "sessions"
SUMMARY_DIR = DATA_DIR / "summaries"
MEMORY_DIR = DATA_DIR / "memories"
EMBEDDING_DIR = DATA_DIR / "embeddings"
ROLEPLAY_DATA_DIR = DATA_DIR / "roleplay"
ROLEPLAY_SESSION_DIR = ROLEPLAY_DATA_DIR / "sessions"
ROLEPLAY_MEMORY_DIR = ROLEPLAY_DATA_DIR / "memory"
ROLEPLAY_MEMORY_INDEX_DIR = ROLEPLAY_DATA_DIR / "memory_indexes"
ALARM_FILE = ROLEPLAY_DATA_DIR / "alarms.json"
APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Shanghai")
# Validate configuration eagerly so scheduled reminders never silently use UTC.
ZoneInfo(APP_TIMEZONE)
KNOWLEDGE_BASE_DIR = LOCAL_DATA_DIR / "knowledge_bases"
KNOWLEDGE_INDEX_DIR = LOCAL_DATA_DIR / "knowledge_indexes"
LOCAL_EMBEDDING_MODEL_DIR = PROJECT_DIR / "models" / "multilingual-minilm"
EMBEDDING_DEVICE = "cpu"

def _project_relative_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else PROJECT_DIR / path


ROLEPLAY_SCENE_RERANKER_MODEL_PATH = _project_relative_path(os.getenv(
    "ROLEPLAY_SCENE_RERANKER_MODEL_PATH", "models/Qwen3-Reranker-0.6B",
))
ROLEPLAY_SCENE_RERANK_CANDIDATES = int(os.getenv("ROLEPLAY_SCENE_RERANK_CANDIDATES", "16"))
if ROLEPLAY_SCENE_RERANK_CANDIDATES < ROLEPLAY_SCENE_ONLY_TOP_K:
    raise ValueError("ROLEPLAY_SCENE_RERANK_CANDIDATES must be at least ROLEPLAY_SCENE_ONLY_TOP_K")


MAX_CONTEXT_MESSAGES = 20
CONTEXT_STRATEGY = "fixed"
SUMMARY_UPDATE_THRESHOLD = 10
MAX_MEMORY_ITEMS = 5
MEMORY_RETRIEVAL_MIN_SCORE = 0.30
ROLEPLAY_MAX_CONTEXT_MESSAGES = 20
ROLEPLAY_MEMORY_ENABLED = os.getenv("ROLEPLAY_MEMORY_ENABLED", "true").lower() == "true"
ROLEPLAY_MEMORY_AUTO_UPDATE_ENABLED = os.getenv("ROLEPLAY_MEMORY_AUTO_UPDATE_ENABLED", "true").lower() == "true"
ROLEPLAY_MEMORY_UPDATE_EVERY_TURNS = int(os.getenv("ROLEPLAY_MEMORY_UPDATE_EVERY_TURNS", "10"))
if ROLEPLAY_MEMORY_UPDATE_EVERY_TURNS < 1:
    raise ValueError("ROLEPLAY_MEMORY_UPDATE_EVERY_TURNS must be positive")
ROLEPLAY_MEMORY_RETRIEVAL_LIMIT = 5
ROLEPLAY_MEMORY_MAX_CHARS = 1200
KNOWLEDGE_RETRIEVAL_LIMIT = 3
KNOWLEDGE_RETRIEVAL_MIN_SCORE = 0.30
KNOWLEDGE_CONTEXT_MAX_CHARS = 4000
KNOWLEDGE_CHUNK_MAX_CHARS = 900
KNOWLEDGE_CHUNK_OVERLAP_CHARS = 120

PAPER = "paper"
EXAM = "exam"
CHAT = "chat"
ROLEPLAY = "roleplay"
DEFAULT_ROLE_ID = "tendou_kei"
MODE_KNOWLEDGE_BASES = {
    PAPER: "paper",
    EXAM: "exam",
    CHAT: "chat",
    ROLEPLAY: None,
}
MODES = {
    PAPER: {"display_name": "论文阅读", "avatar": None},
    EXAM: {"display_name": "习题讲解", "avatar": None},
    CHAT: {"display_name": "日常交流", "avatar": None},
    ROLEPLAY: {"display_name": "角色扮演"},
}
