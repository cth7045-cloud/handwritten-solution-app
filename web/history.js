// "내 기록" 화면
import { request } from "./api.js";

const PAGE = 30;
const list = document.getElementById("history-list");
const empty = document.getElementById("history-empty");
const more = document.getElementById("history-more");
let offset = 0;
let onOpen = () => {};

const dateFmt = new Intl.DateTimeFormat("ko-KR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
const MODE_LABEL = { killer_tutor: "1타 강사 압축", standard_concept: "개념 정석" };

function card(item) {
  const el = document.createElement("article");
  el.className = "history-card";

  const open = document.createElement("button");
  open.type = "button";
  open.className = "history-open";
  open.setAttribute("aria-label", `${item.title || "풀이"} 열기`);
  const img = document.createElement("img");
  img.loading = "lazy";
  img.alt = "";
  img.src = `/api/history/${item.id}/image?thumb=true`;
  const body = document.createElement("div");
  body.className = "history-body";
  const title = document.createElement("b");
  title.textContent = item.title || "제목 없는 풀이";
  const meta = document.createElement("span");
  meta.className = "muted";
  meta.textContent = `${dateFmt.format(new Date(item.created_at))} · ${MODE_LABEL[item.mode] || item.mode}`;
  const ans = document.createElement("span");
  ans.className = "history-answer";
  ans.textContent = item.final_answer ? `정답 ${item.final_answer}` : "";
  body.append(title, meta, ans);
  open.append(img, body);
  open.addEventListener("click", () => onOpen(item.id));

  const del = document.createElement("button");
  del.type = "button";
  del.className = "icon-btn history-delete";
  del.setAttribute("aria-label", "기록 삭제");
  del.textContent = "✕";
  del.addEventListener("click", async () => {
    if (!confirm("이 풀이 기록을 삭제할까요?")) return;
    try {
      await request(`/api/history/${item.id}`, { method: "DELETE" });
      el.remove();
      empty.hidden = list.children.length > 0;
    } catch (err) {
      alert(err.message);
    }
  });

  el.append(open, del);
  return el;
}

async function loadPage() {
  const { items } = await request(`/api/history?offset=${offset}`);
  for (const item of items) list.appendChild(card(item));
  offset += items.length;
  more.hidden = items.length < PAGE;
  empty.hidden = list.children.length > 0;
}

export async function showHistory() {
  list.replaceChildren();
  offset = 0;
  try {
    await loadPage();
  } catch (err) {
    empty.textContent = err.message;
    empty.hidden = false;
  }
}

export function initHistory({ onOpenSolve }) {
  onOpen = onOpenSolve;
  more.addEventListener("click", () => loadPage().catch((err) => alert(err.message)));
}
