可做為 **Python 套件、CLI、與 Agent 工具** 的 Cofacts 真假查詢工具。
支援 **Cofacts GraphQL API** 與 **Hugging Face Dataset** 的融合查詢、去重、快取索引、資料庫記錄與機器摘要。

## 安裝與需求

* Python 3.10–3.12（建議 3.10）
* 建議使用虛擬環境

```bash
# 若使用 pyproject.toml
pip install -e ".[dev]"        # 安裝核心 + 開發相依（pytest 等）
# 需要 Sentence-Transformer 再另外裝：
# pip install -e ".[sbert]"
```

> 若你使用 `Makefile`：`make install`

## 環境變數設定

在專案根目錄建立 `.env`（可參考 `.env.sample`）：

```env
# Cofacts API（可留空；留空則走 HF-only）
COFACTS_APP_SECRET=""
COFACTS_APP_ID=""

# HF Token（公開資料集可留空）
HF_TOKEN=""

# API 分頁控制
COFACTS_API_FIRST=50           # 每頁抓幾篇（1~10000）
COFACTS_API_CANDIDATES=3000    # 本次查詢最多抓多少篇做本地排序

# 偵錯
DEBUG=1

# 搜尋引擎切換
COFACTS_SEARCH_ENGINE=tfidf     # tfidf|bm25|sbert
# COFACTS_TFIDF_ANALYZER=char_wb

# HF 本地快取
COFACTS_HF_LOCAL_DIR=./.hf_cache
COFACTS_HF_REFRESH_DAYS=7
HF_HUB_OFFLINE=0                # 1=離線（僅用本地 parquet）

# 向量快取（TF-IDF 索引）
COFACTS_CACHE_ENABLE=1
COFACTS_CACHE_DIR=./.vector_cache

# DB（紀錄文章與查詢 log）
COFACTS_DB_URL=sqlite:///cofacts.db
```

> Windows PowerShell 設定例：
>
> ```powershell
> $env:COFACTS_APP_SECRET="..."
> ```

## 快速開始

### 1) 建 TF-IDF 索引（強烈建議，讓 HF 查詢變快）

```bash
# analyzer 建議中文用 char_wb
$env:COFACTS_TFIDF_ANALYZER="char_wb"   # Windows PowerShell
cofacts-cli index --min-df 2 --ngram-min 1 --ngram-max 2
```

看到 `Cache directory:` 與 `meta.json` 代表索引建立成功。之後 HF 查詢就會從快取取 TopN 候選，速度快很多。
要確認有用到快取，可執行查詢時加 `--debug`，會看到：

```
[DEBUG] using cache from <你的 COFACTS_CACHE_DIR>
```

### 2) 初始化資料庫（選用）

```bash
cofacts-cli db init
```

查詢過程會自動 upsert 文章與回覆至 DB（避免重複依 `id`/`reply_id`），並記錄查詢 log（包含 query、花費時間、來源與排名分數）。

### 3) CLI 查詢

```bash
# 混用 API + HF（預設）
cofacts-cli search "mRNA 疫苗會改變DNA？" --top-k 5

# 只走 HF
cofacts-cli search "mRNA 疫苗" --no-api --top-k 5 --debug

# 只走 API
cofacts-cli search "mRNA 疫苗" --no-hf --top-k 20 --debug

# 時間篩選（會傳給 API 的 timeRange；HF 目前不套此篩選）
cofacts-cli search "mRNA 疫苗" --time-gte 2024-01-01 --time-lte 2025-09-12

# 匯出結果（輸出至 cofact_output/YYYY-MM-DD/…）
cofacts-cli search "mRNA 疫苗" --export json --out out/search.json
cofacts-cli search "mRNA 疫苗" --export csv  --out out/search.csv
```

### 4) 取得單篇

```bash
cofacts-cli get --id 283m3crc6em7f
```

### 5) 快速「機器判讀」摘要（RUMOR/NOT\_RUMOR/OPINIONATED/NOT\_ARTICLE/UNSURE）

```bash
cofacts-cli verdict "維他命C可治療新冠？" --threshold 0.15
# 可用 --no-api / --no-hf 切換資料來源
```

> **說明**：判讀是依「回覆類型分布」做簡單加總與閾值判斷，僅供快速參考，非官方結論。

## Python 套件使用

```python
from cofacts_tool.search import search_text, get_article
from cofacts_tool.verdict import summarize_verdict

sr = search_text("mRNA 疫苗會改變DNA？", top_k=5)
a  = get_article("283m3crc6em7f")
v  = summarize_verdict("維他命C可治療新冠？", threshold=0.15)
```

## Agent 工具（ADK / Google Agent）

`cofacts_tool/agent_tool.py` 提供 3 個工具與 JSON schema：

* `cofacts_search_text({ text, top_k?, time_range?, use_api?, use_hf? })`
* `cofacts_get_article({ article_id })`
* `cofacts_summarize_verdict({ text, threshold?, use_api?, use_hf? })`

範例掛載：

```python
from cofacts_tool.agent_tool import (
  TOOLS, cofacts_search_text, cofacts_get_article, cofacts_summarize_verdict
)

tools_map = {
  "cofacts_search_text": cofacts_search_text,
  "cofacts_get_article": cofacts_get_article,
  "cofacts_summarize_verdict": cofacts_summarize_verdict,
}
# 在你的 ADK pipeline 註冊 TOOLS 與 tools_map
```

