"""Find the earliest news about the 2026 Taipei mayoral race.

Pieces:
  * is_election_story: decides whether a pre-2026 headline is about the 2026 race
  * fetch_adaptive: queries a date window and splits it when Google's result cap is hit
  * month_windows / scan: walk back month by month and stop after a run of empty months
  * compute_firsts: the earliest story of each kind plus monthly coverage counts
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Callable

from . import config as C

CHIANG = C.CANDIDATES["蔣萬安"]["aliases"]
SHEN = C.CANDIDATES["沈伯洋"]["aliases"]


def _has(title: str, words) -> bool:
    return any(w in title for w in words)


def is_election_story(title: str, published: str | None) -> bool:
    """True when a headline from before START_DATE is about the 2026 race."""
    if not published or not title:
        return False
    for fp in C.FALSE_POSITIVES:
        title = title.replace(fp, "")
    chiang, shen = _has(title, CHIANG), _has(title, SHEN)
    if not (chiang or shen):
        return False
    day = published[:10]
    if day < C.HISTORY_FLOOR:
        # Before 蔣萬安 took office only an explicit "2026" ties a story to this race.
        return "2026" in title
    if "2028" in title and not _has(title, ["2026", "連任"]):
        return False  # presidential speculation, not the mayoral race
    if shen and not chiang and "市長" not in title:
        return False  # 沈伯洋 stories are about the race only once 市長 is mentioned
    return _has(title, C.ELECTION_TERMS) or (chiang and shen)


def month_windows(newest_month_start: date, oldest: date):
    """Yield (start, end) month windows from newest back to oldest, end exclusive."""
    d = newest_month_start
    while d >= oldest.replace(day=1):
        nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
        yield max(d, oldest), nxt
        d = (d - timedelta(days=1)).replace(day=1)


class Budget:
    def __init__(self, limit: int):
        self.limit, self.used = limit, 0

    def take(self) -> bool:
        if self.used >= self.limit:
            return False
        self.used += 1
        return True


def fetch_adaptive(fetch: Callable[[str], list[dict]], query: str, start: date, end: date,
                   budget: Budget, splits: list | None = None) -> list[dict]:
    """Fetch one window; if the result looks capped, split it in half and retry both halves."""
    if not budget.take():
        return []
    got = fetch(f"{query} after:{start.isoformat()} before:{end.isoformat()}")
    span = (end - start).days
    if len(got) >= C.RESULT_CAP and span > 1:
        if splits is not None:
            splits.append((query, start.isoformat(), end.isoformat()))
        mid = start + timedelta(days=span // 2)
        return (fetch_adaptive(fetch, query, start, mid, budget, splits)
                + fetch_adaptive(fetch, query, mid, end, budget, splits))
    return got


def scan(fetch: Callable[[str], list[dict]], today: date, keep: Callable[[dict], bool],
         budget: Budget | None = None, sleep: Callable[[], None] = lambda: None) -> tuple[list[dict], dict]:
    """Walk back from the month before START_DATE.

    Months down to HISTORY_FLOOR are always searched. Older months are searched
    until HISTORY_STOP_AFTER_EMPTY consecutive months keep nothing.
    Returns (raw items, report).
    """
    budget = budget or Budget(C.HISTORY_MAX_REQUESTS)
    start2026 = date.fromisoformat(C.START_DATE)
    floor = date.fromisoformat(C.HISTORY_FLOOR)
    hard = date.fromisoformat(C.HISTORY_HARD_FLOOR)
    raw, splits, per_month = [], [], {}
    newest = (start2026 - timedelta(days=1)).replace(day=1)
    empty_run, months = 0, 0
    for a, b in month_windows(newest, hard):
        got = []
        for q in C.HISTORY_QUERIES:
            got += fetch_adaptive(fetch, q, a, b, budget, splits)
            sleep()
        kept = sum(1 for r in got if keep(r))
        per_month[a.strftime("%Y-%m")] = kept
        raw += got
        months += 1
        if a <= floor:
            empty_run = empty_run + 1 if kept == 0 else 0
            if empty_run >= C.HISTORY_STOP_AFTER_EMPTY:
                break
        if budget.used >= budget.limit:
            break
    # Busy 2026 weeks: rerun the narrow election queries with splitting.
    d = start2026
    while d <= today:
        e = d + timedelta(days=7)
        for q in C.HISTORY_2026_QUERIES:
            raw += fetch_adaptive(fetch, q, d, e, budget, splits)
            sleep()
        d = e
    report = {
        "months_scanned": months,
        "oldest_month_scanned": min(per_month) if per_month else None,
        "kept_per_month": dict(sorted(per_month.items())),
        "requests": budget.used,
        "budget_exhausted": budget.used >= budget.limit,
        "split_windows": len(splits),
    }
    return raw, report


FIRSTS = [
    ("earliest", "最早一則 2026 台北市長選舉相關報導", lambda t: True),
    ("chiang_2026", "最早提到蔣萬安 2026 連任", lambda t: _has(t, CHIANG) and _has(t, ["連任", "2026"])),
    ("shen_mayor", "最早提到沈伯洋與台北市長", lambda t: _has(t, SHEN) and "市長" in t),
    ("matchup", "最早同時出現兩人名字", lambda t: _has(t, CHIANG) and _has(t, SHEN)),
    ("matchup_poll", "最早的蔣沈對決民調報導", lambda t: _has(t, CHIANG) and _has(t, SHEN) and "民調" in t),
]


def _brief(r: dict) -> dict:
    return {k: r.get(k) for k in ("title", "url", "source", "published")}


def compute_firsts(history: list[dict], current: list[dict]) -> dict:
    """Earliest story of each kind and monthly counts of race coverage.

    Uses history (pre-2026, already filtered) plus 2026 stories that pass the
    same election test, so the monthly series means the same thing throughout.
    """
    pool = [r for r in history if r.get("published")]
    pool += [r for r in current if r.get("published") and is_election_story(r["title"], "2025-12-31")]
    pool.sort(key=lambda r: r["published"])
    firsts = []
    for key, label, test in FIRSTS:
        hit = next((r for r in pool if test(r["title"])), None)
        if hit:
            firsts.append({"key": key, "label": label, **_brief(hit)})
    monthly: dict[str, dict] = {}
    for r in pool:
        m = r["published"][:7]
        row = monthly.setdefault(m, {"蔣萬安": 0, "沈伯洋": 0, "both": 0, "total": 0})
        c, s = _has(r["title"], CHIANG), _has(r["title"], SHEN)
        row["total"] += 1
        row["蔣萬安"] += c
        row["沈伯洋"] += s
        row["both"] += c and s
    return {"firsts": firsts, "monthly": dict(sorted(monthly.items())), "pool_size": len(pool)}
