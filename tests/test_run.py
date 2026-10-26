from datetime import datetime, timezone

from scraper.run import catch_up_window, fold_duplicate_urls, merge

NOW = datetime(2026, 10, 26, 10, 0, tzinfo=timezone.utc)


def rec(id_, title, url, first_seen="2026-10-25T00:00:00+00:00"):
    return {"id": id_, "title": title, "url": url, "source": "UDN", "origin": "Google 新聞",
            "published": "2026-10-25T00:00:00+00:00", "first_seen": first_seen,
            "cls": {"kind": "一般報導", "by": "rule"}}


def test_headline_edit_is_tracked_not_duplicated():
    old = rec("a", "全英文回應被中國跟蹤 沈伯洋：若當選…", "https://news.google.com/rss/articles/X")
    new = rec("b", "以英文回應被中國跟蹤 沈伯洋：若當選…", "https://news.google.com/rss/articles/X")
    rows, added, edits = merge([old], [new], "2026-10-26T00:00:00+00:00")
    assert (len(rows), added, edits) == (1, 0, 1)
    assert rows[0]["id"] == "a"
    assert rows[0]["title"].startswith("以英文")
    assert rows[0]["title_history"][0]["title"].startswith("全英文")


def test_punctuation_only_change_is_ignored():
    old = rec("a", "蔣萬安：政策不能天馬行空", "u1")
    new = rec("b", "蔣萬安 政策不能天馬行空", "u1")
    rows, _, edits = merge([old], [new], "t")
    assert edits == 0 and "title_history" not in rows[0]


def test_existing_duplicates_are_folded():
    a = rec("a", "沈伯洋提南北縫合 蔣：政策不能天馬行空", "u1", "2026-10-25T01:00:00+00:00")
    b = rec("b", "沈伯洋提南北縫合 蔣萬安：政策不能天馬行空", "u1", "2026-10-25T05:00:00+00:00")
    rows = fold_duplicate_urls([b, a])
    assert len(rows) == 1 and rows[0]["id"] == "a"
    assert rows[0]["title"].endswith("蔣萬安：政策不能天馬行空")
    assert rows[0]["title_history"][0]["replaced_at"] == "2026-10-25T05:00:00+00:00"


def test_catch_up_window():
    assert catch_up_window(None, NOW) == ("when", "2d")
    assert catch_up_window("2026-10-26T09:30:00+00:00", NOW) == ("when", "2d")
    assert catch_up_window("2026-10-22T09:30:00+00:00", NOW) == ("when", "6d")
    assert catch_up_window("2026-10-10T09:30:00+00:00", NOW) == ("since", "2026-10-09")
