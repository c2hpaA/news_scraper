from __future__ import annotations
import json
import os
from typing import Optional

import click

from .cache import write_export
from .models import Article, SearchResult, Verdict
from .search import get_article as get_article_func
from .search import search_text as search_text_func
from .verdict import summarize_verdict as summarize_verdict_func


@click.group(name="cofacts-cli")
def cli() -> None:
    """Cofacts quick lookup CLI."""


@cli.command("search")
@click.argument("query", type=str)
@click.option("--top-k", default=5, show_default=True, type=int)
@click.option("--no-api", is_flag=True, default=False, help="Disable GraphQL API; use HF only")
@click.option("--no-hf", is_flag=True, default=False, help="Disable HuggingFace dataset; use API only")
@click.option("--time-gte", type=str, default=None)
@click.option("--time-lte", type=str, default=None)
@click.option("--export", "export_fmt", type=click.Choice(["json", "csv"]), default=None)
@click.option("--out", type=str, default=None)
@click.option("--debug", is_flag=True, default=False, help="Print debug info")
def search_cmd(
    query: str,
    top_k: int,
    no_api: bool,
    no_hf: bool,
    time_gte: Optional[str],
    time_lte: Optional[str],
    export_fmt: Optional[str],
    out: Optional[str],
    debug: bool,
):
    """Search text across Cofacts sources and print summary."""
    if debug:
        os.environ["DEBUG"] = "1"

    time_range = None
    if time_gte or time_lte:
        time_range = {"GTE": time_gte, "LTE": time_lte}

    sr: SearchResult = search_text_func(
        query,
        top_k=top_k,
        use_api=not no_api,
        use_hf=not no_hf,
        time_range=time_range,
    )
    _print_search(sr)

    if export_fmt:
        name = out or "articles"
        # Pydantic v2
        rows = [a.model_dump() for a in sr.items]
        path = write_export(name, rows, fmt=export_fmt)
        click.echo(f"Exported to {path}")


def _print_search(sr: SearchResult) -> None:
    click.echo(f"Query: {sr.query}")
    src_api = sr.source.get("api") if isinstance(sr.source, dict) else getattr(sr.source, "api", None)
    src_hf = sr.source.get("hf") if isinstance(sr.source, dict) else getattr(sr.source, "hf", None)
    click.echo(f"Sources used: API={src_api} HF={src_hf}")
    click.echo("\nTop matches:")
    for i, a in enumerate(sr.items, 1):
        click.echo(f"{i}. id={a.id} replies={a.replyCount} url={a.article_url}")
        snippet = (a.text or "").strip().replace("\n", " ")
        if len(snippet) > 80:
            snippet = snippet[:77] + "..."
        click.echo(f"   {snippet}")


@cli.command("get")
@click.option("--id", "article_id", required=True, type=str, help="Article ID")
def get_cmd(article_id: str):
    a = get_article_func(article_id)
    if not a:
        click.echo("Article not found")
        raise SystemExit(1)
    click.echo(json.dumps(a.model_dump(), ensure_ascii=False, indent=2))


@cli.command("verdict")
@click.argument("text", type=str)
@click.option("--threshold", default=0.15, show_default=True, type=float)
@click.option("--no-api", is_flag=True, default=False, help="Disable GraphQL API; use HF only")
@click.option("--no-hf", is_flag=True, default=False, help="Disable HuggingFace dataset; use API only")
@click.option("--export", "export_fmt", type=click.Choice(["json", "csv"]), default=None)
@click.option("--out", type=str, default=None)
@click.option("--debug", is_flag=True, default=False, help="Print debug info")
def verdict_cmd(
    text: str,
    threshold: float,
    no_api: bool,
    no_hf: bool,
    export_fmt: Optional[str],
    out: Optional[str],
    debug: bool,
):
    if debug:
        os.environ["DEBUG"] = "1"

    v: Verdict = summarize_verdict_func(
        text,
        threshold=threshold,
        use_api=not no_api,
        use_hf=not no_hf,
    )
    _print_verdict(v)

    if export_fmt:
        name = out or "verdict"
        data = v.model_dump()
        if export_fmt == "json":
            path = write_export(name, [data], fmt="json")
        else:
            # flatten evidence for CSV
            rows = []
            ev_list = data.get("evidence") or []
            for ev in ev_list:
                row = {k: val for k, val in data.items() if k != "evidence"}
                for k, val in ev.items():
                    row[f"evidence_{k}"] = val
                rows.append(row)
            path = write_export(name, rows, fmt="csv")
        click.echo(f"Exported to {path}")

@cli.command("index")
@click.option("--min-df", default=2, show_default=True, type=int, help="TF-IDF min_df")
@click.option("--ngram-min", default=1, show_default=True, type=int)
@click.option("--ngram-max", default=2, show_default=True, type=int)
def index_cmd(min_df: int, ngram_min: int, ngram_max: int):
    """Build/rebuild local TF-IDF cache for fast search."""
    from .index import build_index, CACHE_DIR, META_PATH
    path = build_index(min_df=min_df, ngram=(ngram_min, ngram_max))
    click.echo(f"Index built at: {path}")
    try:
        import json, os
        with open(META_PATH, "r", encoding="utf-8") as f:
            meta = json.load(f)
        click.echo(json.dumps(meta, ensure_ascii=False, indent=2))
        click.echo(f"Cache directory: {CACHE_DIR}")
    except Exception:
        pass

@cli.group("db")
def db_group(): ...

@db_group.command("init")
def db_init_cmd():
    from .store import init_db
    init_db()
    click.echo("DB initialized.")


def _print_verdict(v: Verdict) -> None:
    click.echo(f"Query: {v.query}")
    click.echo(f"Machine verdict: {v.verdict} (threshold={v.threshold})")
    click.echo("Scores:")
    for k, s in v.scores.items():
        click.echo(f" - {k}: {s:.2f}")
    if v.evidence:
        click.echo("Evidence:")
        for e in v.evidence[:5]:
            click.echo(f" - [{e.reply_type}] {e.url} {e.createdAt} :: {(e.snippet or '')[:80]}")
    click.echo(getattr(v, "note", ""))


def main():
    cli(prog_name="cofacts-cli")


if __name__ == "__main__":
    main()
