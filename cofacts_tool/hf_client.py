# from __future__ import annotations

# from typing import Dict, List, Optional

# import pandas as pd
# import os,json,time
# from .config import (
#     HF_DATASET_NAME, HF_TOKEN,
#     COFACTS_HF_LOCAL_DIR as HF_LOCAL_DIR,
#     COFACTS_HF_REFRESH_DAYS as HF_REFRESH_DAYS,
#     HF_HUB_OFFLINE,
# )
# def _needs_refresh(meta_path: str) -> bool:
#     if not os.path.exists(meta_path): return True
#     try:
#         meta = json.load(open(meta_path, "r", encoding="utf-8"))
#         last = meta.get("last_sync_ts", 0)
#         return ((time.time() - last) / 86400.0) > HF_REFRESH_DAYS
#     except Exception:
#         return True

# class HFClient:
#     """Lightweight HF dataset loader using pandas.

#     In production you would use datasets.load_dataset, but for offline tests
#     we allow injecting dataframes or CSVs. This client focuses on joining the
#     three tables into article-level objects with replies.
#     """

#     def __init__(self, articles: Optional[pd.DataFrame] = None, replies: Optional[pd.DataFrame] = None, article_replies: Optional[pd.DataFrame] = None) -> None:
#         self._articles = articles
#         self._replies = replies
#         self._article_replies = article_replies
#         self.dataset_name = HF_DATASET_NAME
#         self.hf_token = HF_TOKEN

#     def load(self) -> None:
#         os.makedirs(HF_LOCAL_DIR, exist_ok=True)
#         p_articles = os.path.join(HF_LOCAL_DIR, "articles.parquet")
#         p_replies = os.path.join(HF_LOCAL_DIR, "replies.parquet")
#         p_ar = os.path.join(HF_LOCAL_DIR, "article_replies.parquet")
#         meta_path = os.path.join(HF_LOCAL_DIR, "meta.json")

#         if all(os.path.exists(p) for p in (p_articles, p_replies, p_ar)) and not _needs_refresh(meta_path):
#             self._articles = pd.read_parquet(p_articles)
#             self._replies = pd.read_parquet(p_replies)
#             self._article_replies = pd.read_parquet(p_ar)
#             return

#         if HF_HUB_OFFLINE and not all(os.path.exists(p) for p in (p_articles, p_replies, p_ar)):
#             # 離線模式但沒有快取 → 給空表，避免網路錯誤
#             self._articles = pd.DataFrame(columns=["id","text","createdAt","updatedAt","replyCount"])
#             self._replies = pd.DataFrame(columns=["id","text","type","createdAt"])
#             self._article_replies = pd.DataFrame(columns=["articleId","replyId"])
#             return

#         # 線上抓（datasets 自帶快取，非每次下載）
#         from datasets import load_dataset
#         ds_articles = load_dataset(HF_DATASET_NAME, "articles", download_mode="reuse_dataset_if_exists")
#         ds_replies = load_dataset(HF_DATASET_NAME, "replies", download_mode="reuse_dataset_if_exists")
#         ds_ar = load_dataset(HF_DATASET_NAME, "article_replies", download_mode="reuse_dataset_if_exists")
#         self._articles = ds_articles["train"].to_pandas()
#         self._replies = ds_replies["train"].to_pandas()
#         self._article_replies = ds_ar["train"].to_pandas()
#         # 存本地
#         self._articles.to_parquet(p_articles, index=False)
#         self._replies.to_parquet(p_replies, index=False)
#         self._article_replies.to_parquet(p_ar, index=False)
#         json.dump({"last_sync_ts": time.time()}, open(meta_path, "w", encoding="utf-8"))


#     @property
#     def articles(self) -> pd.DataFrame:
#         if self._articles is None:
#             self.load()
#         assert self._articles is not None
#         return self._articles

#     @property
#     def replies(self) -> pd.DataFrame:
#         if self._replies is None:
#             self.load()
#         assert self._replies is not None
#         return self._replies

#     @property
#     def article_replies(self) -> pd.DataFrame:
#         if self._article_replies is None:
#             self.load()
#         assert self._article_replies is not None
#         return self._article_replies

#     def joined_articles(self) -> List[Dict]:
#         arts = self.articles.copy()
#         reps = self.replies.copy()
#         ars = self.article_replies.copy()

#         # Normalize dtypes
#         arts["id"] = arts.get("id", pd.Series(dtype=str)).astype(str)
#         reps["id"] = reps.get("id", pd.Series(dtype=str)).astype(str)
#         ars["articleId"] = ars.get("articleId", pd.Series(dtype=str)).astype(str)
#         ars["replyId"] = ars.get("replyId", pd.Series(dtype=str)).astype(str)
#         if "text" in arts.columns: arts["text"] = arts["text"].fillna("")
#         for col in ("text", "type", "createdAt"):
#             if col in reps.columns: 
#                 reps[col] = reps[col].fillna("")
#         merged = ars.merge(reps, left_on="replyId", right_on="id", how="left", suffixes=("", "_rep"))
#         merged = merged.merge(arts, left_on="articleId", right_on="id", how="left", suffixes=("", "_art"))

#         # group replies by article
#         articles_out: Dict[str, Dict] = {}
#         for _, row in merged.iterrows():
#             aid = str(row.get("articleId"))
#             if aid not in articles_out:
#                 articles_out[aid] = {
#                     "id": aid,
#                     "text": row.get("text_art") if "text_art" in row else row.get("text"),
#                     "createdAt": row.get("createdAt_art") if "createdAt_art" in row else row.get("createdAt"),
#                     "updatedAt": row.get("updatedAt_art") if "updatedAt_art" in row else None,
#                     "replyCount": 0,
#                     "articleReplies": [],
#                 }
#             # attach reply if exists
#             rid = row.get("replyId")
#             if pd.notna(rid):
#                 reply = {
#                     "id": str(row.get("id_rep") if "id_rep" in row else row.get("id")),
#                     "text": row.get("text"),
#                     "type": row.get("type"),
#                     "createdAt": row.get("createdAt"),
#                 }
#                 if reply["id"] != "nan":
#                     articles_out[aid]["articleReplies"].append(reply)
#         # Fill replyCount
#         for a in articles_out.values():
#             a["replyCount"] = len(a.get("articleReplies") or [])

#         # add standalone articles with no replies
#         for _, row in arts.iterrows():
#             aid = str(row.get("id"))
#             if aid not in articles_out:
#                 articles_out[aid] = {
#                     "id": aid,
#                     "text": row.get("text"),
#                     "createdAt": row.get("createdAt"),
#                     "updatedAt": row.get("updatedAt"),
#                     "replyCount": int(row.get("replyCount") or 0),
#                     "articleReplies": [],
#                 }

#         return list(articles_out.values())

# cofacts_tool/hf_client.py
from __future__ import annotations
from typing import Dict, List, Optional

import pandas as pd
import os, json, time

from .config import (
    HF_DATASET_NAME, HF_TOKEN,
    COFACTS_HF_LOCAL_DIR as HF_LOCAL_DIR,
    COFACTS_HF_REFRESH_DAYS as HF_REFRESH_DAYS,
    HF_HUB_OFFLINE,
)

def _needs_refresh(meta_path: str) -> bool:
    if not os.path.exists(meta_path): return True
    try:
        meta = json.load(open(meta_path, "r", encoding="utf-8"))
        last = meta.get("last_sync_ts", 0)
        return ((time.time() - last) / 86400.0) > HF_REFRESH_DAYS
    except Exception:
        return True

class HFClient:
    def __init__(self, articles: Optional[pd.DataFrame] = None,
                       replies: Optional[pd.DataFrame] = None,
                       article_replies: Optional[pd.DataFrame] = None) -> None:
        self._articles = articles
        self._replies = replies
        self._article_replies = article_replies
        self.dataset_name = HF_DATASET_NAME
        self.hf_token = HF_TOKEN

    def load(self) -> None:
        os.makedirs(HF_LOCAL_DIR, exist_ok=True)
        p_articles = os.path.join(HF_LOCAL_DIR, "articles.parquet")
        p_replies  = os.path.join(HF_LOCAL_DIR, "replies.parquet")
        p_ar       = os.path.join(HF_LOCAL_DIR, "article_replies.parquet")
        meta_path  = os.path.join(HF_LOCAL_DIR, "meta.json")

        # 1) 本地 parquet 快取
        if all(os.path.exists(p) for p in (p_articles, p_replies, p_ar)) and not _needs_refresh(meta_path):
            self._articles = pd.read_parquet(p_articles)
            self._replies = pd.read_parquet(p_replies)
            self._article_replies = pd.read_parquet(p_ar)
            return

        # 2) 離線但沒有 parquet → 回傳空表避免撞網路
        if HF_HUB_OFFLINE and not all(os.path.exists(p) for p in (p_articles, p_replies, p_ar)):
            self._articles = pd.DataFrame(columns=["id","text","createdAt","updatedAt","replyCount"])
            self._replies = pd.DataFrame(columns=["id","text","type","createdAt"])
            self._article_replies = pd.DataFrame(columns=["articleId","replyId"])
            return

        # 3) 線上抓（datasets 有官方快取）
        from datasets import load_dataset
        # 嘗試用 token 登入（若有）
        if self.hf_token:
            try:
                from huggingface_hub import login
                login(token=self.hf_token)
            except Exception:
                pass

        ds_articles = load_dataset(self.dataset_name, "articles", download_mode="reuse_dataset_if_exists")
        ds_replies  = load_dataset(self.dataset_name, "replies", download_mode="reuse_dataset_if_exists")
        ds_ar       = load_dataset(self.dataset_name, "article_replies", download_mode="reuse_dataset_if_exists")
        self._articles        = ds_articles["train"].to_pandas()
        self._replies         = ds_replies["train"].to_pandas()
        self._article_replies = ds_ar["train"].to_pandas()

        # 存 parquet（若系統缺 pyarrow，就略過存檔，不影響執行）
        try:
            self._articles.to_parquet(p_articles, index=False)
            self._replies.to_parquet(p_replies, index=False)
            self._article_replies.to_parquet(p_ar, index=False)
            json.dump({"last_sync_ts": time.time()}, open(meta_path, "w", encoding="utf-8"))
        except Exception:
            pass

    @property
    def articles(self) -> pd.DataFrame:
        if self._articles is None:
            self.load()
        assert self._articles is not None
        return self._articles

    @property
    def replies(self) -> pd.DataFrame:
        if self._replies is None:
            self.load()
        assert self._replies is not None
        return self._replies

    @property
    def article_replies(self) -> pd.DataFrame:
        if self._article_replies is None:
            self.load()
        assert self._article_replies is not None
        return self._article_replies

    def joined_articles(self) -> List[Dict]:
        arts = self.articles.copy()
        reps = self.replies.copy()
        ars  = self.article_replies.copy()

        # Normalize dtypes
        arts["id"] = arts.get("id", pd.Series(dtype=str)).astype(str)
        reps["id"] = reps.get("id", pd.Series(dtype=str)).astype(str)
        ars["articleId"] = ars.get("articleId", pd.Series(dtype=str)).astype(str)
        ars["replyId"]   = ars.get("replyId", pd.Series(dtype=str)).astype(str)

        if "text" in arts.columns: arts["text"] = arts["text"].fillna("")
        for col in ("text", "type", "createdAt"):
            if col in reps.columns:
                reps[col] = reps[col].fillna("")

        merged = ars.merge(reps, left_on="replyId", right_on="id", how="left", suffixes=("", "_rep"))
        merged = merged.merge(arts, left_on="articleId", right_on="id", how="left", suffixes=("", "_art"))

        # group replies by article
        articles_out: Dict[str, Dict] = {}
        for _, row in merged.iterrows():
            aid = str(row.get("articleId"))
            if aid not in articles_out:
                articles_out[aid] = {
                    "id": aid,
                    "text": row.get("text_art") if "text_art" in row else row.get("text"),
                    "createdAt": row.get("createdAt_art") if "createdAt_art" in row else row.get("createdAt"),
                    "updatedAt": row.get("updatedAt_art") if "updatedAt_art" in row else None,
                    "replyCount": 0,
                    "articleReplies": [],
                }
            rid = row.get("replyId")
            if pd.notna(rid):
                reply = {
                    "id": str(row.get("id_rep") if "id_rep" in row else row.get("id")),
                    "text": row.get("text"),
                    "type": row.get("type"),
                    "createdAt": row.get("createdAt"),
                }
                if reply["id"] != "nan":
                    articles_out[aid]["articleReplies"].append(reply)

        for a in articles_out.values():
            a["replyCount"] = len(a.get("articleReplies") or [])

        # add standalone articles with no replies
        for _, row in arts.iterrows():
            aid = str(row.get("id"))
            if aid not in articles_out:
                articles_out[aid] = {
                    "id": aid,
                    "text": row.get("text"),
                    "createdAt": row.get("createdAt"),
                    "updatedAt": row.get("updatedAt"),
                    "replyCount": int(row.get("replyCount") or 0),
                    "articleReplies": [],
                }
        return list(articles_out.values())
