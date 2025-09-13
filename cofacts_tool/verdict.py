from __future__ import annotations
from typing import Dict, List, Optional, Tuple, Any

from .models import Evidence, Verdict
from .search import search_text

VERDICT_TYPES = ["RUMOR", "NOT_RUMOR", "OPINIONATED", "NOT_ARTICLE"]


def _as_reply_obj(r: Any):
    """
    回傳一個具備 .type / .text / .createdAt 的物件（或 dict-like）。
    兼容兩種形態：
      1) r 直接是 ReplyLite（有屬性）
      2) r 是 {"reply": ReplyLite or dict}
    """
    # r 是 {"reply": ...}
    if hasattr(r, "reply"):
        return r.reply
    if isinstance(r, dict) and "reply" in r:
        return r["reply"]
    # r 已經是回覆本體
    return r


def _get_attr(obj: Any, name: str, default=None):
    if hasattr(obj, name):
        return getattr(obj, name)
    if isinstance(obj, dict):
        return obj.get(name, default)
    return default


def _aggregate_scores(articles) -> Dict[str, float]:
    counts: Dict[str, int] = {t: 0 for t in VERDICT_TYPES}
    total = 0
    for a in articles:
        for r_raw in getattr(a, "articleReplies", []) or []:
            r = _as_reply_obj(r_raw)
            t = (_get_attr(r, "type", "") or "").upper()
            if t in counts:
                counts[t] += 1
                total += 1
    total = max(total, 1)
    return {k: v / total for k, v in counts.items()}


def _top_two(scores: Dict[str, float]) -> Tuple[str, float, str, float]:
    sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    (t1, s1) = sorted_items[0]
    (t2, s2) = sorted_items[1] if len(sorted_items) > 1 else ("", 0.0)
    return t1, s1, t2, s2


def summarize_verdict(
    text: str,
    threshold: float = 0.15,
    *,
    # ★ 新增：接受 CLI 旗標並往下傳
    use_api: bool = True,
    use_hf: bool = True,
    time_range: Optional[dict] = None,
    search_func=search_text,
) -> Verdict:
    # 透過 search_func 取得結果（預設為 search_text）
    sr = search_func(
        text,
        top_k=50,           # 取大一點做統計較穩定；如需可參數化
        use_api=use_api,
        use_hf=use_hf,
        time_range=time_range,
    )

    scores = _aggregate_scores(sr.items)
    t1, s1, t2, s2 = _top_two(scores)
    verdict = t1 if (s1 - s2) >= threshold else "UNSURE"

    # Build evidence snippets（每篇取 1 則代表性回覆）
    ev: List[Evidence] = []
    for a in sr.items:
        replies = getattr(a, "articleReplies", []) or []
        if not replies:
            continue
        r = _as_reply_obj(replies[0])
        snippet = (_get_attr(r, "text", "") or "").strip()
        if len(snippet) > 160:
            snippet = snippet[:157] + "..."
        ev.append(
            Evidence(
                article_id=getattr(a, "id", None),
                url=getattr(a, "article_url", "") or "",
                reply_type=_get_attr(r, "type", None),
                snippet=snippet,
                createdAt=_get_attr(r, "createdAt", None),
            )
        )

    return Verdict(
        query=text,
        verdict=verdict,
        scores=scores,
        threshold=threshold,
        evidence=ev,
    )
