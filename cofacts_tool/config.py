# import os
# from typing import Optional

# try:
#     # Optional: load .env if present
#     from dotenv import load_dotenv  # type: ignore

#     load_dotenv()
# except Exception:
#     pass


# COFACTS_GRAPHQL_ENDPOINT: str = os.getenv(
#     "COFACTS_GRAPHQL_ENDPOINT", "https://cofacts-api.g0v.tw/graphql"
# )
# COFACTS_APP_SECRET: Optional[str] = os.getenv("COFACTS_APP_SECRET")
# COFACTS_APP_ID: Optional[str] = os.getenv("COFACTS_APP_ID")

# HF_TOKEN: Optional[str] = os.getenv("HF_TOKEN")
# HF_DATASET_NAME: str = os.getenv(
#     "HF_DATASET_NAME", "Cofacts/line-msg-fact-check-tw"
# )

# RATE_LIMIT_MIN_INTERVAL_SEC: float = float(
#     os.getenv("RATE_LIMIT_MIN_INTERVAL_SEC", "0.2")
# )
# RETRY_MAX_ATTEMPTS: int = int(os.getenv("RETRY_MAX_ATTEMPTS", "3"))
# RETRY_MIN_WAIT_SEC: float = float(os.getenv("RETRY_MIN_WAIT_SEC", "0.5"))
# RETRY_MAX_WAIT_SEC: float = float(os.getenv("RETRY_MAX_WAIT_SEC", "4.0"))

# DEFAULT_TOP_K: int = int(os.getenv("DEFAULT_TOP_K", "5"))

# OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "cofact_output")
# COFACTS_WEB_BASE: str = os.getenv("COFACTS_WEB_BASE", "https://cofacts.tw")

import os
from typing import Optional

try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

# ---------- helpers ----------
def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")

def _env_int(name: str, default: int, minv: Optional[int] = None, maxv: Optional[int] = None) -> int:
    try:
        val = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    if minv is not None:
        val = max(minv, val)
    if maxv is not None:
        val = min(maxv, val)
    return val

def _env_path(name: str, default: str) -> str:
    p = os.getenv(name, default)
    return os.path.abspath(os.path.expanduser(p))

# ---------- API / HF ----------
COFACTS_GRAPHQL_ENDPOINT: str = os.getenv("COFACTS_GRAPHQL_ENDPOINT", "https://cofacts-api.g0v.tw/graphql")
COFACTS_APP_SECRET: Optional[str] = os.getenv("COFACTS_APP_SECRET")
COFACTS_APP_ID: Optional[str] = os.getenv("COFACTS_APP_ID")

HF_TOKEN: Optional[str] = os.getenv("HF_TOKEN")
HF_DATASET_NAME: str = os.getenv("HF_DATASET_NAME", "Cofacts/line-msg-fact-check-tw")

# ---------- behavior toggles ----------
DEBUG: bool = _env_bool("DEBUG", False)
COFACTS_CACHE_ENABLE: bool = _env_bool("COFACTS_CACHE_ENABLE", True)  # 向量/TF-IDF 索引快取總開關
COFACTS_SEARCH_ENGINE: str = os.getenv("COFACTS_SEARCH_ENGINE", "tfidf")  # tfidf|bm25|sbert

# SBERT 模型名（僅當 engine=sbert 時使用）
COFACTS_SBERT_MODEL: Optional[str] = os.getenv("COFACTS_SBERT_MODEL")

# HF 本地快取（如果你的 HFClient 有實作 Parquet 快取）
COFACTS_HF_LOCAL_DIR: str = _env_path("COFACTS_HF_LOCAL_DIR", "./.hf_cache")
COFACTS_HF_REFRESH_DAYS: int = _env_int("COFACTS_HF_REFRESH_DAYS", 7, 0, 365)

# 官方 datasets 快取也會參考 HF_* 變數，但我們仍保留讀值供程式判斷
HF_HUB_OFFLINE: bool = _env_bool("HF_HUB_OFFLINE", False)

# ---------- API 抓取邏輯 ----------
COFACTS_API_FIRST: int = _env_int("COFACTS_API_FIRST", 50, 1, 10000)
COFACTS_API_CANDIDATES: int = _env_int("COFACTS_API_CANDIDATES", 3000, 1, 100000)

# ---------- retry / rate limit ----------
RATE_LIMIT_MIN_INTERVAL_SEC: float = float(os.getenv("RATE_LIMIT_MIN_INTERVAL_SEC", "0.2"))
RETRY_MAX_ATTEMPTS: int = _env_int("RETRY_MAX_ATTEMPTS", 3, 1, 10)
RETRY_MIN_WAIT_SEC: float = float(os.getenv("RETRY_MIN_WAIT_SEC", "0.5"))
RETRY_MAX_WAIT_SEC: float = float(os.getenv("RETRY_MAX_WAIT_SEC", "4.0"))

# ---------- output / web ----------
OUTPUT_DIR: str = _env_path("OUTPUT_DIR", "cofact_output")
COFACTS_OUTPUT_UTC: bool = _env_bool("COFACTS_OUTPUT_UTC", True)  # True=UTC(原本行為) / False=本地時間
COFACTS_WEB_BASE: str = os.getenv("COFACTS_WEB_BASE", "https://cofacts.tw")

# ---------- db ----------
COFACTS_DB_URL: str = os.getenv("COFACTS_DB_URL", "sqlite:///cofacts.db")

# 預設 top-k（CLI 可覆蓋）
DEFAULT_TOP_K: int = _env_int("DEFAULT_TOP_K", 5, 1, 200)
