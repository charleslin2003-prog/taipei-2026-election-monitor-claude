"use strict";
const REFRESH_MS = 5 * 60 * 1000;
const PAGE = 50;
const CANDS = ["蔣萬安", "沈伯洋"];
const CC = { 蔣萬安: ["var(--chiang)", "var(--chiang-soft)"], 沈伯洋: ["var(--shen)", "var(--shen-soft)"], 不明: ["var(--neutral)", "var(--neu-bg)"] };
const TONE = {
  bad: ["錯誤", "部分錯誤", "含有不實訊息", "曲解／斷章", "指控不成立", "謠言", "詐騙"],
  warn: ["誤導", "易誤解", "證據不足", "部分屬實", "爭議中", "程序爭議", "無證據", "誇大爭議", "含有個人意見"],
  ok: ["正確", "含有正確訊息", "事實釐清", "屬實", "已澄清"],
};
const TONE_VARS = { bad: ["var(--bad)", "var(--bad-bg)"], warn: ["var(--warn)", "var(--warn-bg)"], ok: ["var(--ok)", "var(--ok-bg)"], neutral: ["var(--neutral)", "var(--neu-bg)"] };
const CAMPS = ["藍營", "綠營", "白營", "境外官方", "名嘴與節目", "網友與粉專", "不明"];

const state = { news: [], meta: {}, curated: { polls: [], attacks: [], factchecks: [] }, shown: PAGE, stamp: null };
const $ = (id) => document.getElementById(id);

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function safeUrl(u) { return /^https?:\/\//i.test(u || "") ? u : "#"; }
function link(u, text) { return `<a href="${esc(safeUrl(u))}" target="_blank" rel="noopener">${esc(text)}</a>`; }
function tone(v) { for (const [k, list] of Object.entries(TONE)) if (list.includes(v)) return k; return "neutral"; }
function pill(v) { const [c, b] = TONE_VARS[tone(v)]; return `<span class="pill" style="--pc:${c};--pb:${b}">${esc(v)}</span>`; }
function tgt(t) { const [c, s] = CC[t] || CC["不明"]; return `<span class="tgt" style="--c:${c};--cs:${s}">${esc(t)}</span>`; }
function fmtDate(iso) {
  if (!iso) return "日期不明";
  const d = new Date(iso);
  return d.toLocaleString("zh-TW", { timeZone: "Asia/Taipei", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
}
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
  if (!r.ok) throw new Error(`${path} ${r.status}`);
  return r.json();
}

async function load() {
  try {
    const [news, meta, curated] = await Promise.all([
      getJSON("data/news.json").catch(() => []),
      getJSON("data/meta.json").catch(() => ({})),
      getJSON("data/curated.json"),
    ]);
    if (meta.updated_at && meta.updated_at === state.stamp) return renderLive();
    Object.assign(state, { news, meta, curated, stamp: meta.updated_at || null });
    renderAll();
  } catch (e) {
    $("live").innerHTML = `<span class="dot stale"></span>資料載入失敗：${esc(e.message)}。請稍後重新整理。`;
  }
}

function renderLive() {
  const m = state.meta;
  if (!m.updated_at) { $("live").innerHTML = `<span class="dot stale"></span>尚未完成第一次自動抓取，目前只顯示人工審核資料。`; return; }
  const fresh = Date.now() - new Date(m.updated_at) < 90 * 60000;
  const chips = Object.entries(m.sources || {}).map(([name, h]) => {
    const cls = h.ok === true ? "ok" : h.ok === "partial" ? "partial" : "bad";
    const tip = h.errors?.length ? ` title="${esc(h.errors[0])}"` : "";
    return `<span class="chip ${cls}"${tip}><i></i>${esc(name)} <span class="mono">${h.kept ?? 0}</span></span>`;
  }).join("");
  $("live").innerHTML = `<span class="dot${fresh ? "" : " stale"}"></span>最後更新 ${esc(ago(m.updated_at))}（${esc(fmtDate(m.updated_at))}）· 共 <span class="mono">${state.news.length}</span> 則 ${chips}`;
}

function renderTiles() {
  const a = attacks();
  const day = state.news.filter((n) => n.first_seen && Date.now() - new Date(n.first_seen) < 86400000).length;
  const tiles = [
    [state.news.length, "2026 年相關報導"],
    [a.length, "攻擊類報導"],
    [a.filter((n) => n.cls.target === "蔣萬安").length, "攻擊蔣萬安"],
    [a.filter((n) => n.cls.target === "沈伯洋").length, "攻擊沈伯洋"],
    [state.news.filter((n) => n.cls?.layer === "查核機構").length, "查核機構文章"],
    [day, "過去 24 小時新增"],
  ];
  $("tiles").innerHTML = tiles.map(([n, l]) => `<div class="tile"><b>${n}</b><span>${l}</span></div>`).join("");
}

function weekStart(d) { const x = new Date(d); const day = (x.getUTCDay() + 6) % 7; x.setUTCHours(0, 0, 0, 0); x.setUTCDate(x.getUTCDate() - day); return x; }

function renderTrend() {
  const a = attacks().filter((n) => n.published);
  if (!a.length) { $("trend").innerHTML = `<div class="empty">還沒有自動抓取的資料，第一次排程執行後就會出現趨勢圖。</div>`; return; }
  const start = weekStart("2026-01-01"), end = weekStart(new Date());
  const weeks = [];
  for (let d = new Date(start); d <= end; d.setUTCDate(d.getUTCDate() + 7)) weeks.push(new Date(d));
  const series = CANDS.map((c) => weeks.map((w) => a.filter((n) => n.cls.target === c && weekStart(n.published).getTime() === w.getTime()).length));
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

function renderMatrix() {
  const a = attacks();
  const cols = ["蔣萬安", "沈伯洋", "不明"];
  const max = Math.max(1, ...CAMPS.flatMap((c) => cols.map((t) => a.filter((n) => (n.cls.attacker || "不明") === c && n.cls.target === t).length)));
  const rows = CAMPS.map((camp) => {
    const cells = cols.map((t) => {
      const n = a.filter((x) => (x.cls.attacker || "不明") === camp && x.cls.target === t).length;
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

function fillSelect(id, values) {
  const s = $(id), keep = s.value;
  [...s.querySelectorAll("option")].slice(1).forEach((o) => o.remove());
  [...new Set(values.filter(Boolean))].sort().forEach((v) => { const o = document.createElement("option"); o.textContent = v; s.appendChild(o); });
  s.value = keep;
}

function newsCard(n) {
  const c = n.cls || {};
  const tags = [];
  if (c.kind === "攻擊") tags.push(`${tgt(c.target || "不明")}<span>被攻擊 · 發動：${esc(c.attacker || "不明")}</span>`);
  else if (c.kind === "澄清回應") tags.push(`${tgt(c.target || "不明")}<span>澄清回應</span>`);
  else tags.push(`<span class="tag">一般報導</span>`);
  if (n.verdict) tags.push(pill(n.verdict));
  (c.topics || []).forEach((t) => tags.push(`<span class="tag">${esc(t)}</span>`));
  const by = c.by === "llm" ? "模型分類" : `規則分類${c.confidence ? "（信心" + esc(c.confidence) + "）" : ""}`;
  return `<article><div class="t">${link(n.url, n.title)}</div>
    <div class="meta"><span>${esc(n.source)}</span><span>${esc(fmtDate(n.published))}</span><span class="tag">${esc(c.layer || "")}</span></div>
    <div class="meta">${tags.join("")}<span class="auto">${by}</span></div></article>`;
}

function filteredNews() {
  const q = $("q").value.trim(), t = $("fTarget").value, k = $("fKind").value, l = $("fLayer").value, tp = $("fTopic").value, days = +$("fDays").value;
  const since = days ? Date.now() - days * 86400000 : 0;
  return state.news.filter((n) => {
    const c = n.cls || {};
    if (q && !(`${n.title} ${n.summary} ${n.source}`.includes(q))) return false;
    if (t && c.target !== t) return false;
    if (k && c.kind !== k) return false;
    if (l && c.layer !== l) return false;
    if (tp && !(c.topics || []).includes(tp)) return false;
    if (since && (!n.published || new Date(n.published) < since)) return false;
    return true;
  });
}

function renderFeed() {
  const rows = filteredNews();
  $("feedCount").textContent = `符合 ${rows.length} 則`;
  $("feed").innerHTML = rows.length ? rows.slice(0, state.shown).map(newsCard).join("") : `<div class="empty">${state.news.length ? "沒有符合條件的報導，試著放寬篩選。" : "還沒有自動抓取的資料，第一次排程執行後就會出現。"}</div>`;
  $("more").hidden = rows.length <= state.shown;
}

function renderCurated() {
  const A = state.curated.attacks || [];
  fillSelect("cLayer", A.map((a) => a.layer));
  fillSelect("cStatus", A.map((a) => a.status));
  const t = $("cTarget").value, l = $("cLayer").value, s = $("cStatus").value;
  const rows = A.filter((a) => (!t || a.target === t) && (!l || a.layer === l) && (!s || a.status === s));
  $("curCount").textContent = `顯示 ${rows.length} / ${A.length} 則`;
  $("curBody").innerHTML = rows.map((a) => `<tr><td class="nowrap mono">${esc(a.date)}</td><td>${tgt(a.target)}</td><td>${esc(a.actor)}</td><td class="layer">${esc(a.layer)}</td><td>${esc(a.claim)}</td><td>${pill(a.status)}</td><td class="src">${link(a.url, "來源")}</td></tr>`).join("");
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
  const rows = Object.entries(m.sources || {}).map(([name, h]) => `<tr><td>${esc(name)}</td><td>${h.ok === true ? pill("正常") : h.ok === "partial" ? pill("部分失敗") : pill("失敗")}</td><td class="mono">${h.fetched ?? 0}</td><td class="mono">${h.kept ?? 0}</td><td>${esc((h.errors || [])[0] || "")}</td></tr>`).join("");
  const llm = m.llm?.enabled ? `模型分類：已啟用，本次標註 ${m.llm.labelled} 則` : "模型分類：未啟用（使用規則分類）";
  $("health").innerHTML = rows
    ? `<div class="tablewrap"><table class="ledger" style="min-width:560px"><thead><tr><th>來源</th><th>狀態</th><th>抓到</th><th>相關</th><th>錯誤訊息</th></tr></thead><tbody>${rows}</tbody></table></div><p class="note">${esc(llm)}</p>`
    : `<p class="note">尚未執行過自動抓取。</p>`;
}

function renderAll() {
  renderLive(); renderTiles(); renderTrend(); renderMatrix(); renderBreakdowns();
  fillSelect("fLayer", state.news.map((n) => n.cls?.layer));
  fillSelect("fTopic", state.news.flatMap((n) => n.cls?.topics || []));
  renderFeed(); renderCurated(); renderFC(); renderPolls(); renderHealth();
}

["q", "fTarget", "fKind", "fLayer", "fTopic", "fDays"].forEach((id) => $(id).addEventListener("input", () => { state.shown = PAGE; renderFeed(); }));
["cTarget", "cLayer", "cStatus"].forEach((id) => $(id).addEventListener("change", renderCurated));
["gCand", "gCat"].forEach((id) => $(id).addEventListener("change", renderFC));
$("more").addEventListener("click", () => { state.shown += PAGE; renderFeed(); });

const tabs = [...document.querySelectorAll("nav.tabs button")];
function show(p) {
  tabs.forEach((b) => { const on = b.dataset.p === p; b.setAttribute("aria-selected", on); $("p-" + b.dataset.p).hidden = !on; });
}
tabs.forEach((b) => b.addEventListener("click", () => { show(b.dataset.p); history.replaceState(null, "", "#" + b.dataset.p); }));
const initial = location.hash.slice(1);
show(tabs.some((b) => b.dataset.p === initial) ? initial : "overview");

load();
setInterval(load, REFRESH_MS);
setInterval(renderLive, 60000);
