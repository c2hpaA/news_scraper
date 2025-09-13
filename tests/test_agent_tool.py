# test_agent_tool.py
import os, json

# 建議開 DEBUG 看路徑、來源
os.environ.setdefault("DEBUG", "1")
# 如果想只走 HF：os.environ["HF_HUB_OFFLINE"]="1"
# 如果想禁用 API：用工具函式參數控制（下方示例有）

from cofacts_tool.agent_tool import (
    TOOLS,
    cofacts_search_text,
    cofacts_get_article,
    cofacts_summarize_verdict,
)

def pretty(x): print(json.dumps(x, ensure_ascii=False, indent=2))

print("== 工具清單（給 ADK 掛載用） ==")
pretty(TOOLS)

print("\n== search_text（混合 API+HF 預設） ==")
res = cofacts_search_text("mRNA 疫苗", top_k=3)

pretty({k: res[k] for k in ["query", "source"]})
print("items len:", len(res["items"]))
if res["items"]:
    print("top1:", res["items"][0]["id"], res["items"][0]["replyCount"])

print("\n== search_text（只 HF、無 API） ==")
# 直接用 search_text 的 use_api/use_hf 參數更精細，但 agent_tool 封裝的是預設值。
# 這裡用環境變數控制 CLI 風格不方便；直接調 search_text 更佳。
from cofacts_tool.search import search_text
sr_hf_only = search_text("mRNA 疫苗", top_k=3, use_api=False, use_hf=True)
pretty(sr_hf_only.model_dump()["source"])

print("\n== get_article（用上一個結果的 id） ==")
first_id = res["items"][0]["id"] if res["items"] else None
if first_id:
    art = cofacts_get_article(first_id)
    pretty({k: art.get(k) for k in ["id", "replyCount", "article_url"]})
else:
    print("沒有資料，略過 get_article")

print("\n== summarize_verdict ==")
vd = cofacts_summarize_verdict("mRNA 疫苗會改變DNA？", threshold=0.2)
pretty({k: vd[k] for k in ["query", "verdict", "scores", "threshold"]})
print("evidence:", len(vd.get("evidence") or []))
