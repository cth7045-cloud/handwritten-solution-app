// "관리자" 화면: 통계, 회원 목록, 이용 정지/해제, 일일 한도, 비밀번호 초기화
import { request } from "./api.js";

const statsEl = document.getElementById("admin-stats");
const tbody = document.getElementById("admin-users");
const statusEl = document.getElementById("admin-status");
const dateFmt = new Intl.DateTimeFormat("ko-KR", { year: "2-digit", month: "2-digit", day: "2-digit" });
let defaultLimit = 20;

function setStatus(msg, isError = false) {
  statusEl.textContent = msg;
  statusEl.classList.toggle("error", isError);
}

function stat(label, value) {
  const d = document.createElement("div");
  d.className = "stat";
  const v = document.createElement("b");
  v.textContent = value;
  const l = document.createElement("span");
  l.textContent = label;
  d.append(v, l);
  return d;
}

async function update(user, body, doneMsg) {
  try {
    await request(`/api/admin/users/${user.id}`, { method: "PATCH", json: body });
    setStatus(doneMsg);
    await showAdmin();
  } catch (err) {
    setStatus(err.message, true);
  }
}

function button(label, onClick, cls = "btn secondary small") {
  const b = document.createElement("button");
  b.type = "button";
  b.className = cls;
  b.textContent = label;
  b.addEventListener("click", onClick);
  return b;
}

function row(u) {
  const tr = document.createElement("tr");
  const isAdmin = u.role === "admin";
  const limitText = u.effective_limit == null ? "무제한" : `${u.effective_limit}${u.daily_limit == null ? " (기본)" : ""}`;
  const cells = [
    `${u.username}${isAdmin ? " 👑" : ""}`,
    `${u.used_today} / ${limitText}`,
    `${u.solve_count}회`,
    dateFmt.format(new Date(u.created_at)),
    u.is_active ? "정상" : "정지",
  ];
  for (const text of cells) {
    const td = document.createElement("td");
    td.textContent = text;
    tr.appendChild(td);
  }
  tr.cells[4].className = u.is_active ? "ok" : "danger";

  const td = document.createElement("td");
  const actions = document.createElement("div");
  actions.className = "actions-inner";
  td.appendChild(actions);
  if (!isAdmin) {
    actions.append(
      button(u.is_active ? "정지" : "해제", () =>
        update(u, { is_active: !u.is_active }, `${u.username} 계정을 ${u.is_active ? "정지" : "정상화"}했습니다.`),
      ),
      button("한도", () => {
        const v = prompt(`${u.username}의 하루 풀이 한도 (비우면 기본값 ${defaultLimit}회)`, u.daily_limit ?? "");
        if (v === null) return;
        const body = v.trim() === "" ? { use_default_limit: true } : { daily_limit: Number(v) };
        if (!body.use_default_limit && !Number.isInteger(body.daily_limit)) return setStatus("숫자를 입력해 주세요.", true);
        update(u, body, `${u.username}의 한도를 변경했습니다.`);
      }),
      button("비번 초기화", () => {
        const v = prompt(`${u.username}의 새 비밀번호 (8자 이상)`);
        if (v) update(u, { new_password: v }, `${u.username}의 비밀번호를 초기화했습니다. (모든 기기 로그아웃)`);
      }),
    );
  }
  tr.appendChild(td);
  return tr;
}

export async function showAdmin() {
  try {
    const [stats, { users }] = await Promise.all([request("/api/admin/stats"), request("/api/admin/users")]);
    defaultLimit = stats.default_daily_limit;
    statsEl.replaceChildren(
      stat("전체 회원", `${stats.total_users}명`),
      stat("오늘 풀이", `${stats.solves_today}회`),
      stat("누적 풀이", `${stats.total_solves}회`),
      stat("기본 하루 한도", `${stats.default_daily_limit}회`),
    );
    tbody.replaceChildren(...users.map(row));
  } catch (err) {
    setStatus(err.message, true);
  }
}
