const FIELD_LABELS = {
  card_number: ["Số thẻ", "番号"],
  name: ["Họ tên", "氏名"],
  date_of_birth: ["Ngày sinh", "生年月日"],
  sex: ["Giới tính", "性別"],
  nationality: ["Quốc tịch", "国籍・地域"],
  address: ["Địa chỉ", "住居地"],
  status_of_residence: ["Tư cách lưu trú", "在留資格"],
  work_restriction: ["Hạn chế làm việc", "就労制限の有無"],
  period_of_stay: ["Thời hạn lưu trú", "在留期間"],
  expiration_date: ["Ngày hết hạn lưu trú", "満了日"],
  permission_type: ["Loại giấy phép", "許可の種類"],
  issuing_authority: ["Cơ quan cấp", "許可機関"],
  permission_date: ["Ngày cấp phép", "許可年月日"],
  issue_date: ["Ngày cấp thẻ", "交付年月日"],
  valid_until: ["Thẻ có hiệu lực đến", "有効期限"],
};
const LOW_SCORE = 0.85;

const $ = (id) => document.getElementById(id);
const drop = $("drop"), fileInput = $("file"), statusEl = $("status");
let lastResult = null;
let lastFileName = "result";

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function setStatus(text, cls = "") {
  statusEl.textContent = text;
  statusEl.className = "status " + cls;
}

async function upload(file) {
  if (!file) return;
  lastFileName = file.name.replace(/\.[^.]+$/, "") || "result";
  const engine = $("engine").value;
  setStatus(
    engine === "vl" ? "Đang nhận dạng bằng PaddleOCR-VL… (trên CPU có thể mất vài phút)" : "Đang nhận dạng… (lần đầu có thể mất vài chục giây)",
    "loading",
  );
  $("warnings").innerHTML = "";
  const form = new FormData();
  form.append("file", file);
  const crop = $("crop").checked;
  try {
    const res = await fetch(`/api/extract?crop=${crop}&engine=${engine}`, { method: "POST", body: form });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
    render(body);
  } catch (err) {
    setStatus("Lỗi: " + err.message, "error");
  }
}

function render(r) {
  lastResult = r;
  const t = r.timing_ms;
  const total = t.preprocess + t.ocr + t.parse;
  const fields = Object.values(r.fields);
  const found = fields.filter((f) => f.value).length;
  const review = fields.filter((f) => f.needs_review).length;
  setStatus(`Xong trong ${(total / 1000).toFixed(1)}s — trích được ${found}/${fields.length} trường, ${review} trường cần kiểm tra lại.`);

  $("warnings").innerHTML = warningsHtml(r);

  // Image + OCR boxes
  $("viewer").hidden = false;
  $("preview").src = r.processed_image;
  const svg = $("overlay");
  svg.setAttribute("viewBox", `0 0 ${r.ocr.image_size.join(" ")}`);
  svg.innerHTML = boxesSvg(r.ocr.lines);
  svg.style.display = $("showBoxes").checked ? "" : "none";
  $("meta").textContent =
    `ID ${r.request_id} · ảnh gốc ${r.ocr.original_size.join("×")} · ` +
    `${r.ocr.model} · ${r.ocr.lines.length} dòng · độ tin cậy TB ${r.mean_ocr_confidence ?? "–"} · ` +
    `${r.ocr.card_cropped ? "đã cắt & nắn thẻ" : "không tìm thấy viền thẻ, dùng ảnh gốc"} · ` +
    `tiền xử lý ${t.preprocess}ms, OCR ${t.ocr}ms`;

  $("tab-fields").innerHTML = fieldsTableHtml(r.fields);

  // JSON (without the base64 image, which is only for display)
  const { processed_image, ...clean } = r;
  $("json").textContent = JSON.stringify(clean, null, 2);

  $("tab-lines").innerHTML =
    `<table class="lines">` +
    r.ocr.lines.map((l) => `<tr><td>${esc(l.text)}</td><td class="score">${l.score.toFixed(3)}</td></tr>`).join("") +
    `</table>`;

  $("tabs").hidden = false;
}

function warningsHtml(r) {
  const q = r.quality;
  const qualityBanner =
    q && q.level === "low"
      ? `<div class="warning bad"><strong>Ảnh chất lượng thấp, kết quả không đáng tin.</strong>` +
        `<ul>${q.reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>${esc(q.advice)}</div>`
      : "";
  return qualityBanner + r.warnings.map((w) => `<div class="warning">⚠ ${esc(w)}</div>`).join("");
}

function boxesSvg(lines) {
  return lines
    .map((l) => {
      const [x1, y1, x2, y2] = l.box;
      return `<rect x="${x1}" y="${y1}" width="${x2 - x1}" height="${y2 - y1}" class="${l.score < LOW_SCORE ? "low" : ""}"><title>${esc(l.text)} (${l.score})</title></rect>`;
    })
    .join("");
}

function fieldsTableHtml(fields) {
  const rows = Object.entries(fields)
    .map(([key, f]) => {
      const [vi, jp] = FIELD_LABELS[key] || [key, ""];
      const conf = f.confidence == null ? "" : ` ${(f.confidence * 100).toFixed(0)}%`;
      const notPrinted = !f.value && !f.needs_review;
      const badge = notPrinted
        ? ""
        : f.needs_review
          ? `<span class="badge review">cần kiểm tra${conf}</span>`
          : `<span class="badge ok">OK${conf}</span>`;
      const val = f.value
        ? `<span class="val">${esc(f.value)}</span>`
        : `<span class="val empty">${notPrinted ? "không có trên mẫu thẻ này" : "không đọc được"}</span>`;
      const raw = f.raw && f.raw !== f.value ? `<span class="raw">OCR: ${esc(f.raw)}</span>` : "";
      const notes = f.notes.map((n) => `<span class="note">${esc(n)}</span>`).join("");
      return `<tr><th>${esc(vi)}<span class="jp">${esc(jp)}</span></th><td>${val}${badge}${raw}${notes}</td></tr>`;
    })
    .join("");
  return `<table>${rows}</table>`;
}

function summary(r) {
  const fields = Object.values(r.fields);
  return {
    found: fields.filter((f) => f.value).length,
    review: fields.filter((f) => f.needs_review).length,
    total: fields.length,
  };
}

const DESIGN_LABELS = {
  "2012": "Mẫu cũ (đến 13/06/2026)",
  "2026": "Mẫu mới (từ 14/06/2026)",
  specified_2026: "特定在留カード — chưa hỗ trợ",
};

// "Mẫu chính thức" view: precomputed results on the ISA specimen cards (scripts/build_demo.py)
let samplesLoaded = false;
async function loadSamples() {
  if (samplesLoaded) return;
  const el = $("samples");
  try {
    const res = await fetch("/static/samples/results.json");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    samplesLoaded = true;
    el.innerHTML =
      `<p class="sub">Ảnh thẻ mẫu (見本) chính thức từ <a href="${esc(data.samples[0].source_page)}" target="_blank" rel="noopener">trang của Cục Xuất nhập cảnh Nhật</a> ` +
      `(<a href="${esc(data.samples[0].source_pdf)}" target="_blank" rel="noopener">tờ hướng dẫn PDF</a>). ` +
      `Kết quả chạy sẵn ngày ${esc(data.generated)}; bấm "Chạy lại" để OCR trực tiếp.</p>` +
      data.samples.map(sampleCardHtml).join("");
    el.querySelectorAll("button[data-rerun]").forEach((b) =>
      b.addEventListener("click", async () => {
        const blob = await (await fetch(b.dataset.rerun)).blob();
        showView("upload");
        upload(new File([blob], b.dataset.rerun.split("/").pop(), { type: blob.type }));
      })
    );
  } catch (err) {
    el.innerHTML = `<p class="status error">Không tải được kết quả mẫu: ${esc(err.message)}</p>`;
  }
}

function sampleCardHtml(s) {
  const r = s.result;
  const { found, review, total } = summary(r);
  const qualityBadge =
    r.quality.level === "low" ? `<span class="badge review">chất lượng thấp</span>` : `<span class="badge ok">chất lượng OK</span>`;
  return `
    <article class="sample">
      <header>
        <h2>${esc(s.title)}</h2>
        <p class="sub">${esc(s.description)}</p>
        <p class="chips">
          <span class="badge design">${esc(DESIGN_LABELS[r.card_design] || r.card_design)}</span>${qualityBadge}
          <span class="badge plain">đọc được ${found}/${total} trường · ${review} cần kiểm tra · OCR ${(r.timing_ms.ocr / 1000).toFixed(1)}s</span>
        </p>
      </header>
      <div class="sample-body">
        <div>
          <div class="stage">
            <img src="${esc(s.processed_image)}" alt="${esc(s.title)}" loading="lazy">
            <svg viewBox="0 0 ${r.ocr.image_size.join(" ")}">${boxesSvg(r.ocr.lines)}</svg>
          </div>
          <p class="meta">Ảnh gốc ${r.ocr.original_size.join("×")}px · <a href="${esc(s.image)}" target="_blank">xem ảnh gốc</a></p>
          <button class="rerun" data-rerun="${esc(s.image)}">Chạy lại trực tiếp</button>
          ${warningsHtml(r)}
        </div>
        <div>${fieldsTableHtml(r.fields)}</div>
      </div>
    </article>`;
}

function showView(view) {
  document.querySelectorAll("#views button").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  $("view-upload").hidden = view !== "upload";
  $("view-samples").hidden = view !== "samples";
  if (view === "samples") loadSamples();
  try {
    localStorage.setItem("view", view);
  } catch {}
}

$("views").addEventListener("click", (e) => {
  if (e.target.dataset?.view) showView(e.target.dataset.view);
});
try {
  if (localStorage.getItem("view") === "samples") showView("samples");
} catch {}

function cleanJson() {
  return $("json").textContent;
}

// Tabs
$("tabs").addEventListener("click", (e) => {
  const tab = e.target.dataset?.tab;
  if (!tab) return;
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  ["fields", "json", "lines"].forEach((t) => ($("tab-" + t).hidden = t !== tab));
});

$("copyJson").addEventListener("click", async () => {
  await navigator.clipboard.writeText(cleanJson());
  $("copyJson").textContent = "Đã copy";
  setTimeout(() => ($("copyJson").textContent = "Copy"), 1200);
});

$("downloadJson").addEventListener("click", () => {
  const blob = new Blob([cleanJson()], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${lastFileName}.json`;
  a.click();
  URL.revokeObjectURL(a.href);
});

$("showBoxes").addEventListener("change", (e) => {
  $("overlay").style.display = e.target.checked ? "" : "none";
});

// Upload: click, drag & drop, paste
fileInput.addEventListener("change", () => {
  upload(fileInput.files[0]);
  fileInput.value = ""; // allow re-selecting the same file
});
drop.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") fileInput.click();
});
["dragenter", "dragover"].forEach((ev) =>
  drop.addEventListener(ev, (e) => {
    e.preventDefault();
    drop.classList.add("over");
  })
);
["dragleave", "drop"].forEach((ev) =>
  drop.addEventListener(ev, (e) => {
    e.preventDefault();
    drop.classList.remove("over");
  })
);
drop.addEventListener("drop", (e) => upload(e.dataTransfer.files[0]));
window.addEventListener("paste", (e) => {
  const item = [...e.clipboardData.items].find((i) => i.type.startsWith("image/"));
  if (item) upload(item.getAsFile());
});
