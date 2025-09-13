import os
import pandas as pd

from cofacts_tool.hf_client import HFClient
from cofacts_tool.search import search_text


def test_smoke_hf_only(monkeypatch):
    # Ensure API secret not set
    monkeypatch.delenv("COFACTS_APP_SECRET", raising=False)

    # Prepare tiny HF dataset in-memory
    arts = pd.DataFrame([
        {"id": "a1", "text": "這是一段測試訊息", "createdAt": "2024-01-01", "updatedAt": "2024-01-02", "replyCount": 1},
    ])
    reps = pd.DataFrame([
        {"id": "r1", "text": "這看起來像是真的消息", "type": "NOT_RUMOR", "createdAt": "2024-01-03"},
    ])
    ars = pd.DataFrame([
        {"articleId": "a1", "replyId": "r1"},
    ])

    hf = HFClient(arts, reps, ars)
    res = search_text("測試訊息", top_k=5, use_api=True, use_hf=True, hf_client=hf)
    assert res.source["hf"] is True
    # API may be disabled in env, ensure still returns items from HF
    assert len(res.items) >= 1

