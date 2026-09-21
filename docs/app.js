const state = {
  data: { setup: [], meta: {} },
  query: "",
  sortKey: "rank",
  sortDirection: 1,
  reasonPriority: "",
};

const reasonOptions = [
    "多頭均線排列",
    "KD 加速且 K < 80",
    "5 日漲幅 1%～8%",
    "5 日相對強勢",
    "量比 1.2～2.5",
    "突破 10 日高點",
    "前日收斂、今日帶寬回升",
    "距 20 日高點不超過 5%",
    "產業相對強勢",
    "MA20 乖離 6%～9%（-1）",
];

const els = {
  body: document.querySelector("#result-body"),
  empty: document.querySelector("#empty-state"),
  dateSelect: document.querySelector("#date-select"),
  reasonSort: document.querySelector("#reason-sort"),
  search: document.querySelector("#search-input"),
  csv: document.querySelector("#csv-link"),
  aiPrompt: document.querySelector("#ai-prompt"),
  copyAiPrompt: document.querySelector("#copy-ai-prompt"),
  aiPromptStatus: document.querySelector("#ai-prompt-status"),
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
  const regimeLabels = { bull: "多頭可操作", neutral: "震盪嚴選", bear: "偏空停選" };
  const contexts = meta.market_contexts || {};
  setText("#trade-date", meta.trade_date || "—");
  setText("#generated-at", meta.generated_at
    ? `更新 ${new Date(meta.generated_at).toLocaleString("zh-TW")}`
    : meta.message || "等待資料");
  setText("#market-state", contexts.TWSE || contexts.TPEx
    ? `上市 ${regimeLabels[contexts.TWSE?.market_regime] || "—"} · 上櫃 ${regimeLabels[contexts.TPEx?.market_regime] || "—"}`
    : regimeLabels[meta.market_regime] || "—");
  setText("#market-return", contexts.TWSE || contexts.TPEx
    ? `上市寬度 ${number(contexts.TWSE?.market_breadth_pct, 0)}% · 上櫃 ${number(contexts.TPEx?.market_breadth_pct, 0)}%`
    : `市場寬度 ${number(meta.market_breadth_pct, 0)}% · 門檻 ${meta.required_score ?? "—"} 分`);
  setText("#setup-count", state.data.setup?.length || 0);
  setText("#data-note", meta.download_errors
    ? `本次有 ${meta.download_errors} 筆下載錯誤，請查看 workflow 紀錄。`
    : "收盤後訊號，僅供研究。");
}

function marketLabel(value) {
  return ({ bull: "多頭", neutral: "震盪", bear: "偏空" })[value] || "—";
}

function visibleRows() {
  const rows = [...(state.data.setup || [])];
  const query = state.query.trim().toLowerCase();
  const filtered = query
    ? rows.filter((row) => `${row.stock_id} ${row.stock_name} ${row.industry || "未分類"}`.toLowerCase().includes(query))
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

function buildAiResearchPrompt(rows) {
  if (!rows.length) {
    return "目前畫面沒有股票，請先調整搜尋條件或切換到有候選股的交易日。";
  }

  const tradeDate = state.data.meta?.trade_date || "未提供";
  const candidates = rows.map((row, index) => [
    `${index + 1}. ${row.stock_id} ${row.stock_name}`,
    `（${row.market}／${row.industry || "未分類"}，掃描日收盤 ${number(row.close)} 元`,
    `，月營收 YoY ${signed(row.revenue_yoy)}，累計 YoY ${signed(row.revenue_ytd_yoy)}`,
    `，5 日 ${signed(row.return_5d)}，20 日 ${signed(row.return_20d)}`,
    `，掃描分數 ${row.score ?? "—"}）`,
  ].join("")).join("\n");

  return `你是一位以 Peter Lynch 成長合理價值（GARP）方法研究台股的分析助手。以下股票已先通過技術面、量能、營收與產業條件篩選，請再做基本面估值，不要把掃描分數直接當成買進依據。

資料基準日：${tradeDate}
候選股票：
${candidates}

請使用目前可取得的最新公開資訊，優先採用公司公告、公開資訊觀測站、法說會、財報與可信市場資料，逐檔完成以下研究：

1. 依 Peter Lynch 的觀點判斷公司較接近緩慢成長、穩健成長、快速成長、景氣循環、資產機會或轉機型；說明判斷依據。
2. 檢查近年與近四季 EPS、營收、獲利成長、毛利率／營益率、負債、現金流與股本變化。適用時估算 PEG＝本益比 ÷ 預期盈餘成長率；景氣循環股不要直接用高峰獲利外推。
3. 評估合理股價：清楚寫出估值方法、關鍵假設、基準合理價與合理價區間。可依公司特性使用合理本益比、PEG、正常化 EPS、股利或資產價值交叉驗證。資料不足時請標示「無法可靠估值」，不要硬算。
4. 以掃描日收盤價為比較基準，計算合理價相對現價的低估／高估幅度，並將所有候選股依「低估程度由高到低」排序。若估值可信度差異很大，請同時標示可信度。
5. 每檔列出未來 6～24 個月可能的新發展、成長催化劑與主要風險，並區分已公告事實與推測。
6. 每檔提出可驗證的「加碼、持有、賣出」條件，例如盈餘成長、估值、負債、產品進度、產業循環或基本面惡化條件；不要只用股價漲跌作為唯一理由。
7. 每項重要數字附來源與資料日期，確認資訊確實是目前可知的最新資料；若不同來源口徑不一致，請說明差異。

請先輸出一張排序表，至少包含：
排名｜股票｜掃描日收盤價｜合理價｜合理價區間｜低估／高估幅度｜PEG／主要估值依據｜估值可信度

接著逐檔回答：
「請用 Peter Lynch 的方法幫我研究台股『股票名稱』：
1. 根據目前可知的最新資訊評估，『合理股價』是多少？
2. 未來可能有什麼新發展？加碼、持有或賣出的條件是什麼？」

最後再列出：
- 最關鍵的估值假設
- 可能讓合理價失效的風險
- 哪些股票因資料不足而不應強行排序

請把事實、估值假設與推論清楚分開，金額一律使用新台幣。這是研究用途，不要把任何單一估值模型當成保證。`;
}

function updateAiPrompt(rows) {
  if (!els.aiPrompt) return;
  els.aiPrompt.value = buildAiResearchPrompt(rows);
  if (els.aiPromptStatus) {
    els.aiPromptStatus.textContent = rows.length
      ? `已帶入目前畫面 ${rows.length} 檔股票，會依畫面排序送入研究提示詞。`
      : "目前沒有可帶入的股票。";
  }
}

async function copyAiPrompt() {
  if (!els.aiPrompt) return;
  const prompt = els.aiPrompt.value;
  if (!prompt) return;

  try {
    await navigator.clipboard.writeText(prompt);
  } catch (_) {
    els.aiPrompt.focus();
    els.aiPrompt.select();
    document.execCommand("copy");
    els.aiPrompt.setSelectionRange(0, 0);
  }

  if (els.aiPromptStatus) {
    els.aiPromptStatus.textContent = "已複製提示詞，可貼到具備最新網路資訊能力的 AI 進行研究。";
  }
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
      <td><a class="stock-link" href="${stockInfoUrl(row)}" target="_blank" rel="noopener noreferrer"><span class="stock"><strong>${escapeHtml(row.stock_id)} ${escapeHtml(row.stock_name)}</strong><span>${escapeHtml(row.market)} · 查看股票資訊 ↗</span></span></a></td>
      <td class="industry">${escapeHtml(row.industry || "未分類")}</td>
      <td><span class="market-badge ${escapeHtml(row.market_regime || "")}">${marketLabel(row.market_regime)}</span></td>
      <td class="${tone(row.revenue_yoy)}"><span class="revenue"><strong>${signed(row.revenue_yoy)}</strong><span>${escapeHtml(row.revenue_month || "月份未提供")} · 累計 ${signed(row.revenue_ytd_yoy)}</span></span></td>
      <td class="score">${row.score}</td>
      <td>${number(row.close)}</td>
      <td class="${tone(row.pct_change)}">${signed(row.pct_change)}</td>
      <td class="${tone(row.return_5d)}">${signed(row.return_5d)}</td>
      <td class="${tone(row.return_20d)}">${signed(row.return_20d)}</td>
      <td>${number(row.volume_ratio)}×</td>
      <td>${number(row.k, 1)} / ${number(row.d, 1)}</td>
      <td class="${Number(row.ma20_deviation_pct) > 6 ? "warning" : ""}">${signed(row.ma20_deviation_pct)}</td>
      <td>${signed(row.distance_to_high20_pct)}</td>
      <td class="trade-plan"><strong>突破 ${number(row.entry_trigger)}</strong><span>上限 ${number(row.max_next_open)} · 取消 ${number(row.cancel_below)} · 停損 ${number(row.initial_stop_reference)}</span></td>
      <td>${(row.reasons || []).map((reason) => `<span class="tag">${escapeHtml(reason)}</span>`).join("")}</td>
    </tr>
  `).join("");
  els.empty.hidden = rows.length > 0;
  updateAiPrompt(rows);
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
  } catch (_) {
    // 績效追蹤不影響最新名單。
  }
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

els.copyAiPrompt?.addEventListener("click", copyAiPrompt);

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
loadPerformance();
