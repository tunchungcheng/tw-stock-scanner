const state = {
  data: { setup: [], meta: {} },
  query: "",
  sortKey: "rank",
  sortDirection: 1,
  reasonPriority: "",
};

const reasonOptions = [
    "收盤 > MA5 > MA20",
    "KD 動能加速",
    "5 日漲幅 1%～8%",
    "5 日相對強勢",
    "量比 1.0～2.5",
    "突破 10 日高點",
    "前日收斂、今日帶寬回升",
    "距 20 日高點不超過 5%",
];

const els = {
  body: document.querySelector("#result-body"),
  empty: document.querySelector("#empty-state"),
  dateSelect: document.querySelector("#date-select"),
  reasonSort: document.querySelector("#reason-sort"),
  search: document.querySelector("#search-input"),
  csv: document.querySelector("#csv-link"),
};

const number = (value, digits = 2) =>
  value === null || value === undefined ? "—" : Number(value).toFixed(digits);

const signed = (value) => {
  if (value === null || value === undefined) return "—";
  const numeric = Number(value);
  return `${numeric > 0 ? "+" : ""}${numeric.toFixed(2)}%`;
};

const tone = (value) => Number(value) > 0 ? "positive" : Number(value) < 0 ? "negative" : "";
const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
})[character]);
const setText = (selector, value) => {
  const element = document.querySelector(selector);
  if (element) element.textContent = value;
};

function updateSummary() {
  const meta = state.data.meta || {};
  setText("#trade-date", meta.trade_date || "—");
  setText("#generated-at", meta.generated_at
    ? `更新 ${new Date(meta.generated_at).toLocaleString("zh-TW")}`
    : meta.message || "等待資料");
  setText("#market-state", meta.market_above_ma60 === undefined
    ? "—"
    : meta.market_above_ma60 ? "MA60 多頭" : "MA60 偏弱");
  setText("#market-return", meta.market_return_5d === undefined
    ? "TAIEX 5 日報酬 —"
    : `${meta.benchmark_source} 5 日 ${signed(meta.market_return_5d)}`);
  setText("#setup-count", state.data.setup?.length || 0);
  setText("#data-note", meta.download_errors
    ? `本次有 ${meta.download_errors} 筆下載錯誤，請查看 workflow 紀錄。`
    : "收盤後訊號，僅供研究。");
}

function visibleRows() {
  const rows = [...(state.data.setup || [])];
  const query = state.query.trim().toLowerCase();
  const filtered = query
    ? rows.filter((row) => `${row.stock_id} ${row.stock_name}`.toLowerCase().includes(query))
    : rows;
  return filtered.sort((a, b) => {
    if (state.reasonPriority) {
      const aMatches = (a.reasons || []).includes(state.reasonPriority);
      const bMatches = (b.reasons || []).includes(state.reasonPriority);
      if (aMatches !== bMatches) return bMatches - aMatches;
      if ((a.score ?? 0) !== (b.score ?? 0)) return (b.score ?? 0) - (a.score ?? 0);
    }
    const aValue = a[state.sortKey];
    const bValue = b[state.sortKey];
    if (state.sortKey === "reasons") {
      return ((a.reasons || []).length - (b.reasons || []).length) * state.sortDirection;
    }
    if (typeof aValue === "string") return aValue.localeCompare(bValue) * state.sortDirection;
    return ((aValue ?? -Infinity) - (bValue ?? -Infinity)) * state.sortDirection;
  });
}

function updateReasonOptions() {
  if (!els.reasonSort) return;
  const current = state.reasonPriority;
  els.reasonSort.innerHTML = '<option value="">依入選原因排序</option>';
  reasonOptions.forEach((reason) => {
    const option = document.createElement("option");
    option.value = reason;
    option.textContent = reason;
    els.reasonSort.append(option);
  });
  els.reasonSort.value = reasonOptions.includes(current) ? current : "";
  state.reasonPriority = els.reasonSort.value;
}

function render() {
  if (!els.body || !els.empty) return;
  const rows = visibleRows();
  els.body.innerHTML = rows.map((row) => `
    <tr>
      <td class="rank">${row.rank}</td>
      <td><span class="stock"><strong>${escapeHtml(row.stock_id)} ${escapeHtml(row.stock_name)}</strong><span>${escapeHtml(row.market)}</span></span></td>
      <td class="score">${row.score}</td>
      <td>${number(row.close)}</td>
      <td class="${tone(row.pct_change)}">${signed(row.pct_change)}</td>
      <td class="${tone(row.return_5d)}">${signed(row.return_5d)}</td>
      <td class="${tone(row.return_20d)}">${signed(row.return_20d)}</td>
      <td>${number(row.volume_ratio)}×</td>
      <td>${number(row.k, 1)} / ${number(row.d, 1)}</td>
      <td>${signed(row.distance_to_high20_pct)}</td>
      <td>${(row.reasons || []).map((reason) => `<span class="tag">${escapeHtml(reason)}</span>`).join("")}</td>
    </tr>
  `).join("");
  els.empty.hidden = rows.length > 0;
}

async function loadData(path = "data/latest.json") {
  if (!els.body || !els.empty) return;
  els.body.innerHTML = "";
  els.empty.hidden = true;
  try {
    const response = await fetch(path, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.data = await response.json();
    updateSummary();
    render();
  } catch (error) {
    els.empty.hidden = false;
    const title = els.empty.querySelector("strong");
    const detail = els.empty.querySelector("span");
    if (title) title.textContent = "資料載入失敗";
    if (detail) detail.textContent = error.message;
  }
}

async function loadDates() {
  if (!els.dateSelect) return;
  try {
    const response = await fetch("data/index.json", { cache: "no-store" });
    const { dates = [] } = await response.json();
    dates.forEach((date) => {
      const option = document.createElement("option");
      option.value = date;
      option.textContent = date;
      els.dateSelect.append(option);
    });
  } catch (_) {
    // 最新資料仍可正常顯示。
  }
}

els.reasonSort?.addEventListener("change", (event) => {
  state.reasonPriority = event.target.value;
  state.sortKey = "rank";
  state.sortDirection = 1;
  render();
});

els.search?.addEventListener("input", (event) => {
  state.query = event.target.value;
  render();
});

els.dateSelect?.addEventListener("change", (event) => {
  const value = event.target.value;
  loadData(value === "latest" ? "data/latest.json" : `data/archive/${value}.json`);
});

document.querySelectorAll("th[data-sort]").forEach((header) => {
  header.addEventListener("click", () => {
    const key = header.dataset.sort;
    state.sortDirection = state.sortKey === key
      ? state.sortDirection * -1
      : key === "reasons" ? -1 : 1;
    state.sortKey = key;
    render();
  });
});

updateReasonOptions();
loadDates();
loadData();
