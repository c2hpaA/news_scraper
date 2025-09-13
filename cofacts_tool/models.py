from __future__ import annotations

from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from .config import COFACTS_WEB_BASE


class ReplyLite(BaseModel):
    id: str
    text: Optional[str] = ""      # 允許 None，預設空字串
    type: Optional[str] = None    # 允許 None
    createdAt: Optional[str] = None


class Article(BaseModel):
    id: str
    text: str
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None
    replyCount: int = 0
    article_url: Optional[str] = None
    articleReplies: List[ReplyLite] = Field(default_factory=list)

    @staticmethod
    def make_url(article_id: str) -> str:
        return f"{COFACTS_WEB_BASE}/article/{article_id}"

    @classmethod
    def from_dict(cls, data: dict) -> "Article":
        raw_replies = data.get("articleReplies") or []
        # 兼容兩種形態：[{...}] 或 [{"reply": {...}}]
        norm_replies = []
        for r in raw_replies:
           if isinstance(r, dict) and "reply" in r:
               r = r["reply"] or {}
          # 安全轉型與填補
           norm_replies.append({
               "id": str((r or {}).get("id", "")),
               "text": (r or {}).get("text") or "",
               "type": (r or {}).get("type") or None,                
               "createdAt": (r or {}).get("createdAt"),
            })
        return cls(
             id=str(data.get("id")),
             text=data.get("text") or "",
             createdAt=data.get("createdAt"),
             updatedAt=data.get("updatedAt"),
             replyCount=int(data.get("replyCount") or 0),
             article_url=data.get("article_url")
             or Article.make_url(str(data.get("id"))),
             articleReplies=[ReplyLite(**r) for r in norm_replies],
         )


class SearchResult(BaseModel):
    query: str
    items: List[Article]
    source: Dict[str, bool] = Field(
        default_factory=lambda: {"api": False, "hf": False}
    )


class Evidence(BaseModel):
    article_id: str
    url: str
    reply_type: Optional[str] = None
    snippet: Optional[str] = None
    createdAt: Optional[str] = None


class Verdict(BaseModel):
    query: str
    verdict: str
    scores: Dict[str, float]
    threshold: float
    evidence: List[Evidence] = Field(default_factory=list)
    note: str = "此為快速機器摘要，非官方結論"

