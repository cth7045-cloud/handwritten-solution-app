// 앱 시작점: 로그인 상태 확인, 화면 전환(#/, #/history, #/admin), 계정 메뉴
import { request, setUnauthorizedHandler } from "./api.js";
import { initStudio, openSolve } from "./studio.js";
import { initHistory, showHistory } from "./history.js";
import { showAdmin } from "./admin.js";

const $ = (id) => document.getElementById(id);
let me = null;
let signupMode = false;
let studioReady = false;

// ---------- 로그인 / 회원가입 ----------
function setAuthMode(signup) {
  signupMode = signup;
  $("tab-login").setAttribute("aria-selected", String(!signup));
  $("tab-signup").setAttribute("aria-selected", String(signup));
  $("auth-confirm-field").hidden = !signup;
  $("auth-hint").hidden = !signup;
  $("auth-password").autocomplete = signup ? "new-password" : "current-password";
  $("auth-submit").textContent = signup ? "가입하고 시작하기" : "로그인";
  $("auth-error").textContent = "";
}

async function submitAuth(e) {
  e.preventDefault();
  const username = $("auth-username").value.trim();
  const password = $("auth-password").value;
  const errEl = $("auth-error");
  if (signupMode && password !== $("auth-confirm").value) {
    errEl.textContent = "비밀번호가 서로 다릅니다.";
    return;
  }
  $("auth-submit").disabled = true;
  try {
    const data = await request(signupMode ? "/api/auth/signup" : "/api/auth/login", {
      method: "POST",
      json: { username, password },
    });
    $("auth-form").reset();
    await enterApp(data);
  } catch (err) {
    errEl.textContent = err.message;
  } finally {
    $("auth-submit").disabled = false;
  }
}

async function showAuth() {
  me = null;
  $("app-view").hidden = true;
  $("auth-view").hidden = false;
  try {
    const { allow_signup } = await request("/api/auth/config");
    $("tab-signup").hidden = !allow_signup;
    if (!allow_signup) setAuthMode(false);
  } catch {
    /* 가입 설정을 못 불러와도 로그인은 가능 */
  }
  $("auth-username").focus();
}

// ---------- 로그인 후 ----------
function setUsage(usage) {
  if (!usage) return;
  const badge = $("usage-badge");
  badge.textContent = usage.limit == null ? `오늘 ${usage.used}회` : `오늘 ${usage.used}/${usage.limit}`;
  badge.classList.toggle("full", usage.limit != null && usage.used >= usage.limit);
}

async function enterApp(data) {
  me = data.user;
  setUsage(data.usage);
  $("account-btn").textContent = me.username;
  $("account-title").textContent = `${me.username}${me.role === "admin" ? " (관리자)" : ""}`;
  $("nav-admin").hidden = me.role !== "admin";
  // 관리자 비밀번호는 서버 설정(ADMIN_PASSWORD)으로 관리합니다
  $("password-form").hidden = me.role === "admin";
  $("auth-view").hidden = true;
  $("app-view").hidden = false;
  if (!studioReady) {
    studioReady = true;
    await initStudio({ onUsageChange: setUsage });
  }
  route();
}

function route() {
  if (!me) return;
  let view = (location.hash.replace(/^#\/?/, "") || "studio").split("?")[0];
  if (view === "admin" && me.role !== "admin") view = "studio";
  if (!["studio", "history", "admin"].includes(view)) view = "studio";
  for (const v of ["studio", "history", "admin"]) $(`view-${v}`).hidden = v !== view;
  window.scrollTo(0, 0);
  for (const a of document.querySelectorAll(".nav a")) {
    if (a.dataset.route === view) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
  if (view === "history") showHistory();
  if (view === "admin") showAdmin();
}

// ---------- 계정 메뉴 ----------
function bindAccount() {
  const dialog = $("account-dialog");
  $("account-btn").addEventListener("click", () => {
    $("pw-status").textContent = "";
    dialog.showModal();
  });
  $("logout-btn").addEventListener("click", async () => {
    try {
      await request("/api/auth/logout", { method: "POST" });
    } finally {
      dialog.close();
      showAuth();
    }
  });
  $("password-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const status = $("pw-status");
    try {
      await request("/api/auth/password", {
        method: "POST",
        json: { current_password: $("pw-current").value, new_password: $("pw-new").value },
      });
      e.target.reset();
      status.classList.remove("error");
      status.textContent = "변경했습니다. 다른 기기에서는 다시 로그인해야 합니다.";
    } catch (err) {
      status.classList.add("error");
      status.textContent = err.message;
    }
  });
}

// ---------- 시작 ----------
setUnauthorizedHandler(showAuth);
$("tab-login").addEventListener("click", () => setAuthMode(false));
$("tab-signup").addEventListener("click", () => setAuthMode(true));
$("auth-form").addEventListener("submit", submitAuth);
bindAccount();
initHistory({
  onOpenSolve: async (id) => {
    location.hash = "#/";
    try {
      await openSolve(id);
    } catch (err) {
      alert(err.message);
    }
  },
});
window.addEventListener("hashchange", route);

request("/api/auth/me")
  .then(enterApp)
  .catch(showAuth);
