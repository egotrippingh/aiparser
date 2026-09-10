"use strict";

/* ---------------------------------------------------------------------
 * Слой API — тонкая обёртка над fetch, всё общение с сервером идёт отсюда.
 * ------------------------------------------------------------------- */
const api = {
  async get(path) { return api._call(path, { method: "GET" }); },
  async post(path, body) { return api._call(path, { method: "POST", body }); },
  async patch(path, body) { return api._call(path, { method: "PATCH", body }); },
  async put(path, body) { return api._call(path, { method: "PUT", body }); },
  async del(path) { return api._call(path, { method: "DELETE" }); },

  async _call(path, { method, body }) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const resp = await fetch(path, opts);
    if (!resp.ok) {
      let msg = resp.statusText;
      try { const j = await resp.json(); msg = j.detail || msg; } catch {}
      throw new Error(msg || `HTTP ${resp.status}`);
    }
    if (resp.status === 204) return null;
    const ct = resp.headers.get("content-type") || "";
    return ct.includes("application/json") ? resp.json() : resp.text();
  },

  async upload(path, file, extraQuery) {
    const fd = new FormData();
    fd.append("file", file);
    const qs = extraQuery ? "?" + new URLSearchParams(extraQuery) : "";
    const resp = await fetch(path + qs, { method: "POST", body: fd });
    if (!resp.ok) throw new Error((await resp.json().catch(() => ({}))).detail || resp.statusText);
    return resp.json();
  },
};

/* ---------------------------------------------------------------------
 * Состояние приложения
 * ------------------------------------------------------------------- */
const state = {
  meta: null,
  projects: [],
  projectId: null,
  view: "dashboard",
  dashboard: null,
  chartHidden: new Set(),
  chartHover: -1,
  queries: [],
  browserStatus: null,
};

// Состояние скана держим отдельно от state вида: скан живёт дольше вкладки,
// его прогресс и лог должны переживать переключение вкладок и перерисовку.
const scan = {
  active: null,   // снимок прогресса с сервера
  es: null,       // EventSource — ровно один на приложение
  log: [],        // строки лога, чтобы восстановить их при возврате на вкладку
};

function svcById(id) {
  return (state.meta?.services || []).find(s => s.id === id);
}
function currentProject() {
  return state.projects.find(p => p.id === state.projectId);
}

/* ---------------------------------------------------------------------
 * Тосты
 * ------------------------------------------------------------------- */
function toast(msg, isErr) {
  const wrap = document.getElementById("toasts");
  const el = document.createElement("div");
  el.className = "toast" + (isErr ? " err" : "");
  el.textContent = msg;
  wrap.appendChild(el);
  setTimeout(() => el.remove(), isErr ? 6000 : 3200);
}
function fail(err) {
  console.error(err);
  toast(err.message || String(err), true);
}

/* ---------------------------------------------------------------------
 * Инициализация
 * ------------------------------------------------------------------- */
async function init() {
  applyTheme();
  try {
    state.meta = await api.get("/api/meta");
    document.getElementById("ver").textContent = `${state.meta.portable ? "portable" : "установлено"} · v${state.meta.version}`;
    await loadProjects();
  } catch (e) { fail(e); }

  document.getElementById("mainNav").addEventListener("click", e => {
    const btn = e.target.closest("button[data-view]");
    if (!btn) return;
    setView(btn.dataset.view);
  });
  document.getElementById("closeDrawer").addEventListener("click", closeDrawer);
  document.getElementById("scrim").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", e => { if (e.key === "Escape") closeDrawer(); });
  window.addEventListener("resize", () => { if (state.view === "dashboard") drawChart(); });

  // Скан мог идти ещё до открытия окна (приложение перезапускали) —
  // подхватываем его прогресс, а не делаем вид, что ничего не происходит.
  await refreshActiveScan();
}

async function loadProjects() {
  state.projects = await api.get("/api/projects");
  renderSidebar();
  if (!state.projectId && state.projects.length) state.projectId = state.projects[0].id;
  if (state.projectId) await setView(state.view);
  else render();
}

function renderSidebar() {
  const box = document.getElementById("projectList");
  box.innerHTML = `<div class="cap">Проекты</div>`;
  for (const p of state.projects) {
    const b = document.createElement("button");
    b.className = "proj" + (p.id === state.projectId ? " on" : "");
    b.innerHTML = `<i class="dot"></i><span class="n">${esc(p.name)}</span>`;
    b.onclick = () => { state.projectId = p.id; renderSidebar(); setView(state.view); };
    box.appendChild(b);
  }
  const add = document.createElement("button");
  add.className = "addproj";
  add.textContent = "+ Новый проект";
  add.onclick = createProjectFlow;
  box.appendChild(add);
}

async function createProjectFlow() {
  const name = prompt("Название проекта:");
  if (!name) return;
  const brand = prompt("Название бренда для поиска в ответах:", name);
  if (!brand) return;
  try {
    const p = await api.post("/api/projects", { name, brand_name: brand, brand_aliases: [], brand_domains: [] });
    state.projects.push(p);
    state.projectId = p.id;
    renderSidebar();
    setView("settings");
    toast("Проект создан — заполните бренд и домены в настройках");
  } catch (e) { fail(e); }
}

/* ---------------------------------------------------------------------
 * Роутинг видов
 * ------------------------------------------------------------------- */
async function setView(view) {
  state.view = view;
  document.querySelectorAll("#mainNav button").forEach(b => b.classList.toggle("on", b.dataset.view === view));
  render();
}

function render() {
  const top = document.getElementById("topBar");
  const box = document.getElementById("view");
  const p = currentProject();

  if (!p) {
    top.innerHTML = `<h1>Нет проектов</h1>`;
    box.innerHTML = `<div class="empty"><div class="big">📋</div><p>Создайте первый проект, чтобы начать отслеживать упоминания бренда в ответах ИИ.</p></div>`;
    return;
  }

  if (state.view === "dashboard") return renderDashboard(p);
  if (state.view === "queries") return renderQueries(p);
  if (state.view === "scan") return renderScan(p);
  if (state.view === "settings") return renderSettings(p);
}

/* ---------------------------------------------------------------------
 * Дашборд
 * ------------------------------------------------------------------- */
async function renderDashboard(p) {
  const top = document.getElementById("topBar");
  top.innerHTML = `
    <div><h1>${esc(p.name)}</h1>
      <div class="meta">${esc(p.brand_domains?.[0] || p.brand_name)}${p.region_code ? " · регион " + esc(p.region_code) : ""}</div>
    </div>
    <div class="spacer"></div>
    <button class="btn" id="runScanBtn">▶ Запустить скан</button>`;
  document.getElementById("runScanBtn").onclick = () => setView("scan");

  const box = document.getElementById("view");
  box.innerHTML = `<div class="empty"><div class="big">⏳</div><p>Загрузка…</p></div>`;

  let d;
  try { d = await api.get(`/api/projects/${p.id}/dashboard?days=30`); }
  catch (e) { fail(e); box.innerHTML = `<div class="empty"><div class="big">⚠️</div><p>${esc(e.message)}</p></div>`; return; }
  state.dashboard = d;

  if (d.empty) {
    box.innerHTML = `<div class="empty"><div class="big">🔍</div><p>По этому проекту ещё не было ни одного скана. Добавьте запросы и запустите первый скан.</p>
      <div style="margin-top:14px"><button class="btn" onclick="setView('queries')">Добавить запросы</button></div></div>`;
    return;
  }

  const c = d.cards;
  const fmtPct = v => v === null || v === undefined ? "—" : v.toFixed(1).replace(".0", "");
  const deltaHtml = v => {
    if (v === null || v === undefined) return "";
    const cls = v > 0 ? "up" : v < 0 ? "dn" : "fl";
    const arrow = v > 0 ? "▲" : v < 0 ? "▼" : "•";
    return `<span class="delta ${cls}">${arrow} ${Math.abs(v).toFixed(1)} п.п.</span>`;
  };

  box.innerHTML = `
    <div class="cards">
      <div class="card">
        <div class="lab">Видимость бренда</div>
        <div class="val">${fmtPct(c.visibility)}<small>%</small></div>
        <div class="sub">${deltaHtml(c.visibility_delta)} к прошлому скану</div>
      </div>
      <div class="card">
        <div class="lab">Найдено упоминаний</div>
        <div class="val">${c.found}<small> / ${c.checked}</small></div>
        <div class="sub">${c.queries} запросов в срезе</div>
      </div>
      <div class="card">
        <div class="lab"><i class="sv-dot" style="background:${svcColor(c.best?.id)}"></i>Лучший сервис</div>
        <div class="val">${c.best ? fmtPct(c.best.pct) : "—"}<small>%</small></div>
        <div class="sub">${c.best ? esc(c.best.name) : "нет данных"}</div>
      </div>
      <div class="card">
        <div class="lab"><i class="sv-dot" style="background:${svcColor(c.worst?.id)}"></i>Худший сервис</div>
        <div class="val">${c.worst ? fmtPct(c.worst.pct) : "—"}<small>%</small></div>
        <div class="sub">${c.worst ? esc(c.worst.name) : "нет данных"}</div>
      </div>
      <div class="card">
        <div class="lab">Требуют проверки</div>
        <div class="val">${c.needs_review}</div>
        <div class="sub">${c.errors} ошибок${c.not_checked ? ` · ${c.not_checked} не проверено (лимит тарифа)` : ""}</div>
      </div>
    </div>

    <section class="panel">
      <div class="ph">
        <h2>Динамика видимости</h2>
        <span class="hint">доля запросов с упоминанием бренда</span>
        <div class="spacer"></div>
        <div class="legend" id="legend"></div>
      </div>
      <div class="chartwrap"><canvas id="chart"></canvas><div id="tip"></div></div>
    </section>

    <section class="panel">
      <div class="tools">
        <div class="search"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5L14 14"/></svg>
          <input id="rowSearch" placeholder="Поиск по запросам…"></div>
        <button class="chip on" data-f="all">Все ${d.rows.length}</button>
        <button class="chip" data-f="found">Найдено</button>
        <button class="chip" data-f="not_found">Не найдено</button>
        <button class="chip" data-f="review">Проверка ${c.needs_review}</button>
      </div>
      <table>
        <thead><tr>
          <th class="l">Запрос</th>
          ${state.meta.services.map(s => `<th>${esc(s.short)}</th>`).join("")}
          <th style="text-align:right;padding-right:15px">Проверен</th>
        </tr></thead>
        <tbody id="rows"></tbody>
      </table>
      <div class="foot" id="rowsFoot"></div>
    </section>`;

  buildLegend();
  drawChart();
  wireRowsTable(d);
}

function svcColor(id) {
  const s = svcById(id);
  return s ? `var(${s.color})` : "var(--faint)";
}

function buildLegend() {
  const legend = document.getElementById("legend");
  legend.innerHTML = "";
  for (const s of state.meta.services) {
    const b = document.createElement("button");
    b.className = "lg" + (state.chartHidden.has(s.id) ? " off" : "");
    b.innerHTML = `<i style="background:var(${s.color})"></i>${esc(s.name)}`;
    b.onclick = () => {
      state.chartHidden.has(s.id) ? state.chartHidden.delete(s.id) : state.chartHidden.add(s.id);
      b.classList.toggle("off");
      drawChart();
    };
    legend.appendChild(b);
  }
}

function drawChart() {
  const cv = document.getElementById("chart");
  if (!cv) return;
  const ctx = cv.getContext("2d");
  const tip = document.getElementById("tip");
  const d = state.dashboard;
  const days = d.days;

  const dpr = window.devicePixelRatio || 1;
  const w = cv.clientWidth, h = 236;
  cv.width = w * dpr; cv.height = h * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);

  if (!days.length) {
    ctx.fillStyle = cssVar("--faint");
    ctx.font = "13px Inter, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("Пока недостаточно данных для графика", w / 2, h / 2);
    return;
  }

  const L = 38, R = 12, T = 10, B = 24;
  const iw = w - L - R, ih = h - T - B;
  const max = 100;
  const line = cssVar("--line"), faint = cssVar("--faint");

  ctx.font = "11px Inter, Segoe UI, sans-serif";
  ctx.textAlign = "right"; ctx.textBaseline = "middle";
  for (let v = 0; v <= max; v += 20) {
    const y = T + ih - (v / max) * ih;
    ctx.strokeStyle = line; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(L, y + .5); ctx.lineTo(w - R, y + .5); ctx.stroke();
    ctx.fillStyle = faint; ctx.fillText(v + "%", L - 8, y);
  }

  ctx.textAlign = "center"; ctx.textBaseline = "top";
  const pts = days.map((_, i) => L + (days.length > 1 ? (iw / (days.length - 1)) * i : iw / 2));
  days.forEach((dt, i) => {
    if (i % Math.ceil(days.length / 8 || 1) === 0 || i === days.length - 1) {
      ctx.fillStyle = faint;
      ctx.fillText(shortDate(dt), pts[i], h - B + 7);
    }
  });

  if (state.chartHover >= 0 && pts[state.chartHover] !== undefined) {
    ctx.strokeStyle = cssVar("--accent"); ctx.globalAlpha = .35; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(pts[state.chartHover] + .5, T); ctx.lineTo(pts[state.chartHover] + .5, T + ih); ctx.stroke();
    ctx.globalAlpha = 1;
  }

  for (const s of state.meta.services) {
    if (state.chartHidden.has(s.id)) continue;
    const vals = d.series[s.id] || [];
    const col = cssVar(s.color);
    ctx.strokeStyle = col; ctx.lineWidth = 2; ctx.lineJoin = "round"; ctx.lineCap = "round";
    ctx.beginPath();
    let started = false;
    vals.forEach((v, i) => {
      if (v === null || v === undefined) { started = false; return; }
      const x = pts[i], y = T + ih - (v / max) * ih;
      if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
    });
    ctx.stroke();
    vals.forEach((v, i) => {
      if (v === null || v === undefined) return;
      if (i !== vals.length - 1 && i !== state.chartHover) return;
      const x = pts[i], y = T + ih - (v / max) * ih;
      ctx.fillStyle = cssVar("--panel"); ctx.beginPath(); ctx.arc(x, y, 4, 0, 7); ctx.fill();
      ctx.strokeStyle = col; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(x, y, 3.2, 0, 7); ctx.stroke();
    });
  }

  cv.onmousemove = e => {
    const r = cv.getBoundingClientRect(), x = e.clientX - r.left;
    let best = 0, bd = 1e9;
    pts.forEach((p, i) => { const dd = Math.abs(p - x); if (dd < bd) { bd = dd; best = i; } });
    if (best !== state.chartHover) { state.chartHover = best; drawChart(); }
    let html = `<div class="d">${esc(days[best])}</div>`;
    for (const s of state.meta.services) {
      if (state.chartHidden.has(s.id)) continue;
      const v = (d.series[s.id] || [])[best];
      html += `<div class="r"><span><i style="display:block;width:8px;height:8px;border-radius:2px;background:var(${s.color})"></i>${esc(s.name)}</span><b>${v === null || v === undefined ? "—" : v + "%"}</b></div>`;
    }
    tip.innerHTML = html; tip.style.opacity = 1;
    const tw = tip.offsetWidth;
    tip.style.left = Math.min(Math.max(pts[best] - tw / 2, 4), cv.clientWidth - tw - 4) + "px";
    tip.style.top = "18px";
  };
  cv.onmouseleave = () => { state.chartHover = -1; tip.style.opacity = 0; drawChart(); };
}

function shortDate(iso) {
  const [, m, dd] = iso.split("-");
  return `${parseInt(dd)}.${m}`;
}
function cssVar(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

const STLAB = {
  found: "✓", not_found: "✗", error: "!", auth_required: "!",
  captcha: "!", skipped: "—", limit_reached: "⏳",
};
const STATUS_TITLE = {
  found: "Упоминание найдено",
  not_found: "Упоминаний нет",
  skipped: "AI-блок не показан",
  error: "Ошибка проверки",
  auth_required: "Нужен вход в аккаунт",
  captcha: "Остановлено капчей",
  limit_reached: "Лимит тарифа — запрос не проверен",
};

function wireRowsTable(d) {
  let filter = "all", q = "";
  const tbody = document.getElementById("rows");
  const foot = document.getElementById("rowsFoot");

  function draw() {
    let rows = d.rows;
    if (filter === "found") rows = rows.filter(r => Object.values(r.statuses).some(s => s.status === "found"));
    if (filter === "not_found") rows = rows.filter(r => Object.values(r.statuses).every(s => s.status !== "found"));
    if (filter === "review") rows = rows.filter(r => Object.values(r.statuses).some(s => s.needs_review));
    if (q) rows = rows.filter(r => r.text.toLowerCase().includes(q));

    tbody.innerHTML = rows.map(r => `
      <tr data-qid="${r.query_id}">
        <td class="q">${esc(r.text)}${r.group_tag ? `<span class="tag">${esc(r.group_tag)}</span>` : ""}</td>
        ${state.meta.services.map(s => {
          const st = r.statuses[s.id];
          if (!st) return `<td><span class="st skipped">·</span></td>`;
          const mk = st.change ? " " + st.change : "";
          return `<td><span class="st ${st.status}${mk}" title="${st.needs_review ? "требует проверки" : ""}">${STLAB[st.status] ?? "?"}</span></td>`;
        }).join("")}
        <td class="when">${relTime(r.checked_at)}</td>
      </tr>`).join("");

    tbody.querySelectorAll("tr").forEach(tr => {
      tr.onclick = () => openQueryDrawer(parseInt(tr.dataset.qid), d.scan.id);
    });
    foot.textContent = `Показано ${rows.length} из ${d.rows.length} · клик по строке открывает карточку запроса`;
  }

  document.getElementById("rowSearch").oninput = e => { q = e.target.value.trim().toLowerCase(); draw(); };
  document.querySelectorAll(".chip[data-f]").forEach(chip => {
    chip.onclick = () => {
      document.querySelectorAll(".chip[data-f]").forEach(c => c.classList.remove("on"));
      chip.classList.add("on");
      filter = chip.dataset.f;
      draw();
    };
  });
  draw();
}

function relTime(iso) {
  if (!iso) return "";
  const diff = (Date.now() - new Date(iso.replace(" ", "T") + "Z").getTime()) / 1000;
  if (diff < 60) return "только что";
  if (diff < 3600) return Math.round(diff / 60) + " мин назад";
  if (diff < 86400) return Math.round(diff / 3600) + " ч назад";
  return Math.round(diff / 86400) + " дн назад";
}

/* ---------------------------------------------------------------------
 * Карточка запроса (drawer)
 * ------------------------------------------------------------------- */
async function openQueryDrawer(queryId, scanId) {
  let detail;
  try { detail = await api.get(`/api/queries/${queryId}/detail?scan_id=${scanId}`); }
  catch (e) { fail(e); return; }

  document.getElementById("dq").textContent = detail.text;
  document.getElementById("dmeta").textContent = `${currentProject().name} · срез ${state.dashboard.scan.scan_date}`;

  const tabsBox = document.getElementById("tabs");
  let cur = state.meta.services.find(s => detail.by_service[s.id])?.id || state.meta.services[0].id;

  function buildTabs() {
    tabsBox.innerHTML = "";
    for (const s of state.meta.services) {
      const info = detail.by_service[s.id];
      const b = document.createElement("button");
      b.className = "tab" + (s.id === cur ? " on" : "");
      const st = info ? info.status : "skipped";
      b.innerHTML = `<span class="st ${st}">${STLAB[st] ?? "·"}</span>${esc(s.name)}`;
      b.onclick = () => { cur = s.id; buildTabs(); renderTab(); };
      tabsBox.appendChild(b);
    }
  }

  function renderTab() {
    const body = document.getElementById("dbody");
    const info = detail.by_service[cur];
    if (!info) { body.innerHTML = `<div class="answer">По этому сервису в срезе нет данных.</div>`; return; }

    const title = STATUS_TITLE[info.status] || info.status;

    const verdictCls = ["found", "not_found", "limit_reached"].includes(info.status) ? info.status : "";

    body.innerHTML = `
      <div class="verdict ${verdictCls}">
        <div class="t"><span class="st ${info.status}">${STLAB[info.status] ?? "·"}</span>${esc(title)}
          ${info.confidence !== null && info.confidence !== undefined ? `<span class="conf">${esc(info.detected_by || "")} · ${Math.round(info.confidence * 100)}%</span>` : ""}
        </div>
        ${info.evidence_quote ? `<blockquote>${esc(info.evidence_quote)}</blockquote>` : ""}
        ${info.error_message ? `<blockquote>${esc(info.error_message)}</blockquote>` : ""}
        ${info.mention_types?.length ? `<div class="mt">${info.mention_types.map(t => `<span>${esc(t)}</span>`).join("")}</div>` : ""}
      </div>

      ${info.screenshot ? `<div class="shot"><div class="cap"><b>Скриншот выдачи</b></div><img src="${info.screenshot}"></div>` : ""}

      ${info.answer_text ? `<div class="sect">Текст ответа</div><div class="answer">${esc(info.answer_text)}</div>` : ""}

      <div class="sect">Источники ${info.sources?.length ? `(${info.sources.length})` : ""}</div>
      ${info.sources?.length
        ? `<ul class="srcs">${info.sources.map(u => `<li><a href="${esc(u)}" target="_blank" rel="noopener">${esc(u)}</a></li>`).join("")}</ul>`
        : `<div class="answer" style="color:var(--faint)">Ссылок нет</div>`}

      ${info.history?.length ? `
        <div class="sect">История по дням</div>
        <div style="display:flex;gap:3px;align-items:flex-end">
          ${info.history.map(h => `
            <div style="flex:1;text-align:center">
              <div style="height:26px;border-radius:4px;background:${h.status === 'found' ? 'var(--ok-soft)' : h.status === 'not_found' ? 'var(--no-soft)' : 'var(--panel-2)'}"></div>
              <div style="font-size:9.5px;color:var(--faint);margin-top:4px">${shortDate(h.scan_date)}</div>
            </div>`).join("")}
        </div>` : ""}
    `;
  }

  buildTabs();
  renderTab();
  document.getElementById("drawer").classList.add("on");
  document.getElementById("scrim").classList.add("on");
}

function closeDrawer() {
  document.getElementById("drawer").classList.remove("on");
  document.getElementById("scrim").classList.remove("on");
}

/* ---------------------------------------------------------------------
 * Запросы
 * ------------------------------------------------------------------- */
async function renderQueries(p) {
  document.getElementById("topBar").innerHTML = `<h1>Запросы — ${esc(p.name)}</h1><div class="spacer"></div>`;
  const box = document.getElementById("view");
  box.innerHTML = `<div class="empty"><div class="big">⏳</div></div>`;

  let queries;
  try { queries = await api.get(`/api/projects/${p.id}/queries`); }
  catch (e) { fail(e); return; }
  state.queries = queries;
  document.getElementById("queryCount").textContent = queries.length;

  box.innerHTML = `
    <section class="panel">
      <div class="ph"><h2>Добавить запросы</h2><span class="hint">по одному в строке, дубликаты внутри проекта пропускаются</span></div>
      <div class="formgrid one">
        <div class="field">
          <textarea id="bulkText" placeholder="купить крепёж оптом от производителя&#10;поставщик метизов оптом в москве&#10;..."></textarea>
        </div>
        <div class="field" style="flex-direction:row;align-items:center;gap:10px">
          <input id="groupTag" placeholder="тег группы (необязательно)" style="max-width:220px">
          <button class="btn" id="addBtn">Добавить</button>
          <span class="hint">или</span>
          <button class="btn ghost" id="uploadBtn">Загрузить .txt / .csv</button>
          <input type="file" id="fileInput" accept=".txt,.csv" style="display:none">
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="ph"><h2>Список запросов</h2><span class="hint">${queries.length} всего</span></div>
      <table>
        <thead><tr><th class="l">Запрос</th><th>Группа</th><th>Активен</th><th style="text-align:right;padding-right:15px">Действия</th></tr></thead>
        <tbody id="qrows"></tbody>
      </table>
    </section>`;

  const qrows = document.getElementById("qrows");
  qrows.innerHTML = queries.map(q => `
    <tr data-id="${q.id}">
      <td class="q">${esc(q.text)}</td>
      <td>${q.group_tag ? esc(q.group_tag) : "—"}</td>
      <td><input type="checkbox" ${q.is_active ? "checked" : ""} class="toggleActive"></td>
      <td style="text-align:right;padding-right:15px"><button class="icobtn delQ" title="Удалить">✕</button></td>
    </tr>`).join("") || `<tr><td colspan="4" style="text-align:center;color:var(--faint);padding:20px">Пока нет запросов</td></tr>`;

  qrows.querySelectorAll(".toggleActive").forEach(cb => {
    cb.onchange = async () => {
      const id = cb.closest("tr").dataset.id;
      try { await api.patch(`/api/projects/${p.id}/queries/${id}?is_active=${cb.checked}`); }
      catch (e) { fail(e); cb.checked = !cb.checked; }
    };
  });
  qrows.querySelectorAll(".delQ").forEach(btn => {
    btn.onclick = async () => {
      const tr = btn.closest("tr");
      if (!confirm("Удалить запрос? История проверок по нему тоже удалится.")) return;
      try { await api.del(`/api/projects/${p.id}/queries/${tr.dataset.id}`); tr.remove(); }
      catch (e) { fail(e); }
    };
  });

  document.getElementById("addBtn").onclick = async () => {
    const text = document.getElementById("bulkText").value;
    if (!text.trim()) return;
    try {
      const res = await api.post(`/api/projects/${p.id}/queries`, { text, group_tag: document.getElementById("groupTag").value || null });
      toast(`Добавлено ${res.added}, пропущено дубликатов ${res.skipped}`);
      renderQueries(p);
    } catch (e) { fail(e); }
  };

  document.getElementById("uploadBtn").onclick = () => document.getElementById("fileInput").click();
  document.getElementById("fileInput").onchange = async e => {
    const file = e.target.files[0];
    if (!file) return;
    try {
      const res = await api.upload(`/api/projects/${p.id}/queries/upload`, file, { group_tag: document.getElementById("groupTag").value || "" });
      toast(`Загружено ${res.added}, пропущено дубликатов ${res.skipped}`);
      renderQueries(p);
    } catch (e) { fail(e); }
  };
}

/* ---------------------------------------------------------------------
 * Скан: глобальный прогресс + подписка на события
 *
 * Прогресс намеренно живёт вне вкладки «Скан»: подписка одна на приложение,
 * состояние хранится в `scan`, а не в DOM, поэтому уход на дашборд и возврат
 * обратно ничего не теряют. При старте приложения состояние подтягивается
 * запросом /api/scans/active — так прогресс виден и после перезапуска.
 * ------------------------------------------------------------------- */
function fmtDur(sec) {
  if (sec === null || sec === undefined) return "—";
  if (sec < 60) return `${sec} сек`;
  const m = Math.round(sec / 60);
  if (m < 60) return `${m} мин`;
  return `${Math.floor(m / 60)} ч ${m % 60} мин`;
}

function renderGlobalScan() {
  const bar = document.getElementById("globalScan");
  const s = scan.active;
  if (!s || s.state === "finished") { bar.hidden = true; return; }

  const svc = svcById(s.current_service);
  const paused = s.state === "paused";
  bar.hidden = false;
  bar.classList.toggle("paused", paused);
  bar.innerHTML = `
    <span class="gs-svc">
      <i class="sv-dot" style="background:${svc ? `var(${svc.color})` : "var(--faint)"}"></i>
      ${esc(svc ? svc.name : "Скан")}${paused ? " · на паузе" : ""}
    </span>
    <span class="gs-bar"><i style="width:${s.percent}%"></i></span>
    <span class="gs-num">${s.done} / ${s.total} · ${s.percent}%</span>
    <span class="gs-eta">осталось ~${fmtDur(s.eta_sec)}</span>
    <button class="btn ghost" id="gsPause" title="${paused ? "Продолжить скан" : "Пауза начнётся после текущего запроса"}">
      ${paused ? "▶ Продолжить" : "⏸ Пауза"}
    </button>
    <button class="btn danger" id="gsStop">⏹ Стоп</button>`;

  document.getElementById("gsPause").onclick = async () => {
    try { await api.post(`/api/scans/${s.scan_id}/${paused ? "resume" : "pause"}`); }
    catch (e) { fail(e); }
  };
  document.getElementById("gsStop").onclick = async () => {
    if (!confirm("Остановить скан? Уже проверенные запросы останутся в базе, скан можно будет продолжить.")) return;
    try { await api.post(`/api/scans/${s.scan_id}/stop`); } catch (e) { fail(e); }
  };
}

function scanLog(text, cls) {
  scan.log.push({ text, cls });
  if (scan.log.length > 400) scan.log.shift();
  const box = document.getElementById("scanLog");
  if (!box) return;                       // вкладка «Скан» сейчас не открыта
  const d = document.createElement("div");
  d.className = "ln" + (cls ? " " + cls : "");
  d.innerHTML = text;
  box.appendChild(d);
  box.scrollTop = box.scrollHeight;
}

function subscribeScan(scanId) {
  if (scan.es) return;                    // подписка уже есть — вторая не нужна
  const es = new EventSource(`/api/scans/${scanId}/stream`);
  scan.es = es;

  const progress = e => { scan.active = e; renderGlobalScan(); };

  const handlers = {
    scan_started: e => { progress(e); scanLog(`<b>Скан запущен</b> · проверок: ${e.total}`); },
    progress,
    paused: e => { progress(e); scanLog(`<b>Пауза</b> (остановится после текущего запроса)`); },
    resumed: e => { progress(e); scanLog(`<b>Продолжено</b>`); },
    stopping: e => { progress(e); scanLog(`<b>Останавливается…</b>`); },
    service_started: e => scanLog(`→ сервис <b>${esc(e.name)}</b> · запросов: ${e.pending}`),
    service_finished: e => scanLog(`← сервис ${esc(e.service)} завершён`),
    service_error: e => scanLog(`⚠ сервис ${esc(e.service)} упал: ${esc(e.error)}`, "err"),
    service_blocked: e => scanLog(`⚠ сервис ${esc(e.service)} недоступен: ${esc(e.reason)}`, "err"),
    service_limit: e => scanLog(
      `⏳ <b>${esc(e.service)}: лимит тарифа</b> — пропущено ${e.skipped} запросов, их возьмёт дозапуск`, "err"),
    query_result: e => {
      const svc = svcById(e.service);
      const cls = e.status === "found" ? "ok"
        : ["error", "captcha", "auth_required", "limit_reached"].includes(e.status) ? "err" : "";
      scanLog(`${STLAB[e.status] ?? "?"} ${esc(svc?.name || e.service)} — #${e.query_id}: <b>${esc(e.status)}</b>`, cls);
    },
    scan_finished: e => {
      scanLog(`<b>Скан завершён: ${esc(e.status)}</b>`, e.status === "done" ? "ok" : "");
      scan.active = null;
      es.close();
      scan.es = null;
      renderGlobalScan();
      toast(e.status === "done" ? "Скан завершён" : "Скан остановлен");
      if (state.view === "scan" || state.view === "dashboard") setView("dashboard");
    },
  };

  for (const [name, fn] of Object.entries(handlers)) {
    es.addEventListener(name, ev => { try { fn(JSON.parse(ev.data)); } catch { fn({}); } });
  }
  // Сервер закрывает поток сам по scan_finished; разрыв сети фатальным не
  // считаем — состояние всё равно перечитывается через /api/scans/active.
  es.onerror = () => {};
}

async function refreshActiveScan() {
  try {
    const s = await api.get("/api/scans/active");
    scan.active = s;
    renderGlobalScan();
    if (s) subscribeScan(s.scan_id);
  } catch { /* сервер ещё поднимается — не шумим */ }
}

async function renderScan(p) {
  document.getElementById("topBar").innerHTML = `<h1>Скан — ${esc(p.name)}</h1><div class="spacer"></div>`;
  const box = document.getElementById("view");

  const [activeQueries, resumable] = await Promise.all([
    api.get(`/api/projects/${p.id}/queries?only_active=true`).catch(() => []),
    api.get(`/api/projects/${p.id}/resumable`).catch(() => null),
  ]);

  const ready = state.meta.services.filter(s => s.has_adapter);
  const notReady = state.meta.services.filter(s => !s.has_adapter);

  box.innerHTML = `
    ${resumable ? `
    <section class="panel">
      <div class="ph">
        <h2>Незаконченный скан от ${esc(resumable.scan_date)}</h2>
        <span class="hint">проверено ${resumable.conclusive} из ${resumable.expected}, осталось ${resumable.remaining}</span>
      </div>
      <div class="ph" style="border-top:1px solid var(--line);border-bottom:0">
        <span class="hint">Бесплатные тарифы упираются в лимит примерно на сороковом запросе, поэтому большую базу приходится добирать за несколько заходов. Дозапуск продолжит с места остановки и допишет результаты в тот же срез.</span>
      </div>
    </section>` : ""}

    <section class="panel">
      <div class="ph"><h2>Сервисы</h2><span class="hint">выберите, какие проверять</span></div>
      <div class="checklist" id="svcCheck">
        ${ready.map(s => `
          <label class="cbox"><input type="checkbox" value="${s.id}" checked><i class="sv-dot" style="background:var(${s.color})"></i>${esc(s.name)}</label>`).join("")}
        ${notReady.map(s => `
          <label class="cbox" style="opacity:.45;cursor:not-allowed" title="Адаптер для этого сервиса ещё не реализован">
            <input type="checkbox" disabled><i class="sv-dot" style="background:var(${s.color})"></i>${esc(s.name)} — нет адаптера</label>`).join("")}
      </div>
      <div class="ph" style="border-top:1px solid var(--line);border-bottom:0">
        <span class="hint">${activeQueries.length} активных запросов × выбранные сервисы</span>
        <div class="spacer"></div>
        ${resumable ? `<button class="btn ghost" id="freshScanBtn">Начать заново</button>` : ""}
        <button class="btn" id="startScanBtn">${resumable ? "▶ Продолжить скан" : "▶ Запустить скан"}</button>
      </div>
    </section>

    <section class="panel">
      <div class="ph"><h2>Лог</h2><span class="hint">прогресс виден в шапке с любой вкладки</span></div>
      <div class="scanlog" id="scanLog"></div>
    </section>`;

  // Восстанавливаем накопленный лог: вкладку могли открыть посреди скана.
  const logBox = document.getElementById("scanLog");
  logBox.innerHTML = scan.log.map(l => `<div class="ln${l.cls ? " " + l.cls : ""}">${l.text}</div>`).join("")
    || `<div class="ln" style="color:var(--faint)">Скан ещё не запускался</div>`;
  logBox.scrollTop = logBox.scrollHeight;

  async function launch(resume) {
    if (!activeQueries.length) { toast("Нет активных запросов — добавьте их на вкладке «Запросы»", true); return; }
    const services = Array.from(document.querySelectorAll("#svcCheck input:checked")).map(i => i.value);
    if (!services.length) { toast("Выберите хотя бы один сервис", true); return; }
    try {
      if (!resume) scan.log = [];
      const res = await api.post(`/api/projects/${p.id}/scans`, { services, resume });
      subscribeScan(res.scan_id);
      await refreshActiveScan();
    } catch (e) { fail(e); }
  }

  document.getElementById("startScanBtn").onclick = () => launch(true);
  const fresh = document.getElementById("freshScanBtn");
  if (fresh) fresh.onclick = () => {
    if (!confirm("Начать новый скан с нуля? Незаконченный останется в истории, но продолжить его будет уже нельзя.")) return;
    launch(false);
  };
}

/* ---------------------------------------------------------------------
 * Настройки
 * ------------------------------------------------------------------- */
function fmtWhen(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d) ? "" : d.toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function authBadge(a) {
  // Две половины правды: кука на диске и то, что сервис ответил в последний
  // реальный прогон. Кука может лежать, а сервис её уже не принимать —
  // поэтому «отклонена» важнее, чем «есть на диске», и показывается первой.
  if (a.login_open) return { cls: "", label: "окно входа открыто", sub: "" };

  const checked = a.last_scan_at ? `последняя проверка: ${fmtWhen(a.last_scan_at)}` : "";

  if (a.last_scan_state === "auth_required") {
    return { cls: "warn", label: "нужен вход", sub: `Сервис не принял сохранённую сессию · ${checked}` };
  }
  if (a.cookie_state === "ok") {
    const until = a.expires_at ? `действует до ${fmtWhen(new Date(a.expires_at * 1000).toISOString())}` : "";
    return { cls: "ok", label: "вход выполнен", sub: [until, checked].filter(Boolean).join(" · ") };
  }
  if (a.cookie_state === "expired") {
    return { cls: "warn", label: "сессия истекла", sub: checked };
  }
  return { cls: "off", label: "вход не выполнен", sub: "" };
}

async function renderSettings(p) {
  document.getElementById("topBar").innerHTML = `<h1>Настройки — ${esc(p.name)}</h1><div class="spacer"></div>`;
  const box = document.getElementById("view");

  let settings, browserStatus;
  try {
    [settings, browserStatus] = await Promise.all([api.get("/api/settings"), api.get("/api/browser/status")]);
  } catch (e) { fail(e); return; }

  box.innerHTML = `
    <section class="panel">
      <div class="ph"><h2>Проект и бренд</h2><span class="hint">формы бренда используются для поиска в ответах</span></div>
      <div class="formgrid">
        <div class="field"><label>Название проекта</label><input id="f_name" value="${escAttr(p.name)}"></div>
        <div class="field"><label>Название бренда</label><input id="f_brand" value="${escAttr(p.brand_name)}"></div>
        <div class="field span2"><label>Алиасы бренда <span class="hint">— по одному в строке: другие написания, старое название и т.п.</span></label>
          <textarea id="f_aliases">${esc((p.brand_aliases || []).join("\n"))}</textarea></div>
        <div class="field span2"><label>Домены бренда <span class="hint">— по одному в строке, без https://</span></label>
          <textarea id="f_domains">${esc((p.brand_domains || []).join("\n"))}</textarea></div>
        <div class="field"><label>Регион (для Яндекса) <span class="hint">— код lr, напр. 213 — Москва</span></label>
          <input id="f_region" value="${escAttr(p.region_code || "")}" placeholder="213"></div>
        <div class="field"><label>Глубокая проверка источников <span class="hint">— сколько страниц открывать, 0 = выключено</span></label>
          <input id="f_deep" type="number" min="0" max="5" value="${p.deep_check_depth || 0}">
          <div class="speedhint">Если бренда нет в самом ответе, программа откроет процитированные страницы и поищет его там — так ловятся упоминания на сайтах партнёров и перекупщиков. Добавляет примерно 5 секунд на каждый запрос без упоминания: на базе в 100 запросов это около получаса к прогону.</div></div>
      </div>
      <div class="ph" style="border-top:1px solid var(--line);justify-content:flex-end;gap:8px">
        <button class="btn ghost" id="delProjBtn" style="color:var(--no)">Удалить проект</button>
        <button class="btn" id="saveProjBtn">Сохранить</button>
      </div>
    </section>

    <section class="panel">
      <div class="ph"><h2>Браузер и аккаунты</h2><span class="hint">${browserStatus.installed ? "Camoufox установлен" : "Camoufox не установлен"}</span></div>
      ${!browserStatus.installed ? `
        <div class="ph" style="border-top:1px solid var(--line)">
          <span class="hint">Первый запуск: скачивается один раз, дальше не требуется</span>
          <div class="spacer"></div>
          <button class="btn" id="installBtn" ${browserStatus.installing ? "disabled" : ""}>${browserStatus.installing ? "Скачивается…" : "Скачать браузер"}</button>
        </div>` : ""}
      <div id="svcList"></div>
    </section>

    <section class="panel">
      <div class="ph">
        <h2>Скорость скана</h2>
        <span class="hint">размен между временем прогона и живучестью аккаунтов</span>
      </div>
      <div class="formgrid">
        <div class="field span2">
          <label>Режим</label>
          <select id="f_speed">
            <option value="careful"${settings.speed_profile === "careful" ? " selected" : ""}>Осторожно — максимальная безопасность аккаунтов</option>
            <option value="balanced"${settings.speed_profile === "balanced" ? " selected" : ""}>Сбалансированно — примерно вдвое быстрее (по умолчанию)</option>
            <option value="fast"${settings.speed_profile === "fast" ? " selected" : ""}>Быстро — минимальные паузы, выше риск капчи</option>
          </select>
          <div class="speedhint" id="speedHint"></div>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="ph"><h2>OpenRouter (LLM-детекция)</h2><span class="hint">две строки: ключ и модель</span></div>
      <div class="formgrid">
        <div class="field"><label>API-ключ ${settings.openrouter_api_key_set ? `<span class="hint">сейчас: ${esc(settings.openrouter_api_key_masked)}</span>` : ""}</label>
          <input id="f_orkey" type="password" placeholder="${settings.openrouter_api_key_set ? "оставьте пустым, чтобы не менять" : "sk-or-..."}"></div>
        <div class="field"><label>Модель</label><input id="f_ormodel" value="${escAttr(settings.openrouter_model)}"></div>
        <div class="field"><label>Когда вызывать LLM</label>
          <select id="f_llmmode">
            <option value="smart" ${settings.llm_mode === "smart" ? "selected" : ""}>Только когда правила не нашли (рекомендуется)</option>
            <option value="always" ${settings.llm_mode === "always" ? "selected" : ""}>Всегда</option>
            <option value="never" ${settings.llm_mode === "never" ? "selected" : ""}>Никогда</option>
          </select></div>
        <div class="field"><label>Порог уверенности LLM</label>
          <input id="f_llmthr" type="number" min="0" max="1" step="0.05" value="${settings.llm_confidence_threshold}"></div>
      </div>
      <div class="ph" style="border-top:1px solid var(--line);justify-content:flex-end">
        <button class="btn" id="saveSettingsBtn">Сохранить</button>
      </div>
    </section>`;

  const svcList = document.getElementById("svcList");
  svcList.innerHTML = state.meta.services.map(s => {
    const a = (browserStatus.services || {})[s.id] || {};
    const st = authBadge(a);
    return `
    <div class="svc-row">
      <i class="svc-dot" style="background:var(${s.color})"></i>
      <div style="flex:1">
        <div class="svc-name">${esc(s.name)}${s.has_adapter ? "" : ` <span class="tag">нет адаптера</span>`}</div>
        <div class="svc-note">${esc(s.note)}</div>
        ${st.sub ? `<div class="svc-sub">${esc(st.sub)}</div>` : ""}
      </div>
      <span class="svc-badge ${st.cls}">${esc(st.label)}</span>
      <button class="btn ghost loginBtn" data-svc="${s.id}" ${browserStatus.installed ? "" : "disabled"}>
        ${st.cls === "ok" ? "Перевойти" : "Войти"}
      </button>
    </div>`;
  }).join("");

  svcList.querySelectorAll(".loginBtn").forEach(btn => {
    btn.onclick = async () => {
      const svc = btn.dataset.svc;
      // Вкладку открываем сразу по клику: после await браузер счёл бы её
      // всплывающим окном и заблокировал.
      const viewer = browserStatus.viewer_url;
      if (viewer) window.open(viewer, "aiparser-browser");
      try {
        await api.post(`/api/browser/services/${svc}/login`, {});
        toast(viewer
          ? "Окно входа открыто во вкладке noVNC — залогиньтесь там и закройте окно крестиком"
          : "Открываю окно входа — залогиньтесь и просто закройте его");
        watchLogin(svc, p);
      } catch (e) { fail(e); }
    };
  });

  const speedSel = document.getElementById("f_speed");
  const speedHint = document.getElementById("speedHint");
  const showSpeed = () => {
    const prof = (settings.speed_profiles || {})[speedSel.value];
    if (!prof) { speedHint.textContent = ""; return; }
    const brk = prof.break_every_n
      ? `длинный перерыв каждые ${prof.break_every_n} запросов`
      : "без длинных перерывов";
    speedHint.textContent =
      `Пауза между запросами ${prof.delay_min_sec}–${prof.delay_max_sec} сек, ${brk}. ` +
      `Ускорение не сокращает время ответа самой нейросети — только паузы между запросами.`;
  };
  speedSel.onchange = showSpeed;
  showSpeed();

  const installBtn = document.getElementById("installBtn");
  if (installBtn) installBtn.onclick = async () => {
    installBtn.disabled = true; installBtn.textContent = "Скачивается…";
    try { await api.post("/api/browser/install", {}); pollInstall(); } catch (e) { fail(e); }
  };

  document.getElementById("saveProjBtn").onclick = async () => {
    const patch = {
      name: document.getElementById("f_name").value.trim(),
      brand_name: document.getElementById("f_brand").value.trim(),
      brand_aliases: splitLines(document.getElementById("f_aliases").value),
      brand_domains: splitLines(document.getElementById("f_domains").value),
      region_code: document.getElementById("f_region").value.trim() || null,
      deep_check_depth: parseInt(document.getElementById("f_deep").value) || 0,
    };
    try {
      const updated = await api.patch(`/api/projects/${p.id}`, patch);
      Object.assign(p, updated);
      renderSidebar();
      toast("Сохранено");
    } catch (e) { fail(e); }
  };

  document.getElementById("delProjBtn").onclick = async () => {
    if (!confirm(`Удалить проект «${p.name}» вместе со всей историей проверок? Это необратимо.`)) return;
    try {
      await api.del(`/api/projects/${p.id}`);
      state.projects = state.projects.filter(x => x.id !== p.id);
      state.projectId = state.projects[0]?.id || null;
      renderSidebar();
      setView("dashboard");
    } catch (e) { fail(e); }
  };

  document.getElementById("saveSettingsBtn").onclick = async () => {
    const body = {
      openrouter_model: document.getElementById("f_ormodel").value.trim(),
      llm_mode: document.getElementById("f_llmmode").value,
      llm_confidence_threshold: document.getElementById("f_llmthr").value,
      speed_profile: document.getElementById("f_speed").value,
    };
    const key = document.getElementById("f_orkey").value;
    if (key) body.openrouter_api_key = key;
    try { await api.put("/api/settings", body); toast("Настройки сохранены"); renderSettings(p); }
    catch (e) { fail(e); }
  };
}

function watchLogin(serviceId, project) {
  // Окно логина живёт своей жизнью, и понять «вошёл ли» можно только по
  // факту его закрытия. Дожидаемся исчезновения сервиса из списка открытых
  // окон и перерисовываем настройки — иначе статус остался бы вчерашним.
  const timer = setInterval(async () => {
    try {
      const st = await api.get("/api/browser/status");
      if (!st.logins_in_progress.includes(serviceId)) {
        clearInterval(timer);
        if (state.view === "settings") renderSettings(project);
      }
    } catch { clearInterval(timer); }
  }, 3000);
}

function pollInstall() {
  const timer = setInterval(async () => {
    try {
      const st = await api.get("/api/browser/install/log");
      if (!st.running) {
        clearInterval(timer);
        if (st.error) toast("Не удалось скачать браузер: " + st.error, true);
        else toast("Браузер установлен");
        setView("settings");
      }
    } catch { clearInterval(timer); }
  }, 2000);
}

function splitLines(text) {
  return text.split("\n").map(s => s.trim()).filter(Boolean);
}

/* ---------------------------------------------------------------------
 * Утилиты
 * ------------------------------------------------------------------- */
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function escAttr(s) { return esc(s); }

function applyTheme() {
  document.documentElement.dataset.theme = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

init();
