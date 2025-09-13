from __future__ import annotations

from typing import Any, Dict, Optional
from functools import partial

from .models import SearchResult, Verdict
from .search import get_article as get_article_func
from .search import search_text as search_text_func
from .verdict import summarize_verdict as summarize_verdict_func


def cofacts_search_text(
    text: str,
    top_k: int = 5,
    time_range: Dict[str, str] | None = None,
    use_api: bool = True,
    use_hf: bool = True,
) -> Dict[str, Any]:
    try:
        sr: SearchResult = search_text_func(
            text,
            top_k=top_k,
            time_range=time_range,
            use_api=use_api,
            use_hf=use_hf,
        )
        # pydantic v2
        return sr.model_dump(exclude_none=True)
    except Exception as e:
        return {"error": str(e)}


def cofacts_get_article(article_id: str) -> Dict[str, Any]:
    try:
        a = get_article_func(article_id)
        if not a:
            return {"error": f"Article {article_id} not found"}
        return a.model_dump(exclude_none=True)
    except Exception as e:
        return {"error": str(e)}


def cofacts_summarize_verdict(
    text: str,
    threshold: float = 0.15,
    use_api: bool = True,
    use_hf: bool = True,
) -> Dict[str, Any]:
    try:
        # 不改 summarize_verdict 簽名，用 partial 傳遞 use_api/use_hf
        search_fn = partial(search_text_func, use_api=use_api, use_hf=use_hf)
        v: Verdict = summarize_verdict_func(text, threshold=threshold, search_func=search_fn)
        return v.model_dump(exclude_none=True)
    except Exception as e:
        return {"error": str(e)}


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "cofacts_search_text",
            "description": "Search Cofacts for related articles and replies, merging API and HF sources.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "minLength": 1},
                    "top_k": {"type": "integer", "minimum": 1, "default": 5},
                    "time_range": {
                        "type": "object",
                        "properties": {
                            "GTE": {"type": "string"},
                            "LTE": {"type": "string"},
                        },
                        "additionalProperties": False,
                    },
                    "use_api": {"type": "boolean", "default": True},
                    "use_hf": {"type": "boolean", "default": True},
                },
                "required": ["text"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cofacts_get_article",
            "description": "Get a single article with its replies by article id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "article_id": {"type": "string", "minLength": 1},
                },
                "required": ["article_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cofacts_summarize_verdict",
            "description": "Summarize a quick machine verdict (RUMOR/NOT_RUMOR/OPINIONATED/NOT_ARTICLE/UNSURE) based on reply distribution.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "minLength": 1},
                    "threshold": {"type": "number", "default": 0.15},
                    "use_api": {"type": "boolean", "default": True},
                    "use_hf": {"type": "boolean", "default": True},
                },
                "required": ["text"],
                "additionalProperties": False,
            },
        },
    },
]
