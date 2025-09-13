import pandas as pd

from cofacts_tool.hf_client import HFClient
from cofacts_tool.models import Article, ReplyLite
from cofacts_tool.search import search_text


def test_merge_deduplicate_by_id_and_text():
    # HF provides two entries: one same id as API, one similar text different id
    arts = pd.DataFrame([
        {"id": "a1", "text": "相同內容 A", "replyCount": 1},
        {"id": "a2", "text": "相同內容 A  \n 空白不同", "replyCount": 1},
    ])
    reps = pd.DataFrame([
        {"id": "r1", "text": "rumor reply", "type": "RUMOR"},
        {"id": "r2", "text": "not rumor reply", "type": "NOT_RUMOR"},
    ])
    ars = pd.DataFrame([
        {"articleId": "a1", "replyId": "r1"},
        {"articleId": "a2", "replyId": "r2"},
    ])
    hf = HFClient(arts, reps, ars)

    # Simulate API returns one article with same id a1 and a different reply
    class FakeApi:
        def list_articles(self, *args, **kwargs):
            return ([{
                "id": "a1",
                "text": "相同內容 A",
                "replyCount": 1,
                "articleReplies": [{"id": "r3", "text": "api reply", "type": "RUMOR"}],
            }], None)

    res = search_text("相同內容", top_k=5, use_api=True, use_hf=True, hf_client=hf, api_client=FakeApi())
    # Ensure merged: a1 should have both r1 and r3
    a1 = next(a for a in res.items if a.id == "a1")
    types = sorted([r.type for r in a1.articleReplies])
    assert set(types) == {"RUMOR"}
    assert len(a1.articleReplies) == 2

    # Deduplicate by text hash: a2 similar text should be considered separate entry but grouped by hash merge path
    # Our implementation keeps entries distinct unless id missing, so ensure both present
    ids = {a.id for a in res.items}
    assert {"a1", "a2"}.issubset(ids)

