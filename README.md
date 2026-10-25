# 台北市長選戰查核台（Claude 版）

2026 台北市長選舉（蔣萬安 vs 沈伯洋）的新聞攻防與事實查核平台。GitHub Actions 每 30 分鐘抓取新聞、論壇與查核機構文章，依標題自動分類「誰在攻擊誰」，再部署到 GitHub Pages。

網站：https://charleslin2003-prog.github.io/taipei-2026-election-monitor-claude/

## 功能

- **總覽**：每週攻擊類報導趨勢、發動陣營 × 被攻擊方矩陣、來源類型、議題、刊登媒體排行
- **即時新聞**：2026/1/1 以來的相關報導，可依被攻擊方、類型、來源類型、議題、期間與關鍵字篩選
- **人工審核攻防**：逐則檢視過的攻擊紀錄與查核狀態
- **個資查核**：學歷、經歷、家世、公開發言的查核結論與依據，以及查核機構的最新文章
- **民調**：各機構民調對照
- **方法**：各資料源的抓取狀態與錯誤訊息

## 架構

```
GitHub Actions（每 30 分鐘）
  └─ scraper/run.py
       ├─ sources.py   Google 新聞 RSS、台灣事實查核中心、MyGoPen、PTT、Cofacts
       ├─ classify.py  規則分類：攻擊／澄清回應／一般報導、被攻擊方、發動陣營、議題、來源類型
       └─ llm.py       （選用）Claude API 重新標註
  └─ data/news.json、data/meta.json  → commit 回 repo
  └─ web/ + data/  → GitHub Pages
```

`data/curated.json` 是人工審核資料（民調、攻擊紀錄、個資查核），不會被程式覆寫。

## 本機執行

```bash
pip install -r requirements.txt
python -m pytest -q              # 分類規則測試
python -m scraper.run            # 抓取近兩天
python -m scraper.run --backfill # 回補 2026/1/1 以來（每週一個區間）
python -m scraper.run --offline  # 不連網，只用新規則重新分類現有資料
python -m http.server -d . 8000  # 再開 http://localhost:8000/web/ （需把 data/ 放在 web/ 旁，或直接看 Pages）
```

## 設定

1. **啟用 Pages**：Settings → Pages → Source 選「GitHub Actions」。
2. **回補歷史資料**：Actions → Update data and deploy → Run workflow，勾選「回補」。
3. **（選用）模型分類**：Settings → Secrets and variables → Actions，新增 `ANTHROPIC_API_KEY`。每次執行最多重新標註 300 則（`LLM_PER_RUN` 可調），規則判為攻擊或澄清的標題優先，可用 `CLAUDE_MODEL` 環境變數換模型。

## 調整分類規則

關鍵字都在 `scraper/config.py`：候選人別名、攻擊用字、各陣營人名、議題詞。改完後在 `tests/test_classify.py` 加入真實標題當測試案例，再跑 `python -m scraper.run --offline` 重新分類。

## 新增人工審核資料

編輯 `data/curated.json`，每筆都要附來源連結。查核結論優先採用 IFCN 認證機構（台灣事實查核中心、MyGoPen）、Cofacts 與官方文件；只有當事人說法的標為「單方澄清」。

## 限制

- 自動分類只看標題字詞，會誤判反諷、雙向互批與多人新聞。人工抽查 25 則攻擊類報導，規則分類判斷被攻擊方正確約 6 成；建議設定 `ANTHROPIC_API_KEY` 啟用模型分類。
- Google 新聞每次查詢最多約 100 則，回補覆蓋率不是 100%。
- YouTube、Podcast、Threads、Dcard 沒有穩定的公開資料源，只收錄被新聞或查核機構記錄的部分。
- 媒體刊登量受各家立場與選題影響，數量差異不代表攻擊強度。

本專案整理公開報導與事實查核機構資料，不代表任何政黨或候選人立場。
