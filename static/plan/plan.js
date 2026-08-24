const NAME_KEY = "plan_display_name";
const HOUR_START = 7;
const HOUR_END = 23;
const HOUR_H = 56;
const WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const IMPORTANCE_LABEL = { low: "Низкая", medium: "Средняя", high: "Высокая" };

const state = {
  name: localStorage.getItem(NAME_KEY) || "",
  mode: "month",
  cursor: startOfToday(),
  events: [],
  filterPerson: "",
  hideRepik: false,
};

const $ = (sel, root = document) => root.querySelector(sel);

function startOfToday() {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d;
}

function pad(n) {
  return String(n).padStart(2, "0");
}

function isoDate(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function parseIso(iso) {
  const [y, m, day] = iso.split("-").map(Number);
  return new Date(y, m - 1, day);
}

function addDays(d, n) {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
}

function startOfWeek(d) {
  const x = new Date(d);
  const day = (x.getDay() + 6) % 7;
  x.setDate(x.getDate() - day);
  x.setHours(0, 0, 0, 0);
  return x;
}

function startOfMonth(d) {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

function monthLabel(d) {
  return d.toLocaleDateString("ru-RU", { month: "long", year: "numeric" });
}

function rangeLabel() {
  if (state.mode === "month") return monthLabel(state.cursor);
  if (state.mode === "day") {
    return state.cursor.toLocaleDateString("ru-RU", { weekday: "long", day: "numeric", month: "long" });
  }
  const from = startOfWeek(state.cursor);
  const to = addDays(from, 6);
  return `${from.toLocaleDateString("ru-RU", { day: "numeric", month: "short" })} — ${to.toLocaleDateString("ru-RU", { day: "numeric", month: "short" })}`;
}

function visibleRange() {
  if (state.mode === "month") {
    const first = startOfMonth(state.cursor);
    const gridStart = startOfWeek(first);
    return { from: isoDate(gridStart), to: isoDate(addDays(gridStart, 41)) };
  }
  if (state.mode === "week") {
    const from = startOfWeek(state.cursor);
    return { from: isoDate(from), to: isoDate(addDays(from, 6)) };
  }
  const day = isoDate(state.cursor);
  return { from: day, to: day };
}

function isRepik(event) {
  return String(event.source || "").toLowerCase() === "classhub" || String(event.title || "").toUpperCase() === "РЕПИК";
}

function eventColorClass(event) {
  if (isRepik(event)) {
    return isOnlineLesson(event) ? "repik-online" : "repik-offline";
  }
  return event.importance || "medium";
}

function isOnlineLesson(event) {
  const loc = String(event.locationType || "").toUpperCase();
  if (loc === "ONLINE") return true;
  if (loc === "OFFLINE") return false;
  return /формат:\s*онлайн/i.test(String(event.description || ""));
}

function visibleEvents() {
  return state.events.filter((event) => {
    if (state.hideRepik && isRepik(event)) return false;
    if (state.filterPerson && String(event.author || "").toLowerCase() !== state.filterPerson.toLowerCase()) return false;
    return true;
  });
}

function peopleNames() {
  const seen = new Map();
  state.events.forEach((event) => {
    if (isRepik(event)) return;
    const name = String(event.author || "").trim();
    if (name) seen.set(name.toLowerCase(), name);
  });
  return [...seen.values()].sort((a, b) => a.localeCompare(b, "ru"));
}

function eventsOn(iso) {
  return visibleEvents().filter((e) => e.date === iso);
}

function minutesOf(time) {
  const [h, m] = String(time || "00:00").split(":").map(Number);
  return (h || 0) * 60 + (m || 0);
}

function formatMinutes(total) {
  const n = ((Number(total) % (24 * 60)) + 24 * 60) % (24 * 60);
  return `${pad(Math.floor(n / 60))}:${pad(n % 60)}`;
}

function layoutDayEvents(events) {
  const pending = events
    .map((event) => ({
      event,
      start: minutesOf(event.time),
      end: minutesOf(event.time) + Math.max(15, event.durationMinutes || 60),
      col: 0,
      cols: 1,
    }))
    .sort((a, b) => a.start - b.start || a.end - b.end || a.event.id - b.event.id);

  const result = [];
  let cluster = [];
  let clusterEnd = -1;

  const flush = () => {
    if (!cluster.length) return;
    const colEnds = [];
    cluster
      .slice()
      .sort((a, b) => a.start - b.start || a.end - b.end)
      .forEach((item) => {
        let placed = colEnds.findIndex((end) => end <= item.start);
        if (placed < 0) {
          placed = colEnds.length;
          colEnds.push(item.end);
        } else {
          colEnds[placed] = item.end;
        }
        item.col = placed;
      });
    const cols = Math.max(1, colEnds.length);
    cluster.forEach((item) => {
      item.cols = cols;
      result.push(item);
    });
    cluster = [];
  };

  pending.forEach((item) => {
    if (cluster.length && item.start >= clusterEnd) flush();
    cluster.push(item);
    clusterEnd = Math.max(clusterEnd, item.end);
  });
  flush();
  return result;
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    method: opts.method || "GET",
    headers: opts.body ? { "Content-Type": "application/json" } : undefined,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : {};
  if (!res.ok) throw new Error(data.error || `Ошибка сервера (${res.status})`);
  return data;
}

function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add("hidden"), 2800);
}

function showGate(force = false) {
  if (state.name && !force) {
    $("#gate").classList.add("hidden");
    $("#app").classList.remove("hidden");
    $("#who").textContent = state.name;
    loadAndRender();
    return;
  }
  $("#app").classList.add("hidden");
  $("#gate").classList.remove("hidden");
  $("#gate").innerHTML = `
    <form class="gate-card" id="name-form">
      <h1>Как вас зовут?</h1>
      <p>Имя будет видно всем в общем календаре рядом с добавленными делами.</p>
      <label>Имя<input id="name-input" value="${escapeHtml(state.name)}" maxlength="80" required autofocus></label>
      <button class="btn-primary" type="submit">Продолжить</button>
    </form>`;
  $("#name-form").onsubmit = (ev) => {
    ev.preventDefault();
    const name = $("#name-input").value.trim();
    if (!name) return;
    state.name = name;
    localStorage.setItem(NAME_KEY, name);
    showGate();
  };
}

function escapeHtml(s) {
  return String(s || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function loadAndRender() {
  const { from, to } = visibleRange();
  try {
    state.events = await api(`/api/plan/events?from=${from}&to=${to}`);
  } catch (err) {
    toast(err.message);
    state.events = [];
  }
  render();
}

function render() {
  $("#period-label").textContent = rangeLabel();
  document.querySelectorAll("#modes .chip").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.mode === state.mode);
  });
  renderFilters();
  if (state.mode === "month") renderMonth();
  else if (state.mode === "day") renderDayAgenda();
  else renderWeekGrid();
}

function renderFilters() {
  const root = $("#filters");
  if (!root) return;
  const current = (state.filterPerson || "").toLowerCase();
  const people = peopleNames().map((name) => {
    const active = name.toLowerCase() === current ? " active" : "";
    return `<button class="chip${active}" data-person="${escapeHtml(name)}">${escapeHtml(name)}</button>`;
  });
  const hideActive = state.hideRepik ? " active" : "";
  people.push(`<button class="chip${hideActive}" data-hide-repik="1">Скрыть репик</button>`);
  if (state.filterPerson || state.hideRepik) {
    people.push(`<button class="chip" data-clear-filters="1">Сбросить</button>`);
  }
  root.innerHTML = people.join("");
}

function renderMonth() {
  const first = startOfMonth(state.cursor);
  const gridStart = startOfWeek(first);
  const today = isoDate(startOfToday());
  const heads = WEEKDAYS.map((d) => `<div class="month-head">${d}</div>`).join("");
  const cells = [];
  for (let i = 0; i < 42; i++) {
    const day = addDays(gridStart, i);
    const iso = isoDate(day);
    const inMonth = day.getMonth() === state.cursor.getMonth();
    const weekend = day.getDay() === 0 || day.getDay() === 6;
    const items = eventsOn(iso)
      .map((e) => `
        <button class="month-item ${eventColorClass(e)}" data-id="${e.id}">
          <span class="month-time">${e.time}</span>
          <span class="month-who">${escapeHtml(e.title)} · ${escapeHtml(e.author)}</span>
        </button>`)
      .join("");
    cells.push(`
      <div class="month-cell ${inMonth ? "" : "empty"} ${weekend ? "weekend" : ""} ${iso === today ? "today" : ""}" data-date="${iso}">
        <div class="month-num">${day.getDate()}</div>
        ${items}
      </div>`);
  }
  $("#calendar").innerHTML = `<div class="month-wrap"><div class="month-grid">${heads}${cells.join("")}</div></div>`;
  $("#calendar").querySelectorAll(".month-item").forEach((el) => {
    el.onclick = (ev) => {
      ev.stopPropagation();
      openEditor(Number(el.dataset.id));
    };
  });
  $("#calendar").querySelectorAll(".month-cell").forEach((el) => {
    el.ondblclick = () => openEditor(null, el.dataset.date);
  });
}

function renderDayAgenda() {
  const iso = isoDate(state.cursor);
  const items = eventsOn(iso).slice().sort((a, b) => minutesOf(a.time) - minutesOf(b.time) || a.id - b.id);
  const title = state.cursor.toLocaleDateString("ru-RU", { weekday: "long", day: "numeric", month: "long" });
  const heading = title.charAt(0).toUpperCase() + title.slice(1);
  if (!items.length) {
    $("#calendar").innerHTML = `<div class="day-agenda"><h3>${heading}</h3><div class="card empty">На этот день дел нет</div></div>`;
    return;
  }
  const first = minutesOf(items[0].time);
  const last = Math.max(...items.map((e) => minutesOf(e.time) + (e.durationMinutes || 60)));
  const cards = items.map((e) => {
    const dur = e.durationMinutes || 60;
    const start = minutesOf(e.time);
    const preview = (e.description || "").split("\n").filter(Boolean)[0] || `${dur} мин`;
    return `<button type="button" class="day-event ${eventColorClass(e)}" data-id="${e.id}">
      <div class="day-event-time"><b>${e.time}</b><span class="muted">${formatMinutes(start + dur)}</span></div>
      <div class="day-event-body">
        <b>${escapeHtml(e.title)}</b>
        <div class="muted">${escapeHtml(e.author)} · ${escapeHtml(preview)}</div>
      </div>
      <div class="day-event-flags"><span class="chip ${e.importance}">${IMPORTANCE_LABEL[e.importance] || e.importance}</span></div>
    </button>`;
  }).join("");
  $("#calendar").innerHTML = `<div class="day-agenda">
    <div>
      <h3>${heading}</h3>
      <div class="muted">${items.length} ${items.length === 1 ? "дело" : items.length < 5 ? "дела" : "дел"} · ${formatMinutes(first)}–${formatMinutes(last)}</div>
    </div>
    ${cards}
  </div>`;
  $("#calendar").querySelectorAll(".day-event").forEach((el) => {
    el.onclick = () => openEditor(Number(el.dataset.id));
  });
}

function renderWeekGrid() {
  const start = startOfWeek(state.cursor);
  start.setHours(0, 0, 0, 0);
  const today = isoDate(startOfToday());
  const hours = HOUR_END - HOUR_START + 1;
  const visFrom = HOUR_START * 60;
  const visTo = (HOUR_END + 1) * 60;
  const heads = Array.from({ length: 7 }, (_, i) => {
    const d = addDays(start, i);
    const iso = isoDate(d);
    const label = d.toLocaleDateString("ru-RU", { weekday: "short", day: "numeric" });
    return `<div class="hour-head ${iso === today ? "today" : ""}">${label}</div>`;
  }).join("");
  const labels = Array.from({ length: hours }, (_, i) =>
    `<div class="hour-label">${pad(HOUR_START + i)}:00</div>`
  ).join("");
  const cols = Array.from({ length: 7 }, (_, i) => {
    const iso = isoDate(addDays(start, i));
    const placed = layoutDayEvents(eventsOn(iso));
    const lines = Array.from({ length: hours }, (_, idx) =>
      `<div class="hour-line" style="top:${idx * HOUR_H}px"></div>`
    ).join("");
    const blocks = placed.map((item) => {
      const topMin = Math.max(item.start, visFrom);
      const botMin = Math.min(item.end, visTo);
      if (botMin <= topMin) return "";
      const top = ((topMin - visFrom) / 60) * HOUR_H;
      const height = Math.max(((botMin - topMin) / 60) * HOUR_H, 18);
      const width = 100 / item.cols;
      const left = (item.col * 100) / item.cols;
      return `<button type="button" class="hour-event ${eventColorClass(item.event)}" data-id="${item.event.id}"
        style="top:${top + 1}px;height:${Math.max(height - 2, 16)}px;left:calc(${left}% + 1px);width:calc(${width}% - 2px)">
        ${escapeHtml(item.event.title)}<small>${escapeHtml(item.event.author)}</small>
      </button>`;
    }).join("");
    return `<div class="day-col"><div class="day-track" style="height:${hours * HOUR_H}px">${lines}${blocks}</div></div>`;
  }).join("");
  $("#calendar").innerHTML = `
    <div class="hour-wrap">
      <div class="week-board days-7">
        <div class="hour-corner"></div>
        ${heads}
        <div class="time-col">${labels}</div>
        ${cols}
      </div>
    </div>`;
  $("#calendar").querySelectorAll(".hour-event").forEach((el) => {
    el.onclick = () => openEditor(Number(el.dataset.id));
  });
}

function closeModal() {
  $("#modal-root").innerHTML = "";
}

function openEditor(id, presetDate) {
  const existing = id || id === 0 ? state.events.find((e) => Number(e.id) === Number(id)) : null;
  const readonly = Boolean(existing?.readonly || existing?.source === "classhub");
  const dateValue = existing?.date || presetDate || isoDate(state.cursor);
  const timeValue = existing?.time || "10:00";
  const importance = existing?.importance || "medium";
  const lock = readonly ? "disabled" : "";
  $("#modal-root").innerHTML = `
    <div class="modal-backdrop" id="backdrop">
      <form class="modal" id="event-form">
        <h3>${existing ? (readonly ? "Занятие ClassHub" : "Дело") : "Новое дело"}</h3>
        ${readonly ? `<p class="muted" style="margin:0">Это занятие из ClassHub. В планировании его можно только просматривать.</p>` : ""}
        <div class="form-grid">
          <label>Название<input name="title" value="${escapeHtml(existing?.title || "")}" required maxlength="200" ${lock}></label>
          <div class="form-row">
            <label>Дата<input type="date" name="date" value="${dateValue}" required ${lock}></label>
            <label>Время<input type="time" name="time" value="${timeValue}" required ${lock}></label>
          </div>
          <label>Длительность, мин
            <input type="number" name="durationMinutes" min="15" max="1440" step="15" value="${existing?.durationMinutes || 60}" ${lock}>
          </label>
          <label>Описание<textarea name="description" ${lock}>${escapeHtml(existing?.description || "")}</textarea></label>
          <div>
            <div class="muted" style="font-size:13px;font-weight:600;margin-bottom:6px">Важность</div>
            <div class="importance-row" id="imp">
              ${["low", "medium", "high"].map((key) => `
                <button type="button" class="chip ${importance === key ? "active" : ""}" data-imp="${key}" ${lock}>${IMPORTANCE_LABEL[key]}</button>
              `).join("")}
            </div>
          </div>
          ${existing ? `<div style="color:var(--muted);font-size:13px">${readonly ? "Ученик" : "Добавил"}: <b>${escapeHtml(existing.author)}</b></div>` : ""}
        </div>
        <div class="row" style="justify-content:space-between;margin-top:8px">
          <div>${existing && !readonly ? `<button type="button" class="btn-danger" id="del">Удалить</button>` : ""}</div>
          <div class="row">
            <button type="button" class="btn-ghost" id="cancel">${readonly ? "Закрыть" : "Отмена"}</button>
            ${readonly ? "" : `<button class="btn-primary" type="submit">Сохранить</button>`}
          </div>
        </div>
      </form>
    </div>`;
  let selectedImp = importance;
  if (!readonly) {
    $("#imp").onclick = (ev) => {
      const btn = ev.target.closest("[data-imp]");
      if (!btn) return;
      selectedImp = btn.dataset.imp;
      $("#imp").querySelectorAll(".chip").forEach((c) => c.classList.toggle("active", c === btn));
    };
  }
  $("#cancel").onclick = closeModal;
  $("#backdrop").onclick = (ev) => { if (ev.target.id === "backdrop") closeModal(); };
  $("#del")?.addEventListener("click", async () => {
    if (!confirm("Удалить это дело?")) return;
    try {
      await api(`/api/plan/events/${id}`, { method: "DELETE" });
      closeModal();
      loadAndRender();
    } catch (err) { toast(err.message); }
  });
  $("#event-form").onsubmit = async (ev) => {
    ev.preventDefault();
    if (readonly) return;
    const form = ev.target;
    const body = {
      title: form.title.value.trim(),
      description: form.description.value.trim(),
      date: form.date.value,
      time: form.time.value.slice(0, 5),
      durationMinutes: Number(form.durationMinutes.value || 60),
      importance: selectedImp,
      author: state.name,
    };
    try {
      if (existing) await api(`/api/plan/events/${id}`, { method: "PUT", body });
      else await api("/api/plan/events", { method: "POST", body });
      closeModal();
      loadAndRender();
    } catch (err) { toast(err.message); }
  };
}

function shift(delta) {
  const d = new Date(state.cursor);
  if (state.mode === "month") d.setMonth(d.getMonth() + delta);
  else d.setDate(d.getDate() + delta * (state.mode === "week" ? 7 : 1));
  state.cursor = d;
  loadAndRender();
}

$("#prev").onclick = () => shift(-1);
$("#next").onclick = () => shift(1);
$("#today").onclick = () => { state.cursor = startOfToday(); state.mode = "day"; loadAndRender(); };
$("#add").onclick = () => openEditor(null, isoDate(state.cursor));
$("#change-name").onclick = () => showGate(true);
$("#open-settings").onclick = () => openSettings();
$("#modes").onclick = (ev) => {
  const btn = ev.target.closest("[data-mode]");
  if (!btn) return;
  state.mode = btn.dataset.mode;
  loadAndRender();
};
$("#filters").onclick = (ev) => {
  const clear = ev.target.closest("[data-clear-filters]");
  if (clear) {
    state.filterPerson = "";
    state.hideRepik = false;
    render();
    return;
  }
  const hide = ev.target.closest("[data-hide-repik]");
  if (hide) {
    state.hideRepik = !state.hideRepik;
    render();
    return;
  }
  const person = ev.target.closest("[data-person]");
  if (!person) return;
  const name = person.dataset.person || "";
  state.filterPerson = state.filterPerson.toLowerCase() === name.toLowerCase() ? "" : name;
  render();
};

function minutesToTime(total) {
  const value = Number(total || 0);
  return `${pad(Math.floor(value / 60))}:${pad(value % 60)}`;
}

async function openSettings() {
  let settings = {};
  let statusHtml = `<p class="muted">Сервер ещё не отправлял список дел</p>`;
  try {
    settings = await api("/api/plan/settings");
  } catch (err) {
    toast(err.message);
    return;
  }
  try {
    const st = await api("/api/plan/telegram/status");
    const parts = [];
    if (st.lastSent) parts.push(`Последняя отправка: ${st.lastSent}`);
    if (st.lastAt) parts.push(`Попытка: ${st.lastAt}`);
    if (st.lastError) parts.push(`Ошибка: ${st.lastError}`);
    if (parts.length) statusHtml = `<p class="muted">${parts.join(" · ")}</p>`;
  } catch (err) {
    statusHtml = `<p class="muted">${err.message}</p>`;
  }
  const chatIds = (settings.chatIds || []).join("\n");
  $("#modal-root").innerHTML = `
    <div class="modal-backdrop" id="backdrop">
      <form class="modal" id="settings-form">
        <h3>Настройки</h3>
        <div class="form-grid">
          <label>Напоминать за (минут)
            <input type="number" name="reminderMinutes" min="1" max="1440" value="${settings.reminderMinutes || 30}">
          </label>
          <p class="muted" style="margin:0">Телефон покажет уведомление за это время до начала дела. Настраивается здесь, в приложении отдельного экрана нет.</p>
          <label>Токен Telegram-бота<input name="token" value="${escapeHtml(settings.telegramBotToken || "")}"></label>
          <label>Chat ID (по одному в строке)<textarea name="chats">${escapeHtml(chatIds)}</textarea></label>
          <label class="check-row">
            <input type="checkbox" name="daily" ${settings.dailyScheduleEnabled ? "checked" : ""}>
            Отправлять список дел каждый день
          </label>
          <label>Время отправки<input type="time" name="time" value="${minutesToTime(settings.dailyScheduleMinutes || 420)}"></label>
          ${statusHtml}
        </div>
        <div class="row" style="justify-content:space-between;margin-top:8px">
          <button type="button" class="btn-outline" id="tg-test">Тест в Telegram</button>
          <div class="row">
            <button type="button" class="btn-ghost" id="cancel">Закрыть</button>
            <button class="btn-primary" type="submit">Сохранить</button>
          </div>
        </div>
      </form>
    </div>`;
  $("#cancel").onclick = closeModal;
  $("#backdrop").onclick = (ev) => { if (ev.target.id === "backdrop") closeModal(); };
  $("#tg-test").onclick = async () => {
    try {
      await api("/api/plan/telegram/daily", { method: "POST", body: { test: true } });
      toast("Тест отправлен");
    } catch (err) { toast(err.message); }
  };
  $("#settings-form").onsubmit = async (ev) => {
    ev.preventDefault();
    const form = ev.target;
    const [h, m] = (form.time.value || "07:00").split(":").map(Number);
    try {
      await api("/api/plan/settings", {
        method: "PUT",
        body: {
          reminderMinutes: Number(form.reminderMinutes.value || 30),
          telegramBotToken: form.token.value.trim(),
          chatIds: form.chats.value.split(/[\n,;]+/).map((x) => x.trim()).filter(Boolean),
          dailyScheduleEnabled: form.daily.checked,
          dailyScheduleMinutes: (h || 0) * 60 + (m || 0),
        },
      });
      toast("Сохранено");
      closeModal();
    } catch (err) { toast(err.message); }
  };
}

showGate();
