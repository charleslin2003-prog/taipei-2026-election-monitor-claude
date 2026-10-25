"""Headline cases taken from real 2026 coverage. Run: python -m pytest -q"""
import pytest

from scraper.classify import classify, factcheck_verdict, is_relevant, layer

CASES = [
    # (headline, kind, target, attacker)
    ("沈伯洋談股市與停班課脫鉤 蔣萬安競辦嗆：搞錯權責「出洋相」", "攻擊", "沈伯洋", "藍營"),
    ("反毒論戰…蔣萬安轟「偷換概念」 沈伯洋反批汙名化第一線", "攻擊", "沈伯洋", "藍營"),
    ("徐巧芯酸他出戰北市拯救藍營大選 沈伯洋:那也是功德一件", "攻擊", "沈伯洋", "藍營"),
    ("綠控金華國中集體食物中毒 陳菁徽批沈伯洋認知作戰蹭食安", "攻擊", "沈伯洋", "藍營"),
    ("蔣萬安遭綠委質疑油品零抽驗", "攻擊", "蔣萬安", "綠營"),
    ("國台辦再批沈伯洋：百般狡辯", "攻擊", "沈伯洋", "境外官方"),
    ("遭指動員學生替競總打掃！蔣萬安競辦駁斥：是教練主動帶學生幫忙", "澄清回應", "蔣萬安", None),
    ("TVBS最新民調公布 蔣萬安支持度49%、沈伯洋41%", "一般報導", None, None),
    # Criticism aimed at someone other than the rival candidate
    ("拖吊10萬太荒謬！蔣萬安痛批「拖吊流氓」 研議作業指引重罰", "其他批評", None, None),
    ("選民擔憂「選後失望」 沈伯洋：會努力維持初衷請用力批評", "其他批評", None, None),
    ("中國曝光沈伯洋住家衛星照！麥玉珍批：違反人權、無助兩岸關係", "其他批評", None, None),
    # Party named after the verb implies the rival candidate's camp
    ("朱政騏涉共諜案蔣萬安酸：整天抗中保台卻一直養共諜就是民進黨", "攻擊", "沈伯洋", "藍營"),
    # Speaker introduced after a colon
    ("批沈伯洋「只監督蔣萬安、不批食藥署」民眾黨：乾脆選議員", "攻擊", "沈伯洋", "白營"),
    ("側翼批沈伯洋不適合選台北 他酸：怕輸太慘", "攻擊", "沈伯洋", "網友與粉專"),
    ("點名蔣萬安是2028最佳人選吳子嘉曝關鍵優勢：台灣會不一樣", "一般報導", None, None),
]


@pytest.mark.parametrize("title,kind,target,attacker", CASES)
def test_headlines(title, kind, target, attacker):
    c = classify(title)
    assert c["kind"] == kind
    assert c["target"] == target
    if attacker:
        assert c["attacker"] == attacker


def test_relevance_skips_drill():
    assert not is_relevant("萬安演習今日登場 北市防空疏散")
    assert is_relevant("蔣萬安出席萬安演習")


def test_layers():
    assert layer("台灣事實查核中心", "https://tfc-taiwan.org.tw/x", "t") == "查核機構"
    assert layer("PTT 八卦板", "https://www.ptt.cc/bbs/Gossiping/M.1.html", "t") == "論壇與社群"
    assert layer("自由時報", "https://news.google.com/x", "少康戰情室專訪沈伯洋") == "網路／政論節目"
    assert layer("聯合新聞網", "https://news.google.com/x", "一般新聞") == "主流媒體"


def test_section_suffix_removed():
    from scraper.classify import display_title
    assert display_title("沈伯洋5問蔣萬安殷瑋酸「問A答B」- 政治") == "沈伯洋5問蔣萬安殷瑋酸「問A答B」"
    assert display_title("傅崐萁喊普發3萬元| 2026九合一選舉") == "傅崐萁喊普發3萬元"


def test_verdict():
    assert factcheck_verdict("【錯誤】網傳沈伯洋名下三公司遭懲戒") == "錯誤"
    assert factcheck_verdict("網傳某某", ["政治與政策", "錯誤"]) == "錯誤"
