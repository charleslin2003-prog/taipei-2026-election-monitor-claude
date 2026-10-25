"""Rule-based headline classifier.

Reads a Chinese news headline and decides:
  * whether it mentions either candidate (relevance)
  * the kind of story: 攻擊 (attack), 澄清回應 (rebuttal) or 一般報導 (general)
  * who is being attacked (target) and which camp is attacking
  * topic tags and the source layer

It works on word order around attack verbs, so it is approximate. Every result
carries a confidence label, and the optional LLM pass (llm.py) can overwrite it.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from . import config as C

VERB_EXCLUDE = ["批准", "批次", "批發", "一批", "大批", "批貨", "酸雨", "酸痛", "轟動", "轟趴"]


def _mask(text: str, words: list[str]) -> str:
    """Blank out phrases so they cannot match later, keeping positions stable."""
    for w in words:
        text = text.replace(w, "　" * len(w))
    return text


def clean_title(title: str, source: str = "") -> str:
    title = (title or "").strip()
    if source and title.endswith(" - " + source):
        title = title[: -len(source) - 3]
    return re.sub(r"\s+", " ", title).strip()


def display_title(title: str, source: str = "") -> str:
    """clean_title plus removal of section labels such as "| 政治" or "- 生活"."""
    t = clean_title(title, source)
    for _ in range(2):
        t = re.sub(r"\s*[|｜\-－]\s*" + C.TITLE_SUFFIXES + r"\s*$", "", t).strip()
    return t


def _speaker_camp(text: str, exclude: str | None = None) -> str | None:
    """Camp of a speaker introduced with a colon, e.g. "民眾黨：…".

    The target's own camp is skipped: "…開轟蔣萬安：…" names the target, not the speaker.
    """
    for m in re.finditer(r"[：:]", text):
        camp = _camp_in(text[max(0, m.start() - 8):m.start()])
        if camp and camp != exclude:
            return camp
    return None


def mentions(text: str) -> dict[str, list[int]]:
    """Positions where each candidate (or their side) appears."""
    text = _mask(text, C.FALSE_POSITIVES)
    found: dict[str, list[int]] = {}
    for cand, info in C.CANDIDATES.items():
        pos = []
        for w in info["aliases"] + info["side"]:
            pos += [m.start() for m in re.finditer(re.escape(w), text)]
        if pos:
            found[cand] = sorted(set(pos))
    return found


def is_relevant(title: str, summary: str = "") -> bool:
    text = _mask(f"{title} {summary}", C.FALSE_POSITIVES)
    return any(a in text for info in C.CANDIDATES.values() for a in info["aliases"])


def _first(text: str, words: list[str]) -> tuple[int, str] | None:
    best = None
    for w in words:
        i = text.find(w)
        if i >= 0 and (best is None or i < best[0] or (i == best[0] and len(w) > len(best[1]))):
            best = (i, w)
    return best


def _camp_in(segment: str, *, nearest_end: bool = True) -> str | None:
    """Camp whose keyword sits closest to the end (or start) of the segment."""
    best = None
    for camp, words in C.CAMPS.items():
        for w in words:
            for m in re.finditer(re.escape(w), segment):
                key = m.end() if nearest_end else -m.start()
                if best is None or key > best[0]:
                    best = (key, camp)
    for cand, info in C.CANDIDATES.items():
        for w in info["aliases"] + info["side"]:
            for m in re.finditer(re.escape(w), segment):
                key = m.end() if nearest_end else -m.start()
                if best is None or key > best[0]:
                    best = (key, C.CANDIDATE_CAMP[cand])
    return best[1] if best else None


def _other(cand: str) -> str:
    return next(c for c in C.CANDIDATES if c != cand)


def topics(text: str) -> list[str]:
    return [t for t, words in C.TOPICS.items() if any(w in text for w in words)]


def layer(source: str, url: str, title: str, origin: str = "") -> str:
    host = urlparse(url or "").netloc.lower()
    if any(d in host for d in C.FACTCHECK_DOMAINS) or origin in ("台灣事實查核中心", "MyGoPen", "Cofacts"):
        return "查核機構"
    if any(d in host for d in C.FORUM_DOMAINS) or origin.startswith("PTT"):
        return "論壇與社群"
    if source in C.OVERSEAS_SOURCES or host.endswith(".cn"):
        return "境外媒體"
    if any(w in title for w in C.SHOW_WORDS):
        return "網路／政論節目"
    return "主流媒體"


VERDICTS = ["部分錯誤", "錯誤", "誤導", "易誤解", "事實釐清", "證據不足", "正確", "詐騙", "查證", "謠言"]


def factcheck_verdict(title: str, categories: list[str] | None = None) -> str | None:
    m = re.match(r"^\s*【([^】]+)】", title or "")
    if m:
        return m.group(1)
    for cat in categories or []:
        for v in VERDICTS:
            if v == cat.strip():
                return v
    return None


def classify(title: str, summary: str = "", source: str = "", url: str = "", origin: str = "") -> dict:
    t = clean_title(title, source)
    masked = _mask(_mask(t, C.FALSE_POSITIVES), VERB_EXCLUDE)
    pos = mentions(masked)
    if not pos:  # candidate only named in the summary
        pos_summary = mentions(summary or "")
        named = sorted(pos_summary)
    else:
        named = sorted(pos, key=lambda c: pos[c][0])

    result = {
        "kind": "一般報導",
        "target": None,
        "attacker": None,
        "confidence": None,
        "candidates": named,
        "topics": topics(f"{t} {summary}"),
        "layer": layer(source, url, t, origin),
        "by": "rule",
    }

    atk = _first(masked, C.ATTACK_VERBS)
    dfn = _first(masked, C.DEFENSE_VERBS)

    # A candidate rebutting before any attack word: "蔣萬安競辦駁斥：…"
    if dfn and (not atk or dfn[0] < atk[0]):
        before = [c for c, ps in pos.items() if any(p < dfn[0] for p in ps)]
        if before:
            subj = max(before, key=lambda c: max(p for p in pos[c] if p < dfn[0]))
            result.update(kind="澄清回應", target=subj, attacker=None, confidence="中")
            return result

    if atk:
        va, verb = atk
        passive = any(mk in masked[max(0, va - 6):va] for mk in C.PASSIVE_MARKERS)
        before = {c: max(p for p in ps if p < va) for c, ps in pos.items() if any(p < va for p in ps)}
        after = {c: min(p for p in ps if p > va) for c, ps in pos.items() if any(p > va for p in ps)}
        target, conf = None, "低"
        if passive and before:
            target, conf = max(before, key=before.get), "中"
            pm = max(masked.rfind(mk, 0, va) for mk in C.PASSIVE_MARKERS)
            attacker = _camp_in(masked[pm + 1:va]) if pm >= 0 else None
        else:
            attacker = _camp_in(masked[:va])
            if after:
                target, conf = min(after, key=after.get), "中"
            elif before:
                other = _other(max(before, key=before.get))
                if other in before:
                    # "沈伯洋談X 蔣萬安競辦嗆：…" — rival named earlier as the topic
                    target, conf = other, "中"
                elif any(w in masked[va:] for w in C.IMPLIED_TARGET[other]):
                    target, conf = other, "低"
                else:
                    result.update(kind="其他批評", confidence="中")
                    return result
        if not attacker:
            attacker = _speaker_camp(masked, exclude=C.CANDIDATE_CAMP.get(target))
        if target and attacker == C.CANDIDATE_CAMP.get(target) and not passive:
            # "沈伯洋陣營內部" style headlines are rare; treat as unclear.
            conf = "低"
        result.update(kind="攻擊", target=target or "不明", attacker=attacker or "不明", confidence=conf)
        return result

    if dfn:
        result.update(kind="澄清回應", target=named[0] if named else None, confidence="低")
    return result
