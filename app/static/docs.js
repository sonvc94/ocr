// "Giấy tờ hỗ trợ" view: the Japanese documents the API reads, with the fields returned and where they sit on the card.
// Illustrations = official specimen images (static/samples, made by scripts/build_demo.py) with the fields numbered:
// residence card boxes come from /api/zones (the templates mode=zone uses), the other documents have no template and
// their boxes (`boxes`, relative to the processed image) were measured on the specimen's own OCR lines.
// Example values = the precomputed specimen results (static/samples/results.json, fake data printed on the specimen).

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
const SPECIAL_PERMANENT_DOC_FIELDS = [
  ["certificate_number", "Số giấy chứng nhận", "番号", "2 chữ + 8 số + 2 chữ (như thẻ cư trú); tự sửa chữ ↔ số theo vị trí"],
  ["expiry_date", "Hạn", "有効期間の満了日 / …まで有効", "Ngày ISO; hết hạn thì cảnh báo"],
];
const DRIVING_HISTORY_DOC_FIELDS = [
  ["license_number", "Số bằng lái (đã trả lại)", "番号 第 ____________ 号", "12 chữ số, như bằng lái; 2 số đầu = mã công an tỉnh"],
  ["issue_date", "Ngày cấp giấy chứng nhận", "交付", "Ngày ISO; bỏ số tra cứu in sau ngày"],
];
const JUKI_CARD_DOC_FIELDS = [
  ["issuer", "Nơi cấp", "○○市 (dòng riêng) / ○○市長", "Tên thành phố/quận nơi cấp, như in trên thẻ"],
  ["expiry_date", "Hạn thẻ", "有効期限 / …まで有効", "Ngày ISO; mọi thẻ đã hết hạn (ngừng cấp 12/2015) → luôn cảnh báo"],
];
const RESIDENT_RECORD_DOC_FIELDS = [
  ["issuer", "Nơi chứng nhận", "○○市長 / ○○区長 (cuối trang)", "Như in, kể cả tên tỉnh (兵庫県神戸市中央区長)"],
  ["certified_date", "Ngày chứng nhận", "…証明する。 令和○年○月○日", "Ngày ISO ngay sau câu chứng nhận"],
  ["address", "Địa chỉ", "住所", "Chữ sau nhãn tới nhãn kế tiếp (không phải 前住所 / 住所を定めた日), bỏ khoảng trắng"],
];
const PENSION_DOC_FIELDS = [
  ["basic_pension_number", "Số hưu trí cơ bản", "基礎年金番号", "Dạng 1234-567890; tự sửa ký tự OCR hay nhầm"],
  ["issue_date", "Ngày cấp", "交付年月日 / …交付", "Ngày ISO; chỉ lấy khi có nhãn 交付 / 発行"],
];

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
    image: "/static/samples/my_number_card_processed.jpg",
    sample: "my_number_card",
    source: "Ảnh mẫu (見本) của TP Kobe",
    boxes: [["issuer", [0.453, 0.437, 0.572, 0.491]], ["expiry_date", [0.649, 0.331, 0.974, 0.390]]],
    fields: MY_NUMBER_DOC_FIELDS,
    note:
      "Chỉ lấy nơi cấp (in dưới ngày sinh, dạng ○○市長) và hạn thẻ (…まで有効); họ tên, địa chỉ, ngày sinh, giới tính cố ý không lấy. " +
      "Trên ảnh mẫu nơi cấp là 「□□市長」 (chữ giữ chỗ) bị dấu みほん đè nên không đọc được. Chưa thử ảnh chụp thẻ thật.",
  },
  {
    document: "jp_driver_license",
    title: "運転免許証 — bằng lái xe Nhật",
    image: "/static/samples/driver_license_processed.jpg",
    sample: "driver_license",
    source: "Ảnh mẫu của cảnh sát tỉnh Kanagawa (đã cắt bỏ chú thích)",
    boxes: [["license_number", [0.040, 0.673, 0.585, 0.735]], ["issue_date", [0.163, 0.291, 0.574, 0.350]]],
    fields: DRIVER_LICENSE_DOC_FIELDS,
    note:
      "Chỉ lấy số bằng lái (第…号) và ngày cấp (dòng 交付, sau ngày là số tra cứu 5 chữ số). Ảnh mẫu rất nhỏ (338px): " +
      "chữ 交付 và niên hiệu của ngày cấp bị đọc sai nên không lấy được ngày cấp. Chưa thử ảnh chụp thật.",
  },
  {
    document: "jp_passport",
    title: "旅券 — hộ chiếu Nhật (trang ảnh)",
    image: "/static/samples/passport_2025_processed.jpg",
    sample: "passport_2025",
    source: "Ảnh mẫu hộ chiếu 2025 của tỉnh Kanagawa (số tròn đỏ có sẵn trên ảnh gốc)",
    boxes: [["passport_number", [0.677, 0.138, 0.853, 0.174]], ["passport_number", [0.049, 0.866, 0.235, 0.906]]],
    fields: PASSPORT_DOC_FIELDS,
    note:
      "Chỉ hộ chiếu Nhật, chỉ lấy số hộ chiếu. Không tự cắt ảnh (trang hộ chiếu không phải cỡ thẻ ID-1): chụp rõ trang ảnh, " +
      "đủ cả 2 dòng MRZ ở dưới. Số đọc ở 2 chỗ: số in cạnh nhãn 旅券番号 và 9 ký tự đầu dòng MRZ thứ 2 (kiểm bằng check digit). " +
      "Mẫu trước 2025 (XS1234567) cũng đọc đúng, xem tab \"Mẫu chính thức\". Chưa thử ảnh chụp thật.",
  },
  {
    document: "jp_health_insurance",
    title: "健康保険証 / 資格確認書 — thẻ bảo hiểm y tế Nhật",
    image: "/static/samples/health_insurance_shikaku_kakuninsho_processed.jpg",
    sample: "health_insurance_shikaku_kakuninsho",
    source: "Ảnh mẫu 資格確認書 bảo hiểm quốc dân của TP Nagoya",
    boxes: [
      ["card_type", [0.016, 0.072, 0.196, 0.183]],
      ["insurer_name", [0.498, 0.824, 0.623, 0.875]],
      ["issue_date", [0.282, 0.540, 0.521, 0.593]],
    ],
    fields: HEALTH_INSURANCE_DOC_FIELDS,
    note:
      "Lấy loại thẻ, đơn vị bảo hiểm, ngày cấp. Thẻ ngừng cấp mới từ 02/12/2024; 資格確認書 thay thế có bố cục tương tự nên cũng nhận. " +
      "Đơn vị lấy ở 保険者名称 (thẻ công ty) hoặc 交付者名 (bảo hiểm quốc dân do thành phố cấp, như mẫu này). " +
      "Tên thẻ in 2 dòng (国民健康保険 / 資格確認書) được ghép lại. Chưa thử ảnh chụp thật.",
  },
  {
    document: "jp_special_permanent",
    title: "特別永住者証明書 — giấy chứng nhận vĩnh trú đặc biệt",
    image: "/static/samples/special_permanent_resident_processed.jpg",
    sample: "special_permanent_resident",
    source: "Ảnh mẫu (見本) trong tờ hướng dẫn của Cục Xuất nhập cảnh",
    boxes: [["certificate_number", [0.760, 0.074, 0.973, 0.120]], ["expiry_date", [0.185, 0.781, 0.628, 0.832]]],
    fields: SPECIAL_PERMANENT_DOC_FIELDS,
    note:
      "Chỉ lấy số giấy chứng nhận và hạn. Mẫu mới (từ 14/06/2026, số in ở dải dưới) và 特定特別永住者証明書 (gộp My Number) cũng đọc đúng, " +
      "xem tab \"Mẫu chính thức\". Số cùng dạng thẻ cư trú; tự nhận diện phân biệt nhờ chữ 特別永住者. Chưa thử ảnh chụp thật.",
  },
  {
    document: "jp_driving_history",
    title: "運転経歴証明書 — giấy chứng nhận lịch sử lái xe",
    image: "/static/samples/driving_history_processed.jpg",
    sample: "driving_history",
    source: "Hình mẫu của tỉnh Okayama (vẽ từ PDF)",
    boxes: [["license_number", [0.084, 0.676, 0.625, 0.753]], ["issue_date", [0.129, 0.257, 0.412, 0.313]]],
    fields: DRIVING_HISTORY_DOC_FIELDS,
    note:
      "Cấp cho người đã trả lại bằng lái; cùng mẫu với bằng lái nên đọc giống hệt. Tự nhận diện nhờ chữ 運転経歴 (thấy chữ này thì không tính là bằng lái). " +
      "Mẫu thật của cảnh sát Aichi (298px) cũng đọc ra số và ngày cấp. Chưa thử ảnh chụp thật.",
  },
  {
    document: "jp_juki_card",
    title: "住民基本台帳カード — thẻ 住基 (có ảnh)",
    image: "/static/samples/juki_card_processed.jpg",
    sample: "juki_card",
    source: "Sơ đồ mẫu thẻ của Bộ Nội vụ (総務省)",
    boxes: [["issuer", [0.314, 0.349, 0.451, 0.432]], ["expiry_date", [0.293, 0.501, 0.631, 0.553]]],
    fields: JUKI_CARD_DOC_FIELDS,
    note:
      "Thẻ ngừng cấp từ 12/2015, hạn tối đa 10 năm: mọi thẻ đã hết hạn, kết quả luôn có cảnh báo. Thẻ in nơi cấp là tên thành phố trên một dòng " +
      "(横浜市), sơ đồ này dùng chữ giữ chỗ △△市. Mẫu thật của TP Yokohama (322px) cũng đọc ra 横浜市 và hạn thẻ. Chưa thử ảnh chụp thật.",
  },
  {
    document: "jp_resident_record",
    title: "住民票の写し — giấy chứng nhận cư trú",
    image: "/static/samples/resident_record_processed.jpg",
    sample: "resident_record",
    source: "Mẫu bố cục chuẩn của TP Kobe",
    boxes: [
      ["issuer", [0.584, 0.924, 0.766, 0.939]],
      ["certified_date", [0.423, 0.869, 0.588, 0.887]],
      ["address", [0.167, 0.219, 0.515, 0.233]],
    ],
    fields: RESIDENT_RECORD_DOC_FIELDS,
    note:
      "Cả trang giấy, không cắt ảnh. Số My Number (個人番号) nếu có in sẽ bị che (****) trong chữ OCR và tô đen trên ảnh, không bao giờ trả về. " +
      "Trên mẫu này ngày chứng nhận là chữ giữ chỗ (令和●年●月●●日) nên không lấy. Bản trích cả hộ: lấy 住所 đầu tiên. Chưa thử ảnh chụp thật.",
  },
  {
    document: "jp_pension_book",
    title: "年金手帳 / 基礎年金番号通知書 — sổ / thông báo số hưu trí",
    image: "/static/samples/pension_notice_processed.jpg",
    sample: "pension_notice",
    source: "Hình minh hoạ 基礎年金番号通知書 (厚生労働省・日本年金機構)",
    boxes: [["basic_pension_number", [0.247, 0.254, 0.859, 0.330]], ["issue_date", [0.248, 0.790, 0.788, 0.877]]],
    fields: PENSION_DOC_FIELDS,
    note:
      "年金手帳 ngừng cấp từ 04/2022, thay bằng 基礎年金番号通知書; cùng số nên nhận cả hai, không cắt ảnh. Hình mẫu chỉ có chữ giữ chỗ " +
      "(XXXX-XXXXXX, 令和X年) nên không có giá trị ví dụ; trang 基礎年金番号 của sổ 年金手帳 mẫu cũng để trống. Chưa thử ảnh chụp thật.",
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
    const examples = Object.fromEntries(samples.samples.map((s) => [s.id, s.result]));
    docsLoaded = true;
    el.innerHTML =
      `<p class="sub">Các giấy tờ Nhật đọc được (mặt trước thẻ, trang ảnh hộ chiếu, trang 住民票 / 年金手帳). Chọn loại giấy tờ ở ô "Giấy tờ" khi upload, hoặc tham số <code>document</code> của API. ` +
      `Số trên hình minh hoạ = số thứ tự trường trong bảng; rê chuột vào một dòng để xem vị trí. Giá trị ví dụ = kết quả OCR thật trên thẻ mẫu (見本, dữ liệu giả), có thể còn lỗi đọc.</p>` +
      DOCS.map((d) => docHtml(d, d.boxes ? null : zones[d.design], examples[d.sample])).join("");
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

function docHtml(d, template, sample) {
  const status = d.unsupported
    ? `<span class="badge review">chưa hỗ trợ</span>`
    : `<span class="badge ok">hỗ trợ</span>`;
  const design = d.design ? `<span class="badge plain">card_design=${esc(d.design)}</span>` : "";
  const boxes = d.boxes || (template ? (d.fields || []).map(([key]) => [key, template.fields[key]?.value?.box]) : []);
  const size = sample?.ocr.image_size;
  const aspect = template ? template.aspect : size ? size[0] / size[1] : null;
  const figure = cardFigure(d, boxes.filter(([, box]) => box), aspect);
  const table = d.fields ? docFieldsTable(d.fields, template, sample?.fields) : "";
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

// Numbered value boxes over the specimen; fields sharing one box (permission type + authority) get one box,
// a field read in two places (passport number + MRZ) gets two. `aspect` = the template's (residence card), else the image's.
function cardFigure(d, boxes, aspect) {
  const img = `<img src="${esc(d.image)}" alt="${esc(d.title)}" loading="lazy">`;
  if (!boxes.length || !aspect) return `<div class="stage">${img}</div>`;
  const w = 1600, h = w / aspect;
  const byBox = new Map();
  boxes.forEach(([key, box]) => {
    const id = box.join(",");
    if (!byBox.has(id)) byBox.set(id, { box, keys: [], nums: [] });
    byBox.get(id).keys.push(key);
    byBox.get(id).nums.push(d.fields.findIndex(([k]) => k === key) + 1);
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
  const how = d.boxes ? "khung = vị trí đọc được trên ảnh mẫu (loại này không có template)" : "khung = ô giá trị trong template (mode zone/hybrid)";
  return `<div class="stage doc-figure">${img}<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">${marks}</svg></div>
    <p class="meta">${esc(d.source || "Ảnh thẻ mẫu ISA đã cắt + nắn")}; ${how}.</p>`;
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
