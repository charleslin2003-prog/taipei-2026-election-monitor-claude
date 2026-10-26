"""Checks on the hand-reviewed records in data/curated.json.

Every record must name a candidate, carry a known verdict and link to an
http(s) source, so a bad edit fails CI instead of reaching the site.
"""
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

DATA = json.loads((Path(__file__).resolve().parent.parent / "data" / "curated.json").read_text(encoding="utf-8"))
CANDS = {"蔣萬安", "沈伯洋"}
STATUSES = {
    "錯誤", "曲解／斷章", "指控不成立", "部分屬實", "爭議中", "程序爭議", "無證據", "誇大爭議",
    "單方澄清", "未查證", "評論", "屬實", "已澄清",
}
LAYERS = {"主流媒體", "網路／政論節目", "論壇與社群", "境外官方"}


def is_url(u):
    p = urlparse(u or "")
    return p.scheme in ("http", "https") and bool(p.netloc)


def test_attacks():
    assert DATA["attacks"]
    for a in DATA["attacks"]:
        assert a["target"] in CANDS, a
        assert a["status"] in STATUSES, a
        assert a["layer"] in LAYERS, a
        assert a["claim"].strip() and a["actor"].strip(), a
        assert is_url(a["url"]), a
        assert isinstance(a.get("response", ""), str)


def test_factchecks():
    assert DATA["factchecks"]
    for f in DATA["factchecks"]:
        assert f["candidate"] in CANDS, f
        assert f["verdict"] in STATUSES, f
        assert f["basis"].strip(), f
        assert is_url(f["url"]), f


def test_polls_and_events():
    for p in DATA["polls"]:
        assert 0 <= p["chiang"] <= 100 and 0 <= p["shen"] <= 100
        assert is_url(p["url"])
    for e in DATA.get("events", []):
        assert datetime.fromisoformat(e["date"]).tzinfo is not None
        assert e["label"].strip() and is_url(e["url"])
