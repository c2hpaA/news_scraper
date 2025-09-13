# # cofacts_tool/index.py
# from __future__ import annotations
# import json, os, time, hashlib
# from typing import List, Tuple, Optional

# import joblib
# from scipy import sparse
# from sklearn.feature_extraction.text import TfidfVectorizer
# from sklearn.preprocessing import normalize

# from .hf_client import HFClient

# import os

# CACHE_DIR = os.path.abspath(
#     os.getenv("COFACTS_CACHE_DIR", os.path.join(os.path.expanduser("~"), ".cofacts_cache"))
# )

# # 自動轉成絕對路徑

# VEC_PATH   = os.path.join(CACHE_DIR, "tfidf_vec.joblib")
# MAT_PATH   = os.path.join(CACHE_DIR, "tfidf_mat.npz")
# IDS_PATH   = os.path.join(CACHE_DIR, "ids.jsonl")
# META_PATH  = os.path.join(CACHE_DIR, "meta.json")

# def _ensure_dir() -> None:
#     os.makedirs(CACHE_DIR, exist_ok=True)

# def _texts_hash(texts: List[str]) -> str:
#     h = hashlib.sha256()
#     for t in texts:
#         h.update((t or "").encode("utf-8", "ignore"))
#         h.update(b"\n")
#     return h.hexdigest()

# def build_index(min_df: int = 2, ngram: Tuple[int, int] = (1,2)) -> str:
#     """建立 TF-IDF 向量快取（一次）。之後查詢只需載入快取比相似度。"""
#     _ensure_dir()
#     hf = HFClient(); hf.load()
#     docs = hf.joined_articles()

#     # 取文本與 id
#     texts = [ (d.get("text") or "") for d in docs ]
#     ids   = [ str(d.get("id")) for d in docs ]
#     if not texts:
#         raise RuntimeError("No HF texts available to build index.")

#     # 向量化
#     vec = TfidfVectorizer(min_df=min_df, ngram_range=ngram)
#     X = vec.fit_transform(texts)
#     X = normalize(X, norm="l2", copy=False)

#     # 存檔
#     joblib.dump(vec, VEC_PATH)
#     sparse.save_npz(MAT_PATH, X)
#     with open(IDS_PATH, "w", encoding="utf-8") as f:
#         for id_ in ids:
#             f.write(json.dumps({"id": id_}, ensure_ascii=False) + "\n")

#     meta = {
#         "built_at": int(time.time()),
#         "num_docs": len(texts),
#         "min_df": min_df,
#         "ngram": list(ngram),
#         "texts_sha256": _texts_hash(texts)[:16],  # 簡短指紋
#         "versions": {
#             "sklearn": __import__("sklearn").__version__,
#             "scipy": __import__("scipy").__version__,
#         },
#     }
#     with open(META_PATH, "w", encoding="utf-8") as f:
#         json.dump(meta, f, ensure_ascii=False, indent=2)

#     return CACHE_DIR

# def cache_exists() -> bool:
#     return all(os.path.exists(p) for p in (VEC_PATH, MAT_PATH, IDS_PATH))

# def load_cache():
#     """載入快取，回傳 (vec, X, ids)；若不存在則回傳 None。"""
#     if not cache_exists():
#         return None
#     vec = joblib.load(VEC_PATH)
#     X   = sparse.load_npz(MAT_PATH)
#     ids: List[str] = []
#     with open(IDS_PATH, "r", encoding="utf-8") as f:
#         for line in f:
#             try:
#                 ids.append(json.loads(line)["id"])
#             except Exception:
#                 continue
#     return vec, X, ids

# def query_cached_similarity(query: str, top_n: int = 5000) -> Optional[List[Tuple[str, float]]]:
#     """用快取做相似度。回傳 [(id, score)]，高到低；快取不存在則回 None。"""
#     loaded = load_cache()
#     if not loaded:
#         print("[DEBUG] cache not found, fallback to live TF-IDF")
#         return None
#     print(f"[DEBUG] using cache from {CACHE_DIR}")
#     vec, X, ids = loaded
#     qv = vec.transform([(query or "").strip()])
#     # X, qv 都已 L2 normalize（X 在 build 時），這裡補一層保險
#     qv = normalize(qv, norm="l2", copy=False)
#     sims = (X @ qv.T).toarray().ravel()
#     # 取 top_n
#     top_n = min(top_n, len(sims))
#     idx = sims.argsort()[-top_n:][::-1]
#     return [(ids[i], float(sims[i])) for i in idx]
# cofacts_tool/index.py
from __future__ import annotations
import json, os, time, hashlib
from typing import List, Tuple, Optional

import joblib
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

from .hf_client import HFClient
from .config import (
    COFACTS_CACHE_ENABLE,
    DEBUG,
)

# 統一從 ENV 讀，但轉絕對路徑
CACHE_DIR = os.path.abspath(
    os.getenv("COFACTS_CACHE_DIR", os.path.join(os.path.expanduser("~"), ".cofacts_cache"))
)
VEC_PATH   = os.path.join(CACHE_DIR, "tfidf_vec.joblib")
MAT_PATH   = os.path.join(CACHE_DIR, "tfidf_mat.npz")
IDS_PATH   = os.path.join(CACHE_DIR, "ids.jsonl")
META_PATH  = os.path.join(CACHE_DIR, "meta.json")

def _ensure_dir() -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)

def _texts_hash(texts: List[str]) -> str:
    h = hashlib.sha256()
    for t in texts:
        h.update((t or "").encode("utf-8", "ignore"))
        h.update(b"\n")
    return h.hexdigest()

def _debug(msg: str) -> None:
    if DEBUG:
        print(f"[DEBUG] {msg}")

def build_index(min_df: int = 2, ngram: Tuple[int, int] = (1,2)) -> str:
    """
    建立 TF-IDF 向量快取（一次）。之後查詢只需載入快取比相似度。
    - 預設 analyzer 使用 ENV: COFACTS_TFIDF_ANALYZER（word|char|char_wb），預設 'word'
      * 中文建議 char_wb（在字詞不分的情況下表現較穩定）
    """
    _ensure_dir()
    hf = HFClient(); hf.load()
    docs = hf.joined_articles()

    # 取文本與 id（先去空、去重、排序保證穩定）
    seen = set()
    pairs = []
    for d in docs:
        aid = str(d.get("id"))
        if not aid or aid in seen:
            continue
        txt = (d.get("text") or "").strip()
        if not txt:
            continue
        seen.add(aid)
        pairs.append((aid, txt))

    if not pairs:
        raise RuntimeError("No HF texts available to build index.")

    # 依 id 排序，確保行列對齊與可重現
    pairs.sort(key=lambda x: x[0])
    ids   = [p[0] for p in pairs]
    texts = [p[1] for p in pairs]

    analyzer = os.getenv("COFACTS_TFIDF_ANALYZER", "word")
    _debug(f"Building TF-IDF index: min_df={min_df}, ngram={ngram}, analyzer={analyzer}, num_docs={len(texts)}")

    # 向量化
    vec = TfidfVectorizer(min_df=min_df, ngram_range=ngram, analyzer=analyzer)
    X = vec.fit_transform(texts)
    # 節省空間：float32 足夠
    if X.dtype != "float32":
        X = X.astype("float32")
    X = normalize(X, norm="l2", copy=False)

    # 存檔（覆蓋寫）
    joblib.dump(vec, VEC_PATH)
    sparse.save_npz(MAT_PATH, X)
    with open(IDS_PATH, "w", encoding="utf-8") as f:
        for id_ in ids:
            f.write(json.dumps({"id": id_}, ensure_ascii=False) + "\n")

    meta = {
        "built_at": int(time.time()),
        "num_docs": len(texts),
        "min_df": min_df,
        "ngram": list(ngram),
        "analyzer": analyzer,
        "texts_sha256": _texts_hash(texts)[:16],  # 簡短指紋
        "versions": {
            "sklearn": __import__("sklearn").__version__,
            "scipy": __import__("scipy").__version__,
        },
    }
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    _debug(f"Index built in {CACHE_DIR}")
    return CACHE_DIR

def cache_exists() -> bool:
    return all(os.path.exists(p) for p in (VEC_PATH, MAT_PATH, IDS_PATH))

def load_cache():
    """
    載入快取，回傳 (vec, X, ids)；不存在或毀損回 None。
    """
    try:
        if not cache_exists():
            return None
        vec = joblib.load(VEC_PATH)
        X   = sparse.load_npz(MAT_PATH)
        ids: List[str] = []
        with open(IDS_PATH, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    ids.append(json.loads(line)["id"])
                except Exception:
                    continue
        # 基本一致性檢查
        if X.shape[0] != len(ids):
            _debug(f"Cache dimension mismatch: X.shape[0]={X.shape[0]} vs ids={len(ids)}")
            return None
        return vec, X, ids
    except Exception as e:
        _debug(f"Failed to load cache: {e}")
        return None

def query_cached_similarity(query: str, top_n: int = 5000) -> Optional[List[Tuple[str, float]]]:
    """
    用快取做相似度。回傳 [(id, score)]，高到低；
    - 快取不存在或被禁用則回 None（讓上層 fallback）。
    """
    if not COFACTS_CACHE_ENABLE:
        _debug("Cache disabled by COFACTS_CACHE_ENABLE=0")
        return None
    loaded = load_cache()
    if not loaded:
        _debug("Cache not found or invalid, fallback to live TF-IDF")
        return None

    vec, X, ids = loaded
    q = (query or "").strip()
    if not q:
        # 空查詢：回最熱門（這裡簡化為空結果 None，讓上層走 fallback）
        return None

    qv = vec.transform([q])
    qv = normalize(qv, norm="l2", copy=False)
    sims = (X @ qv.T).toarray().ravel()

    if top_n <= 0:
        return []

    top_n = min(top_n, len(sims))
    # 取 top_n：用 argpartition 更快，再做排序
    import numpy as np
    idx = np.argpartition(sims, -top_n)[-top_n:]
    idx = idx[np.argsort(sims[idx])[::-1]]
    return [(ids[i], float(sims[i])) for i in idx]
