import hashlib
import json
import os
from datetime import datetime
from typing import Any, Dict, Iterable, Optional

from .config import OUTPUT_DIR


def _today_dir() -> str:
    day = datetime.utcnow().strftime("%Y-%m-%d")
    out = os.path.join(OUTPUT_DIR, day)
    os.makedirs(out, exist_ok=True)
    return out


def seen_ids_path() -> str:
    return os.path.join(_today_dir(), "seen_ids.jsonl")


def append_seen_ids(ids: Iterable[str]) -> None:
    path = seen_ids_path()
    with open(path, "a", encoding="utf-8") as f:
        for i in ids:
            f.write(json.dumps({"id": str(i)}) + "\n")


def load_seen_ids() -> set[str]:
    path = seen_ids_path()
    if not os.path.exists(path):
        return set()
    seen: set[str] = set()
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
                if "id" in obj:
                    seen.add(str(obj["id"]))
            except Exception:
                continue
    return seen


def write_export(name: str, data: Iterable[Dict[str, Any]], fmt: str = "json") -> str:
    # 基底目錄：cofact_output/<YYYY-MM-DD>
    base_dir = _today_dir()

    # 支援絕對路徑；否則就接到 base_dir 下
    target = name if os.path.isabs(name) else os.path.join(base_dir, name)

    # 如果以斜線結尾，視為資料夾；自動補預設檔名
    if target.endswith(os.sep) or target.endswith("/") or target.endswith("\\"):
        default_name = "articles." + fmt
        target = os.path.join(target, default_name)

    # 自動加副檔名（若未給）
    root, ext = os.path.splitext(target)
    if not ext:
        target = f"{target}.{fmt}"
        ext = "." + fmt

    # 確保父資料夾存在 ★
    os.makedirs(os.path.dirname(target), exist_ok=True)

    rows = list(data)

    if fmt == "json" or ext.lower() == ".json":
        with open(target, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        return target

    elif fmt == "csv" or ext.lower() == ".csv":
        import csv
        fieldnames = sorted({k for r in rows for k in r.keys()}) if rows else []
        with open(target, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in rows:
                writer.writerow(r)
        return target

    else:
        raise ValueError("Unsupported export format: " + fmt)


def normalize_text_hash(text: str) -> str:
    norm = (text or "").replace("\n", " ").replace("\r", " ")
    norm = "".join(norm.split())  # remove all whitespace
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()

