"""Fetch, classify and merge news into data/news.json.

Usage:
    python -m scraper.run              # incremental: last two days of news
    python -m scraper.run --backfill   # week-by-week from START_DATE to today
    python -m scraper.run --history    # look back before 2026 for the earliest race news
    python -m scraper.run --offline    # reclassify existing data only (no network)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import classify as K
from . import config as C
from . import history as H
from . import llm
from . import sources as S

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
NEWS = DATA / "news.json"
HISTORY = DATA / "history.json"     # pre-2026 stories about the 2026 race
FIRSTS = DATA / "firsts.json"       # earliest stories and monthly coverage
META = DATA / "meta.json"
LLM_PER_RUN = int(os.environ.get("LLM_PER_RUN", "300"))
INCREMENTAL_DAYS = 2      # normal look-back window for each run
RETRIES = 2               # extra attempts per request after a network error


def item_id(title: str, source: str) -> str:
    norm = re.sub(r"[\s「」『』\"'“”‘’，,。：:！!？?、]", "", K.clean_title(title, source))
    return hashlib.sha1(norm.encode()).hexdigest()[:12]


def norm_title(title: str) -> str:
    """Comparison key for headline edits: ignore spacing and punctuation."""
    return re.sub(r"[\W_]", "", title or "")


def parse_iso(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def catch_up_window(last_success: str | None, now: datetime) -> tuple[str, str | None]:
    """How far back this run must look so a gap in runs does not lose news.

    Returns ("when", "<n>d") for gaps up to a week, or ("since", "<date>") when
    the last success is older and week-by-week windows are needed.
    """
    last = parse_iso(last_success)
    if not last:
        return "when", f"{INCREMENTAL_DAYS}d"
    days = max(INCREMENTAL_DAYS, math.ceil((now - last).total_seconds() / 86400) + 1)
    if days <= 7:
        return "when", f"{days}d"
    return "since", (last.date() - timedelta(days=1)).isoformat()


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_lines(path: Path, rows: list[dict]):
    """One record per line keeps git diffs readable."""
    body = ",\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for r in rows)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("[\n" + body + "\n]\n", encoding="utf-8")
    tmp.replace(path)


def weekly_windows(start: str, end: date):
    d = date.fromisoformat(start)
    while d <= end:
        nxt = d + timedelta(days=7)
        yield d.isoformat(), nxt.isoformat()
        d = nxt


def gather(backfill: bool, previous: dict | None = None, now: datetime | None = None) -> tuple[list[dict], dict, dict]:
    """Fetch every source. Returns (raw items, per-source health, window info)."""
    previous = previous or {}
    now = now or datetime.now(timezone.utc)
    stamp = now.replace(microsecond=0).isoformat()
    raw, health = [], {}

    def run(name, fn, *args):
        h = health.setdefault(name, {"ok": True, "fetched": 0, "errors": [], "calls": 0, "failed_calls": 0})
        h["calls"] += 1
        for attempt in range(RETRIES + 1):
            try:
                got = fn(*args)
                h["fetched"] += len(got)
                raw.extend(got)
                return
            except Exception as e:  # noqa: BLE001 - record and continue
                err = f"{type(e).__name__}: {e}"[:200]
                if attempt < RETRIES:
                    time.sleep(2 ** attempt)
        h["failed_calls"] += 1
        if err not in h["errors"]:
            h["errors"].append(err)

    today = now.date()
    if backfill:
        window = {"mode": "backfill", "since": C.START_DATE}
    else:
        last_google = (previous.get("Google 新聞") or {}).get("last_success_at")
        kind, value = catch_up_window(last_google, now)
        window = {"mode": "catch_up" if kind == "since" or value != f"{INCREMENTAL_DAYS}d" else "incremental",
                  kind: value}
    for q in C.GOOGLE_NEWS_QUERIES:
        if "since" in window:
            for a, b in weekly_windows(window["since"], today):
                run("Google 新聞", S.google_news, f"{q} after:{a} before:{b}")
                S.polite_sleep()
        else:
            run("Google 新聞", S.google_news, f"{q} when:{window['when']}")
            S.polite_sleep()
    for name, url in C.RSS_FEEDS.items():
        run(name, S.rss, name, url)
    for cand in C.CANDIDATES:
        run("Cofacts", S.cofacts, cand)

    for name, h in health.items():
        prev = previous.get(name) or {}
        if h["failed_calls"] == 0:
            h["ok"] = True
        elif h["failed_calls"] < h["calls"]:
            h["ok"] = "partial"
        else:
            h["ok"] = False
        h["last_attempt_at"] = stamp
        h["last_success_at"] = stamp if h["ok"] is not False else prev.get("last_success_at")
    return raw, health, window


def to_record(r: dict, allow_history: bool = False) -> dict | None:
    """Raw item -> stored record, or None when it is not relevant.

    Items published before START_DATE are kept only with allow_history and
    only when the headline is about the 2026 race; they get era="history".
    """
    if not r.get("title") or not K.is_relevant(r["title"], r.get("summary", "")):
        return None
    pub = r.get("published")
    title = K.display_title(r["title"], r.get("source", ""))
    era = None
    if pub and pub[:10] < C.START_DATE:
        if not (allow_history and H.is_election_story(title, pub)):
            return None
        era = "history"
    rec = {
        "id": item_id(r["title"], r.get("source", "")),
        "title": title,
        "url": r.get("url", ""),
        "source": r.get("source", ""),
        "origin": r.get("origin", ""),
        "published": pub,
        # Google News descriptions only repeat the headline, so skip them.
        "summary": "" if r.get("origin") == "Google 新聞" else r.get("summary", "")[:240],
    }
    rec["cls"] = K.classify(title, r.get("summary", ""), rec["source"], rec["url"], rec["origin"])
    if rec["cls"]["layer"] == "查核機構":
        rec["verdict"] = K.factcheck_verdict(title, r.get("categories"))
    if era:
        rec["era"] = era
    return rec


def retrying_fetch(errors: list[str]):
    """Google News fetch with retries; a failed window returns [] and is logged."""
    def fetch(query: str) -> list[dict]:
        for attempt in range(RETRIES + 1):
            try:
                return S.google_news(query)
            except Exception as e:  # noqa: BLE001
                if attempt == RETRIES:
                    errors.append(f"{query}: {type(e).__name__}: {e}"[:200])
                    return []
                time.sleep(2 ** attempt)
        return []
    return fetch


def run_history(now_dt: datetime) -> tuple[list[dict], dict]:
    errors: list[str] = []
    keep = lambda r: bool(to_record(r, allow_history=True)) and (r.get("published") or "")[:10] < C.START_DATE
    raw, report = H.scan(retrying_fetch(errors), now_dt.date(), keep, sleep=S.polite_sleep)
    report["errors"] = errors[:20]
    report["failed_requests"] = len(errors)
    report["ran_at"] = now_dt.isoformat()
    return raw, report


def _record_title_change(old: dict, new_title: str, now: str) -> bool:
    if norm_title(new_title) == norm_title(old["title"]):
        return False
    hist = old.setdefault("title_history", [])
    hist.append({"title": old["title"], "replaced_at": now})
    del hist[:-5]
    old["title"] = new_title
    return True


def fold_duplicate_urls(rows: list[dict]) -> list[dict]:
    """Records saved before headline tracking may share a URL; merge them.

    The earliest-seen record keeps its id; later titles become the current
    title and earlier ones go into title_history.
    """
    groups: dict[str, list[dict]] = {}
    out = []
    for r in rows:
        if r.get("url"):
            groups.setdefault(r["url"], []).append(r)
        else:
            out.append(r)
    for recs in groups.values():
        recs.sort(key=lambda r: r.get("first_seen") or "")
        keep = recs[0]
        for later in recs[1:]:
            _record_title_change(keep, later["title"], later.get("first_seen") or "")
            if later.get("cls", {}).get("by") == "llm" or keep.get("cls", {}).get("by") != "llm":
                keep["cls"] = later["cls"]
        out.append(keep)
    return out


def merge(existing: list[dict], fresh: list[dict], now: str) -> tuple[list[dict], int, int]:
    """Returns (rows, added, headline_edits)."""
    existing = fold_duplicate_urls(existing)
    by_id = {e["id"]: e for e in existing}
    by_url = {e["url"]: e for e in existing if e.get("url")}
    added = edits = 0
    for rec in fresh:
        old = by_id.get(rec["id"])
        if old is None and rec.get("url") in by_url:
            # Same article link, new headline: the outlet edited its title.
            old = by_url[rec["url"]]
            if _record_title_change(old, rec["title"], now):
                edits += 1
                old["cls"] = rec["cls"] if old.get("cls", {}).get("by") != "llm" else old["cls"]
            by_id[rec["id"]] = old
            continue
        if old is None:
            rec["first_seen"] = now
            by_id[rec["id"]] = rec
            if rec.get("url"):
                by_url[rec["url"]] = rec
            added += 1
        else:
            # Keep the earliest timestamp and any LLM label already earned.
            if rec.get("published") and (not old.get("published") or rec["published"] < old["published"]):
                old["published"] = rec["published"]
            if old.get("cls", {}).get("by") != "llm":
                old["cls"] = rec["cls"]
            if rec.get("verdict"):
                old["verdict"] = rec["verdict"]
    unique = {id(r): r for r in by_id.values()}.values()
    rows = sorted(unique, key=lambda e: e.get("published") or "", reverse=True)
    return rows, added, edits


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
    ap.add_argument("--history", action="store_true")
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args(argv)

    DATA.mkdir(exist_ok=True)
    now_dt = datetime.now(timezone.utc).replace(microsecond=0)
    now = now_dt.isoformat()
    existing = load(NEWS, [])
    history = load(HISTORY, [])
    meta = load(META, {})
    window, edits = {}, 0
    hist_report = None

    if args.offline:
        raw, health = [], {}
        existing = fold_duplicate_urls(existing)
        # Re-apply the current race test to saved pre-2026 stories.
        history = [r for r in fold_duplicate_urls(history) if H.is_election_story(r["title"], r.get("published"))]
        for e in existing:
            if e.get("origin") == "Google 新聞":
                e["summary"] = ""
            e["title"] = K.display_title(e["title"], e["source"])
            if e.get("cls", {}).get("by") == "llm":
                continue
            e["cls"] = K.classify(e["title"], e.get("summary", ""), e["source"], e["url"], e.get("origin", ""))
        rows, added = sorted(existing, key=lambda e: e.get("published") or "", reverse=True), 0
    else:
        raw, health, window = gather(args.backfill, meta.get("sources", {}), now_dt)
        if args.history:
            hist_raw, hist_report = run_history(now_dt)
            raw += hist_raw
        fresh = [rec for rec in (to_record(r, allow_history=args.history) for r in raw) if rec]
        for name, h in health.items():
            h["kept"] = len({f["id"] for f in fresh if f["origin"] == name})
        old_fresh = [f for f in fresh if f.get("era") == "history"]
        fresh = [f for f in fresh if f.get("era") != "history"]
        rows, added, edits = merge(existing, fresh, now)
        if old_fresh:
            history, hist_added, _ = merge(history, old_fresh, now)
            hist_report["added"] = hist_added

    llm_status = llm_pass(rows)
    write_lines(NEWS, rows)
    if history or HISTORY.exists():
        write_lines(HISTORY, history)
    firsts = H.compute_firsts(history, rows)
    firsts["updated_at"] = now
    FIRSTS.write_text(json.dumps(firsts, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if hist_report is not None:
        meta["history"] = {**hist_report, "total": len(history),
                           "earliest": min((r["published"] for r in history if r.get("published")), default=None)}
    elif "history" in meta:
        meta["history"]["total"] = len(history)
        meta["history"]["earliest"] = min((r["published"] for r in history if r.get("published")), default=None)
    if args.offline:
        # Reclassifying is not a fetch: keep the fetch time and window shown on the site.
        meta.update({"reclassified_at": now, "total": len(rows),
                     "headline_edited_total": sum(1 for r in rows if r.get("title_history")), "llm": llm_status})
        META.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"reclassified total={len(rows)}")
        return 0
    meta.update({
        "updated_at": now,
        "mode": "history" if args.history else window.get("mode", "incremental"),
        "window": window,
        "total": len(rows),
        "added": added,
        "headline_edits": edits,
        "headline_edited_total": sum(1 for r in rows if r.get("title_history")),
        "sources": health or meta.get("sources", {}),
        "llm": llm_status,
        "start_date": C.START_DATE,
    })
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"total={len(rows)} added={added} edits={edits} window={window} sources={ {k: v['ok'] for k, v in health.items()} } llm={llm_status}")
    # Fail the job only when every source failed, so the site keeps old data.
    if health and not any(h["ok"] for h in health.values()):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
