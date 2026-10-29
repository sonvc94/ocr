// Field names per result.document_type: [Vietnamese, as printed on the card]
const RESIDENCE_FIELDS = {
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
const MY_NUMBER_FIELDS = {
  issuer: ["Nơi cấp", "○○市長"],
  expiry_date: ["Có hiệu lực đến", "まで有効"],
};
const DRIVER_LICENSE_FIELDS = {
  license_number: ["Số bằng lái", "番号 第…号"],
  issue_date: ["Ngày cấp", "交付"],
};
const PASSPORT_FIELDS = { passport_number: ["Số hộ chiếu", "旅券番号 / Passport No."] };
const HEALTH_INSURANCE_FIELDS = {
  card_type: ["Loại thẻ", "…被保険者証 / 資格確認書"],
  insurer_name: ["Đơn vị bảo hiểm (nơi cấp)", "保険者名称 / 交付者名"],
  issue_date: ["Ngày cấp", "交付年月日"],
};
const DRIVING_HISTORY_FIELDS = {
  license_number: ["Số bằng lái (đã trả lại)", "番号 第…号"],
  issue_date: ["Ngày cấp giấy chứng nhận", "交付"],
};
const SPECIAL_PERMANENT_FIELDS = {
  certificate_number: ["Số giấy chứng nhận", "番号"],
  expiry_date: ["Hạn", "有効期間の満了日"],
};
const JUKI_CARD_FIELDS = {
  issuer: ["Nơi cấp", "○○市長"],
  expiry_date: ["Hạn thẻ", "有効期限"],
};
const RESIDENT_RECORD_FIELDS = {
  issuer: ["Nơi cấp (chứng nhận)", "○○市長"],
  certified_date: ["Ngày chứng nhận", "証明日"],
  address: ["Địa chỉ", "住所"],
};
const PENSION_FIELDS = {
  basic_pension_number: ["Số hưu trí cơ bản", "基礎年金番号"],
  issue_date: ["Ngày cấp", "交付年月日"],
};
const FIELD_LABELS = {
  residence_card: RESIDENCE_FIELDS,
  my_number_card: MY_NUMBER_FIELDS,
  driver_license: DRIVER_LICENSE_FIELDS,
  passport: PASSPORT_FIELDS,
  health_insurance_card: HEALTH_INSURANCE_FIELDS,
  special_permanent_resident_certificate: SPECIAL_PERMANENT_FIELDS,
  driving_history_certificate: DRIVING_HISTORY_FIELDS,
  juki_card: JUKI_CARD_FIELDS,
  resident_record: RESIDENT_RECORD_FIELDS,
  pension_book: PENSION_FIELDS,
};
const LOW_SCORE = 0.85;

const $ = (id) => document.getElementById(id);
const drop = $("drop"), fileInput = $("file"), statusEl = $("status");
let lastResult = null;
let lastFileName = "result";
let selectedFile = null; // chosen image, sent only when the user presses "Nhận dạng"
let previewUrl = null;

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function setStatus(text, cls = "") {
  statusEl.textContent = text;
  statusEl.className = "status " + cls;
}

// Choosing an image (picker, drag & drop, paste, camera) only previews it: the user then picks the document type
// and options and presses "Nhận dạng". The image stays selected, so options can be changed and the run repeated.
function selectFile(file) {
  if (!file) return;
  selectedFile = file;
  lastFileName = file.name.replace(/\.[^.]+$/, "") || "result";
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = URL.createObjectURL(file);
  $("viewer").hidden = false;
  $("preview").src = previewUrl;
  $("overlay").innerHTML = "";
  $("meta").textContent = `Ảnh đã chọn: ${file.name} · ${(file.size / 1024).toFixed(0)} KB (chưa nhận dạng)`;
  $("warnings").innerHTML = "";
  $("tabs").hidden = true;
  $("tab-fields").innerHTML = $("tab-lines").innerHTML = $("json").textContent = "";
  $("submit").disabled = false;
  setStatus(`Đã chọn ảnh "${file.name}". Chọn loại giấy tờ, tuỳ chọn rồi bấm "Nhận dạng".`);
  $("submit").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function upload(file) {
  if (!file) return;
  const documentType = $("document").value;
  const engine = $("engine").value;
  const mode = engine === "vl" ? "label" : $("mode").value; // VL has no per-line boxes to place
  setStatus(
    engine === "vl" ? "Đang nhận dạng bằng PaddleOCR-VL… (trên CPU có thể mất vài phút)" : "Đang nhận dạng… (lần đầu có thể mất vài chục giây)",
    "loading",
  );
  $("warnings").innerHTML = "";
  $("submit").disabled = true;
  $("submit").textContent = "Đang nhận dạng…";
  const form = new FormData();
  form.append("file", file);
  const crop = $("crop").checked;
  try {
    const query = new URLSearchParams({ crop, engine, mode, document: documentType });
    const res = await fetch(`/api/extract?${query}`, { method: "POST", body: form });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
    render(body);
  } catch (err) {
    setStatus("Lỗi: " + err.message, "error");
  } finally {
    $("submit").disabled = false;
    $("submit").textContent = "Nhận dạng";
  }
}

function render(r) {
  lastResult = r;
  const t = r.timing_ms;
  const total = t.preprocess + t.ocr + t.parse;
  const fields = Object.values(r.fields);
  const found = fields.filter((f) => f.value).length;
  const review = fields.filter((f) => f.needs_review).length;
  const det = r.document_detection;
  const detected = !det
    ? ""
    : `Tự nhận diện: ${$("document").querySelector(`option[value="${det.detected}"]`)?.textContent || det.detected}` +
      `${det.guessed ? " (đoán, không thấy tiêu đề)" : det.confident ? "" : " (không chắc chắn)"} · `;
  if (!r.document) {
    setStatus(
      `Không nhận diện được loại giấy tờ — chỉ có chữ OCR (${r.ocr.lines.length} dòng). Xong trong ${(total / 1000).toFixed(1)}s.`,
      "error",
    );
  } else {
    setStatus(
      `${detected}Xong trong ${(total / 1000).toFixed(1)}s — trích được ${found}/${fields.length} trường, ${review} trường cần kiểm tra lại.`,
    );
  }

  $("warnings").innerHTML = warningsHtml(r);

  // Image + OCR boxes
  $("viewer").hidden = false;
  $("preview").src = r.processed_image;
  const svg = $("overlay");
  svg.setAttribute("viewBox", `0 0 ${r.ocr.image_size.join(" ")}`);
  svg.innerHTML = `<g id="boxesLayer">${boxesSvg(r.ocr.lines)}</g><g id="zonesLayer">${zonesSvg(r.layout)}</g>`;
  syncLayers();
  const reg = r.layout?.registration;
  $("meta").textContent =
    `ID ${r.request_id} · ảnh gốc ${r.ocr.original_size.join("×")} · ` +
    `${r.ocr.model} · ${r.ocr.lines.length} dòng · độ tin cậy TB ${r.mean_ocr_confidence ?? "–"} · ` +
    `${r.ocr.card_cropped ? "đã cắt & nắn thẻ" : "không tìm thấy viền thẻ, dùng ảnh gốc"} · ` +
    (reg ? `khớp mẫu thẻ: ${reg.anchors_used} mốc, sai số ${reg.residual ?? "–"}, xoay ${reg.rotation_deg}° · ` : "") +
    `tiền xử lý ${t.preprocess}ms, OCR ${t.ocr}ms`;

  $("tab-fields").innerHTML = fieldsTableHtml(r.fields, r.document_type);

  // JSON (without the base64 image, which is only for display)
  const { processed_image, ...clean } = r;
  $("json").textContent = JSON.stringify(clean, null, 2);

  $("tab-lines").innerHTML =
    `<table class="lines">` +
    r.ocr.lines.map((l) => `<tr><td>${esc(l.text)}</td><td class="score">${l.score.toFixed(3)}</td></tr>`).join("") +
    `</table>`;

  $("tabs").hidden = false;
  // Nothing recognised: the OCR text is the whole result, open its tab
  if (!r.document) document.querySelector('#tabs button[data-tab="lines"]').click();
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

function zonesSvg(layout) {
  return Object.entries(layout?.zones_px || {})
    .map(([key, quad]) => `<polygon class="zone" points="${quad.map((p) => p.join(",")).join(" ")}"><title>${esc(key)}</title></polygon>`)
    .join("");
}

function syncLayers() {
  const boxes = document.getElementById("boxesLayer"), zones = document.getElementById("zonesLayer");
  if (boxes) boxes.style.display = $("showBoxes").checked ? "" : "none";
  if (zones) zones.style.display = $("showZones").checked ? "" : "none";
}

const SOURCE_TAGS = { zone: "theo vị trí", "label+zone": "nhãn + vị trí khớp" };

function fieldsTableHtml(fields, documentType) {
  const names = FIELD_LABELS[documentType] || {};
  const rows = Object.entries(fields)
    .map(([key, f]) => {
      const [vi, jp] = names[key] || [key, ""];
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
      const source = SOURCE_TAGS[f.source] && f.value ? `<span class="badge plain">${SOURCE_TAGS[f.source]}</span>` : "";
      return `<tr><th>${esc(vi)}<span class="jp">${esc(jp)}</span></th><td>${val}${badge}${source}${raw}${notes}</td></tr>`;
    })
    .join("");
  if (!rows) return `<p class="sub">Không nhận diện được loại giấy tờ nên không có trường nào; xem tab "Dòng OCR" hoặc <code>full_text</code> trong JSON.</p>`;
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
      `<p class="sub">Ảnh mẫu (見本) chính thức do cơ quan Nhật công bố (Cục Xuất nhập cảnh, chính quyền tỉnh/thành phố, cảnh sát tỉnh), ` +
      `dữ liệu in trên mẫu là giả. Nguồn ghi dưới từng mẫu. Kết quả chạy sẵn ngày ${esc(data.generated)}; bấm "Chạy lại" để OCR trực tiếp.</p>` +
      data.samples.map(sampleCardHtml).join("");
    el.querySelectorAll("button[data-rerun]").forEach((b) =>
      b.addEventListener("click", async () => {
        const blob = await (await fetch(b.dataset.rerun)).blob();
        showView("upload");
        $("document").value = b.dataset.document;
        syncEngine();
        selectFile(new File([blob], b.dataset.rerun.split("/").pop(), { type: blob.type }));
        upload(selectedFile); // the sample already carries its document type: run straight away
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
          <span class="badge design">document=${esc(s.document)}</span>
          ${r.card_design ? `<span class="badge design">${esc(DESIGN_LABELS[r.card_design] || r.card_design)}</span>` : ""}${qualityBadge}
          <span class="badge plain">đọc được ${found}/${total} trường · ${review} cần kiểm tra · OCR ${(r.timing_ms.ocr / 1000).toFixed(1)}s</span>
        </p>
      </header>
      <div class="sample-body">
        <div>
          <div class="stage">
            <img src="${esc(s.processed_image)}" alt="${esc(s.title)}" loading="lazy">
            <svg viewBox="0 0 ${r.ocr.image_size.join(" ")}">${boxesSvg(r.ocr.lines)}</svg>
          </div>
          <p class="meta">Ảnh gốc ${r.ocr.original_size.join("×")}px · <a href="${esc(s.image)}" target="_blank">xem ảnh gốc</a> ·
            nguồn: <a href="${esc(s.source_page)}" target="_blank" rel="noopener">${esc(s.source_name)}</a>${
              s.source_pdf ? ` (<a href="${esc(s.source_pdf)}" target="_blank" rel="noopener">PDF</a>)` : ""}</p>
          <button class="rerun" data-rerun="${esc(s.image)}" data-document="${esc(s.document)}">Chạy lại trực tiếp</button>
          ${warningsHtml(r)}
        </div>
        <div>${fieldsTableHtml(r.fields, r.document_type)}</div>
      </div>
    </article>`;
}

function showView(view) {
  document.querySelectorAll("#views button").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  $("view-upload").hidden = view !== "upload";
  $("view-samples").hidden = view !== "samples";
  $("view-docs").hidden = view !== "docs";
  $("view-guide").hidden = view !== "guide";
  $("view-api").hidden = view !== "api";
  if (view === "samples") loadSamples();
  if (view === "docs") loadDocs();
  try {
    localStorage.setItem("view", view);
  } catch {}
}

$("views").addEventListener("click", (e) => {
  if (e.target.dataset?.view) showView(e.target.dataset.view);
});
try {
  const savedView = localStorage.getItem("view");
  if (["samples", "docs", "guide", "api"].includes(savedView)) showView(savedView);
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

$("showBoxes").addEventListener("change", syncLayers);
$("showZones").addEventListener("change", syncLayers);
// Document type: remembered per browser. engine=vl only reads by label (no per-line boxes for zone/hybrid).
function syncEngine() {
  $("mode").disabled = $("engine").value === "vl";
}
try {
  const saved = localStorage.getItem("document");
  if (saved && $("document").querySelector(`option[value="${saved}"]`)) $("document").value = saved;
} catch {}
$("document").addEventListener("change", () => {
  syncEngine();
  try {
    localStorage.setItem("document", $("document").value);
  } catch {}
});
$("engine").addEventListener("change", syncEngine);
syncEngine();

// Upload: click, drag & drop, paste
fileInput.addEventListener("change", () => {
  selectFile(fileInput.files[0]);
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
drop.addEventListener("drop", (e) => selectFile(e.dataTransfer.files[0]));
window.addEventListener("paste", (e) => {
  const item = [...e.clipboardData.items].find((i) => i.type.startsWith("image/"));
  if (item) selectFile(item.getAsFile());
});

// Camera. getUserMedia only works in a secure context (https or localhost): a phone opening the demo at
// http://<LAN IP> falls back to <input capture>, which opens the phone's own camera app (better photos anyway).
const camera = { stream: null, facing: "environment" };

async function openCamera() {
  if (!navigator.mediaDevices?.getUserMedia || !window.isSecureContext) {
    $("cameraInput").click();
    return;
  }
  try {
    await startStream();
    $("camera").hidden = false;
  } catch (err) {
    setStatus(`Không mở được camera (${err.name || err.message}), chuyển sang chọn ảnh.`, "error");
    $("cameraInput").click();
  }
}

async function startStream() {
  stopStream();
  camera.stream = await navigator.mediaDevices.getUserMedia({
    // ask for the highest resolution: text on the card needs ≥ 1500px across the card
    video: { facingMode: { ideal: camera.facing }, width: { ideal: 3840 }, height: { ideal: 2160 } },
    audio: false,
  });
  $("cameraVideo").srcObject = camera.stream;
}

function stopStream() {
  camera.stream?.getTracks().forEach((t) => t.stop());
  camera.stream = null;
}

function closeCamera() {
  stopStream();
  $("cameraVideo").srcObject = null;
  $("camera").hidden = true;
}

function takePhoto() {
  const video = $("cameraVideo");
  if (!video.videoWidth) return;
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d").drawImage(video, 0, 0);
  canvas.toBlob(
    (blob) => {
      closeCamera();
      const stamp = new Date().toISOString().replace(/[:.]/g, "-");
      selectFile(new File([blob], `camera_${stamp}.jpg`, { type: "image/jpeg" }));
    },
    "image/jpeg",
    0.92,
  );
}

$("cameraBtn").addEventListener("click", openCamera);
$("cameraShot").addEventListener("click", takePhoto);
$("submit").addEventListener("click", () => upload(selectedFile));
$("cameraClose").addEventListener("click", closeCamera);
$("cameraSwitch").addEventListener("click", async () => {
  camera.facing = camera.facing === "environment" ? "user" : "environment";
  try {
    await startStream();
  } catch (err) {
    setStatus(`Không đổi được camera: ${err.name || err.message}`, "error");
  }
});
$("camera").addEventListener("click", (e) => {
  if (e.target === $("camera")) closeCamera();
});
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !$("camera").hidden) closeCamera();
});
$("cameraInput").addEventListener("change", () => {
  selectFile($("cameraInput").files[0]);
  $("cameraInput").value = "";
});
