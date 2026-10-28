// "Giấy tờ hỗ trợ" view: the Japanese documents the API reads, with the fields returned and where they sit on the card.
// Residence card illustrations = ISA specimen (static/samples) + value boxes from /api/zones (the templates mode=zone uses);
// example values = the precomputed specimen results (static/samples/results.json, fake data printed on the specimen).
// The other documents have no specimen image: drawn as schematics (approximate positions, made-up text).

// [key, Vietnamese name, label printed on the card, value format]
const RESIDENCE_DOC_FIELDS = [
  ["card_number", "Số thẻ", "番号", "2 chữ + 8 số + 2 chữ; tự sửa ký tự OCR hay nhầm (O→0, I→1…)"],
];
const MY_NUMBER_DOC_FIELDS = [
  ["issuer", "Nơi cấp", "○○市長 / 区長 / 町長 / 村長", "Tên thị trưởng/trưởng quận nơi cấp, như in trên thẻ"],
  ["expiry_date", "Có hiệu lực đến", "YYYY年 M月 D日まで有効", "Ngày ISO; không đọc được まで有効 thì lấy ngày muộn nhất + cần kiểm tra"],
];
const DRIVER_LICENSE_DOC_FIELDS = [
  ["license_number", "Số bằng lái", "番号 第 ____________ 号", "12 chữ số; 2 số đầu = mã công an tỉnh (公安委員会), sai mã thì cần kiểm tra"],
  ["issue_date", "Ngày cấp", "交付", "Ngày ISO (đổi từ năm 令和/平成); bỏ số tra cứu 5 chữ số in sau ngày"],
];
const PASSPORT_DOC_FIELDS = [
  ["passport_number", "Số hộ chiếu", "旅券番号 / Passport No. + dòng MRZ", "2 chữ + 7 số; ưu tiên MRZ khi đúng check digit, khác số in trên trang thì cần kiểm tra"],
];
const HEALTH_INSURANCE_DOC_FIELDS = [
  ["card_type", "Loại thẻ", "国民健康保険被保険者証 / 健康保険被保険者証 / …資格確認書", "Tên thẻ như in (bỏ khoảng trắng)"],
  ["insurer_name", "Đơn vị bảo hiểm (nơi cấp)", "保険者名称 / 交付者名", "Chữ sau nhãn tới hết dòng (bỏ dấu 印)"],
  ["issue_date", "Ngày cấp", "交付年月日 / …交付", "Ngày ISO (nhận cả R5.4.1)"],
];

// Schematic drawings: card size in px (ID-1 1600×1009, passport page ID-3 1600×1126), texts [x, y, text, size, class],
// dashed slots (photo…) [x, y, w, h], boxes of the fields read [key, x, y, w, h] (a key may have several boxes).
const SCHEMATICS = {
  jp_mynumber: {
    h: 1009,
    texts: [
      [60, 90, "個人番号カード", 52, "title"],
      [60, 190, "氏名", 26, "lbl"], [150, 190, "番号　花子", 40],
      [60, 290, "住所", 26, "lbl"], [150, 290, "○○県○○市○○町○丁目○番地○○号", 34],
      [60, 390, "昭和○○年 ○月 ○日生", 34], [560, 390, "性別", 26, "lbl"], [640, 390, "女", 34],
      [60, 520, "2035年 3月31日まで有効", 36],
      [60, 640, "電子証明書の有効期限の記載欄", 22, "lbl"],
      [60, 880, "○○市長", 34],
      [1290, 440, "写真", 34, "lbl"], [1150, 760, "セキュリティコード ○○○○", 24, "lbl"], [1150, 820, "臓器提供意思", 24, "lbl"],
    ],
    slots: [[60, 660, 560, 120], [1150, 190, 380, 480]],
    zones: [["issuer", 45, 838, 200, 58], ["expiry_date", 45, 478, 470, 58]],
  },
  jp_driver_license: {
    h: 1009,
    texts: [
      [60, 100, "氏名", 26, "lbl"], [150, 100, "日本　花子", 40], [800, 100, "昭和○○年 ○月 ○日生", 32],
      [60, 200, "住所", 26, "lbl"], [150, 200, "東京都○○区○○町○丁目○番○号", 34],
      [60, 300, "交付", 26, "lbl"], [150, 300, "令和03年05月10日 12345", 34],
      [60, 400, "2029年(令和11年)06月01日まで有効", 36],
      [60, 520, "免許の", 22, "lbl"], [60, 550, "条件等", 22, "lbl"], [170, 540, "眼鏡等", 32],
      [60, 680, "番号", 26, "lbl"], [150, 680, "第 301234567890 号", 40],
      [700, 690, "運転免許証", 48, "title"],
      [60, 800, "二・小・原", 26, "lbl"], [300, 800, "他", 26, "lbl"], [500, 800, "種類", 26, "lbl"],
      [1080, 920, "東京都公安委員会", 34],
      [1290, 470, "写真", 34, "lbl"],
    ],
    slots: [[55, 760, 600, 180], [1150, 230, 390, 480]],
    zones: [["license_number", 140, 638, 460, 58], ["issue_date", 140, 258, 335, 58]],
  },
  jp_passport: {
    h: 1126,
    texts: [
      [60, 80, "日本国 JAPAN", 34, "title"], [700, 80, "旅券 PASSPORT", 34, "title"],
      [520, 170, "型/Type", 20, "lbl"], [520, 205, "P", 30], [720, 170, "発行国/Issuing country", 20, "lbl"], [720, 205, "JPN", 30],
      [1080, 170, "旅券番号/Passport No.", 20, "lbl"], [1080, 205, "TR1234567", 34],
      [520, 270, "姓/Surname", 20, "lbl"], [520, 305, "NIHON", 30],
      [520, 360, "名/Given name", 20, "lbl"], [520, 395, "HANAKO", 30],
      [520, 450, "国籍/Nationality", 20, "lbl"], [520, 485, "JAPAN", 30],
      [520, 540, "生年月日/Date of birth", 20, "lbl"], [520, 575, "01 JAN 1990", 30],
      [520, 630, "発行年月日/Date of issue", 20, "lbl"], [520, 665, "01 APR 2024", 30],
      [520, 720, "有効期間満了日/Date of expiry", 20, "lbl"], [520, 755, "01 APR 2034", 30],
      [210, 470, "写真", 34, "lbl"],
      [60, 960, "P<JPNNIHON<<HANAKO<<<<<<<<<<<<<<<<<<<<<<<<<", 38, "mrz"],
      [60, 1040, "TR12345672JPN9001011F3404012<<<<<<<<<<<<<<04", 38, "mrz"],
    ],
    slots: [[60, 150, 400, 520]],
    zones: [["passport_number", 1070, 172, 200, 46], ["passport_number", 50, 1003, 265, 50]],
  },
  jp_health_insurance: {
    h: 1009,
    texts: [
      [60, 90, "健康保険", 40, "title"], [260, 90, "被保険者証", 40, "title"], [520, 90, "本人(被保険者)", 28],
      [1000, 90, "令和 5年 4月 1日交付", 30],
      [60, 200, "記号", 24, "lbl"], [150, 200, "1234", 32], [380, 200, "番号", 24, "lbl"], [470, 200, "56", 32],
      [60, 300, "氏名", 24, "lbl"], [150, 300, "保険　花子", 36],
      [60, 400, "生年月日", 24, "lbl"], [200, 400, "昭和○○年 ○月 ○日", 32], [800, 400, "性別", 24, "lbl"], [880, 400, "女", 32],
      [60, 500, "資格取得年月日", 24, "lbl"], [260, 500, "令和 5年 4月 1日", 32],
      [60, 640, "事業所名称", 24, "lbl"], [230, 640, "株式会社○○", 32],
      [60, 760, "保険者番号", 24, "lbl"], [230, 760, "01130012", 32],
      [60, 860, "保険者名称", 24, "lbl"], [230, 860, "全国健康保険協会 東京支部", 32], [1300, 860, "印", 32, "lbl"],
    ],
    slots: [],
    zones: [["card_type", 45, 48, 440, 58], ["insurer_name", 220, 818, 420, 58], ["issue_date", 990, 48, 400, 58]],
  },
};

const DOCS = [
  {
    document: "jp_residence",
    design: "2012",
    title: "在留カード — mẫu hiện hành (cấp đến 13/06/2026)",
    image: "/static/samples/residence_card_current_processed.jpg",
    sample: "residence_card_current",
    fields: RESIDENCE_DOC_FIELDS,
    note: "Chỉ trả số thẻ (các mục khác vẫn đọc nội bộ để nhận mẫu thẻ, không trả về). Số thẻ in góc trên bên phải.",
  },
  {
    document: "jp_residence",
    design: "2026",
    title: "在留カード — mẫu mới (cấp từ 14/06/2026)",
    image: "/static/samples/residence_card_new_2026_processed.jpg",
    sample: "residence_card_new_2026",
    fields: RESIDENCE_DOC_FIELDS,
    note: "Chỉ trả số thẻ; mẫu mới in số thẻ ở phía dưới. Tự nhận mẫu, không cần chọn.",
  },
  {
    document: "jp_mynumber",
    title: "マイナンバーカード — thẻ My Number (個人番号カード)",
    schematic: true,
    sample: "my_number_card",
    fields: MY_NUMBER_DOC_FIELDS,
    note:
      "Chỉ lấy nơi cấp và hạn thẻ; họ tên, địa chỉ, ngày sinh, giới tính cố ý không lấy. Ví dụ = ảnh mẫu của TP Kobe " +
      "(nơi cấp 「□□市長」 bị dấu みほん che nên không đọc được). Chưa thử ảnh chụp thẻ thật.",
  },
  {
    document: "jp_driver_license",
    title: "運転免許証 — bằng lái xe Nhật",
    schematic: true,
    sample: "driver_license",
    fields: DRIVER_LICENSE_DOC_FIELDS,
    note:
      "Chỉ lấy số bằng lái và ngày cấp. Ví dụ = ảnh mẫu của cảnh sát tỉnh Kanagawa (rất nhỏ, ngày cấp không đọc được). " +
      "Chưa thử ảnh chụp thật.",
  },
  {
    document: "jp_passport",
    title: "旅券 — hộ chiếu Nhật (trang ảnh)",
    schematic: true,
    sample: "passport_2025",
    fields: PASSPORT_DOC_FIELDS,
    note:
      "Chỉ hộ chiếu Nhật, chỉ lấy số hộ chiếu. Không tự cắt ảnh (trang hộ chiếu không phải cỡ thẻ ID-1): chụp rõ trang ảnh, " +
      "đủ cả 2 dòng MRZ ở dưới. Ví dụ = ảnh mẫu 2025 của tỉnh Kanagawa (MRZ khớp số in). Chưa thử ảnh chụp thật.",
  },
  {
    document: "jp_health_insurance",
    title: "健康保険証 / 資格確認書 — thẻ bảo hiểm y tế Nhật",
    schematic: true,
    sample: "health_insurance_shikaku_kakuninsho",
    fields: HEALTH_INSURANCE_DOC_FIELDS,
    note:
      "Lấy loại thẻ, đơn vị bảo hiểm, ngày cấp. Thẻ ngừng cấp mới từ 02/12/2024; 資格確認書 thay thế có bố cục tương tự nên cũng nhận. " +
      "Thẻ 国民健康保険 do thành phố cấp: đơn vị lấy ở 保険者名称 hoặc 交付者名. Ví dụ = 資格確認書 mẫu của TP Nagoya. Chưa thử ảnh chụp thật.",
  },
  {
    document: "jp_residence",
    design: "specified_2026",
    title: "特定在留カード — thẻ cư trú gộp My Number (từ 14/06/2026)",
    image: "/static/samples/specified_residence_card_2026_processed.jpg",
    unsupported: true,
    note: "Nhận ra được mẫu thẻ nhưng bố cục khác, chưa hỗ trợ: số thẻ luôn bị đánh dấu cần kiểm tra.",
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
      `<p class="sub">Các giấy tờ Nhật đọc được (mặt trước / trang ảnh hộ chiếu). Chọn loại giấy tờ ở ô "Giấy tờ" khi upload, hoặc tham số <code>document</code> của API. ` +
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
  const figure = d.schematic ? schematicFigure(d) : cardFigure(d, template);
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

// Drawn layout (no specimen image is bundled); only the fields read are boxed, numbered like the table.
function schematicFigure(d) {
  const s = SCHEMATICS[d.document];
  const num = Object.fromEntries(d.fields.map(([key], i) => [key, i + 1]));
  const texts = s.texts
    .map(([x, y, text, size, cls = ""]) => `<text x="${x}" y="${y}" font-size="${size}" class="${cls}">${esc(text)}</text>`)
    .join("");
  const slots = s.slots.map(([x, y, w, h]) => `<rect class="slot" x="${x}" y="${y}" width="${w}" height="${h}" rx="10"/>`).join("");
  const zones = s.zones
    .map(([key, x, y, w, h]) => `<g class="field-zone" data-fields="${key}">
        <rect x="${x}" y="${y}" width="${w}" height="${h}" rx="6"/>
        <rect class="num-bg" x="${x - 8}" y="${y - 30}" width="44" height="34" rx="17"/>
        <text x="${x + 14}" y="${y - 6}">${num[key]}</text>
      </g>`)
    .join("");
  return `<div class="stage doc-figure">
      <svg class="schematic" viewBox="-20 -40 1640 ${s.h + 60}" role="img" aria-label="${esc(d.title)}">
        <rect class="card" x="0" y="0" width="1600" height="${s.h}" rx="${s.h > 1100 ? 30 : 60}"/>
        ${texts}${slots}${zones}
      </svg>
    </div>
    <p class="meta">Sơ đồ vẽ lại, vị trí ước lượng, chữ là dữ liệu giả; parser đọc theo nhãn/mẫu chữ nên không phụ thuộc vị trí.</p>`;
}
