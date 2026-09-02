const state = {
  data: { setup: [], trigger: [], meta: {} },
  activeList: "setup",
  query: "",
  sortKey: "rank",
  sortDirection: 1,
};

const els = {
  body: document.querySelector("#result-body"),
  empty: document.querySelector("#empty-state"),
  dateSelect: document.querySelector("#date-select"),
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

function updateSummary() {
  const meta = state.data.meta || {};
  document.querySelector("#trade-date").textContent = meta.trade_date || "—";
  document.querySelector("#generated-at").textContent = meta.generated_at
    ? `更新 ${new Date(meta.generated_at).toLocaleString("zh-TW")}`
    : meta.message || "等待資料";
  document.querySelector("#market-state").textContent = meta.market_above_ma60 === undefined
    ? "—"
    : meta.market_above_ma60 ? "MA60 多頭" : "MA60 偏弱";
  document.querySelector("#market-return").textContent = meta.market_return_5d === undefined
    ? "TAIEX 5 日報酬 —"
    : `${meta.benchmark_source} 5 日 ${signed(meta.market_return_5d)}`;
  document.querySelector("#setup-count").textContent = state.data.setup?.length || 0;
  document.querySelector("#trigger-count").textContent = state.data.trigger?.length || 0;
  document.querySelector("#data-note").textContent = meta.download_errors
    ? `本次有 ${meta.download_errors} 筆下載錯誤，請查看 workflow 紀錄。`
    : "收盤後訊號，僅供研究。";
}

function visibleRows() {
  const rows = [...(state.data[state.activeList] || [])];
  const query = state.query.trim().toLowerCase();
  const filtered = query
    ? rows.filter((row) => `${row.stock_id} ${row.stock_name}`.toLowerCase().includes(query))
    : rows;
  return filtered.sort((a, b) => {
    const aValue = a[state.sortKey];
    const bValue = b[state.sortKey];
    if (typeof aValue === "string") return aValue.localeCompare(bValue) * state.sortDirection;
    return ((aValue ?? -Infinity) - (bValue ?? -Infinity)) * state.sortDirection;
  });
}

function render() {
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
      <td>${state.activeList === "trigger" ? "已突破" : signed(row.distance_to_high20_pct)}</td>
      <td>${(row.reasons || []).map((reason) => `<span class="tag">${escapeHtml(reason)}</span>`).join("")}</td>
    </tr>
  `).join("");
  els.empty.hidden = rows.length > 0;
}

async function loadData(path = "data/latest.json") {
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
    els.empty.querySelector("strong").textContent = "資料載入失敗";
    els.empty.querySelector("span").textContent = error.message;
  }
}

async function loadDates() {
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

document.querySelectorAll(".tab").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((tab) => {
      const active = tab === button;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", String(active));
    });
    state.activeList = button.dataset.list;
    state.sortKey = "rank";
    state.sortDirection = 1;
    els.csv.href = `data/${state.activeList}_latest.csv`;
    render();
  });
});

els.search.addEventListener("input", (event) => {
  state.query = event.target.value;
  render();
});

els.dateSelect.addEventListener("change", (event) => {
  const value = event.target.value;
  loadData(value === "latest" ? "data/latest.json" : `data/archive/${value}.json`);
});

document.querySelectorAll("th[data-sort]").forEach((header) => {
  header.addEventListener("click", () => {
    const key = header.dataset.sort;
    state.sortDirection = state.sortKey === key ? state.sortDirection * -1 : 1;
    state.sortKey = key;
    render();
  });
});

loadDates();
loadData();
