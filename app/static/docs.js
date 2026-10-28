// "Giấy tờ hỗ trợ" view: the Japanese documents the API reads, with the fields returned and where they sit on the card.
// Residence card illustrations = ISA specimen (static/samples) + value boxes from /api/zones (the templates mode=zone uses);
// example values = the precomputed specimen results (static/samples/results.json, fake data printed on the specimen).
// My Number has no specimen image: drawn as a schematic (approximate positions).

// key -> [Vietnamese name, label printed on the card, value format]
const RESIDENCE_DOC_FIELDS = [
  ["card_number", "Số thẻ", "番号", "2 chữ + 8 số + 2 chữ; tự sửa ký tự OCR hay nhầm (O→0, I→1…)"],
  ["name", "Họ tên", "氏名", "Chữ Latin in hoa như trên thẻ"],
  ["date_of_birth", "Ngày sinh", "生年月日", "Ngày ISO YYYY-MM-DD"],
  ["sex", "Giới tính", "性別", "M / F"],
  ["nationality", "Quốc tịch", "国籍・地域", "Tên nước tiếng Nhật, chuẩn hoá theo danh sách chính thức"],
  ["address", "Địa chỉ", "住居地", "Tiếng Nhật như in trên thẻ"],
  ["status_of_residence", "Tư cách lưu trú", "在留資格", "Chuẩn hoá theo danh sách tư cách chính thức"],
  ["work_restriction", "Hạn chế làm việc", "就労制限の有無", "就労制限なし / 就労不可 / …"],
  ["period_of_stay", "Thời hạn lưu trú", "在留期間", "Ví dụ 4年3月"],
  ["expiration_date", "Ngày hết hạn lưu trú", "在留期間満了日", "Ngày ISO"],
  ["permission_type", "Loại giấy phép", "許可の種類", "Ví dụ 在留期間更新許可"],
  ["issuing_authority", "Cơ quan cấp", "許可機関", "Ví dụ 東京入国在留管理局長"],
  ["permission_date", "Ngày cấp phép", "許可年月日", "Ngày ISO"],
  ["issue_date", "Ngày cấp thẻ", "交付年月日", "Ngày ISO"],
  ["valid_until", "Thẻ có hiệu lực đến", "このカードは…まで有効", "Ngày ISO"],
];
const MY_NUMBER_DOC_FIELDS = [
  ["issuer", "Nơi cấp", "○○市長 / 区長 / 町長 / 村長", "Tên thị trưởng/trưởng quận nơi cấp, như in trên thẻ"],
  ["expiry_date", "Có hiệu lực đến", "YYYY年 M月 D日まで有効", "Ngày ISO; không đọc được まで有効 thì lấy ngày muộn nhất + cần kiểm tra"],
];

const DOCS = [
  {
    document: "jp_residence",
    design: "2012",
    title: "在留カード — mẫu hiện hành (cấp đến 13/06/2026)",
    image: "/static/samples/residence_card_current_processed.jpg",
    sample: "residence_card_current",
    fields: RESIDENCE_DOC_FIELDS,
    note: "In đủ 15 trường ở mặt trước.",
  },
  {
    document: "jp_residence",
    design: "2026",
    title: "在留カード — mẫu mới (cấp từ 14/06/2026)",
    image: "/static/samples/residence_card_new_2026_processed.jpg",
    sample: "residence_card_new_2026",
    fields: RESIDENCE_DOC_FIELDS,
    note:
      "Mẫu mới không in thời hạn lưu trú, loại giấy phép, cơ quan cấp, ngày cấp phép, ngày cấp thẻ (chỉ lưu trong chip IC): " +
      "các trường này trả null và không bị đánh dấu cần kiểm tra. Tự nhận mẫu, không cần chọn.",
  },
  {
    document: "jp_mynumber",
    title: "マイナンバーカード — thẻ My Number (個人番号カード)",
    schematic: true,
    fields: MY_NUMBER_DOC_FIELDS,
    note:
      "Chỉ lấy nơi cấp và hạn thẻ; họ tên, địa chỉ, ngày sinh, giới tính cố ý không lấy. Đọc theo mẫu chữ (không có template vị trí). " +
      "Chưa thử trên ảnh thẻ thật.",
  },
  {
    document: "jp_residence",
    design: "specified_2026",
    title: "特定在留カード — thẻ cư trú gộp My Number (từ 14/06/2026)",
    image: "/static/samples/specified_residence_card_2026_processed.jpg",
    unsupported: true,
    note: "Nhận ra được mẫu thẻ nhưng bố cục khác, chưa hỗ trợ: mọi trường đều bị đánh dấu cần kiểm tra.",
  },
];

let docsLoaded = false;
async function loadDocs() {
  if (docsLoaded) return;
  const el = $("docs");
  try {
    const [zones, samples] = await Promise.all(
      ["/api/zones?document=jp_residence", "/static/samples/results.json"].map(async (url) => {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
        return res.json();
      })
    );
    const examples = Object.fromEntries(samples.samples.map((s) => [s.image.split("/").pop().replace(/\.\w+$/, ""), s.result.fields]));
    docsLoaded = true;
    el.innerHTML =
      `<p class="sub">Các giấy tờ Nhật đọc được (mặt trước). Chọn loại giấy tờ ở ô "Giấy tờ" khi upload, hoặc tham số <code>document</code> của API. ` +
      `Số trên hình minh hoạ = số thứ tự trường trong bảng; rê chuột vào một dòng để xem vị trí. Giá trị ví dụ = kết quả OCR thật trên thẻ mẫu (見本, dữ liệu giả), có thể còn lỗi đọc.</p>` +
      DOCS.map((d) => docHtml(d, zones[d.design], examples[d.sample])).join("");
    el.querySelectorAll(".doc").forEach((card) =>
      card.querySelectorAll("tr[data-field]").forEach((row) => {
        const zone = card.querySelectorAll(`[data-fields~="${row.dataset.field}"]`);
        row.addEventListener("mouseenter", () => zone.forEach((z) => z.classList.add("hl")));
        row.addEventListener("mouseleave", () => zone.forEach((z) => z.classList.remove("hl")));
      })
    );
  } catch (err) {
    el.innerHTML = `<p class="status error">Không tải được: ${esc(err.message)}</p>`;
  }
}

function docHtml(d, template, example) {
  const status = d.unsupported
    ? `<span class="badge review">chưa hỗ trợ</span>`
    : `<span class="badge ok">hỗ trợ</span>`;
  const design = d.design ? `<span class="badge plain">card_design=${esc(d.design)}</span>` : "";
  const figure = d.schematic ? myNumberSchematic() : cardFigure(d, template);
  const table = d.fields ? docFieldsTable(d.fields, template, example) : "";
  return `
    <article class="sample doc">
      <header>
        <h2>${esc(d.title)}</h2>
        <p class="chips">${status}<span class="badge design">document=${esc(d.document)}</span>${design}
          ${d.fields ? `<span class="badge plain">${d.fields.length} trường</span>` : ""}</p>
        <p class="sub">${esc(d.note)}</p>
      </header>
      <div class="sample-body">
        <div>${figure}</div>
        <div>${table}</div>
      </div>
    </article>`;
}

// Numbered value boxes over the specimen; fields sharing one box (permission type + authority) get one box.
function cardFigure(d, template) {
  if (!template) return `<div class="stage"><img src="${esc(d.image)}" alt="${esc(d.title)}" loading="lazy"></div>`;
  const w = 1600, h = w / template.aspect;
  const byBox = new Map();
  (d.fields || []).forEach(([key], i) => {
    const box = template.fields[key]?.value?.box;
    if (!box) return;
    const id = box.join(",");
    if (!byBox.has(id)) byBox.set(id, { box, keys: [], nums: [] });
    byBox.get(id).keys.push(key);
    byBox.get(id).nums.push(i + 1);
  });
  const marks = [...byBox.values()]
    .map(({ box: [x0, y0, x1, y1], keys, nums }) => {
      const label = nums.join(",");
      const bw = 26 + 18 * label.length;
      return `<g class="field-zone" data-fields="${keys.join(" ")}">
        <rect x="${x0 * w}" y="${y0 * h}" width="${(x1 - x0) * w}" height="${(y1 - y0) * h}" rx="6"/>
        <rect class="num-bg" x="${x0 * w - 8}" y="${y0 * h - 30}" width="${bw}" height="34" rx="17"/>
        <text x="${x0 * w - 8 + bw / 2}" y="${y0 * h - 6}">${label}</text>
      </g>`;
    })
    .join("");
  return `<div class="stage doc-figure">
      <img src="${esc(d.image)}" alt="${esc(d.title)}" loading="lazy">
      <svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">${marks}</svg>
    </div>
    <p class="meta">Ảnh thẻ mẫu ISA đã cắt + nắn; khung = ô giá trị trong template (mode zone/hybrid).</p>`;
}

function docFieldsTable(fields, template, example) {
  const rows = fields
    .map(([key, vi, printed, format], i) => {
      const notPrinted = template && !template.fields[key];
      const ex = example?.[key]?.value;
      const value = notPrinted
        ? `<span class="val empty">không in trên mẫu này → null</span>`
        : ex
          ? `<span class="val">${esc(ex)}</span>`
          : "";
      return `<tr data-field="${key}" class="${notPrinted ? "absent" : ""}">
        <td class="num">${notPrinted ? "–" : i + 1}</td>
        <th>${esc(vi)}<span class="jp">${esc(printed)}</span><code>${key}</code></th>
        <td>${value}<span class="raw">${esc(format)}</span></td>
      </tr>`;
    })
    .join("");
  return `<table class="doc-fields">${rows}</table>`;
}

// Approximate front layout of the My Number card, drawn (no specimen image is bundled); only the read fields are boxed.
function myNumberSchematic() {
  const t = (x, y, s, size = 30, cls = "") => `<text x="${x}" y="${y}" font-size="${size}" class="${cls}">${s}</text>`;
  const zone = (key, num, x, y, w, h) => `<g class="field-zone" data-fields="${key}">
      <rect x="${x}" y="${y}" width="${w}" height="${h}" rx="6"/>
      <rect class="num-bg" x="${x - 8}" y="${y - 30}" width="44" height="34" rx="17"/>
      <text x="${x + 14}" y="${y - 6}">${num}</text>
    </g>`;
  return `<div class="stage doc-figure">
      <svg class="schematic" viewBox="-20 -40 1640 1070" role="img" aria-label="Sơ đồ mặt trước thẻ My Number">
        <rect class="card" x="0" y="0" width="1600" height="1009" rx="60"/>
        ${t(60, 90, "個人番号カード", 52, "title")}
        ${t(60, 190, "氏名", 26, "lbl")}${t(150, 190, "番号　花子", 40)}
        ${t(60, 290, "住所", 26, "lbl")}${t(150, 290, "○○県○○市○○町○丁目○番地○○号", 34)}
        ${t(60, 390, "昭和○○年 ○月 ○日生", 34)}${t(560, 390, "性別", 26, "lbl")}${t(640, 390, "女", 34)}
        ${t(60, 520, "2035年 3月31日まで有効", 36)}
        ${t(60, 640, "電子証明書の有効期限の記載欄", 22, "lbl")}
        <rect class="slot" x="60" y="660" width="560" height="120" rx="8"/>
        ${t(60, 880, "○○市長", 34)}
        <rect class="slot" x="1150" y="190" width="380" height="480" rx="10"/>
        ${t(1290, 440, "写真", 34, "lbl")}
        ${t(1150, 760, "セキュリティコード ○○○○", 24, "lbl")}
        ${t(1150, 820, "臓器提供意思", 24, "lbl")}
        ${zone("expiry_date", 2, 45, 478, 470, 58)}
        ${zone("issuer", 1, 45, 838, 200, 58)}
      </svg>
    </div>
    <p class="meta">Sơ đồ vẽ lại, vị trí ước lượng (không có ảnh thẻ mẫu); parser đọc theo mẫu chữ nên không phụ thuộc vị trí.</p>`;
}
