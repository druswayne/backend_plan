const state = { route: "home", params: {}, month: null };

function $(sel, root = document) {
  return root.querySelector(sel);
}

function toast(text) {
  const el = $("#toast");
  el.textContent = text;
  el.classList.remove("hidden");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.add("hidden"), 2800);
}

async function api(url, options = {}) {
  const init = { ...options, credentials: "same-origin", headers: { ...(options.headers || {}) } };
  if (init.body && typeof init.body !== "string" && !(init.body instanceof FormData)) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(init.body);
  }
  const res = await fetch(url, init);
  if (res.status === 401) {
    window.location.href = "/login";
    throw new Error("Нужна авторизация");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Ошибка запроса");
  return data;
}

function money(v) {
  return `${Number(v || 0).toFixed(2)} BYN`;
}

function pad(n) {
  return String(n).padStart(2, "0");
}

function fromEpoch(day) {
  return new Date(Number(day) * 86400000);
}

function toEpoch(date) {
  return Math.floor(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()) / 86400000);
}

function fmtDate(epoch) {
  const d = fromEpoch(epoch);
  const months = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
  return `${d.getUTCDate()} ${months[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

function fmtTime(min) {
  return `${pad(Math.floor(min / 60))}:${pad(min % 60)}`;
}

function fmtRange(start, duration) {
  return `${fmtTime(start)}–${fmtTime(start + duration)}`;
}

function shortPerson(name) {
  return String(name || "").trim().split(/\s+/)[0] || "";
}

const SUBJECT_SHORT = {
  английский: "Англ.",
  "английский язык": "Англ.",
  математика: "Матем.",
  матем: "Матем.",
  алгебра: "Алг.",
  алге: "Алг.",
  геометрия: "Геом.",
  геом: "Геом.",
  информатика: "Инф.",
  инф: "Инф.",
  программирование: "Прогр.",
  прога: "Прогр.",
  "русский язык": "Рус.",
  русский: "Рус.",
  физика: "Физ.",
  химия: "Хим.",
  биология: "Биол.",
  история: "Ист.",
  география: "Геогр.",
  литература: "Лит.",
  обществознание: "Общ.",
  немецкий: "Нем.",
  французский: "Фр.",
};

function shortSubject(name) {
  const raw = String(name || "Предмет").trim();
  const key = raw.toLowerCase();
  if (SUBJECT_SHORT[key]) return SUBJECT_SHORT[key];
  const hit = Object.keys(SUBJECT_SHORT).sort((a, b) => b.length - a.length).find((k) => key.startsWith(k));
  if (hit) return SUBJECT_SHORT[hit];
  const word = raw.split(/[\s/]+/)[0];
  const base = word.slice(0, 4);
  return `${base.charAt(0).toUpperCase()}${base.slice(1).toLowerCase()}${word.length > 4 ? "." : ""}`;
}

function isoDate(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function avatar(name) {
  const colors = ["#6366f1", "#14b8a6", "#4338ca", "#8b5cf6"];
  const color = colors[Math.abs(hash(name || "")) % colors.length];
  return `<div class="avatar" style="background:${color}22;color:${color}">${(name || "?")[0].toUpperCase()}</div>`;
}

function hash(s) {
  let h = 0;
  for (const ch of s) h = (h * 31 + ch.charCodeAt(0)) | 0;
  return h;
}

const STATUS = { EXPECTED: "Ожидается", CONDUCTED: "Проведено", CANCELLED: "Отменено" };

function chip(status, paid) {
  const cls = status === "CONDUCTED" ? "conducted" : status === "CANCELLED" ? "cancelled" : "expected";
  return `<span class="chip ${cls}">${STATUS[status] || status}</span>${paid ? '<span class="chip paid">Оплачено</span>' : ""}`;
}

function val(id) {
  return document.getElementById(id)?.value;
}

function pluralRu(n, one, few, many) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

function openModal(html) {
  $("#modal-root").innerHTML = `<div class="modal-backdrop"><div class="modal">${html}</div></div>`;
  $(".modal-backdrop").addEventListener("click", (e) => {
    if (e.target.classList.contains("modal-backdrop")) closeModal();
  });
}

function closeModal() {
  $("#modal-root").innerHTML = "";
}

function parseHash() {
  const raw = (location.hash || "#/home").replace(/^#\//, "");
  const parts = raw.split("/");
  state.route = parts[0] || "home";
  state.params = { id: parts[1] };
}

function setNav() {
  document.querySelectorAll(".nav a").forEach((a) => {
    a.classList.toggle("active", a.dataset.route === state.route);
  });
}

async function render() {
  parseHash();
  setNav();
  $("#app").innerHTML = `<div class="page"><div class="card">Загрузка…</div></div>`;
  try {
    const map = {
      home: renderHome,
      students: renderStudents,
      student: renderStudent,
      journals: renderJournals,
      journal: renderJournal,
      entry: renderEntry,
      calendar: renderCalendar,
      lesson: renderLesson,
      payments: renderPayments,
      settings: renderSettings,
    };
    await (map[state.route] || renderHome)();
  } catch (e) {
    $("#app").innerHTML = `<div class="page"><div class="card empty">${e.message}</div></div>`;
  }
}

function lessonCard(lesson) {
  const occ = lesson.occurrence || lesson.occurrence;
  return `<div class="card clickable lesson-card" data-open="${occ.id}">
    ${avatar(lesson.student.name)}
    <div>
      <b>${lesson.student.name}</b> · ${lesson.subjectName}<br>
      <span class="muted">${fmtDate(occ.dateEpochDay)} · ${fmtRange(occ.startTimeMinutes, occ.durationMinutes)}</span>
    </div>
    <div class="actions">
      ${chip(occ.status, lesson.isFullyPaid ?? lesson.isFullyPaid)}
      ${occ.status === "EXPECTED" ? `<button type="button" class="btn-icon ok" data-status="${occ.id}:CONDUCTED" title="Проведено">✓</button>
      <button type="button" class="btn-icon no" data-status="${occ.id}:CANCELLED" title="Отменить">✕</button>` : ""}
    </div>
  </div>`;
}

async function setStatus(id, status) {
  try {
    await api(`/api/lessons/${id}/status`, { method: "PATCH", body: { status } });
    toast("Статус обновлён");
    render();
  } catch (e) {
    toast(e.message);
  }
}

async function renderHome() {
  const data = await api("/api/home" + (state.month ? `?month=${state.month}` : ""));
  const m = data.stats.monthly;
  $("#app").innerHTML = `
    <div class="page">
      <div class="hero">
        <h1>ClassHub</h1>
        <p>Учёт занятий репетитора</p>
        <p style="margin-top:16px">
          <a class="btn-primary" href="/plan" style="background:#fff;color:#4338ca">Совместное планирование</a>
        </p>
      </div>
      <div class="row space">
        <button class="btn-outline" id="pm">←</button><b>${data.monthLabel}</b><button class="btn-outline" id="nm">→</button>
      </div>
      <div class="grid cols-3">
        <div class="card"><div class="muted">Учеников</div><div class="stat">${data.stats.studentCount ?? data.stats.studentCount}</div></div>
        <div class="card"><div class="muted">Неделя</div><div class="stat">${data.stats.weekly.conducted} / ${data.stats.weekly.total}</div></div>
        <div class="card"><div class="muted">Доход</div><div class="stat" style="font-size:20px">${money(m.earned)}</div></div>
      </div>
      <div class="card">Занятия: <b>${m.conductedCount}</b> / ${m.plannedCount} · оплачено ${money(m.paidAmount)} · к оплате ${money(m.unpaidAmount)}</div>
      ${data.ongoing.length ? `<div class="section-title">Сейчас идёт</div>${data.ongoing.map(lessonCard).join("")}` : ""}
      ${(data.needsStatus || data.needsStatus || []).length ? `<div class="section-title">Нужно отметить</div>${(data.needsStatus || data.needsStatus).map(lessonCard).join("")}` : ""}
      <div class="section-title">Ближайшие занятия</div>
      ${data.upcoming.length ? data.upcoming.map(lessonCard).join("") : `<div class="card empty">Нет предстоящих занятий</div>`}
    </div>`;
  $("#pm").onclick = () => { state.month = shiftMonth(data.month, -1); render(); };
  $("#nm").onclick = () => { state.month = shiftMonth(data.month, 1); render(); };
}

function shiftMonth(iso, delta) {
  const [y, m] = iso.split("-").map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-01`;
}

async function renderStudents() {
  const archived = state.params.id === "archive";
  const list = await api(`/api/students?archived=${archived ? 1 : 0}`);
  $("#app").innerHTML = `
    <div class="page">
      <div class="row space">
        <h2>${archived ? "Архив" : "Ученики"}</h2>
        <div class="toolbar">
          <a class="btn-outline" href="${archived ? "#/students" : "#/students/archive"}">${archived ? "Активные" : "Архив"}</a>
          ${archived ? "" : `<button class="btn-primary" id="add">+ Ученик</button>`}
        </div>
      </div>
      ${list.length ? list.map((s) => `<div class="card clickable row" data-student="${s.id}">
        ${avatar(s.name)}<div><b>${s.name}</b><div class="muted">${s.subjectsLabel} · ${s.grade || ""}</div></div>
      </div>`).join("") : `<div class="card empty">${archived ? "Архив пуст" : "Добавьте первого ученика"}</div>`}
    </div>`;
  $("#add")?.addEventListener("click", addStudentModal);
}

function addStudentModal() {
  openModal(`<h3>Новый ученик</h3>
    <label>Имя<input id="n"></label><label>Класс<input id="g"></label><label>Адрес<input id="a"></label>
    <div id="subs"></div><button class="btn-outline" id="add-s">+ Предмет</button>
    <div class="row space" style="margin-top:12px"><button class="btn-ghost" id="c">Отмена</button><button class="btn-primary" id="s">Создать</button></div>`);
  const box = $("#subs");
  const add = () => {
    const d = document.createElement("div");
    d.className = "row";
    d.innerHTML = `<input class="sn" placeholder="Предмет"><input class="sp" type="number" placeholder="Цена">`;
    box.appendChild(d);
  };
  add();
  $("#add-s").onclick = add;
  $("#c").onclick = closeModal;
  $("#s").onclick = async () => {
    const subjects = [...box.querySelectorAll(".row")].map((r) => ({
      name: r.querySelector(".sn").value, price: Number(r.querySelector(".sp").value),
    })).filter((x) => x.name);
    try {
      const res = await api("/api/students", { method: "POST", body: { name: val("n"), grade: val("g"), address: val("a"), subjects } });
      closeModal(); location.hash = `#/student/${res.id}`;
    } catch (e) { toast(e.message); }
  };
}

async function renderStudent() {
  const data = await api(`/api/students/${state.params.id}${state.month ? `?month=${state.month}` : ""}`);
  const s = data.student;
  $("#app").innerHTML = `
    <div class="page">
      <div class="row space"><a class="btn-ghost" href="#/students">← Назад</a>
        <div class="toolbar">
          <button class="btn-outline" id="edit">Изменить</button>
          <button class="btn-outline" id="arch">${s.isArchived ? "Восстановить" : "В архив"}</button>
          <button class="btn-danger" id="del">Удалить</button>
        </div>
      </div>
      <div class="card row">${avatar(s.name)}<div><h2 style="margin:0">${s.name}</h2><div class="muted">${s.grade || ""} ${s.address ? "· " + s.address : ""}</div></div></div>
      <div class="card"><div class="row space"><b>Предметы</b><button class="btn-outline" id="add-sub">+</button></div>
        ${(s.subjects || []).map((sub) => `<div class="row space" style="margin-top:8px"><span>${sub.name} · ${money(sub.price)}</span>
          <span><button class="btn-outline" data-editsub='${JSON.stringify(sub)}'>✎</button>
          <button class="btn-danger" data-delsub="${sub.id}">✕</button></span></div>`).join("")}
      </div>
      <div class="row space"><button class="btn-outline" id="pm">←</button><b>${data.monthLabel}</b><button class="btn-outline" id="nm">→</button></div>
      <div class="card">Баланс <b>${money(data.balance)}</b> · проведено ${data.stats.conductedCount}/${data.stats.plannedCount}</div>
      <div class="toolbar"><button class="btn-primary" id="nl">+ Занятие</button><button class="btn-outline" id="np">+ Оплата</button></div>
      ${(data.lessons || []).map((occ) => `<div class="card clickable" data-open="${occ.id}"><b>${fmtDate(occ.dateEpochDay)} ${fmtRange(occ.startTimeMinutes, occ.durationMinutes)}</b><div class="muted">${occ.subjectName || ""}</div>${chip(occ.status, occ.paidAmount >= occ.price - 0.001)}</div>`).join("") || `<div class="card empty">Нет занятий</div>`}
      ${(data.payments || []).map((p) => `<div class="card row space"><div><b>${money(p.amount)}</b><div class="muted">${new Date(p.createdAt).toLocaleString("ru")} ${p.note || ""}</div></div><button class="btn-danger" data-delpay="${p.id}">Удалить</button></div>`).join("")}
    </div>`;
  $("#pm").onclick = () => { state.month = shiftMonth(data.month, -1); render(); };
  $("#nm").onclick = () => { state.month = shiftMonth(data.month, 1); render(); };
  $("#nl").onclick = () => lessonModal(s);
  $("#np").onclick = () => paymentModal(s.id);
  $("#add-sub").onclick = () => subjectModal(s.id);
  $("#arch").onclick = async () => { await api(`/api/students/${s.id}/archive`, { method: "POST", body: { archived: !s.isArchived } }); render(); };
  $("#del").onclick = async () => { if (confirm("Удалить ученика?")) { await api(`/api/students/${s.id}`, { method: "DELETE" }); location.hash = "#/students"; } };
  $("#edit").onclick = () => {
    openModal(`<h3>Ученик</h3><label>Имя<input id="n" value="${s.name}"></label><label>Класс<input id="g" value="${s.grade || ""}"></label><label>Адрес<input id="a" value="${s.address || ""}"></label>
      <div class="row space" style="margin-top:12px"><button class="btn-ghost" id="c">Отмена</button><button class="btn-primary" id="sv">Сохранить</button></div>`);
    $("#c").onclick = closeModal;
    $("#sv").onclick = async () => { await api(`/api/students/${s.id}`, { method: "PUT", body: { name: val("n"), grade: val("g"), address: val("a") } }); closeModal(); render(); };
  };
}

function subjectModal(studentId, subject) {
  openModal(`<h3>Предмет</h3><label>Название<input id="n" value="${subject?.name || ""}"></label><label>Цена<input id="p" type="number" value="${subject?.price || ""}"></label>
    <div class="row space" style="margin-top:12px"><button class="btn-ghost" id="c">Отмена</button><button class="btn-primary" id="sv">Сохранить</button></div>`);
  $("#c").onclick = closeModal;
  $("#sv").onclick = async () => {
    try {
      if (subject) await api(`/api/subjects/${subject.id}`, { method: "PUT", body: { name: val("n"), price: Number(val("p")) } });
      else await api(`/api/students/${studentId}/subjects`, { method: "POST", body: { name: val("n"), price: Number(val("p")) } });
      closeModal(); render();
    } catch (e) { toast(e.message); }
  };
}

function paymentModal(studentId) {
  openModal(`<h3>Оплата</h3><label>Сумма<input id="a" type="number"></label><label>Комментарий<input id="n"></label>
    <div class="row space" style="margin-top:12px"><button class="btn-ghost" id="c">Отмена</button><button class="btn-primary" id="sv">Сохранить</button></div>`);
  $("#c").onclick = closeModal;
  $("#sv").onclick = async () => {
    try { await api("/api/payments", { method: "POST", body: { studentId, amount: Number(val("a")), note: val("n") } }); closeModal(); toast("Оплата сохранена"); render(); }
    catch (e) { toast(e.message); }
  };
}

function lessonModal(student) {
  const today = isoDate(new Date());
  openModal(`<h3>Новое занятие</h3>
    <label>Предмет<select id="sub">${(student.subjects || []).map((s) => `<option value="${s.id}">${s.name}</option>`).join("")}</select></label>
    <label>Дата<input id="d" type="date" value="${today}"></label>
    <div class="row"><label>Час<input id="h" type="number" value="14"></label><label>Мин<input id="m" type="number" value="0"></label><label>Длительность<input id="dur" type="number" value="60"></label></div>
    <label>Формат<select id="loc"><option value="ONLINE">Онлайн</option><option value="OFFLINE">Офлайн</option></select></label>
    <label>Адрес<input id="addr" value="${student.address || ""}"></label>
    <label><input type="checkbox" id="w"> Еженедельно</label>
    <label>До<input id="end" type="date" value="${today}"></label>
    <div class="row space" style="margin-top:12px"><button class="btn-ghost" id="c">Отмена</button><button class="btn-primary" id="sv">Создать</button></div>`);
  $("#c").onclick = closeModal;
  $("#sv").onclick = async () => {
    try {
      await api("/api/lessons", { method: "POST", body: {
        studentId: student.id, studentSubjectId: Number(val("sub")), date: val("d"),
        startTimeMinutes: Number(val("h")) * 60 + Number(val("m")), durationMinutes: Number(val("dur")),
        isWeekly: $("#w").checked, endDate: val("end"), locationType: val("loc"), address: val("addr"),
      } });
      closeModal(); toast("Занятие создано"); render();
    } catch (e) { toast(e.message); }
  };
}

async function renderJournals() {
  const list = await api("/api/journals");
  $("#app").innerHTML = `<div class="page"><h2>Журналы</h2><input id="q" placeholder="Поиск…"><div id="list"></div></div>`;
  const draw = (q = "") => {
    const items = list.filter((i) => `${i.student.name} ${i.student.grade} ${i.student.subjectsLabel} ${i.lastNotePreview}`.toLowerCase().includes(q.toLowerCase()));
    $("#list").innerHTML = items.map((i) => `<div class="card clickable row" data-journal="${i.student.id}">
      ${avatar(i.student.name)}<div><b>${i.student.name}</b><div class="muted">${i.lastNotePreview || "Нет записей"}</div></div></div>`).join("") || `<div class="card empty">Ничего не найдено</div>`;
  };
  draw();
  $("#q").oninput = (e) => draw(e.target.value);
}

async function renderJournal() {
  const data = await api(`/api/journals/${state.params.id}`);
  const item = (i) => `<div class="card clickable" data-entry="${i.occurrence.id}"><b>${fmtDate(i.occurrence.dateEpochDay)} · ${i.subjectName}</b><div class="muted">${i.hasNotes ? i.preview : "Нет записи"}</div></div>`;
  $("#app").innerHTML = `<div class="page"><a class="btn-ghost" href="#/journals">← Журналы</a><h2>${data.student.name}</h2>
    <div class="section-title">Ближайшие</div>${data.upcoming.map(item).join("") || `<div class="card empty">Нет занятий</div>`}
    <div class="section-title">Проведённые</div>${data.conducted.map(item).join("") || `<div class="card empty">Нет записей</div>`}</div>`;
}

async function renderEntry() {
  const data = await api(`/api/lessons/${state.params.id}`);
  const occ = data.occurrence;
  $("#app").innerHTML = `<div class="page"><button class="btn-ghost" onclick="history.back()">← Назад</button>
    <div class="card"><h2>${data.student.name}</h2><div class="muted">${fmtDate(occ.dateEpochDay)} · ${fmtRange(occ.startTimeMinutes, occ.durationMinutes)} · ${data.subjectName}</div>${chip(occ.status, data.isFullyPaid)}</div>
    <label>Запись<textarea id="notes">${occ.notes || ""}</textarea></label>
    <div class="toolbar"><button class="btn-primary" id="sv">Сохранить</button><a class="btn-outline" href="#/lesson/${occ.id}">Занятие</a></div></div>`;
  $("#sv").onclick = async () => { await api(`/api/lessons/${occ.id}/notes`, { method: "PATCH", body: { notes: val("notes") } }); toast("Сохранено"); };
}

let calDate = new Date();
let calMode = "month";

async function renderCalendar() {
  const start = new Date(calDate);
  const end = new Date(calDate);
  if (calMode === "month") { start.setDate(1); end.setMonth(end.getMonth() + 1); end.setDate(0); }
  else if (calMode === "week") { start.setDate(start.getDate() - ((start.getDay() + 6) % 7)); end.setDate(start.getDate() + 6); }
  const lessons = await api(`/api/lessons?start=${isoDate(start)}&end=${isoDate(end)}`);
  $("#app").innerHTML = `<div class="page">
    <div class="row space"><h2>Календарь</h2>
      <div class="chips">${["month", "week", "day"].map((m) => `<span class="chip ${calMode === m ? "active" : ""}" data-mode="${m}">${m === "month" ? "Месяц" : m === "week" ? "Неделя" : "День"}</span>`).join("")}</div>
    </div>
    <div class="week-bar"><button class="btn-outline" id="p">←</button><b>${isoDate(calDate)}</b><button class="btn-outline" id="n">→</button></div>
    <div id="body"></div></div>`;
  $("#p").onclick = () => { moveCal(-1); render(); };
  $("#n").onclick = () => { moveCal(1); render(); };
  document.querySelectorAll("[data-mode]").forEach((el) => { el.onclick = () => { calMode = el.dataset.mode; render(); }; });
  $("#body").innerHTML =
    calMode === "month" ? monthGrid(lessons) : calMode === "day" ? dayAgenda(lessons) : hourGrid(lessons, 7);
}

function moveCal(dir) {
  if (calMode === "month") calDate.setMonth(calDate.getMonth() + dir);
  else calDate.setDate(calDate.getDate() + dir * (calMode === "week" ? 7 : 1));
}

function monthGrid(lessons) {
  const year = calDate.getFullYear();
  const month = calDate.getMonth();
  const first = new Date(year, month, 1);
  const offset = (first.getDay() + 6) % 7;
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells = Array(offset).fill(null).concat([...Array(daysInMonth)].map((_, i) => i + 1));
  while (cells.length % 7) cells.push(null);
  const byDay = {};
  for (const l of lessons) {
    const d = fromEpoch(l.occurrence.dateEpochDay).getUTCDate();
    (byDay[d] = byDay[d] || []).push(l);
  }
  Object.values(byDay).forEach((list) => list.sort((a, b) => a.occurrence.startTimeMinutes - b.occurrence.startTimeMinutes));
  const today = new Date();
  const names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
  return `<div class="month-wrap"><div class="month-grid">${names.map((n) => `<div class="month-head">${n}</div>`).join("")}${cells.map((d, i) => {
    if (!d) return `<div class="month-cell empty"></div>`;
    const items = byDay[d] || [];
    const isToday = today.getDate() === d && today.getMonth() === month && today.getFullYear() === year;
    const weekend = i % 7 >= 5;
    return `<div class="month-cell${isToday ? " today" : ""}${weekend ? " weekend" : ""}">
      <div class="month-num">${d}</div>
      <div class="month-list">${items.map((l) => {
        const st = (l.occurrence.status || "EXPECTED").toLowerCase();
        return `<button type="button" class="month-item ${st}" data-open="${l.occurrence.id}">
          <span class="month-time">${fmtTime(l.occurrence.startTimeMinutes)}</span>
          <span class="month-who">${shortPerson(l.student.name)}</span>
          <span class="month-subj">${shortSubject(l.subjectName)}</span>
        </button>`;
      }).join("")}</div>
    </div>`;
  }).join("")}</div></div>`;
}

function dayAgenda(lessons) {
  const items = lessons
    .filter((l) => {
      const ld = fromEpoch(l.occurrence.dateEpochDay);
      return ld.getUTCDate() === calDate.getDate() && ld.getUTCMonth() === calDate.getMonth() && ld.getUTCFullYear() === calDate.getFullYear();
    })
    .sort((a, b) => a.occurrence.startTimeMinutes - b.occurrence.startTimeMinutes);
  const title = calDate.toLocaleDateString("ru-RU", { weekday: "long", day: "numeric", month: "long" });
  const heading = title.charAt(0).toUpperCase() + title.slice(1);
  if (!items.length) {
    return `<div class="day-agenda"><h3>${heading}</h3><div class="card empty">На этот день занятий нет</div></div>`;
  }
  const first = items[0].occurrence.startTimeMinutes;
  const last = Math.max(...items.map((l) => l.occurrence.startTimeMinutes + (l.occurrence.durationMinutes || 60)));
  return `<div class="day-agenda">
    <div>
      <h3>${heading}</h3>
      <div class="muted">${items.length} ${items.length === 1 ? "занятие" : items.length < 5 ? "занятия" : "занятий"} · ${fmtTime(first)}–${fmtTime(last)}</div>
    </div>
    ${items.map((l) => {
      const occ = l.occurrence;
      const dur = occ.durationMinutes || 60;
      const loc = occ.locationType === "ONLINE" ? "Онлайн" : (occ.address || "Офлайн");
      const st = (occ.status || "EXPECTED").toLowerCase();
      return `<button type="button" class="day-event ${st}" data-open="${occ.id}">
        <div class="day-event-time"><b>${fmtTime(occ.startTimeMinutes)}</b><span class="muted">${fmtTime(occ.startTimeMinutes + dur)}</span></div>
        <div class="day-event-body">
          <b>${l.student.name}</b>
          <div class="muted">${l.subjectName || "Предмет"} · ${dur} мин · ${loc}</div>
        </div>
        <div class="day-event-flags">${chip(occ.status, l.isFullyPaid)}</div>
      </button>`;
    }).join("")}
  </div>`;
}

function hourGrid(lessons, count) {
  const HOUR_START = 7;
  const HOUR_END = 23;
  const HOUR_H = 56;
  const start = new Date(calDate);
  if (count === 7) start.setDate(start.getDate() - ((start.getDay() + 6) % 7));
  const days = [...Array(count)].map((_, i) => { const d = new Date(start); d.setDate(start.getDate() + i); return d; });
  const sameDay = (lesson, day) => {
    const ld = fromEpoch(lesson.occurrence.dateEpochDay);
    return ld.getUTCDate() === day.getDate() && ld.getUTCMonth() === day.getMonth() && ld.getUTCFullYear() === day.getFullYear();
  };
  const pack = (items) => {
    const events = items
      .map((l) => {
        const from = l.occurrence.startTimeMinutes;
        const to = from + (l.occurrence.durationMinutes || 60);
        return { l, from, to, col: 0, cols: 1 };
      })
      .sort((a, b) => a.from - b.from || b.to - a.to);
    const active = [];
    for (const ev of events) {
      for (let i = active.length - 1; i >= 0; i--) {
        if (active[i].to <= ev.from) active.splice(i, 1);
      }
      const used = new Set(active.map((x) => x.col));
      let col = 0;
      while (used.has(col)) col += 1;
      ev.col = col;
      active.push(ev);
      const n = Math.max(...active.map((x) => x.col)) + 1;
      active.forEach((x) => { x.cols = Math.max(x.cols, n); });
    }
    return events;
  };
  const visFrom = HOUR_START * 60;
  const visTo = (HOUR_END + 1) * 60;
  const hours = HOUR_END - HOUR_START + 1;
  let html = `<div class="hour-wrap"><div class="week-board days-${count}"><div class="hour-corner"></div>${days.map((d) => {
    const today = d.toDateString() === new Date().toDateString();
    return `<div class="hour-head${today ? " today" : ""}">${d.toLocaleDateString("ru", { weekday: "short", day: "numeric" })}</div>`;
  }).join("")}<div class="time-col">${[...Array(hours)].map((_, i) => `<div class="hour-label">${pad(HOUR_START + i)}:00</div>`).join("")}</div>`;
  for (const d of days) {
    const events = pack(lessons.filter((l) => sameDay(l, d)));
    html += `<div class="day-col"><div class="day-track" style="height:${hours * HOUR_H}px">`;
    html += [...Array(hours)].map((_, i) => `<div class="hour-line" style="top:${i * HOUR_H}px"></div>`).join("");
    html += events.map((ev) => {
      const topMin = Math.max(ev.from, visFrom);
      const botMin = Math.min(ev.to, visTo);
      if (botMin <= topMin) return "";
      const top = ((topMin - visFrom) / 60) * HOUR_H;
      const height = Math.max(((botMin - topMin) / 60) * HOUR_H, 18);
      const width = 100 / ev.cols;
      const left = (ev.col * 100) / ev.cols;
      const st = (ev.l.occurrence.status || "EXPECTED").toLowerCase();
      return `<button type="button" class="hour-event ${st}" style="top:${top + 1}px;height:${Math.max(height - 2, 16)}px;left:calc(${left}% + 1px);width:calc(${width}% - 2px)" data-open="${ev.l.occurrence.id}">${shortPerson(ev.l.student.name)}<small>${shortSubject(ev.l.subjectName)}</small></button>`;
    }).join("");
    html += `</div></div>`;
  }
  return html + "</div></div>";
}

async function renderLesson() {
  const data = await api(`/api/lessons/${state.params.id}`);
  const occ = data.occurrence;
  $("#app").innerHTML = `<div class="page"><button class="btn-ghost" onclick="history.back()">← Назад</button>
    <div class="card">${avatar(data.student.name)}<h2>${data.student.name}</h2><div class="muted">${data.subjectName}</div>
      <p>${fmtDate(occ.dateEpochDay)} · ${fmtRange(occ.startTimeMinutes, occ.durationMinutes)}</p>
      <p>${occ.locationType === "ONLINE" ? "Онлайн" : occ.address || "Офлайн"} · ${money(data.lessonPrice)}</p>${chip(occ.status, data.isFullyPaid)}</div>
    <div class="card"><div class="section-title">Статус</div><div class="chips">${["EXPECTED", "CONDUCTED", "CANCELLED"].filter((s) => s !== occ.status).map((s) => `<button class="btn-outline" data-status="${occ.id}:${s}">${STATUS[s]}</button>`).join("")}</div></div>
    <div class="card"><textarea id="notes">${occ.notes || ""}</textarea><button class="btn-primary" id="sn" style="margin-top:8px">Сохранить заметки</button></div>
    <div class="toolbar"><button class="btn-outline" id="mv">Перенести</button><button class="btn-danger" id="d1">Удалить занятие</button>
      ${data.series?.isWeekly ? `<button class="btn-danger" id="ds">Удалить серию</button>` : ""}</div></div>`;
  $("#sn").onclick = async () => { await api(`/api/lessons/${occ.id}/notes`, { method: "PATCH", body: { notes: val("notes") } }); toast("Сохранено"); };
  $("#d1").onclick = async () => { if (confirm("Удалить занятие?")) { await api(`/api/lessons/${occ.id}`, { method: "DELETE" }); history.back(); } };
  $("#ds")?.addEventListener("click", async () => { if (confirm("Удалить серию?")) { await api(`/api/series/${occ.seriesId}`, { method: "DELETE" }); history.back(); } });
  $("#mv").onclick = () => {
    const d = fromEpoch(occ.dateEpochDay).toISOString().slice(0, 10);
    openModal(`<h3>Перенести</h3><label>Дата<input id="d" type="date" value="${d}"></label>
      <label>Начало, мин<input id="st" type="number" value="${occ.startTimeMinutes}"></label>
      <label>Длительность<input id="du" type="number" value="${occ.durationMinutes}"></label>
      <label>Формат<select id="loc"><option value="ONLINE">Онлайн</option><option value="OFFLINE">Офлайн</option></select></label>
      <label>Адрес<input id="ad" value="${occ.address || ""}"></label>
      <div class="row space" style="margin-top:12px"><button class="btn-ghost" id="c">Отмена</button><button class="btn-primary" id="sv">Сохранить</button></div>`);
    $("#loc").value = occ.locationType;
    $("#c").onclick = closeModal;
    $("#sv").onclick = async () => {
      try {
        await api(`/api/lessons/${occ.id}/reschedule`, { method: "PATCH", body: { date: val("d"), startTimeMinutes: Number(val("st")), durationMinutes: Number(val("du")), locationType: val("loc"), address: val("ad") } });
        closeModal(); toast("Перенесено"); render();
      } catch (e) { toast(e.message); }
    };
  };
}

let paymentsTab = "unpaid";
const paymentsExpanded = new Set();

async function renderPayments() {
  const [list, unpaid] = await Promise.all([api("/api/payments"), api("/api/payments/unpaid")]);
  const unpaidTotal = unpaid.reduce((sum, item) => sum + Number(item.unpaidAmount || 0), 0);
  const unpaidTabLabel = unpaid.length ? `К оплате (${unpaid.length})` : "К оплате";
  const unpaidHtml = unpaid.length
    ? `<div class="card">
        <div class="muted">К оплате</div>
        <div class="stat amount-due">${money(unpaidTotal)}</div>
        <div class="muted">${unpaid.length} ${pluralRu(unpaid.length, "ученик", "ученика", "учеников")} с неоплаченными занятиями</div>
      </div>` +
      unpaid.map((item) => {
        const student = item.student || {};
        const count = item.unpaidLessonsCount || (item.lessons || []).length;
        const lessons = (item.lessons || []).map((lesson) =>
          `<div class="unpaid-lesson clickable" data-open="${lesson.id}">
            <div>
              <b>${fmtDate(lesson.dateEpochDay)}</b>
              <div class="muted">${lesson.subjectName || "Предмет"} · ${fmtTime(lesson.startTimeMinutes)}</div>
            </div>
            <span class="amount-due">${money(lesson.unpaidAmount)}</span>
          </div>`
        ).join("");
        const expanded = paymentsExpanded.has(String(student.id));
        return `<div class="card unpaid-card${expanded ? " expanded" : ""}" data-unpaid-card="${student.id}">
          <div class="row space unpaid-student">
            <div class="row clickable unpaid-student-main" data-unpaid-toggle="${student.id}">
              ${avatar(student.name)}
              <div class="unpaid-student-info">
                <b>${student.name || "Ученик"}</b>${student.isArchived ? ' <span class="muted">архив</span>' : ""}
                <div class="muted">${count} ${pluralRu(count, "занятие", "занятия", "занятий")} не оплачено</div>
              </div>
            </div>
            <b class="amount-due">${money(item.unpaidAmount)}</b>
            <button type="button" class="btn-icon unpaid-toggle" data-unpaid-toggle="${student.id}" aria-expanded="${expanded ? "true" : "false"}" title="Показать занятия">▾</button>
            <button type="button" class="btn-icon" data-student="${student.id}" title="Открыть ученика">›</button>
          </div>
          <div class="unpaid-lessons"${expanded ? "" : " hidden"}>${lessons}</div>
        </div>`;
      }).join("")
    : `<div class="card empty">Нет неоплаченных занятий</div>`;
  const historyHtml = list.length
    ? list.map((i) => `<div class="card row space"><div class="row">${avatar(i.student?.name || "Ученик")}<div><b>${i.student?.name || "Ученик"}</b><div class="amount-paid">${money(i.payment.amount)}</div><div class="muted">${new Date(i.payment.createdAt).toLocaleString("ru")} ${i.payment.note || ""}</div></div></div><button class="btn-danger" data-delpay="${i.payment.id}">Удалить</button></div>`).join("")
    : `<div class="card empty">Платежей пока нет</div>`;
  $("#app").innerHTML = `<div class="page">
    <h2>Платежи</h2>
    <div class="chips">
      <span class="chip ${paymentsTab === "unpaid" ? "active" : ""}" data-paytab="unpaid">${unpaidTabLabel}</span>
      <span class="chip ${paymentsTab === "history" ? "active" : ""}" data-paytab="history">История</span>
    </div>
    ${paymentsTab === "unpaid" ? unpaidHtml : historyHtml}
  </div>`;
  document.querySelectorAll("[data-paytab]").forEach((el) => {
    el.onclick = () => {
      paymentsTab = el.dataset.paytab;
      render();
    };
  });
  document.querySelectorAll("[data-unpaid-toggle]").forEach((el) => {
    el.onclick = (e) => {
      e.preventDefault();
      e.stopPropagation();
      toggleUnpaidStudent(el.dataset.unpaidToggle);
    };
  });
}

function toggleUnpaidStudent(studentId) {
  const id = String(studentId || "");
  if (!id) return;
  if (paymentsExpanded.has(id)) paymentsExpanded.delete(id);
  else paymentsExpanded.add(id);
  const expanded = paymentsExpanded.has(id);
  const card = document.querySelector(`[data-unpaid-card="${id}"]`);
  if (!card) return;
  card.classList.toggle("expanded", expanded);
  const lessons = card.querySelector(".unpaid-lessons");
  if (lessons) lessons.hidden = !expanded;
  card.querySelectorAll("[data-unpaid-toggle]").forEach((btn) => {
    btn.setAttribute("aria-expanded", expanded ? "true" : "false");
  });
}

async function renderSettings() {
  const s = await api("/api/settings");
  const me = await api("/api/auth/me").catch(() => ({ username: "admin" }));
  applyTheme(s.themeMode);
  const extras = (s.extraChatIds || []).join("\n");
  const minutes = Number(s.dailyScheduleMinutes || 420);
  const hh = String(Math.floor(minutes / 60)).padStart(2, "0");
  const mm = String(minutes % 60).padStart(2, "0");
  let statusHtml = "";
  try {
    const st = await api("/api/telegram/status");
    const parts = [];
    if (st.lastSent) parts.push(`Последняя отправка: ${st.lastSent}`);
    if (st.lastAt) parts.push(`Попытка: ${st.lastAt}`);
    if (st.lastError) parts.push(`Ошибка: ${st.lastError}`);
    statusHtml = parts.length ? `<p class="muted">${parts.join(" · ")}</p>` : `<p class="muted">Сервер ещё не отправлял расписание</p>`;
  } catch (e) {
    statusHtml = `<p class="muted">${e.message}</p>`;
  }
  $("#app").innerHTML = `<div class="page"><h2>Настройки</h2>
    <div class="card"><div class="section-title">Доступ к сайту</div>
      <p class="muted">Эти логин и пароль нужны, чтобы открыть сайт в браузере и чтобы приложение могло писать в базу.</p>
      <label>Логин<input id="site-user" value="${me.username || ""}" autocomplete="username"></label>
      <label>Текущий пароль<input id="site-cur" type="password" autocomplete="current-password"></label>
      <label>Новый пароль<input id="site-new" type="password" autocomplete="new-password"></label>
      <div class="toolbar"><button class="btn-primary" id="site-save">Сохранить доступ</button></div>
    </div>
    <div class="card"><div class="section-title">Тема</div><div class="chips">${["SYSTEM", "LIGHT", "DARK"].map((m) => `<span class="chip ${s.themeMode === m ? "active" : ""}" data-theme="${m}">${m === "SYSTEM" ? "Система" : m === "LIGHT" ? "Светлая" : "Тёмная"}</span>`).join("")}</div></div>
    <div class="card"><div class="section-title">Telegram</div>
      <p class="muted">Ежедневное расписание уходит с этого компьютера, пока запущен сервер.</p>
      <label>Токен<input id="tok" value="${s.telegramBotToken || ""}"></label>
      <label>Chat ID<input id="chat" value="${s.telegramChatId || ""}"></label>
      <label class="check-row"><input id="den" type="checkbox" ${s.dailyScheduleEnabled ? "checked" : ""}> Отправлять расписание каждый день</label>
      <label>Время отправки<input id="dtime" type="time" value="${hh}:${mm}"></label>
      <label>Доп. chat id (по одному в строке)<textarea id="extra">${extras}</textarea></label>
      ${statusHtml}
      <div class="toolbar"><button class="btn-primary" id="stg">Сохранить</button><button class="btn-outline" id="td">Тест расписания</button><button class="btn-outline" id="tb">Бэкап в Telegram</button></div></div>
    <div class="card"><div class="section-title">База данных</div><p class="muted">Эта же база используется мобильным приложением.</p>
      <div class="toolbar"><a class="btn-primary" href="/api/backup">Скачать</a><label class="btn-outline">Загрузить<input id="up" type="file" hidden></label></div></div>
    <div class="card"><a class="btn-outline" href="/api/export/schedule">Excel расписания на неделю</a></div></div>`;
  $("#app").querySelectorAll("[data-theme]").forEach((el) => {
    el.onclick = async (e) => {
      e.stopPropagation();
      const mode = el.dataset.theme;
      applyTheme(mode);
      await api("/api/settings", { method: "PUT", body: { themeMode: mode } });
      render();
    };
  });
  $("#site-save").onclick = async () => {
    try {
      await api("/api/auth/credentials", {
        method: "PUT",
        body: {
          username: val("site-user"),
          currentPassword: val("site-cur"),
          password: val("site-new"),
        },
      });
      toast("Логин и пароль сохранены");
      render();
    } catch (e) { toast(e.message); }
  };
  $("#stg").onclick = async () => {
    const [h, m] = (val("dtime") || "07:00").split(":").map(Number);
    await api("/api/settings", {
      method: "PUT",
      body: {
        telegramBotToken: val("tok"),
        telegramChatId: val("chat"),
        dailyScheduleEnabled: $("#den").checked,
        dailyScheduleMinutes: (h || 0) * 60 + (m || 0),
        extraChatIds: val("extra").split(/[\n,;]+/).map((x) => x.trim()).filter(Boolean),
      },
    });
    toast("Сохранено");
    render();
  };
  $("#td").onclick = async () => { try { await api("/api/telegram/daily", { method: "POST", body: { test: true } }); toast("Тест отправлен"); } catch (e) { toast(e.message); } };
  $("#tb").onclick = async () => { try { await api("/api/telegram/backup", { method: "POST", body: {} }); toast("Отправлено"); } catch (e) { toast(e.message); } };
  $("#up").onchange = async (e) => {
    const file = e.target.files[0]; if (!file) return;
    const fd = new FormData(); fd.append("file", file);
    const res = await fetch("/api/backup", { method: "POST", body: fd, credentials: "same-origin" });
    if (res.status === 401) { window.location.href = "/login"; return; }
    const data = await res.json().catch(() => ({}));
    toast(res.ok ? "База загружена" : (data.error || "Ошибка"));
    if (res.ok) render();
  };
}

let themeMode = localStorage.getItem("themeMode") || "SYSTEM";
let themeEpoch = 0;

function applyTheme(mode) {
  if (mode) {
    themeMode = String(mode).toUpperCase();
    localStorage.setItem("themeMode", themeMode);
    themeEpoch += 1;
  }
  const dark =
    themeMode === "DARK" ||
    (themeMode === "SYSTEM" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("theme-dark", dark);
}

applyTheme(themeMode);
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => applyTheme());

document.addEventListener("click", async (e) => {
  const status = e.target.closest("[data-status]");
  if (status) {
    e.preventDefault();
    const [id, s] = status.dataset.status.split(":");
    await setStatus(id, s);
    return;
  }
  const open = e.target.closest("[data-open]");
  if (open) {
    location.hash = `#/lesson/${open.dataset.open}`;
    return;
  }
  const st = e.target.closest("[data-student]");
  if (st) {
    location.hash = `#/student/${st.dataset.student}`;
    return;
  }
  const j = e.target.closest("[data-journal]");
  if (j) location.hash = `#/journal/${j.dataset.journal}`;
  const en = e.target.closest("[data-entry]");
  if (en) location.hash = `#/entry/${en.dataset.entry}`;
  const dp = e.target.closest("[data-delpay]");
  if (dp) { if (confirm("Удалить платёж?")) { await api(`/api/payments/${dp.dataset.delpay}`, { method: "DELETE" }); toast("Удалено"); render(); } }
  const ds = e.target.closest("[data-delsub]");
  if (ds) { try { await api(`/api/subjects/${ds.dataset.delsub}`, { method: "DELETE" }); render(); } catch (err) { toast(err.message); } }
  const es = e.target.closest("[data-editsub]");
  if (es) subjectModal(state.params.id, JSON.parse(es.dataset.editsub));
});

window.addEventListener("hashchange", render);
render();
(() => {
  const started = themeEpoch;
  api("/api/settings")
    .then((s) => {
      if (started === themeEpoch) applyTheme(s.themeMode);
    })
    .catch(() => {});
})();
