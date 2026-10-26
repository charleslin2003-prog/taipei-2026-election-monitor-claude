"use strict";
const POLL_MS = 60 * 1000;          // check meta.json this often while the tab is visible
const STALE_SOURCE_MS = 2 * 3600 * 1000;
const PAGE = 50;
const CANDS = ["蔣萬安", "沈伯洋"];
const CC = { 蔣萬安: ["var(--chiang)", "var(--chiang-soft)"], 沈伯洋: ["var(--shen)", "var(--shen-soft)"], 不明: ["var(--neutral)", "var(--neu-bg)"] };
const TONE = {
  bad: ["錯誤", "部分錯誤", "含有不實訊息", "曲解／斷章", "指控不成立", "謠言", "詐騙", "失敗"],
  warn: ["誤導", "易誤解", "證據不足", "部分屬實", "爭議中", "程序爭議", "無證據", "誇大爭議", "含有個人意見", "部分失敗"],
  ok: ["正確", "含有正確訊息", "事實釐清", "屬實", "已澄清", "正常"],
};
const TONE_VARS = { bad: ["var(--bad)", "var(--bad-bg)"], warn: ["var(--warn)", "var(--warn-bg)"], ok: ["var(--ok)", "var(--ok-bg)"], neutral: ["var(--neutral)", "var(--neu-bg)"] };
const CAMPS = ["藍營", "綠營", "白營", "境外官方", "名嘴與節目", "網友與粉專", "不明"];
const FEED_FILTERS = ["q", "fTarget", "fKind", "fLayer", "fTopic", "fMention", "fSource", "fDays", "fFrom", "fTo", "fEdited"];

const state = { news: [], meta: {}, curated: { polls: [], attacks: [], factchecks: [], events: [] }, shown: PAGE, stamp: null, busy: false, lastRows: [] };
const $ = (id) => document.getElementById(id);

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function safeUrl(u) {
  try { const x = new URL(u); return (x.protocol === "https:" || x.protocol === "http:") && !x.username && !x.password ? x.href : "#"; } catch { return "#"; }
}
function link(u, text) { return `<a href="${esc(safeUrl(u))}" target="_blank" rel="noopener noreferrer">${esc(text)}</a>`; }
function tone(v) { for (const [k, list] of Object.entries(TONE)) if (list.includes(v)) return k; return "neutral"; }
function pill(v) { const [c, b] = TONE_VARS[tone(v)]; return `<span class="pill" style="--pc:${c};--pb:${b}">${esc(v)}</span>`; }
function tgt(t) { const [c, s] = CC[t] || CC["不明"]; return `<span class="tgt" style="--c:${c};--cs:${s}">${esc(t)}</span>`; }
function fmtDate(iso) {
  if (!iso) return "日期不明";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "日期不明";
  return d.toLocaleString("zh-TW", { timeZone: "Asia/Taipei", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
}
const dayFmt = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Taipei", year: "numeric", month: "2-digit", day: "2-digit" });
function taipeiDay(iso) { return iso ? dayFmt.format(new Date(iso)) : ""; }
function ago(iso) {
  const m = Math.round((Date.now() - new Date(iso)) / 60000);
  if (m < 1) return "剛剛";
  if (m < 60) return `${m} 分鐘前`;
  if (m < 1440) return `${Math.round(m / 60)} 小時前`;
  return `${Math.round(m / 1440)} 天前`;
}
function countBy(rows, key) { const g = {}; rows.forEach((r) => { const k = key(r); if (k != null) g[k] = (g[k] || 0) + 1; }); return g; }
const attacks = () => state.news.filter((n) => n.cls?.kind === "攻擊");

async function getJSON(path) {
  const r = await fetch(`${path}?t=${Date.now()}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`${path} 回應 ${r.status}`);
  return r.json();
}

// Fetch the small files every time; download the large news file only when
// meta.json says the data changed.
async function load() {
  if (state.busy) return;
  state.busy = true;
  try {
    const [meta, curated] = await Promise.all([getJSON("data/meta.json").catch(() => ({})), getJSON("data/curated.json")]);
    const changed = !state.stamp || (meta.updated_at && meta.updated_at !== state.stamp);
    if (changed) {
      const news = await getJSON("data/news.json").catch(() => state.news);
      if (!Array.isArray(news)) throw new Error("新聞資料格式錯誤");
      Object.assign(state, { news, meta, curated, stamp: meta.updated_at || "none" });
      renderAll();
    } else {
      const curatedChanged = JSON.stringify(curated) !== JSON.stringify(state.curated);
      Object.assign(state, { meta, curated });
      if (curatedChanged) { renderCurated(); renderFC(); renderPolls(); }
      renderLive();
    }
  } catch (e) {
    $("live").innerHTML = `<span class="dot stale"></span>無法取得最新資料：${esc(e.message)}。畫面上的內容可能已過期。`;
  } finally {
    state.busy = false;
  }
}

function renderCountdown() {
  const now = Date.now();
  const chips = (state.curated.events || []).map((e) => {
    const t = new Date(e.date).getTime();
    const days = Math.ceil((t - now) / 86400000);
    let txt;
    if (now >= t + 6 * 3600000) return "";
    if (now >= t) txt = "進行中";
    else if (days <= 1) txt = `${Math.max(1, Math.round((t - now) / 3600000))} 小時後`;
    else txt = `還有 <b class="mono">${days}</b> 天`;
    return `<a class="cd" href="${esc(safeUrl(e.url))}" target="_blank" rel="noopener noreferrer"><span>${esc(e.label)}</span><span class="mono">${esc(taipeiDay(e.date).slice(5).replace("-", "/"))}</span><span>${txt}</span></a>`;
  }).join("");
  $("countdown").innerHTML = chips;
  $("countdown").hidden = !chips;
}

function renderLive() {
  renderCountdown();
  const m = state.meta;
  if (!m.updated_at) { $("live").innerHTML = `<span class="dot stale"></span>尚未完成第一次自動抓取，目前只顯示人工審核資料。`; return; }
  const fresh = Date.now() - new Date(m.updated_at) < 90 * 60000;
  const chips = Object.entries(m.sources || {}).map(([name, h]) => {
    const stale = h.last_success_at && Date.now() - new Date(h.last_success_at) > STALE_SOURCE_MS;
    const cls = h.ok === true && !stale ? "ok" : h.ok === false ? "bad" : "partial";
    const tip = h.errors?.length ? h.errors[0] : h.last_success_at ? `上次成功 ${fmtDate(h.last_success_at)}` : "";
    return `<span class="chip ${cls}" title="${esc(tip)}"><i></i>${esc(name)} <span class="mono">${h.kept ?? 0}</span></span>`;
  }).join("");
  const notes = [];
  if (m.mode === "catch_up") notes.push(`<span class="warnline">上次抓取中斷較久，本次已自動補抓${m.window?.since ? "自 " + esc(m.window.since) : "近 " + esc(m.window?.when || "")}的新聞。</span>`);
  if (!fresh) notes.push(`<span class="warnline">超過 90 分鐘沒有更新，GitHub 排程可能延遲。</span>`);
  $("live").innerHTML = `<span class="dot${fresh ? "" : " stale"}"></span>最後更新 ${esc(ago(m.updated_at))}（${esc(fmtDate(m.updated_at))}）· 共 <span class="mono">${state.news.length}</span> 則 ${chips}${notes.join("")}`;
}

function renderTiles() {
  const a = attacks();
  const day = state.news.filter((n) => n.published && Date.now() - new Date(n.published) < 86400000).length;
  const edited = state.news.filter((n) => n.title_history?.length).length;
  const tiles = [
    [state.news.length, "2026 年相關報導", null],
    [a.length, "攻擊類報導", null],
    [a.filter((n) => n.cls.target === "蔣萬安").length, "攻擊蔣萬安", "蔣萬安"],
    [a.filter((n) => n.cls.target === "沈伯洋").length, "攻擊沈伯洋", "沈伯洋"],
    [day, "過去 24 小時發布", null],
    [edited, "標題曾被修改", "edited"],
  ];
  $("tiles").innerHTML = tiles.map(([n, l, go]) => go
    ? `<button type="button" class="tile" data-go="${go}"><b>${n}</b><span>${l} →</span></button>`
    : `<div class="tile"><b>${n}</b><span>${l}</span></div>`).join("");
}

function weekStart(d) { const x = new Date(d); const day = (x.getUTCDay() + 6) % 7; x.setUTCHours(0, 0, 0, 0); x.setUTCDate(x.getUTCDate() - day); return x; }

function renderTrend() {
  const a = attacks().filter((n) => n.published);
  if (!a.length) { $("trend").innerHTML = `<div class="empty">還沒有自動抓取的資料，第一次排程執行後就會出現趨勢圖。</div>`; return; }
  const start = weekStart("2026-01-01"), end = weekStart(new Date());
  const weeks = [];
  for (let d = new Date(start); d <= end; d.setUTCDate(d.getUTCDate() + 7)) weeks.push(new Date(d));
  const idx = new Map(weeks.map((w, i) => [w.getTime(), i]));
  const series = CANDS.map(() => weeks.map(() => 0));
  a.forEach((n) => { const ci = CANDS.indexOf(n.cls.target); const wi = idx.get(weekStart(n.published).getTime()); if (ci >= 0 && wi != null) series[ci][wi]++; });
  const max = Math.max(4, ...series.flat());
  const nice = Math.ceil(max / 4) * 4;
  const W = 1000, H = 240, L = 40, R = 12, T = 12, B = 28;
  const x = (i) => L + (weeks.length === 1 ? 0 : (i * (W - L - R)) / (weeks.length - 1));
  const y = (v) => T + (H - T - B) * (1 - v / nice);
  let g = "";
  for (let k = 0; k <= 4; k++) { const v = (nice / 4) * k; g += `<line class="gridline" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${v}</text>`; }
  let lastMonth = -1;
  weeks.forEach((w, i) => { const mth = new Date(w.getTime() + 3 * 86400000).getUTCMonth(); if (mth !== lastMonth) { lastMonth = mth; g += `<text x="${x(i)}" y="${H - 8}" text-anchor="middle">${mth + 1}月</text>`; } });
  const colors = ["var(--chiang)", "var(--shen)"];
  series.forEach((s, si) => {
    const pts = s.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
    g += `<polyline points="${pts}" fill="none" stroke="${colors[si]}" stroke-width="2"/>`;
    const li = s.length - 1;
    g += `<circle cx="${x(li)}" cy="${y(s[li])}" r="3.5" fill="${colors[si]}"/>`;
  });
  $("trend").innerHTML = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="每週攻擊類報導數折線圖">${g}</svg>`;
}

function renderHot() {
  const now = Date.now(), wk = 7 * 86400000;
  const cur = {}, prev = {};
  state.news.forEach((n) => {
    if (!n.published) return;
    const age = now - new Date(n.published);
    const bucket = age < wk ? cur : age < 2 * wk ? prev : null;
    if (bucket) (n.cls?.topics || []).forEach((t) => (bucket[t] = (bucket[t] || 0) + 1));
  });
  const entries = Object.entries(cur).sort((p, q) => q[1] - p[1]).slice(0, 8);
  const max = Math.max(1, ...entries.map((e) => e[1]));
  $("hot").innerHTML = entries.length ? entries.map(([t, n]) => {
    const p = prev[t] || 0, d = n - p;
    const delta = p === 0 ? `<span class="delta up">新</span>` : `<span class="delta ${d >= 0 ? "up" : "down"}">${d >= 0 ? "▲" : "▼"}${Math.abs(d)}</span>`;
    return `<button type="button" class="hbar hot" style="--c:var(--fg)" data-topic="${esc(t)}"><span>${esc(t)}</span><span class="track"><span style="width:${(n / max) * 100}%"></span></span><span class="mono">${n}</span>${delta}</button>`;
  }).join("") : `<div class="note">近 7 天沒有可歸類議題的報導。</div>`;
}

function renderMatrix() {
  const a = attacks();
  const cols = ["蔣萬安", "沈伯洋", "不明"];
  const cell = {};
  a.forEach((x) => { const k = `${x.cls.attacker || "不明"}|${x.cls.target}`; cell[k] = (cell[k] || 0) + 1; });
  const max = Math.max(1, ...Object.values(cell));
  const rows = CAMPS.map((camp) => {
    const cells = cols.map((t) => {
      const n = cell[`${camp}|${t}`] || 0;
      const col = (CC[t] || CC["不明"])[0];
      return `<td class="heat mono" style="--c:${col};--a:${(n / max * 0.45).toFixed(2)}">${n}</td>`;
    }).join("");
    return `<tr><td>${esc(camp)}</td>${cells}</tr>`;
  }).join("");
  $("matrix").innerHTML = `<div class="tablewrap" style="border:0"><table class="matrix"><thead><tr><th>發動陣營</th>${cols.map((c) => `<th>攻擊${esc(c)}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>`;
}

function hbars(groups, color) {
  const entries = Object.entries(groups).sort((p, q) => q[1] - p[1]).slice(0, 8);
  const max = Math.max(1, ...entries.map((e) => e[1]));
  if (!entries.length) return `<div class="note">尚無資料</div>`;
  return entries.map(([k, n]) => `<div class="hbar" style="--c:${color}"><span>${esc(k)}</span><span class="track"><span style="width:${(n / max) * 100}%"></span></span><span class="mono">${n}</span></div>`).join("");
}

function renderBreakdowns() {
  const a = attacks();
  const block = (fn) => CANDS.map((c) => `<div style="display:grid;gap:6px"><div>${tgt(c)} 被攻擊</div>${hbars(fn(a.filter((n) => n.cls.target === c)), CC[c][0])}</div>`).join("");
  $("layers").innerHTML = block((rows) => countBy(rows, (n) => n.cls.layer));
  $("topics").innerHTML = block((rows) => { const g = {}; rows.forEach((n) => (n.cls.topics || []).forEach((t) => (g[t] = (g[t] || 0) + 1))); return g; });
  const bySrc = {};
  a.forEach((n) => { const s = n.source || "不明"; bySrc[s] = bySrc[s] || { 蔣萬安: 0, 沈伯洋: 0, total: 0 }; if (bySrc[s][n.cls.target] != null) bySrc[s][n.cls.target]++; bySrc[s].total++; });
  const top = Object.entries(bySrc).sort((p, q) => q[1].total - p[1].total).slice(0, 10);
  $("outlets").innerHTML = top.length
    ? `<table class="matrix"><thead><tr><th>媒體</th><th>攻擊蔣萬安</th><th>攻擊沈伯洋</th></tr></thead><tbody>${top.map(([s, v]) => `<tr><td>${esc(s)}</td><td class="mono">${v.蔣萬安}</td><td class="mono">${v.沈伯洋}</td></tr>`).join("")}</tbody></table>`
    : `<div class="note">尚無資料</div>`;
}

function fillSelect(id, values, byCount = false) {
  const s = $(id), keep = s.value;
  [...s.querySelectorAll("option")].slice(1).forEach((o) => o.remove());
  const counts = countBy(values.filter(Boolean), (v) => v);
  const keys = Object.keys(counts).sort(byCount ? (a, b) => counts[b] - counts[a] : undefined);
  keys.forEach((v) => { const o = document.createElement("option"); o.value = v; o.textContent = byCount ? `${v}（${counts[v]}）` : v; s.appendChild(o); });
  s.value = keys.includes(keep) ? keep : "";
}

function newsCard(n) {
  const c = n.cls || {};
  const tags = [];
  if (c.kind === "攻擊") tags.push(`${tgt(c.target || "不明")}<span>被攻擊 · 發動：${esc(c.attacker || "不明")}</span>`);
  else if (c.kind === "澄清回應") tags.push(`${tgt(c.target || "不明")}<span>澄清回應</span>`);
  else if (c.kind === "其他批評") tags.push(`<span class="tag">其他批評</span>`);
  else tags.push(`<span class="tag">一般報導</span>`);
  if (n.verdict) tags.push(pill(n.verdict));
  (c.topics || []).forEach((t) => tags.push(`<span class="tag">${esc(t)}</span>`));
  const by = c.by === "llm" ? "模型分類" : `規則分類${c.confidence ? "（信心" + esc(c.confidence) + "）" : ""}`;
  const hist = n.title_history?.length
    ? `<details class="hist"><summary>${pill("標題曾修改")} ${n.title_history.length} 次</summary><ol>${n.title_history.map((h) => `<li><s>${esc(h.title)}</s><span class="auto"> 發現改動：${esc(fmtDate(h.replaced_at))}</span></li>`).join("")}</ol></details>`
    : "";
  return `<article><div class="t">${link(n.url, n.title)}</div>
    <div class="meta"><span>${esc(n.source)}</span><span>${esc(fmtDate(n.published))}</span><span class="tag">${esc(c.layer || "")}</span></div>
    <div class="meta">${tags.join("")}<span class="auto">${by}</span></div>${hist}</article>`;
}

function filteredNews() {
  const q = $("q").value.trim(), t = $("fTarget").value, k = $("fKind").value, l = $("fLayer").value, tp = $("fTopic").value;
  const mention = $("fMention").value, src = $("fSource").value, from = $("fFrom").value, to = $("fTo").value, edited = $("fEdited").checked;
  const days = +$("fDays").value;
  const since = days ? Date.now() - days * 86400000 : 0;
  const bad = Boolean(from && to && from > to);
  $("dateError").hidden = !bad;
  if (bad) return [];
  return state.news.filter((n) => {
    const c = n.cls || {};
    if (q && !(`${n.title} ${n.summary || ""} ${n.source} ${(n.title_history || []).map((h) => h.title).join(" ")}`.includes(q))) return false;
    if (t && c.target !== t) return false;
    if (k && c.kind !== k) return false;
    if (l && c.layer !== l) return false;
    if (tp && !(c.topics || []).includes(tp)) return false;
    if (src && n.source !== src) return false;
    if (edited && !n.title_history?.length) return false;
    if (mention) {
      const has = (x) => n.title.includes(x);
      if (mention === "both" ? !(has("蔣萬安") && has("沈伯洋")) : !has(mention)) return false;
    }
    if (since && (!n.published || new Date(n.published) < since)) return false;
    if (from || to) {
      const d = taipeiDay(n.published);
      if (!d || (from && d < from) || (to && d > to)) return false;
    }
    return true;
  });
}

function renderFeed() {
  const rows = filteredNews();
  state.lastRows = rows;
  $("feedCount").textContent = `符合 ${rows.length} 則`;
  $("csv").disabled = rows.length === 0;
  $("feed").innerHTML = rows.length ? rows.slice(0, state.shown).map(newsCard).join("") : `<div class="empty">${state.news.length ? "沒有符合條件的報導。可以放寬篩選；沒有收錄不代表沒有相關新聞。" : "還沒有自動抓取的資料，第一次排程執行後就會出現。"}</div>`;
  $("more").hidden = rows.length <= state.shown;
}

function exportCSV() {
  // A leading = + - @ makes spreadsheets run the cell as a formula; prefix it.
  const cell = (v) => { let s = String(v ?? ""); if (/^[=+\-@\t\r]/.test(s)) s = "'" + s; return `"${s.replace(/"/g, '""')}"`; };
  const head = ["發布時間（台北）", "媒體", "標題", "類型", "被攻擊方", "發動陣營", "議題", "來源類型", "分類方式", "信心", "舊標題", "連結"];
  const rows = state.lastRows.map((n) => {
    const c = n.cls || {};
    return [fmtDate(n.published), n.source, n.title, c.kind, c.target || "", c.attacker || "", (c.topics || []).join("、"), c.layer, c.by === "llm" ? "模型" : "規則", c.confidence || "",
      (n.title_history || []).map((h) => h.title).join(" ／ "), n.url];
  });
  const csv = "﻿" + [head, ...rows].map((r) => r.map(cell).join(",")).join("\r\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url; a.download = `taipei-2026-news-${taipeiDay(new Date().toISOString())}.csv`;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function renderCurated() {
  const A = state.curated.attacks || [];
  fillSelect("cLayer", A.map((a) => a.layer));
  fillSelect("cStatus", A.map((a) => a.status));
  const t = $("cTarget").value, l = $("cLayer").value, s = $("cStatus").value;
  const rows = A.filter((a) => (!t || a.target === t) && (!l || a.layer === l) && (!s || a.status === s));
  $("curCount").textContent = `顯示 ${rows.length} / ${A.length} 則`;
  $("curBody").innerHTML = rows.map((a) => `<tr><td class="nowrap mono">${esc(a.date)}</td><td>${tgt(a.target)}</td><td>${esc(a.actor)}</td><td class="layer">${esc(a.layer)}</td><td>${esc(a.claim)}</td><td class="resp">${a.response ? esc(a.response) : '<span class="auto">未見回應</span>'}</td><td>${pill(a.status)}</td><td class="src">${link(a.url, "來源")}</td></tr>`).join("");
}

function renderFC() {
  const F = state.curated.factchecks || [];
  fillSelect("gCat", F.map((f) => f.category));
  const c = $("gCand").value, k = $("gCat").value;
  const rows = F.filter((f) => (!c || f.candidate === c) && (!k || f.category === k));
  $("fcCount").textContent = `顯示 ${rows.length} / ${F.length} 項`;
  $("fcBody").innerHTML = rows.map((f) => `<tr><td>${tgt(f.candidate)}</td><td class="nowrap">${esc(f.category)}</td><td>${esc(f.claim)}</td><td>${pill(f.verdict)}</td><td>${esc(f.basis)}</td><td class="src">${link(f.url, "來源")}</td></tr>`).join("");
  const auto = state.news.filter((n) => n.cls?.layer === "查核機構").slice(0, 40);
  $("fcFeed").innerHTML = auto.length ? auto.map(newsCard).join("") : `<div class="empty">目前沒有自動收錄的查核文章。</div>`;
}

function renderPolls() {
  const P = [...(state.curated.polls || [])].sort((a, b) => a.date.localeCompare(b.date));
  $("poll").innerHTML = P.map((p) => `<div class="prow"><div class="plabel"><b>${link(p.url, p.name)}</b>${esc(p.date)}${p.note ? " · " + esc(p.note) : ""}　差距 <span class="mono">${Math.abs(p.chiang - p.shen).toFixed(1)}</span></div>
    <div class="bars">${[["蔣萬安", p.chiang], ["沈伯洋", p.shen]].map(([k, v]) => `<div class="bar${p.scientific ? "" : " dim"}" style="--c:${CC[k][0]}"><span class="fill" style="width:calc(${(v / 60) * 100}% - 50px)"></span><span class="mono">${v}%</span></div>`).join("")}</div></div>`).join("");
}

function renderHealth() {
  const m = state.meta;
  const rows = Object.entries(m.sources || {}).map(([name, h]) => {
    const st = h.ok === true ? "正常" : h.ok === "partial" ? "部分失敗" : "失敗";
    const calls = h.calls ? `${h.calls - (h.failed_calls || 0)}／${h.calls}` : "";
    return `<tr><td>${esc(name)}</td><td>${pill(st)}</td><td class="mono">${esc(calls)}</td><td class="mono">${h.fetched ?? 0}</td><td class="mono">${h.kept ?? 0}</td><td class="nowrap">${esc(h.last_success_at ? fmtDate(h.last_success_at) : "—")}</td><td>${esc((h.errors || [])[0] || "")}</td></tr>`;
  }).join("");
  const llm = m.llm?.enabled ? `模型分類：已啟用，本次標註 ${m.llm.labelled} 則。` : "模型分類：未啟用（使用規則分類）。";
  const edits = m.headline_edited_total != null ? `目前有 ${m.headline_edited_total} 則新聞偵測到標題修改。` : "";
  $("health").innerHTML = rows
    ? `<div class="tablewrap"><table class="ledger" style="min-width:680px"><thead><tr><th>來源</th><th>狀態</th><th>成功請求</th><th>抓到</th><th>相關</th><th>上次成功</th><th>錯誤訊息</th></tr></thead><tbody>${rows}</tbody></table></div><p class="note">${esc(llm)}${esc(edits)}</p>`
    : `<p class="note">尚未執行過自動抓取。</p>`;
}

function renderAll() {
  renderLive(); renderTiles(); renderTrend(); renderHot(); renderMatrix(); renderBreakdowns();
  fillSelect("fLayer", state.news.map((n) => n.cls?.layer));
  fillSelect("fTopic", state.news.flatMap((n) => n.cls?.topics || []));
  fillSelect("fSource", state.news.map((n) => n.source), true);
  renderFeed(); renderCurated(); renderFC(); renderPolls(); renderHealth();
}

FEED_FILTERS.forEach((id) => $(id).addEventListener(id === "q" ? "input" : "change", () => { state.shown = PAGE; renderFeed(); }));
["cTarget", "cLayer", "cStatus"].forEach((id) => $(id).addEventListener("change", renderCurated));
["gCand", "gCat"].forEach((id) => $(id).addEventListener("change", renderFC));
$("more").addEventListener("click", () => { state.shown += PAGE; renderFeed(); });
$("csv").addEventListener("click", exportCSV);
function resetFeed() { FEED_FILTERS.forEach((id) => { const el = $(id); if (el.type === "checkbox") el.checked = false; else el.value = ""; }); state.shown = PAGE; }
$("reset").addEventListener("click", () => { resetFeed(); renderFeed(); });

const tabs = [...document.querySelectorAll("nav.tabs button")];
function show(p) {
  tabs.forEach((b) => { const on = b.dataset.p === p; b.setAttribute("aria-selected", on); $("p-" + b.dataset.p).hidden = !on; });
}
tabs.forEach((b) => b.addEventListener("click", () => { show(b.dataset.p); history.replaceState(null, "", "#" + b.dataset.p); }));
function openFeed(apply) { resetFeed(); apply(); renderFeed(); show("feed"); history.replaceState(null, "", "#feed"); $("p-feed").scrollIntoView({ block: "start" }); }
$("tiles").addEventListener("click", (e) => {
  const b = e.target.closest("[data-go]"); if (!b) return;
  openFeed(() => { if (b.dataset.go === "edited") $("fEdited").checked = true; else { $("fTarget").value = b.dataset.go; $("fKind").value = "攻擊"; } });
});
$("hot").addEventListener("click", (e) => {
  const b = e.target.closest("[data-topic]"); if (!b) return;
  openFeed(() => { $("fTopic").value = b.dataset.topic; $("fDays").value = "7"; });
});
const initial = location.hash.slice(1);
show(tabs.some((b) => b.dataset.p === initial) ? initial : "overview");

load();
setInterval(() => { if (!document.hidden) load(); else renderLive(); }, POLL_MS);
document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });
