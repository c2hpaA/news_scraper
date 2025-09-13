# cofacts_tool/api_client.py
from __future__ import annotations
import json, threading, time, os
from typing import Any, Dict, List, Optional, Tuple

import requests
from tenacity import RetryError, retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .config import (
    COFACTS_APP_ID,
    COFACTS_APP_SECRET,
    COFACTS_GRAPHQL_ENDPOINT,
    RATE_LIMIT_MIN_INTERVAL_SEC,
    RETRY_MAX_ATTEMPTS,
    RETRY_MAX_WAIT_SEC,
    RETRY_MIN_WAIT_SEC,
    # ⬇️ 新增這個可在 config.py 定義（若你已加）
    COFACTS_API_FIRST,  # e.g. from env, default 50
)

class ApiDisabledError(RuntimeError):
    pass

class GraphQLClient:
    def __init__(self) -> None:
        self.endpoint = COFACTS_GRAPHQL_ENDPOINT
        self._last_call = 0.0
        self._lock = threading.Lock()
        # ✅ Cofacts 是公開 API；有憑證就帶，沒有也一樣可用
        self._use_auth = bool(COFACTS_APP_SECRET or COFACTS_APP_ID)
        self._debug = os.getenv("DEBUG", "").lower() in ("1", "true", "yes")

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._use_auth:
            if COFACTS_APP_SECRET:
                headers["x-app-secret"] = COFACTS_APP_SECRET
            if COFACTS_APP_ID:
                headers["x-app-id"] = COFACTS_APP_ID
        return headers

    def _rate_limit(self) -> None:
        with self._lock:
            now = time.time()
            delta = now - self._last_call
            if delta < RATE_LIMIT_MIN_INTERVAL_SEC:
                time.sleep(RATE_LIMIT_MIN_INTERVAL_SEC - delta)
            self._last_call = time.time()

    @retry(
        reraise=True,
        stop=stop_after_attempt(RETRY_MAX_ATTEMPTS),
        wait=wait_exponential(min=RETRY_MIN_WAIT_SEC, max=RETRY_MAX_WAIT_SEC),
        retry=retry_if_exception_type((requests.RequestException, RuntimeError)),
    )
    def _post(self, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        self._rate_limit()
        headers = self._headers()
        if self._debug:
            safe_headers = {k: ("***" if k in ("x-app-secret",) else v) for k, v in headers.items()}
            print(f"[DEBUG] API POST {self.endpoint} vars={variables} headers={safe_headers}")
        resp = requests.post(
            self.endpoint,
            headers=headers,
            data=json.dumps({"query": query, "variables": variables}),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            # 可能是暫時錯誤，交給 tenacity 重試
            raise RuntimeError(f"GraphQL returned errors: {data['errors']}")
        return data.get("data", {})

    def list_articles(
        self,
        text: str,
        first: int = None,
        after: Optional[str] = None,
        time_range: Optional[Dict[str, str]] = None,  # 暫留但不送
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        # ✅ 不送 filter、不要 hasNextPage、不要 statuses
        q = """
        query GetArticles($first: Int, $after: String) {
        ListArticles(first: $first, after: $after) {
            edges {
            cursor
            node {
                id
                text
                createdAt
                updatedAt
                replyCount
                articleReplies {
                reply { id text type createdAt }
                }
            }
            }
            pageInfo { lastCursor }
        }
        }
        """
        variables = {"first": first, "after": after}
        data = self._post(q, variables)

        la = data.get("ListArticles") or {}
        edges = la.get("edges") or []
        articles: List[Dict[str, Any]] = []
        for e in edges:
            n = e.get("node") or {}
            flat_replies = []
            for ar in (n.get("articleReplies") or []):
                rep = (ar or {}).get("reply") or {}
                flat_replies.append({
                    "id": str(rep.get("id") or ""),
                    "text": rep.get("text") or "",
                    "type": rep.get("type") or "",
                    "createdAt": rep.get("createdAt") or None,
                })
            articles.append({
                "id": str(n.get("id") or ""),
                "text": n.get("text") or "",
                "createdAt": n.get("createdAt"),
                "updatedAt": n.get("updatedAt"),
                "replyCount": int(n.get("replyCount") or 0),
                "articleReplies": flat_replies,
                "article_url": f"https://cofacts.tw/article/{n.get('id')}",
            })

        # ✅ 只有 lastCursor；沒有 hasNextPage
        next_cursor = None
        if edges:
            c = edges[-1].get("cursor")
            if c:
                next_cursor = c
        if not next_cursor:
            next_cursor = (la.get("pageInfo") or {}).get("lastCursor")

        return articles, next_cursor



    def get_article(self, article_id: str) -> Dict[str, Any]:
        q = """
        query GetArticle($id: String!) {
        GetArticle(id: $id) {
            id
            text
            createdAt
            updatedAt
            replyCount
            articleReplies { reply { id text type createdAt } }
        }
        }
        """
        data = self._post(q, {"id": article_id})
        n = data.get("GetArticle") or {}
        flat_replies = []
        for ar in (n.get("articleReplies") or []):
            rep = (ar or {}).get("reply") or {}
            flat_replies.append({
                "id": str(rep.get("id") or ""),
                "text": rep.get("text") or "",
                "type": rep.get("type") or "",
                "createdAt": rep.get("createdAt") or None,
            })
        return {
            "id": str(n.get("id") or ""),
            "text": n.get("text") or "",
            "createdAt": n.get("createdAt"),
            "updatedAt": n.get("updatedAt"),
            "replyCount": int(n.get("replyCount") or 0),
            "articleReplies": flat_replies,
            "article_url": f"https://cofacts.tw/article/{n.get('id')}",
        }

