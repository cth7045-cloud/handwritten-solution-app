// "만들기" 화면: 이미지 등록 -> /api/solve (AI 풀이) -> /api/render (손글씨 PNG)
// 풀이가 저장된 뒤에는 solve_id로 다시 그리므로 이미지를 다시 올리지 않습니다.

import { request } from "./api.js";

const MAX_SIDE = 1800;

const state = {
  image: null, // 새로 올린 이미지 Blob (축소된 JPEG)
  mode: "killer_tutor",
  font: "NanumAmsterdam",
  pen: "deepblue",
  layout: "margin",
  postit: "yellow",
  seed: 1,
  solution: null,
  solveId: null,
  resultUrl: null,
};

const $ = (id) => document.getElementById(id);
const els = {
  dropzone: $("dropzone"),
  sourcePreview: $("source-preview"),
  dropHint: $("drop-hint"),
  fileInput: $("file-input"),
  cameraInput: $("camera-input"),
  pasteBtn: $("paste-btn"),
  modeOptions: $("mode-options"),
  penOptions: $("pen-options"),
  fontOptions: $("font-options"),
  layoutOptions: $("layout-options"),
  postitOptions: $("postit-options"),
  generateBtn: $("generate-btn"),
  status: $("status"),
  resultBox: $("result-box"),
  resultEmpty: $("result-empty"),
  resultImg: $("result-img"),
  rewriteBtn: $("rewrite-btn"),
  downloadBtn: $("download-btn"),
  solutionText: $("solution-text"),
  solutionBody: $("solution-body"),
};

let onUsage = () => {};

function setStatus(msg, isError = false) {
  els.status.textContent = msg;
  els.status.classList.toggle("error", isError);
}

const newSeed = () => Math.floor(Math.random() * 1e9);

// ---------- 라디오 버튼 묶음 ----------
function renderRadioGroup(container, items, selectedId, build, onSelect) {
  container.replaceChildren();
  for (const item of items) {
    const btn = build(item);
    btn.type = "button";
    btn.setAttribute("role", "radio");
    btn.dataset.id = item.id;
    btn.setAttribute("aria-checked", String(item.id === selectedId));
    btn.addEventListener("click", () => {
      selectRadio(container, item.id);
      onSelect(item.id);
    });
    container.appendChild(btn);
  }
}

function selectRadio(container, id) {
  for (const b of container.children) b.setAttribute("aria-checked", String(b.dataset.id === id));
}

function choiceButton(item) {
  const b = document.createElement("button");
  b.className = "choice";
  const t = document.createElement("b");
  t.textContent = item.label;
  const d = document.createElement("span");
  d.textContent = item.description;
  b.append(t, d);
  return b;
}

function chipButton(item) {
  const b = document.createElement("button");
  b.className = "chip";
  const sw = document.createElement("span");
  sw.className = "swatch";
  sw.style.background = item.color;
  b.append(sw, document.createTextNode(item.label));
  return b;
}

function fontPreviewUrl(fontId) {
  return `/api/fonts/${encodeURIComponent(fontId)}/preview.png?pen=${encodeURIComponent(state.pen)}`;
}

function fontCard(item) {
  const b = document.createElement("button");
  b.className = "font-card";
  const label = document.createElement("span");
  label.className = "font-label";
  label.textContent = item.label;
  const img = document.createElement("img");
  img.loading = "lazy";
  img.alt = `${item.label} 필기 예시`;
  img.src = fontPreviewUrl(item.id);
  b.append(label, img);
  return b;
}

function refreshFontPreviews() {
  for (const card of els.fontOptions.children) card.querySelector("img").src = fontPreviewUrl(card.dataset.id);
}

async function loadStyles() {
  const s = await request("/api/styles");
  renderRadioGroup(els.modeOptions, s.solve_modes, state.mode, choiceButton, (id) => {
    state.mode = id;
    if (state.solution) setStatus("풀이 방식이 바뀌었습니다. 새로 풀려면 버튼을 눌러주세요.");
  });
  renderRadioGroup(els.penOptions, s.pens, state.pen, chipButton, (id) => {
    state.pen = id;
    refreshFontPreviews();
    scheduleRender();
  });
  renderRadioGroup(els.fontOptions, s.fonts, state.font, fontCard, (id) => {
    state.font = id;
    scheduleRender();
  });
  renderRadioGroup(els.layoutOptions, s.layouts, state.layout, choiceButton, (id) => {
    state.layout = id;
    els.postitOptions.hidden = id !== "postit";
    scheduleRender();
  });
  renderRadioGroup(els.postitOptions, s.postit_colors, state.postit, chipButton, (id) => {
    state.postit = id;
    scheduleRender();
  });
}

// ---------- 이미지 등록 ----------
// 휴대폰 원본 사진(수 MB)을 그대로 올리면 느리므로 브라우저에서 먼저 줄이고 EXIF 회전을 적용합니다.
async function shrinkImage(file) {
  try {
    const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
    const scale = Math.min(1, MAX_SIDE / Math.max(bmp.width, bmp.height));
    const w = Math.round(bmp.width * scale);
    const h = Math.round(bmp.height * scale);
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, w, h);
    ctx.drawImage(bmp, 0, 0, w, h);
    bmp.close?.();
    const blob = await new Promise((r) => canvas.toBlob(r, "image/jpeg", 0.92));
    return blob || file;
  } catch {
    return file; // 브라우저가 지원하지 않으면 원본 전송 (서버에서도 축소합니다)
  }
}

function setSourcePreview(url) {
  if (els.sourcePreview.src.startsWith("blob:")) URL.revokeObjectURL(els.sourcePreview.src);
  els.sourcePreview.src = url;
  els.sourcePreview.hidden = false;
  els.dropHint.hidden = true;
}

async function acceptImage(file) {
  if (!file || !file.type.startsWith("image/")) {
    setStatus("이미지 파일만 올릴 수 있습니다.", true);
    return;
  }
  state.image = await shrinkImage(file);
  state.solution = null;
  state.solveId = null;
  setSourcePreview(URL.createObjectURL(state.image));
  els.generateBtn.disabled = false;
  els.rewriteBtn.disabled = true;
  setStatus("문제 이미지가 등록되었습니다.");
}

function imageFromItems(items) {
  for (const item of items || []) {
    if (item.kind === "file" && item.type.startsWith("image/")) return item.getAsFile();
  }
  return null;
}

function bindImageInputs() {
  els.dropzone.addEventListener("click", () => els.fileInput.click());
  els.dropzone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      els.fileInput.click();
    }
  });
  for (const input of [els.fileInput, els.cameraInput]) {
    input.addEventListener("change", () => {
      acceptImage(input.files[0]);
      input.value = "";
    });
  }
  els.dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    els.dropzone.classList.add("dragover");
  });
  els.dropzone.addEventListener("dragleave", () => els.dropzone.classList.remove("dragover"));
  els.dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    els.dropzone.classList.remove("dragover");
    acceptImage(e.dataTransfer.files[0]);
  });
  // Ctrl+V: 화면 캡처를 페이지 어디서든 붙여넣기 (만들기 화면이 보일 때만)
  document.addEventListener("paste", (e) => {
    if (document.getElementById("view-studio").hidden) return;
    const file = imageFromItems(e.clipboardData?.items);
    if (file) {
      e.preventDefault();
      acceptImage(file);
    }
  });
  els.pasteBtn.addEventListener("click", async () => {
    if (!navigator.clipboard?.read) {
      setStatus("이 브라우저에서는 Ctrl+V(길게 눌러 붙여넣기)를 이용해 주세요.", true);
      return;
    }
    try {
      for (const item of await navigator.clipboard.read()) {
        const type = item.types.find((t) => t.startsWith("image/"));
        if (type) {
          const blob = await item.getType(type);
          return acceptImage(new File([blob], "clipboard", { type }));
        }
      }
      setStatus("클립보드에 이미지가 없습니다.", true);
    } catch {
      setStatus("클립보드 접근이 거부되었습니다. Ctrl+V로 붙여넣어 주세요.", true);
    }
  });
}

// ---------- AI 풀이 + 렌더링 ----------
let renderController = null;
let renderTimer = null;

function scheduleRender() {
  if (!state.solution) return;
  clearTimeout(renderTimer);
  renderTimer = setTimeout(renderResult, 120);
}

async function renderResult() {
  if (!state.solution) return;
  renderController?.abort();
  renderController = new AbortController();
  const form = new FormData();
  if (state.solveId) {
    form.append("solve_id", String(state.solveId));
  } else {
    form.append("image", state.image, "problem.jpg");
    form.append("solution", JSON.stringify(state.solution));
  }
  form.append("font", state.font);
  form.append("pen", state.pen);
  form.append("layout", state.layout);
  form.append("postit_color", state.postit);
  form.append("seed", String(state.seed));

  els.resultBox.classList.add("busy");
  try {
    const res = await request("/api/render", { method: "POST", form, signal: renderController.signal, raw: true });
    const blob = await res.blob();
    if (state.resultUrl) URL.revokeObjectURL(state.resultUrl);
    state.resultUrl = URL.createObjectURL(blob);
    els.resultImg.src = state.resultUrl;
    els.resultImg.hidden = false;
    els.resultEmpty.hidden = true;
    els.downloadBtn.href = state.resultUrl;
    els.downloadBtn.classList.remove("disabled");
    els.downloadBtn.setAttribute("aria-disabled", "false");
    els.rewriteBtn.disabled = false;
  } catch (err) {
    if (err.name !== "AbortError") setStatus(err.message, true);
  } finally {
    els.resultBox.classList.remove("busy");
  }
}

function showSolutionText(sol, elapsedMs) {
  const frag = document.createDocumentFragment();
  const title = document.createElement("p");
  const b = document.createElement("b");
  b.textContent = sol.problem_title || "풀이";
  title.append(b);
  const ol = document.createElement("ol");
  for (const s of sol.steps) {
    const li = document.createElement("li");
    li.textContent = s;
    ol.appendChild(li);
  }
  const ans = document.createElement("p");
  ans.className = "answer";
  ans.textContent = `정답: ${sol.final_answer}`;
  frag.append(title, ol, ans);
  if (sol.tip) {
    const tip = document.createElement("p");
    tip.textContent = `Tip: ${sol.tip}`;
    frag.append(tip);
  }
  const meta = document.createElement("p");
  meta.className = "meta";
  meta.textContent = `${sol.used_model || "AI"} · 풀이 ${(elapsedMs / 1000).toFixed(1)}초`;
  frag.append(meta);
  els.solutionBody.replaceChildren(frag);
  els.solutionText.hidden = false;
}

function scrollToResultOnPhone() {
  if (window.matchMedia("(max-width: 959px)").matches) els.resultBox.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function generate() {
  if (!state.image) return;
  els.generateBtn.disabled = true;
  els.resultBox.classList.add("busy");
  const started = performance.now();
  const tick = setInterval(() => {
    setStatus(`AI가 문제를 푸는 중… ${((performance.now() - started) / 1000).toFixed(0)}초`);
  }, 500);
  setStatus("AI가 문제를 푸는 중…");

  try {
    const form = new FormData();
    form.append("image", state.image, "problem.jpg");
    form.append("mode", state.mode);
    const { solution, solve_id, elapsed_ms, usage } = await request("/api/solve", { method: "POST", form });
    onUsage(usage);
    state.solution = solution;
    state.solveId = solve_id;
    state.seed = newSeed();
    clearInterval(tick);
    setStatus("손글씨로 옮겨 쓰는 중…");
    await renderResult();
    showSolutionText(solution, elapsed_ms);
    scrollToResultOnPhone();
    setStatus(`완성! (총 ${((performance.now() - started) / 1000).toFixed(1)}초) 펜·글씨체를 바꾸면 바로 다시 그립니다.`);
  } catch (err) {
    setStatus(err.message, true);
  } finally {
    clearInterval(tick);
    els.generateBtn.disabled = false;
    els.resultBox.classList.remove("busy");
  }
}

// 기록에서 연 풀이를 만들기 화면에 불러옵니다 (저장된 스타일 그대로).
export async function openSolve(solveId) {
  const rec = await request(`/api/history/${solveId}`);
  state.solution = rec.solution;
  state.solveId = rec.id;
  state.image = null;
  state.mode = rec.mode;
  const st = rec.style || {};
  if (st.font) state.font = st.font;
  if (st.pen) state.pen = st.pen;
  if (st.layout) state.layout = st.layout;
  if (st.postit_color) state.postit = st.postit_color;
  state.seed = st.seed ?? newSeed();
  selectRadio(els.modeOptions, state.mode);
  selectRadio(els.fontOptions, state.font);
  selectRadio(els.penOptions, state.pen);
  selectRadio(els.layoutOptions, state.layout);
  selectRadio(els.postitOptions, state.postit);
  els.postitOptions.hidden = state.layout !== "postit";
  refreshFontPreviews();
  setSourcePreview(`/api/history/${rec.id}/image`);
  els.generateBtn.disabled = true; // 새로 풀려면 이미지를 다시 올리도록
  showSolutionText(rec.solution, rec.elapsed_ms);
  setStatus("저장된 풀이를 불러왔습니다. 펜·글씨체를 바꾸면 바로 다시 그립니다.");
  await renderResult();
}

export async function initStudio({ onUsageChange }) {
  onUsage = onUsageChange;
  bindImageInputs();
  els.generateBtn.addEventListener("click", generate);
  els.rewriteBtn.addEventListener("click", () => {
    state.seed = newSeed();
    renderResult();
  });
  try {
    await loadStyles();
  } catch (err) {
    setStatus(`설정을 불러오지 못했습니다: ${err.message}`, true);
  }
}
