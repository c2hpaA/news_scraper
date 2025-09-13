import pandas as pd

from cofacts_tool.hf_client import HFClient
from cofacts_tool.verdict import summarize_verdict


def test_verdict_unsure_threshold():
    arts = pd.DataFrame([
        {"id": "a1", "text": "text A"},
        {"id": "a2", "text": "text B"},
    ])
    reps = pd.DataFrame([
        {"id": "r1", "text": "rr1", "type": "RUMOR"},
        {"id": "r2", "text": "rr2", "type": "NOT_RUMOR"},
    ])
    ars = pd.DataFrame([
        {"articleId": "a1", "replyId": "r1"},
        {"articleId": "a2", "replyId": "r2"},
    ])
    hf = HFClient(arts, reps, ars)

    # Patch search_text inside summarize_verdict via monkeypatching through module import
    from cofacts_tool import search as search_mod

    def fake_search_text(text, *args, **kwargs):
        # reuse real search with injected hf_client, no api
        return orig(text, use_api=False, hf_client=hf)

    # Monkeypatch in
    orig = search_mod.search_text
    search_mod.search_text = fake_search_text
    try:
        v = summarize_verdict("text", search_func=fake_search_text)
    finally:
        search_mod.search_text = orig

    assert v.verdict == "UNSURE"
    # scores should distribute across types
    assert abs(v.scores.get("RUMOR", 0) - 0.5) < 1e-6
    assert abs(v.scores.get("NOT_RUMOR", 0) - 0.5) < 1e-6
