# from __future__ import annotations

# import math
# from typing import Any, Dict, List, Optional, Tuple

# import numpy as np
# from sklearn.feature_extraction.text import TfidfVectorizer
# from sklearn.metrics.pairwise import cosine_similarity
# from .similarity import score as sim_score

# from .api_client import ApiDisabledError, GraphQLClient
# from .cache import normalize_text_hash
# from .hf_client import HFClient
# from .models import Article, ReplyLite, SearchResult

# from scipy import sparse
# import joblib, json
# import os
# # 頂部
# MAX_TFIDF_CANDIDATES = 4000  # 可調 2k~10k；用於「沒快取」時的候選上限

# from .index import query_cached_similarity  # 新增
# from time import perf_counter
# from .store import upsert_articles_with_replies, log_search


# from .config import (
#     DEFAULT_TOP_K,
#     COFACTS_API_FIRST,
#     COFACTS_API_CANDIDATES,
#     COFACTS_SEARCH_ENGINE,
#     DEBUG,
# )





# def _merge_articles(existing: Article, new: Article) -> Article:
#     # Merge replies uniquely by reply id
#     seen = {r.id for r in existing.articleReplies}
#     for r in new.articleReplies:
#         if r.id not in seen:
#             existing.articleReplies.append(r)
#             seen.add(r.id)
#     existing.replyCount = len(existing.articleReplies)
#     # Prefer earlier createdAt if missing
#     if not existing.createdAt and new.createdAt:
#         existing.createdAt = new.createdAt
#     if not existing.updatedAt and new.updatedAt:
#         existing.updatedAt = new.updatedAt
#     return existing


# def _score_article(sim: float, article: Article) -> float:
#     # reply factor favors more replies (diminishing returns)
#     reply_factor = 1.0 + math.log1p(max(article.replyCount, 0))
#     # type balance factor: weight towards a clear majority
#     type_counts: Dict[str, int] = {}
#     for r in article.articleReplies:
#         t = (r.type or "").upper()
#         type_counts[t] = type_counts.get(t, 0) + 1
#     total = sum(type_counts.values()) or 1
#     type_factor = 1.0 + (max(type_counts.values()) / total if type_counts else 0.0)
#     return sim * reply_factor * type_factor


# def search_text(
#     text: str,
#     top_k: int = DEFAULT_TOP_K,
#     use_api: bool = True,
#     use_hf: bool = True,
#     time_range: Optional[Dict[str, str]] = None,
#     hf_client: Optional[HFClient] = None,
#     api_client: Optional[GraphQLClient] = None,
# ) -> SearchResult:
#     t0 = perf_counter()  # ⏱️ 計時（用於 log_search）
#     items: List[Article] = []
#     used = {"api": False, "hf": False}

#     # =========================
#     # API branch
#     # =========================
#     articles_api: List[Dict[str, Any]] = []
#     if use_api:
#         client = api_client or GraphQLClient()
#         try:
#             used["api"] = True  # 嘗試就紀錄
#             cursor: Optional[str] = None
#             for _ in range(COFACTS_API_CANDIDATES):  # 如需更多候選，改大（或改成環境變數）
#                 batch, cursor = client.list_articles(text, first=COFACTS_API_FIRST, after=cursor, time_range=time_range)
#                 if not batch:
#                     break
#                 articles_api.extend(batch)
#                 if not cursor:
#                     break

#             # 先 upsert 到 DB（原始 dict 結構）
#             try:
#                 if articles_api:
#                     upsert_articles_with_replies(articles_api, source="api")
#             except Exception as e:
#                 if os.getenv("DEBUG","").lower() in ("1","true","yes"):
#                     print(f"[DEBUG] db upsert(api) error: {e}")

#             # 轉 Article 並補相似度（用你現有的 TF-IDF）
#             for a in articles_api:
#                 art = Article.from_dict(a)
#                 #sim = _tfidf_similarity(text, [art.text])[0] if art.text else 0.0
#                 sim = sim_score(text, [art.text])[0] if art.text else 0.0
#                 setattr(art, "_sim", float(sim))
#                 items.append(art)

#         except Exception as e:
#             if os.getenv("DEBUG","").lower() in ("1","true","yes"):
#                 print(f"[DEBUG] API error: {type(e).__name__}: {e}")
#             # 若失敗就不要把 api 算入 used
#             used["api"] = False

#     # =========================
#     # HF branch
#     # =========================
#     candidates: List[Dict[str, Any]] = []
#     sims: List[float] = []
#     if use_hf:
#         hf = hf_client or HFClient()
#         hf.load()
#         used["hf"] = True
#         joined = hf.joined_articles()

#         # 先嘗試向量快取命中；失敗或無命中再 fallback TF-IDF 全量
#         hits = None
#         try:
#             hits = query_cached_similarity(text, top_n=max(1, min(MAX_TFIDF_CANDIDATES, top_k * 1000)))
#         except Exception as e:
#             if os.getenv("DEBUG","").lower() in ("1","true","yes"):
#                 print(f"[DEBUG] cached similarity not available: {e}")

#         if hits:
#             by_id = {str(j.get("id")): j for j in joined}
#             candidates = [by_id[i] for i, _ in hits if i in by_id]
#             sims = [s for i, s in hits if i in by_id]
#         else:
#             texts = [(j.get("text") or "") for j in joined]
#             #sims = _tfidf_similarity(text, texts)
#             sims = sim_score(text, texts)
#             candidates = joined

#         # upsert HF 候選到 DB
#         try:
#             if candidates:
#                 upsert_articles_with_replies(candidates, source="hf")
#         except Exception as e:
#             if os.getenv("DEBUG","").lower() in ("1","true","yes"):
#                 print(f"[DEBUG] db upsert(hf) error: {e}")

#         for j, s in zip(candidates, sims):
#             art = Article.from_dict(j)
#             setattr(art, "_sim", float(s))
#             items.append(art)

#     # =========================
#     # Dedup / merge
#     # =========================
#     merged_by_id: Dict[str, Article] = {}
#     merged_by_hash: Dict[str, Article] = {}

#     def get_hash(a: Article) -> str:
#         return normalize_text_hash(a.text)

#     for a in items:
#         aid = a.id
#         if aid and aid in merged_by_id:
#             merged_by_id[aid] = _merge_articles(merged_by_id[aid], a)
#             continue
#         th = get_hash(a)
#         if aid and aid != "nan":
#             merged_by_id[aid] = a
#             if th not in merged_by_hash:
#                 merged_by_hash[th] = a
#             else:
#                 merged_by_hash[th] = _merge_articles(merged_by_hash[th], a)
#         else:
#             if th in merged_by_hash:
#                 merged_by_hash[th] = _merge_articles(merged_by_hash[th], a)
#             else:
#                 merged_by_hash[th] = a

#     deduped: List[Article] = list(merged_by_id.values())
#     for _, a in merged_by_hash.items():
#         if a.id not in merged_by_id:
#             deduped.append(a)

#     # =========================
#     # Scoring & sort
#     # =========================
#     sims_local: List[float] = []
#     for a in deduped:
#         sim = getattr(a, "_sim", None)
#         if sim is None:
#             #sim = _tfidf_similarity(text, [a.text])[0] if a.text else 0.0
#             sim = sim_score(text, [a.text])[0] if a.text else 0.0

#         sims_local.append(sim)

#     scored_pairs: List[Tuple[float, Article]] = [(_score_article(sim, a), a) for sim, a in zip(sims_local, deduped)]
#     scored_pairs.sort(key=lambda x: x[0], reverse=True)
#     top_n = max(1, top_k)
#     ranked_pairs = scored_pairs[:top_n]
#     ranked = [a for s, a in ranked_pairs]

#     for a in ranked:
#         if hasattr(a, "_sim"):
#             delattr(a, "_sim")
#         if not a.article_url:
#             a.article_url = Article.make_url(a.id)

#     # =========================
#     # DB: log this search (query + engine + sources + duration + ranked with score)
#     # =========================
#     duration_ms = int((perf_counter() - t0) * 1000)
#     try:
#         engine_name = os.getenv("COFACTS_SEARCH_ENGINE", "tfidf")
#         ranked_with_score = []
#         for s, a in ranked_pairs:
#             d = a.dict()
#             d["_score"] = float(s)
#             ranked_with_score.append(d)
#         log_search(text, engine_name, top_k, used["api"], used["hf"], duration_ms, ranked_with_score)
#     except Exception as e:
#         if os.getenv("DEBUG","").lower() in ("1","true","yes"):
#             print(f"[DEBUG] db log_search error: {e}")

#     return SearchResult(query=text, items=ranked, source=used)



# def get_article(article_id: str, api_client: Optional[GraphQLClient] = None, hf_client: Optional[HFClient] = None) -> Optional[Article]:
#     # Try API first
#     client = api_client or GraphQLClient()
#     try:
#         data = client.get_article(article_id)
#         return Article.from_dict(data)
#     except ApiDisabledError:
#         pass
#     except Exception:
#         pass

#     # Fallback to HF dataset search by id
#     hf = hf_client or HFClient()
#     hf.load()
#     for a in hf.joined_articles():
#         if str(a.get("id")) == str(article_id):
#             return Article.from_dict(a)
#     return None

from __future__ import annotations

import math
import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from time import perf_counter

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .api_client import GraphQLClient
from .cache import normalize_text_hash
from .config import (
    DEFAULT_TOP_K,
    COFACTS_API_FIRST,
    COFACTS_API_CANDIDATES,
    COFACTS_SEARCH_ENGINE,
    DEBUG,
)
from .hf_client import HFClient
from .index import query_cached_similarity
from .models import Article, SearchResult
from .similarity import score as sim_score
from .store import upsert_articles_with_replies, log_search

# 用於「無快取」時的候選上限（避免全量計算）
MAX_TFIDF_CANDIDATES = 4000  # 可調 2k~10k

def _debug(msg: str) -> None:
    if DEBUG:
        print(f"[DEBUG] {msg}")

def _tfidf_similarity(query: str, texts: List[str]) -> List[float]:
    """僅作為最終 fallback；實際預設用 similarity.score()。"""
    if not texts:
        return []
    norm = [(t if isinstance(t, str) else ("" if t is None else str(t))).strip() for t in texts]
    q = (query or "").strip()
    if not q and all(not t for t in norm):
        return [0.0] * len(norm)
    corpus = [q] + norm
    try:
        vec = TfidfVectorizer(min_df=1, ngram_range=(1, 2))
        mat = vec.fit_transform(corpus)
        sims = cosine_similarity(mat[0:1], mat[1:]).ravel()
        return sims.tolist()
    except ValueError:
        return [0.0] * len(norm)

def _merge_articles(existing: Article, new: Article) -> Article:
    # Merge replies uniquely by reply id
    seen = {r.id for r in existing.articleReplies}
    for r in new.articleReplies:
        if r.id not in seen:
            existing.articleReplies.append(r)
            seen.add(r.id)
    existing.replyCount = len(existing.articleReplies)
    if not existing.createdAt and new.createdAt:
        existing.createdAt = new.createdAt
    if not existing.updatedAt and new.updatedAt:
        existing.updatedAt = new.updatedAt
    return existing

def _score_article(sim: float, article: Article) -> float:
    # reply factor favors more replies (diminishing returns)
    reply_factor = 1.0 + math.log1p(max(article.replyCount, 0))
    # type balance factor: weight towards a clear majority
    type_counts: Dict[str, int] = {}
    for r in article.articleReplies:
        t = (r.type or "").upper()
        type_counts[t] = type_counts.get(t, 0) + 1
    total = sum(type_counts.values()) or 1
    type_factor = 1.0 + (max(type_counts.values()) / total if type_counts else 0.0)
    return sim * reply_factor * type_factor

def _page_through_api(client: GraphQLClient, text: str, time_range: Optional[Dict[str, str]]) -> List[Dict[str, Any]]:
    """依 .env 的 COFACTS_API_FIRST / COFACTS_API_CANDIDATES 控制分頁抓取。"""
    page_size = max(1, int(COFACTS_API_FIRST))
    remain = max(1, int(COFACTS_API_CANDIDATES))
    cursor: Optional[str] = None
    out: List[Dict[str, Any]] = []
    while remain > 0:
        first = min(page_size, remain)
        batch, cursor = client.list_articles(text, first=first, after=cursor, time_range=time_range)
        if not batch:
            break
        out.extend(batch)
        remain -= len(batch)
        if not cursor:
            break
    return out

def search_text(
    text: str,
    top_k: int = DEFAULT_TOP_K,
    use_api: bool = True,
    use_hf: bool = True,
    time_range: Optional[Dict[str, str]] = None,
    hf_client: Optional[HFClient] = None,
    api_client: Optional[GraphQLClient] = None,
) -> SearchResult:
    """
    混合 API + HF 的召回，並用相似度（由 similarity.score 控制 tfidf/bm25/sbert）排序。
    - 會將候選 upsert 進 DB（articles/replies），並記錄本次 search log。
    """
    t0 = perf_counter()
    items: List[Article] = []
    used = {"api": False, "hf": False}

    # ========== API branch ==========
    articles_api: List[Dict[str, Any]] = []
    if use_api:
        client = api_client or GraphQLClient()
        try:
            articles_api = _page_through_api(client, text, time_range)
            if articles_api:
                used["api"] = True
                # 儲存 DB
                try:
                    upsert_articles_with_replies(articles_api, source="api")
                except Exception as e:
                    _debug(f"db upsert(api) error: {e}")
            # 轉 Article + 相似度
            for a in articles_api:
                art = Article.from_dict(a)
                sim = sim_score(text, [art.text])[0] if art.text else 0.0
                setattr(art, "_sim", float(sim))
                items.append(art)
        except Exception as e:
            _debug(f"API error: {type(e).__name__}: {e}")
            used["api"] = False

    # ========== HF branch ==========
    hf_candidates: List[Dict[str, Any]] = []
    hf_sims: List[float] = []
    if use_hf:
        hf = hf_client or HFClient()
        hf.load()
        joined = hf.joined_articles()
        if joined:
            used["hf"] = True

            # 先嘗試快取查詢
            hits = None
            try:
                topn_cached = max(1, min(MAX_TFIDF_CANDIDATES, top_k * 1000))
                hits = query_cached_similarity(text, top_n=topn_cached)
            except Exception as e:
                _debug(f"cached similarity not available: {e}")

            if hits:
                by_id = {str(j.get("id")): j for j in joined}
                hf_candidates = [by_id[i] for i, _ in hits if i in by_id]
                hf_sims = [s for i, s in hits if i in by_id]
            else:
                # 無快取：對全量 texts 計分，但只取前 N（避免超時）
                texts = [(j.get("text") or "") for j in joined]
                scores = sim_score(text, texts) if texts else []
                if scores:
                    scores_np = np.asarray(scores, dtype=float)
                    N = min(MAX_TFIDF_CANDIDATES, max(top_k * 1000, 1000))
                    N = min(N, len(scores_np))
                    idx = np.argpartition(scores_np, -N)[-N:]
                    idx = idx[np.argsort(scores_np[idx])[::-1]]
                    hf_candidates = [joined[i] for i in idx]
                    hf_sims = [float(scores_np[i]) for i in idx]
                else:
                    hf_candidates, hf_sims = [], []

            # upsert HF 候選
            try:
                if hf_candidates:
                    upsert_articles_with_replies(hf_candidates, source="hf")
            except Exception as e:
                _debug(f"db upsert(hf) error: {e}")

            for j, s in zip(hf_candidates, hf_sims):
                art = Article.from_dict(j)
                setattr(art, "_sim", float(s))
                items.append(art)

    # ========== Dedup / merge ==========
    merged_by_id: Dict[str, Article] = {}
    merged_by_hash: Dict[str, Article] = {}

    def get_hash(a: Article) -> str:
        return normalize_text_hash(a.text)

    for a in items:
        aid = a.id
        if aid and aid in merged_by_id:
            merged_by_id[aid] = _merge_articles(merged_by_id[aid], a)
            continue
        th = get_hash(a)
        if aid and aid != "nan":
            merged_by_id[aid] = a
            if th not in merged_by_hash:
                merged_by_hash[th] = a
            else:
                merged_by_hash[th] = _merge_articles(merged_by_hash[th], a)
        else:
            if th in merged_by_hash:
                merged_by_hash[th] = _merge_articles(merged_by_hash[th], a)
            else:
                merged_by_hash[th] = a

    deduped: List[Article] = list(merged_by_id.values())
    for _, a in merged_by_hash.items():
        if a.id not in merged_by_id:
            deduped.append(a)

    # ========== Scoring & sort ==========
    sims_local: List[float] = []
    for a in deduped:
        sim = getattr(a, "_sim", None)
        if sim is None:
            sim = sim_score(text, [a.text])[0] if a.text else 0.0  # ← 修正 art→a
        sims_local.append(float(sim))

    scored_pairs: List[Tuple[float, Article]] = [(_score_article(sim, a), a) for sim, a in zip(sims_local, deduped)]
    scored_pairs.sort(key=lambda x: x[0], reverse=True)
    top_n = max(1, top_k)
    ranked_pairs = scored_pairs[:top_n]
    ranked = [a for _, a in ranked_pairs]

    # 清理暫存欄位 & 補 URL
    for a in ranked:
        if hasattr(a, "_sim"):
            delattr(a, "_sim")
        if not a.article_url:
            a.article_url = Article.make_url(a.id)

    # ========== DB log ==========
    duration_ms = int((perf_counter() - t0) * 1000)
    try:
        engine_name = COFACTS_SEARCH_ENGINE
        ranked_with_score = []
        for s, a in ranked_pairs:
            d = a.model_dump()
            d["_score"] = float(s)
            ranked_with_score.append(d)
        log_search(text, engine_name, top_k, used.get("api", False), used.get("hf", False), duration_ms, ranked_with_score)
    except Exception as e:
        _debug(f"db log_search error: {e}")

    return SearchResult(query=text, items=ranked, source=used)

def get_article(article_id: str, api_client: Optional[GraphQLClient] = None, hf_client: Optional[HFClient] = None) -> Optional[Article]:
    # Try API first
    client = api_client or GraphQLClient()
    try:
        data = client.get_article(article_id)
        return Article.from_dict(data)
    except Exception:
        pass

    # Fallback to HF dataset search by id
    hf = hf_client or HFClient()
    hf.load()
    for a in hf.joined_articles():
        if str(a.get("id")) == str(article_id):
            return Article.from_dict(a)
    return None
