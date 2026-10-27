"""Keyword lists and source settings for the Taipei 2026 mayoral race monitor.

Everything the rule-based classifier relies on lives here, so the lists can be
reviewed and corrected without touching the logic.
"""

START_DATE = "2026-01-01"

# ---------------------------------------------------------------- candidates
# Each candidate has aliases that identify them in a headline, plus "side"
# terms (campaign office, administration) that speak for them.
CANDIDATES = {
    "蔣萬安": {
        "aliases": ["蔣萬安", "蔣市長"],
        "side": ["蔣競辦", "蔣萬安競辦", "蔣陣營", "蔣營", "北市府", "台北市府", "臺北市府", "市府團隊"],
    },
    "沈伯洋": {
        "aliases": ["沈伯洋", "Puma", "puma"],
        "side": ["沈競辦", "沈伯洋競辦", "沈陣營", "沈營"],
    },
}

# Phrases that contain an alias but are about something else.
FALSE_POSITIVES = ["萬安演習"]

# ------------------------------------------------------------- attack words
ATTACK_VERBS = [
    "抹黑", "造謠", "打臉", "砲轟", "炮轟", "痛批", "狠批", "怒批", "反批", "開砲", "開嗆",
    "嗆", "轟", "酸", "批", "諷", "譏", "嘲", "質疑", "指控", "踢爆", "爆料", "出征",
    "圍剿", "撻伐", "說謊", "謊言", "翻車", "要求道歉", "抓包", "打假", "戳破",
]
PASSIVE_MARKERS = ["遭", "被", "挨"]
DEFENSE_VERBS = ["駁斥", "澄清", "闢謠", "回應", "回擊", "反擊", "喊冤", "提告", "嚴正"]

# ------------------------------------------------------------ attacker camps
# Matched against the part of the headline before the attack verb.
CAMPS = {
    "藍營": [
        "國民黨", "藍委", "藍營", "藍議員", "徐巧芯", "羅智強", "王鴻薇", "柳采葳", "游淑慧",
        "陳菁徽", "賴苡任", "殷瑋", "楊沛緰", "魏汶萱", "傅崐萁", "鄭麗文", "李彥秀", "戴錫欽",
    ],
    "綠營": [
        "民進黨", "綠委", "綠營", "綠議員", "林俊憲", "王定宇", "吳思瑤", "簡舒培", "洪健益",
        "林延鳳", "鍾佩玲", "吳崢", "賴清德", "徐國勇", "卓榮泰", "王世堅", "曹興誠", "吳沛憶",
    ],
    "白營": ["民眾黨", "黃國昌", "黃珊珊", "柯文哲", "陳智菡"],
    "境外官方": ["國台辦", "中共", "陸方", "中國官方", "央視", "新華社", "環球時報", "公安"],
    "名嘴與節目": ["名嘴", "主持人", "政論", "戰情室", "節目"],
    "網友與粉專": ["網友", "網紅", "粉專", "鄉民", "Threads", "脆友", "PTT", "側翼"],
}
# When a candidate criticises someone who is not named as the other candidate,
# the headline only counts as an attack on that candidate if these party or
# side words appear after the attack verb. Otherwise it is "其他批評".
IMPLIED_TARGET = {
    "蔣萬安": ["國民黨", "藍營", "藍委", "藍白", "北市府", "市府", "市政府", "蔣市府"],
    "沈伯洋": ["民進黨", "綠營", "綠委", "沈陣營", "沈競辦"],
}

# Section labels Google News appends to some titles.
TITLE_SUFFIXES = r"(政治|生活|社會|即時|要聞|焦點|地方|國際|財經|2026九合一選舉|九合一選舉|選舉|新聞)"

# A candidate (or their side) speaking first counts as that candidate's camp.
CANDIDATE_CAMP = {"蔣萬安": "藍營", "沈伯洋": "綠營"}

# ---------------------------------------------------------------- topics
TOPICS = {
    "毒品政策": ["毒品", "美沙冬", "減害", "針頭"],
    "食安／營養午餐": ["營養午餐", "食安", "食物中毒", "小卷", "毒油", "油品"],
    "家世／身世": ["改姓", "章孝嚴", "DNA", "身世", "蔣家", "沈父", "父親", "爺爺", "家族"],
    "子女": ["兒子", "交換學生", "交換生", "蔣得立"],
    "學經歷": ["學歷", "博士", "碩士", "賓州", "律師", "履歷", "經歷"],
    "國安／兩岸": ["國台辦", "中共", "統戰", "認知作戰", "雙城論壇", "中配", "陸配", "通緝", "跟監"],
    "民調": ["民調", "支持度", "看好度"],
    "辯論": ["辯論", "政見發表"],
    "颱風／災害": ["颱風", "停班", "停課", "淹水", "撿樹枝"],
    "交通／建設": ["捷運", "交通", "塞車", "大巨蛋", "內湖", "松機", "北士科", "輝達"],
    "市政管理": ["鼠患", "老鼠", "砍樹", "路樹", "吸菸區", "無菸"],
    "網軍／假帳號": ["網軍", "假帳號", "洗版", "小帳", "側翼"],
}

# ---------------------------------------------------------------- layers
FACTCHECK_DOMAINS = ["tfc-taiwan.org.tw", "mygopen.com", "cofacts.tw"]
FORUM_DOMAINS = ["ptt.cc", "dcard.tw", "threads.net", "threads.com"]
OVERSEAS_SOURCES = ["新華網", "人民網", "中國台灣網", "環球網", "央視", "華夏經緯網", "中新網", "台海網", "海峽之聲"]
SHOW_WORDS = ["節目", "戰情室", "直播", "Podcast", "podcast", "YouTube", "街訪", "政論", "頻道"]

# ---------------------------------------------------------------- sources
GOOGLE_NEWS_QUERIES = ["蔣萬安", "沈伯洋", "蔣萬安 沈伯洋", "台北市長 選舉"]
GOOGLE_NEWS_URL = "https://news.google.com/rss/search?q={q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"

RSS_FEEDS = {
    "台灣事實查核中心": "https://tfc-taiwan.org.tw/feed/",
    "MyGoPen": "https://www.mygopen.com/feeds/posts/default?alt=rss",
    "PTT 八卦板": "https://www.ptt.cc/atom/Gossiping.xml",
    "PTT 政黑板": "https://www.ptt.cc/atom/HatePolitics.xml",
}

COFACTS_GRAPHQL = "https://api.cofacts.tw/graphql"

USER_AGENT = "taipei-2026-election-monitor-claude/1.0 (+https://github.com/charleslin2003-prog/taipei-2026-election-monitor-claude)"

# ---------------------------------------------------------------- history
# News before START_DATE is kept only when it is about the 2026 race. The
# history pass searches month by month back to HISTORY_FLOOR (the day after
# 蔣萬安 won in 2022, when talk of a 2026 re-election could begin), then keeps
# going further back until HISTORY_STOP_AFTER_EMPTY months in a row find
# nothing, never earlier than HISTORY_HARD_FLOOR.
HISTORY_FLOOR = "2022-11-27"
HISTORY_HARD_FLOOR = "2019-01-01"
HISTORY_STOP_AFTER_EMPTY = 6
HISTORY_QUERIES = [
    "蔣萬安 連任", "蔣萬安 2026", "台北市長 2026", "2026 台北市長 民進黨",
    "沈伯洋 台北市長", "沈伯洋 市長",
]
# In 2026 the generic queries hit Google's ~100-results cap every week; these
# narrower election queries are re-run with window splitting during a history
# pass so election stories in busy weeks are not lost.
HISTORY_2026_QUERIES = ["蔣萬安 沈伯洋", "台北市長 選舉", "沈伯洋 參選", "蔣萬安 連任"]
# A window that returns at least this many items is assumed capped and split.
RESULT_CAP = 95
HISTORY_MAX_REQUESTS = 1500
# Words that make a pre-2026 headline about the 2026 race.
ELECTION_TERMS = [
    "2026", "連任", "參選", "選舉", "選戰", "民調", "提名", "徵召", "人選", "對手", "出戰",
    "挑戰者", "大選", "九合一", "母雞", "市長選", "接班", "競選", "選情", "藍綠", "對決",
]
