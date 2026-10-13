const state = {
  data: { setup: [], meta: {} },
};

const els = {
  body: document.querySelector("#result-body"),
  empty: document.querySelector("#empty-state"),
  dateSelect: document.querySelector("#date-select"),
  search: document.querySelector("#stock-search"),
  industry: document.querySelector("#industry-filter"),
  clearFilters: document.querySelector("#clear-filters"),
  kdLowOnly: document.querySelector("#kd-low-only"),
  resultCount: document.querySelector("#result-count"),
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

const stockInfoUrl = (row) => {
  const suffix = row.market === "TPEx" ? "TWO" : "TW";
  return `https://tw.stock.yahoo.com/quote/${encodeURIComponent(row.stock_id)}.${suffix}`;
};

function updateSummary() {
  const meta = state.data.meta || {};
  setText("#trade-date", meta.trade_date || "—");
  setText("#generated-at", meta.generated_at
    ? `更新 ${new Date(meta.generated_at).toLocaleString("zh-TW")}`
    : meta.message || "等待資料");
  setText("#setup-count", state.data.setup?.length || 0);
  setText("#data-note", meta.download_errors
    ? `本次有 ${meta.download_errors} 筆下載錯誤，請查看 workflow 紀錄。`
    : "收盤後訊號，僅供研究。");
}

function visibleRows() {
  const rows = state.data.setup || [];
  const query = (els.search?.value || "").trim().toLocaleLowerCase("zh-TW");
  const industry = els.industry?.value || "";
  return rows.filter((row) => {
    const matchesQuery = !query || [row.stock_id, row.stock_name, row.industry]
      .some((value) => String(value ?? "").toLocaleLowerCase("zh-TW").includes(query));
    const matchesIndustry = !industry || String(row.industry || "未分類") === industry;
    const matchesKdLow = !els.kdLowOnly?.checked || row.kd_relative_low === true;
    return matchesQuery && matchesIndustry && matchesKdLow;
  });
}

function updateFilterOptions() {
  if (!els.industry) return;
  const selected = els.industry.value;
  const industries = [...new Set((state.data.setup || []).map((row) => row.industry || "未分類"))]
    .sort((a, b) => a.localeCompare(b, "zh-TW"));
  els.industry.innerHTML = '<option value="">所有產業</option>';
  industries.forEach((industry) => {
    const option = document.createElement("option");
    option.value = industry;
    option.textContent = industry;
    els.industry.append(option);
  });
  if (industries.includes(selected)) els.industry.value = selected;
}

function updateResultCount(visible, total) {
  if (!els.resultCount) return;
  els.resultCount.textContent = visible === total
    ? `共 ${total} 檔`
    : `顯示 ${visible} / ${total} 檔`;
}

function cell(label, value, className = "") {
  return `<td class="${className}" data-label="${label}">${value}</td>`;
}

function render() {
  if (!els.body || !els.empty) return;
  const allRows = state.data.setup || [];
  const rows = visibleRows();
  updateResultCount(rows.length, allRows.length);
  els.body.innerHTML = rows.map((row) => `
    <tr>
      ${cell("排名", row.rank, "rank")}
      ${cell("股票", `<a class="stock-link" href="${stockInfoUrl(row)}" target="_blank" rel="noopener noreferrer"><span class="stock"><strong>${escapeHtml(row.stock_id)} ${escapeHtml(row.stock_name)}</strong><span>查看股票資訊 ↗</span></span></a>`, "stock-cell")}
      ${cell("產業", escapeHtml(row.industry || "未分類"), "industry")}
      ${cell("月營收 YoY", `<span class="revenue"><strong>${signed(row.revenue_yoy)}</strong><span>${escapeHtml(row.revenue_month || "月份未提供")} · 累計 ${signed(row.revenue_ytd_yoy)}</span></span>`, tone(row.revenue_yoy))}
      ${cell("分數", row.score, "score")}
      ${cell("收盤", number(row.close))}
      ${cell("當日", signed(row.pct_change), tone(row.pct_change))}
      ${cell("5 日", signed(row.return_5d), tone(row.return_5d))}
      ${cell("20 日", signed(row.return_20d), tone(row.return_20d))}
      ${cell("量比", `${number(row.volume_ratio)}×`)}
      ${cell("K / D", `${number(row.k, 1)} / ${number(row.d, 1)}`)}
      ${cell("全市場 KD 百分位", row.kd_relative_rank_pct == null ? "—" : `${number(row.kd_relative_rank_pct, 1)}%`, row.kd_relative_low ? "positive" : "")}
      ${cell("MA20 乖離", signed(row.ma20_deviation_pct), Number(row.ma20_deviation_pct) > 6 ? "warning" : "")}
      ${cell("距高點", signed(row.distance_to_high20_pct))}
      ${cell("入選原因", (row.reasons || []).map((reason) => `<span class="tag">${escapeHtml(reason)}</span>`).join(""))}
    </tr>
  `).join("");
  els.empty.hidden = rows.length > 0;
  const title = els.empty.querySelector("strong");
  const detail = els.empty.querySelector("span");
  if (title && detail) {
    if (allRows.length === 0) {
      title.textContent = "目前沒有符合條件的股票";
      detail.textContent = "嚴格條件下出現空名單是正常結果。";
    } else {
      title.textContent = "找不到符合條件的股票";
      detail.textContent = "請調整搜尋關鍵字或產業篩選。";
    }
  }
}

async function loadPerformance() {
  try {
    const response = await fetch("data/performance.json", { cache: "no-store" });
    if (!response.ok) return;
    const { summary = {} } = await response.json();
    if (!summary.completed_10d) {
      setText("#tracking-result", "樣本累積中");
      setText("#tracking-detail", `已發布 ${summary.published_signals || 0} 筆 · 已進場 ${summary.entered_signals || 0} 筆`);
      return;
    }
    setText("#tracking-result", `${signed(summary.average_return_10d)} · 勝率 ${number(summary.win_rate_10d, 0)}%`);
    setText("#tracking-detail", `${summary.completed_10d} 筆完整樣本 · 已估 ${number(summary.estimated_cost_pct, 1)}% 成本`);
  } catch (_) {}
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
    updateFilterOptions();
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
  } catch (_) {}
}

els.dateSelect?.addEventListener("change", (event) => {
  const value = event.target.value;
  loadData(value === "latest" ? "data/latest.json" : `data/archive/${value}.json`);
});

els.search?.addEventListener("input", render);
els.industry?.addEventListener("change", render);
els.kdLowOnly?.addEventListener("change", render);
els.clearFilters?.addEventListener("click", () => {
  if (els.search) els.search.value = "";
  if (els.industry) els.industry.value = "";
  if (els.kdLowOnly) els.kdLowOnly.checked = false;
  render();
});

loadDates();
loadData();
loadPerformance();
