# cofacts_tool/store.py
from __future__ import annotations
import os
from contextlib import contextmanager
from typing import Iterable, Dict, Any, List
from datetime import datetime

DB_ENABLED = os.getenv("COFACTS_DB_ENABLE", "1").lower() not in ("0", "false", "no", "")

# ──────────────────────────────────────────────────────────────────────────────
# 若關閉 DB：提供 no-op 介面，其他模組可照呼叫而不會出錯
# ──────────────────────────────────────────────────────────────────────────────
if not DB_ENABLED:
    def init_db() -> None:
        return None

    def upsert_articles_with_replies(items: Iterable[Dict[str, Any]], source: str):
        return 0

    def log_search(query: str, engine_name: str, top_k: int, used_api: bool, used_hf: bool, duration_ms: int, ranked: List[Dict[str, Any]]) -> int:
        return 0

else:
    from sqlalchemy import (
        create_engine, MetaData, Table, Column, Text, Integer, Float, Boolean,
        ForeignKey, TIMESTAMP, PrimaryKeyConstraint
    )
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    DB_URL = os.getenv("COFACTS_DB_URL", "sqlite:///cofacts.db")
    engine = create_engine(DB_URL, future=True)
    Session = sessionmaker(bind=engine, future=True)
    md = MetaData()

    articles = Table("articles", md,
        Column("id", Text, primary_key=True),
        Column("text", Text),
        Column("created_at", TIMESTAMP, nullable=True),
        Column("updated_at", TIMESTAMP, nullable=True),
        Column("reply_count", Integer, nullable=False, default=0),
        Column("article_url", Text),
    )

    replies = Table("replies", md,
        Column("id", Text, primary_key=True),
        Column("article_id", Text, ForeignKey("articles.id", ondelete="CASCADE")),
        Column("text", Text),
        Column("type", Text),
        Column("created_at", TIMESTAMP, nullable=True),
    )

    article_sources = Table("article_sources", md,
        Column("article_id", Text, ForeignKey("articles.id", ondelete="CASCADE")),
        Column("source", Text),  # 'api' | 'hf'
        Column("fetched_at", TIMESTAMP),
        PrimaryKeyConstraint("article_id", "source")
    )

    search_logs = Table("search_logs", md,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("query", Text),
        Column("engine", Text),
        Column("top_k", Integer),
        Column("used_api", Boolean),
        Column("used_hf", Boolean),
        Column("duration_ms", Integer),
        Column("created_at", TIMESTAMP),
    )

    search_results = Table("search_results", md,
        Column("search_id", Integer, ForeignKey("search_logs.id", ondelete="CASCADE")),
        Column("rank", Integer),
        Column("article_id", Text, ForeignKey("articles.id")),
        Column("score", Float),
        PrimaryKeyConstraint("search_id", "rank")
    )

    def init_db():
        md.create_all(engine)

    @contextmanager
    def get_sess():
        s = Session()
        try:
            yield s
            s.commit()
        except:
            s.rollback()
            raise
        finally:
            s.close()

    def _insert(table, values, unique_cols):
        """跨 DB 的 upsert：優先用真正的 ON CONFLICT DO UPDATE；否則退回保守策略。"""
        backend = engine.url.get_backend_name()
        if backend.startswith("postgresql"):
            ins = pg_insert(table).values(**values)
            upd = {k: getattr(ins.excluded, k) for k in values.keys() if k not in unique_cols}
            return ins.on_conflict_do_update(index_elements=unique_cols, set_=upd)
        elif backend.startswith("sqlite"):
            ins = sqlite_insert(table).values(**values)
            # SQLAlchemy 1.4+/SQLite 3.24+ 才有 on_conflict_do_update
            if hasattr(ins, "on_conflict_do_update"):
                upd = {k: getattr(ins.excluded, k) for k in values.keys() if k not in unique_cols}
                return ins.on_conflict_do_update(index_elements=unique_cols, set_=upd)
            else:
                # 最保守：避免 REPLACE 的連鎖刪除 → 改用 IGNORE
                return ins.prefix_with("OR IGNORE")
        else:
            # 其他資料庫：先試普通 insert；若違反唯一鍵，交由 DB 擲出例外
            return table.insert().values(**values)

    def _coerce_dt(val):
        """把各種時間格式轉成 datetime | None（給 TIMESTAMP 欄位用）"""
        if val is None or val == "" or str(val).lower() in ("null", "nan"):
            return None
        if isinstance(val, datetime):
            return val
        s = str(val).strip()
        # ISO 8601
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            pass
        # timestamp（秒/毫秒）
        try:
            if s.isdigit():
                ts = int(s)
                if ts > 10**12:      # ns
                    ts = ts / 10**9
                elif ts > 10**10:    # ms
                    ts = ts / 1000.0
                return datetime.fromtimestamp(ts)
        except Exception:
            pass
        # 最後嘗試 python-dateutil（可選）
        try:
            from dateutil import parser as dtparser  # 確保 requirements 有 python-dateutil
            return dtparser.parse(s)
        except Exception:
            return None

    def upsert_articles_with_replies(items: Iterable[Dict[str, Any]], source: str):
        now = datetime.now()
        with get_sess() as s:
            for a in items:
                text = (a.get("text") or "").strip()
                if not text:
                    continue
                s.execute(_insert(articles, {
                    "id": a["id"],
                    "text": a.get("text"),
                    "created_at": _coerce_dt(a.get("createdAt")),
                    "updated_at": _coerce_dt(a.get("updatedAt")),
                    "reply_count": int(a.get("replyCount") or 0),
                    "article_url": a.get("article_url"),
                }, ["id"]))

                for r in a.get("articleReplies") or []:
                    rid = r.get("id")
                    if not rid:
                        continue
                    s.execute(_insert(replies, {
                        "id": rid,
                        "article_id": a["id"],
                        "text": r.get("text"),
                        "type": r.get("type"),
                        "created_at": _coerce_dt(r.get("createdAt")),
                    }, ["id"]))

                # 來源標記
                backend = engine.url.get_backend_name()
                if backend.startswith("postgresql"):
                    ins = pg_insert(article_sources).values(
                        article_id=a["id"], source=source, fetched_at=now
                    ).on_conflict_do_nothing()
                    s.execute(ins)
                elif backend.startswith("sqlite"):
                    ins = sqlite_insert(article_sources).values(
                        article_id=a["id"], source=source, fetched_at=now
                    )
                    if hasattr(ins, "on_conflict_do_nothing"):
                        s.execute(ins.on_conflict_do_nothing())
                    else:
                        s.execute(ins.prefix_with("OR IGNORE"))
                else:
                    # 其他 DB：嘗試普通 insert；如違反唯一鍵就讓 DB 決定
                    s.execute(article_sources.insert().values(
                        article_id=a["id"], source=source, fetched_at=now
                    ))

    def log_search(query: str, engine_name: str, top_k: int, used_api: bool, used_hf: bool, duration_ms: int, ranked: List[Dict[str, Any]]) -> int:
        now = datetime.now()
        with get_sess() as s:
            res = s.execute(search_logs.insert().values(
                query=query, engine=engine_name, top_k=top_k, used_api=used_api, used_hf=used_hf,
                duration_ms=duration_ms, created_at=now
            ))
            sid = res.inserted_primary_key[0]
            rows = [{"search_id": sid, "rank": i + 1, "article_id": a["id"], "score": float(a.get("_score", 0.0))}
                    for i, a in enumerate(ranked)]
            if rows:
                s.execute(search_results.insert(), rows)
        return sid
