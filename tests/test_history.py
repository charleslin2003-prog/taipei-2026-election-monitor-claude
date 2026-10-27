from datetime import date

from scraper import config as C
from scraper import history as H

ok = H.is_election_story


def test_election_story_rules():
    # After 蔣萬安 took office: candidate + election word
    assert ok("蔣萬安拚連任 綠營人選仍未定", "2025-06-01T00:00:00+00:00")
    assert ok("2026台北市長民調 蔣萬安大幅領先", "2024-03-01T00:00:00+00:00")
    assert ok("曹興誠：賴總統應徵召沈伯洋選北市長", "2025-11-12T00:00:00+00:00")
    # Ordinary city-hall news is not about the race
    assert not ok("蔣萬安視察大巨蛋工程進度", "2024-05-01T00:00:00+00:00")
    # 沈伯洋 without 市長 is not about the mayoral race
    assert not ok("沈伯洋遭中共通緝 民進黨團聲援", "2025-11-01T00:00:00+00:00")
    # 2028 presidential talk alone is excluded
    assert not ok("蔣萬安2028大選聲勢看好", "2025-01-01T00:00:00+00:00")
    # Before the 2022 win, only an explicit 2026 counts
    assert not ok("蔣萬安宣布參選台北市長", "2022-06-01T00:00:00+00:00")
    assert ok("蔣萬安若當選 2026年連任之路", "2022-06-01T00:00:00+00:00")
    # The civil-defence drill is not the candidate
    assert not ok("萬安演習 2026 台北市長宣導", "2025-07-01T00:00:00+00:00")
    # Appointments, other elections, 2026 as a calendar year, helping others campaign
    assert not ok("蔣萬安當選臺北市長 外界關注副市長人選", "2022-11-27T00:00:00+00:00")
    assert not ok("2024選戰溫度計／對決「台中蔣萬安」當選率曝光", "2023-12-13T00:00:00+00:00")
    assert not ok("北台灣最大水樂園荒廢 蔣萬安：力拚2026年整修完成", "2023-06-08T00:00:00+00:00")
    assert not ok("2026國際扶輪年會在北市登場 蔣萬安簽署備忘錄", "2024-01-22T00:00:00+00:00")
    assert not ok("讚王鴻薇問政表現佳 蔣萬安陪拜票拚連任", "2024-01-02T00:00:00+00:00")
    assert not ok("連任無懸念！高虹安重返市府 侯漢廷盼與蔣萬安組「安安連線」", "2025-12-18T00:00:00+00:00")
    assert not ok("蔣萬安是總統熱門人選？小池百合子：這是台灣選民決定的事", "2024-02-07T00:00:00+00:00")
    # Generic election words in 2023-24 usually mean the 2024 national race
    assert not ok("妻子不滿忙選舉？蔣萬安欲言又止", "2024-01-04T00:00:00+00:00")
    # 蔣萬安's own re-election, even far from his name
    assert ok("誰來戰都死路一條？他揭蔣萬安「拿到這紅利」：連任不難", "2024-12-11T00:00:00+00:00")
    assert ok("各界幫找連任對手 蔣萬安4字闡心境", "2024-01-22T00:00:00+00:00")
    # In 2026 a 沈伯洋 election story counts without 市長
    assert ok("批選戰只剩洋流、民調 柯文哲出題考沈伯洋", "2026-10-01T00:00:00+00:00")
    assert not ok("批選戰只剩洋流、民調 柯文哲出題考沈伯洋", "2025-10-01T00:00:00+00:00")


def test_clear_race_story_for_earliest_card():
    assert not H.is_clear_race_story("TVBS民調／六都市長滿意度出爐 蔣萬安墊底", "2023-03-23T00:00:00+00:00")
    assert H.is_clear_race_story("2026誰戰蔣萬安？一面倒推「綠營女戰將」", "2024-01-21T00:00:00+00:00")


def test_month_windows_walk_back():
    w = list(H.month_windows(date(2025, 12, 1), date(2025, 10, 15)))
    assert w == [(date(2025, 12, 1), date(2026, 1, 1)), (date(2025, 11, 1), date(2025, 12, 1)),
                 (date(2025, 10, 15), date(2025, 11, 1))]


def test_fetch_adaptive_splits_capped_windows():
    calls = []

    def fetch(q):
        calls.append(q)
        a = q.split("after:")[1].split()[0]
        b = q.split("before:")[1]
        days = (date.fromisoformat(b) - date.fromisoformat(a)).days
        return [{}] * (100 if days > 8 else 10)  # capped until the window is 8 days or less

    got = H.fetch_adaptive(fetch, "q", date(2025, 1, 1), date(2025, 2, 1), H.Budget(100))
    assert len(calls) == 1 + 2 + 4  # 31 days -> 15+16 -> four windows of about a week
    assert len(got) == 40


def test_scan_stops_after_empty_months(monkeypatch):
    monkeypatch.setattr(C, "HISTORY_FLOOR", "2025-10-01")
    monkeypatch.setattr(C, "HISTORY_STOP_AFTER_EMPTY", 2)
    monkeypatch.setattr(C, "HISTORY_QUERIES", ["q"])
    monkeypatch.setattr(C, "HISTORY_2026_QUERIES", [])

    def fetch(q):
        a = q.split("after:")[1].split()[0]
        return [{"published": a}] if a >= "2025-09-01" else []  # nothing before September

    raw, rep = H.scan(fetch, date(2026, 1, 2), keep=lambda r: True)
    # Dec, Nov, Oct (floor), Sep (found), Aug and Jul empty -> stop
    assert rep["months_scanned"] == 6
    assert rep["oldest_month_scanned"] == "2025-07"


def test_compute_firsts():
    hist = [
        {"title": "TVBS民調／六都市長滿意度出爐 蔣萬安墊底", "url": "u0", "source": "A", "published": "2023-01-01T00:00:00+00:00"},
        {"title": "蔣萬安拚2026連任 綠營誰出戰", "url": "u1", "source": "A", "published": "2023-02-01T00:00:00+00:00"},
        {"title": "曹興誠：應徵召沈伯洋選台北市長", "url": "u2", "source": "B", "published": "2025-11-12T00:00:00+00:00"},
    ]
    cur = [
        {"title": "民調：蔣萬安、沈伯洋支持度差距縮小", "url": "u3", "source": "C", "published": "2026-06-01T00:00:00+00:00"},
        {"title": "蔣萬安視察捷運", "url": "u4", "source": "D", "published": "2026-02-01T00:00:00+00:00"},
    ]
    f = H.compute_firsts(hist, cur)
    by = {x["key"]: x for x in f["firsts"]}
    assert by["earliest"]["url"] == "u1"      # the satisfaction poll is not a clear race story
    assert f["monthly"]["2023-01"]["total"] == 1  # but it still counts as race coverage
    assert by["chiang_2026"]["url"] == "u1"
    assert by["shen_mayor"]["url"] == "u2"
    assert by["matchup"]["url"] == "u3" and by["matchup_poll"]["url"] == "u3"
    assert "2026-02" not in f["monthly"]  # ordinary city news is not counted as race coverage
    assert f["monthly"]["2026-06"]["both"] == 1
