"""Fetch, classify and merge news into data/news.json.

Usage:
    python -m scraper.run              # incremental: last two days of news
    python -m scraper.run --backfill   # week-by-week from START_DATE to today
    python -m scraper.run --offline    # reclassify existing data only (no network)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import classify as K
from . import config as C
from . import llm
from . import sources as S

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
NEWS = DATA / "news.json"
META = DATA / "meta.json"
LLM_PER_RUN = int(__import__("os").environ.get("LLM_PER_RUN", "300"))


def item_id(title: str, source: str) -> str:
    norm = re.sub(r"[\s「」『』\"'“”‘’，,。：:！!？?、]", "", K.clean_title(title, source))
    return hashlib.sha1(norm.encode()).hexdigest()[:12]


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_lines(path: Path, rows: list[dict]):
    """One record per line keeps git diffs readable."""
    body = ",\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("[\n" + body + "\n]\n", encoding="utf-8")
    tmp.replace(path)


def weekly_windows(start: str, end: date):
    d = date.fromisoformat(start)
    while d <= end:
        nxt = d + timedelta(days=7)
        yield d.isoformat(), nxt.isoformat()
        d = nxt


def gather(backfill: bool) -> tuple[list[dict], dict]:
    raw, health = [], {}

    def run(name, fn, *args):
        h = health.setdefault(name, {"ok": True, "fetched": 0, "errors": []})
        try:
            got = fn(*args)
            h["fetched"] += len(got)
            raw.extend(got)
        except Exception as e:  # noqa: BLE001 - record and continue
            h["ok"] = False
            h["errors"].append(f"{type(e).__name__}: {e}"[:200])

    today = datetime.now(timezone.utc).date()
    for q in C.GOOGLE_NEWS_QUERIES:
        if backfill:
            for a, b in weekly_windows(C.START_DATE, today):
                run("Google 新聞", S.google_news, f"{q} after:{a} before:{b}")
                S.polite_sleep()
        else:
            run("Google 新聞", S.google_news, f"{q} when:2d")
            S.polite_sleep()
    for name, url in C.RSS_FEEDS.items():
        run(name, S.rss, name, url)
    for cand in C.CANDIDATES:
        run("Cofacts", S.cofacts, cand)
    for h in health.values():
        if h["ok"] is False and h["fetched"]:
            h["ok"] = "partial"
    return raw, health


def to_record(r: dict) -> dict | None:
    if not r.get("title") or not K.is_relevant(r["title"], r.get("summary", "")):
        return None
    pub = r.get("published")
    if pub and pub[:10] < C.START_DATE:
        return None
    title = K.display_title(r["title"], r.get("source", ""))
    rec = {
        "id": item_id(r["title"], r.get("source", "")),
        "title": title,
        "url": r.get("url", ""),
        "source": r.get("source", ""),
        "origin": r.get("origin", ""),
        "published": pub,
        "summary": r.get("summary", "")[:240],
    }
    rec["cls"] = K.classify(title, r.get("summary", ""), rec["source"], rec["url"], rec["origin"])
    if rec["cls"]["layer"] == "查核機構":
        rec["verdict"] = K.factcheck_verdict(title, r.get("categories"))
    return rec


def merge(existing: list[dict], fresh: list[dict], now: str) -> tuple[list[dict], int]:
    by_id = {e["id"]: e for e in existing}
    added = 0
    for rec in fresh:
        old = by_id.get(rec["id"])
        if old is None:
            rec["first_seen"] = now
            by_id[rec["id"]] = rec
            added += 1
        else:
            # Keep the earliest timestamp and any LLM label already earned.
            if rec.get("published") and (not old.get("published") or rec["published"] < old["published"]):
                old["published"] = rec["published"]
            if old.get("cls", {}).get("by") != "llm":
                old["cls"] = rec["cls"]
            if rec.get("verdict"):
                old["verdict"] = rec["verdict"]
    rows = sorted(by_id.values(), key=lambda e: e.get("published") or "", reverse=True)
    return rows, added


def llm_pass(rows: list[dict]) -> dict:
    status = {"enabled": llm.enabled(), "labelled": 0, "errors": []}
    if not status["enabled"]:
        return status
    # Headlines the rules flagged as attacks or rebuttals go first, newest first.
    todo = [r for r in rows if r.get("cls", {}).get("by") != "llm"]
    todo.sort(key=lambda r: (r["cls"].get("kind") == "一般報導", r.get("published") is None))
    todo = todo[:LLM_PER_RUN]
    for i in range(0, len(todo), 30):
        chunk = todo[i:i + 30]
        try:
            labels = llm.classify_batch(chunk)
        except Exception as e:  # noqa: BLE001
            status["errors"].append(f"{type(e).__name__}: {e}"[:200])
            break
        for r in chunk:
            if r["id"] in labels:
                r["cls"].update(labels[r["id"]], by="llm", confidence="高")
                status["labelled"] += 1
    return status


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args(argv)

    DATA.mkdir(exist_ok=True)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    existing = load(NEWS, [])

    if args.offline:
        raw, health = [], {}
        for e in existing:
            e["title"] = K.display_title(e["title"], e["source"])
            if e.get("cls", {}).get("by") == "llm":
                continue
            e["cls"] = K.classify(e["title"], e.get("summary", ""), e["source"], e["url"], e.get("origin", ""))
        rows, added = sorted(existing, key=lambda e: e.get("published") or "", reverse=True), 0
    else:
        raw, health = gather(args.backfill)
        fresh = [rec for rec in map(to_record, raw) if rec]
        for name, h in health.items():
            h["kept"] = len({f["id"] for f in fresh if f["origin"] == name})
        rows, added = merge(existing, fresh, now)

    llm_status = llm_pass(rows)
    write_lines(NEWS, rows)
    meta = load(META, {})
    meta.update({
        "updated_at": now,
        "mode": "offline" if args.offline else ("backfill" if args.backfill else "incremental"),
        "total": len(rows),
        "added": added,
        "sources": health or meta.get("sources", {}),
        "llm": llm_status,
        "start_date": C.START_DATE,
    })
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"total={len(rows)} added={added} sources={ {k: v['ok'] for k, v in health.items()} } llm={llm_status}")
    # Fail the job only when every source failed, so the site keeps old data.
    if health and not any(h["ok"] for h in health.values()):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
