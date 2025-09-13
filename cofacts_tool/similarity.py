# cofacts_tool/similarity.py
from __future__ import annotations
import os
from typing import List
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

ENGINE = os.getenv("COFACTS_SEARCH_ENGINE", "tfidf").lower()  # tfidf | bm25 | sbert

def _normalize_docs(docs: List[str]) -> List[str]:
    return [(d if isinstance(d, str) else ("" if d is None else str(d))).strip() for d in docs]

def tfidf_scores(query: str, docs: List[str]) -> List[float]:
    docs = _normalize_docs(docs)
    q = (query or "").strip()
    vec = TfidfVectorizer(min_df=1, ngram_range=(1,2))
    X = vec.fit_transform([q] + docs)
    return cosine_similarity(X[0:1], X[1:]).ravel().tolist()

def bm25_scores(query: str, docs: List[str]) -> List[float]:
    from rank_bm25 import BM25Okapi
    tok = lambda s: list(s)  # 中文可換 jieba.lcut(s)
    corpus = [tok(d or "") for d in docs]
    bm25 = BM25Okapi(corpus)
    return bm25.get_scores(tok(query or "")).tolist()

# def sbert_scores(query: str, docs: List[str]) -> List[float]:
#     from sentence_transformers import SentenceTransformer
#     import numpy as np
#     model_name = os.getenv("COFACTS_SBERT_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
#     device = os.getenv("COFACTS_SBERT_DEVICE", None)  # "cuda" | "cpu" | None
#     model = SentenceTransformer(model_name, device=device)
#     emb_q = model.encode([query], normalize_embeddings=True)
#     emb_d = model.encode(docs, normalize_embeddings=True, batch_size=int(os.getenv("SBERT_BATCH","64")))
#     return (emb_d @ emb_q.T).reshape(-1).tolist()

def score(query: str, docs: List[str]) -> List[float]:
    eng = ENGINE
    try:
        if eng == "bm25":
            return bm25_scores(query, docs)
        # if eng == "sbert":
        #     return sbert_scores(query, docs)
    except Exception as e:
        print(f"[WARN] similarity engine={eng} failed: {e}. Fallback to tfidf.")
    return tfidf_scores(query, docs)
