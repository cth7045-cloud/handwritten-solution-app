// 서버 API 호출 공통 처리. 401(로그인 만료)이면 등록된 핸들러로 로그인 화면을 띄웁니다.

let onUnauthorized = () => {};

export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function errorFrom(res) {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
  } catch {
    /* 본문이 JSON이 아님 */
  }
  return `요청 실패 (${res.status})`;
}

export async function request(path, { method = "GET", json, form, signal, raw = false } = {}) {
  const opts = { method, signal, headers: {}, credentials: "same-origin" };
  if (json !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(json);
  } else if (form) {
    opts.body = form;
  }
  const res = await fetch(path, opts);
  if (!res.ok) {
    const msg = await errorFrom(res);
    if (res.status === 401 && !path.startsWith("/api/auth/")) onUnauthorized();
    throw new ApiError(msg, res.status);
  }
  if (raw) return res;
  return res.status === 204 ? null : res.json();
}
