"""Fetchers. Each returns a list of raw items with a common shape:

    {title, url, source, published (ISO-8601 UTC), summary, origin, categories}

Fetch errors raise; run.py records them per source so one broken feed never
stops the others.
"""
from __future__ import annotations

import html
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote

import feedparser
import requests

from . import config as C

SESSION = requests.Session()
SESSION.headers["User-Agent"] = C.USER_AGENT


def _get(url: str, **kw) -> bytes:
    r = SESSION.get(url, timeout=25, **kw)
    r.raise_for_status()
    return r.content


def _strip(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _when(entry) -> str | None:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc).isoformat()
    return None


def _parse(content: bytes, origin: str, default_source: str) -> list[dict]:
    feed = feedparser.parse(content)
    if feed.bozo and not feed.entries:
        raise ValueError(f"unreadable feed: {feed.bozo_exception}")
    items = []
    for e in feed.entries:
        src = default_source
        if e.get("source") and e.source.get("title"):
            src = e.source["title"]
        items.append({
            "title": _strip(e.get("title", "")),
            "url": e.get("link", ""),
            "source": src,
            "published": _when(e),
            "summary": _strip(e.get("summary", ""))[:400],
            "origin": origin,
            "categories": [t.get("term", "") for t in e.get("tags", [])],
        })
    return items


def google_news(query: str) -> list[dict]:
    url = C.GOOGLE_NEWS_URL.format(q=quote(query))
    return _parse(_get(url), "Google 新聞", "Google 新聞")


def rss(name: str, url: str) -> list[dict]:
    cookies = {"over18": "1"} if "ptt.cc" in url else None
    return _parse(_get(url, cookies=cookies), name, name)


COFACTS_QUERY = """
query($text: String!) {
  ListArticles(filter: {moreLikeThis: {like: $text}}, orderBy: [{createdAt: DESC}], first: 40) {
    edges { node { id text createdAt articleReplies { reply { type text } } } }
  }
}
"""
COFACTS_TYPES = {"RUMOR": "含有不實訊息", "NOT_RUMOR": "含有正確訊息", "OPINIONATED": "含有個人意見", "NOT_ARTICLE": "不在查證範圍"}


def cofacts(term: str) -> list[dict]:
    r = SESSION.post(C.COFACTS_GRAPHQL, json={"query": COFACTS_QUERY, "variables": {"text": term}},
                     headers={"x-app-id": "RUMORS_SITE"}, timeout=25)
    r.raise_for_status()
    body = r.json()
    if body.get("errors"):
        raise ValueError(body["errors"][0].get("message", "GraphQL error"))
    items = []
    for edge in body["data"]["ListArticles"]["edges"]:
        n = edge["node"]
        types = [ar["reply"]["type"] for ar in n.get("articleReplies") or [] if ar.get("reply")]
        verdict = COFACTS_TYPES.get(max(set(types), key=types.count)) if types else "尚無回應"
        text = re.sub(r"\s+", " ", n.get("text") or "").strip()
        items.append({
            "title": text[:80] + ("…" if len(text) > 80 else ""),
            "url": f"https://cofacts.tw/article/{n['id']}",
            "source": "Cofacts",
            "published": n.get("createdAt"),
            "summary": text[:400],
            "origin": "Cofacts",
            "categories": [verdict],
        })
    return items


def polite_sleep():
    time.sleep(1.2)
