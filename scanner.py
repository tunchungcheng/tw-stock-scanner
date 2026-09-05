from __future__ import annotations

import json
import math
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "docs" / "data"
ARCHIVE_DIR = DATA_DIR / "archive"

TWSE_URL = "https://www.twse.com.tw/exchangeReport/MI_INDEX"
TPEX_URL = "https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes"
TWSE_PROFILE_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
TPEX_PROFILE_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"

BACKFILL_CALENDAR_DAYS = 150
REQUEST_INTERVAL_SECONDS = 0.25
MIN_AVG_TURNOVER_20 = 30_000_000
SETUP_MIN_SCORE = 6
SETUP_LIMIT = 20

INDUSTRY_NAMES = {
    "01": "水泥工業",
    "02": "食品工業",
    "03": "塑膠工業",
    "04": "紡織纖維",
    "05": "電機機械",
    "06": "電器電纜",
    "08": "玻璃陶瓷",
    "09": "造紙工業",
    "10": "鋼鐵工業",
    "11": "橡膠工業",
    "12": "汽車工業",
    "14": "建材營造",
    "15": "航運業",
    "16": "觀光餐旅",
    "17": "金融保險",
    "18": "貿易百貨",
    "19": "綜合",
    "20": "其他",
    "21": "化學工業",
    "22": "生技醫療業",
    "23": "油電燃氣業",
    "24": "半導體業",
    "25": "電腦及週邊設備業",
    "26": "光電業",
    "27": "通信網路業",
    "28": "電子零組件業",
    "29": "電子通路業",
    "30": "資訊服務業",
    "31": "其他電子業",
    "32": "文化創意業",
    "33": "農業科技業",
    "34": "電子商務",
    "35": "綠能環保",
    "36": "數位雲端",
    "37": "運動休閒",
    "38": "居家生活",
}

ALIASES = {
    "stock_id": {"證券代號", "代號", "股票代號", "SecuritiesCompanyCode", "Code"},
    "stock_name": {"證券名稱", "名稱", "股票名稱", "CompanyName", "Name"},
    "open": {"開盤價", "開盤", "Open"},
    "high": {"最高價", "最高", "High"},
    "low": {"最低價", "最低", "Low"},
    "close": {"收盤價", "收盤", "Close"},
    "volume": {"成交股數", "成交量", "TradingShares", "TradeVolume"},
    "turnover": {"成交金額", "成交值", "TransactionAmount", "TradeValue"},
}


def clean_label(value: object) -> str:
    return re.sub(r"[\s　()（）/\-]+", "", str(value)).strip()


NORMALIZED_ALIASES = {
    key: {clean_label(value) for value in values} for key, values in ALIASES.items()
}


def clean_number(value: object) -> float:
    if value is None:
        return np.nan
    text = str(value).strip().replace(",", "").replace("＋", "").replace("+", "")
    text = text.replace("−", "-").replace("－", "-").replace("X", "")
    text = text.replace("除權", "").replace("除息", "")
    if text in {"", "--", "---", "----", "N/A", "nan"}:
        return np.nan
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group()) if match else np.nan


def get_json(url: str, params: dict[str, str], attempts: int = 3) -> object:
    query = urlencode(params)
    full_url = f"{url}?{query}" if query else url
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(
                full_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; tw-stock-scanner/1.0)",
                    "Accept": "application/json,text/plain,*/*",
                },
            )
            with urlopen(request, timeout=45) as response:
                return json.loads(response.read().decode("utf-8-sig"))
        except Exception as exc:  # 網路、HTTP 與 JSON 錯誤統一重試
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"下載失敗：{url}，{last_error}")


def normalize_industry_code(value: object) -> str:
    text = str(value or "").strip().replace("－", "").replace("-", "")
    return text.zfill(2) if text.isdigit() else text


def normalize_company_profiles(
    twse_payload: object | None, tpex_payload: object | None
) -> pd.DataFrame:
    specs = [
        ("TWSE", twse_payload, "公司代號", "產業別"),
        ("TPEx", tpex_payload, "SecuritiesCompanyCode", "SecuritiesIndustryCode"),
    ]
    records: list[dict[str, str]] = []
    for market, payload, stock_field, industry_field in specs:
        if not isinstance(payload, list):
            continue
        for row in payload:
            if not isinstance(row, dict):
                continue
            stock_id = str(row.get(stock_field, "")).strip()
            if not re.fullmatch(r"[1-9]\d{3}", stock_id):
                continue
            industry_code = normalize_industry_code(row.get(industry_field))
            industry = INDUSTRY_NAMES.get(industry_code)
            if not industry:
                industry = f"產業代碼 {industry_code}" if industry_code else "未分類"
            records.append(
                {
                    "market": market,
                    "stock_id": stock_id,
                    "industry_code": industry_code,
                    "industry": industry,
                }
            )
    columns = ["market", "stock_id", "industry_code", "industry"]
    return pd.DataFrame(records, columns=columns).drop_duplicates(
        ["market", "stock_id"], keep="last"
    )


def collect_company_profiles() -> tuple[pd.DataFrame, list[dict[str, str]]]:
    payloads: dict[str, object | None] = {"TWSE": None, "TPEx": None}
    errors: list[dict[str, str]] = []
    for market, url in (("TWSE", TWSE_PROFILE_URL), ("TPEx", TPEX_PROFILE_URL)):
        try:
            payloads[market] = get_json(url, {})
        except Exception as exc:
            errors.append({"date": "company-profile", "market": market, "error": str(exc)})
    return normalize_company_profiles(payloads["TWSE"], payloads["TPEx"]), errors


def iter_tables(obj: object):
    if isinstance(obj, dict):
        field_key = next(
            (key for key in ("fields", "columns", "titles") if isinstance(obj.get(key), list)),
            None,
        )
        data_key = next(
            (key for key in ("data", "aaData", "rows") if isinstance(obj.get(key), list)),
            None,
        )
        if field_key and data_key:
            yield obj[field_key], obj[data_key]
        for value in obj.values():
            yield from iter_tables(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from iter_tables(value)


def map_fields(fields: list[object]) -> dict[str, int]:
    labels = [clean_label(value) for value in fields]
    mapped: dict[str, int] = {}
    for canonical, aliases in NORMALIZED_ALIASES.items():
        for index, label in enumerate(labels):
            if label in aliases:
                mapped[canonical] = index
                break
    return mapped


def table_to_frame(payload: object, market: str, requested_date: date) -> pd.DataFrame:
    required = {"stock_id", "stock_name", "open", "high", "low", "close", "volume"}
    selected = None
    for fields, rows in iter_tables(payload):
        mapping = map_fields(fields)
        if required.issubset(mapping) and rows:
            selected = mapping, rows
            break

    if selected is None and isinstance(payload, list) and payload and isinstance(payload[0], dict):
        fields = list(payload[0].keys())
        mapping = map_fields(fields)
        if required.issubset(mapping):
            selected = mapping, [[row.get(field) for field in fields] for row in payload]

    if selected is None:
        summary = json.dumps(payload, ensure_ascii=False)[:300]
        if any(word in summary for word in ("沒有符合條件", "查無資料", "很抱歉", "No data")):
            return pd.DataFrame()
        raise ValueError(f"{market} 找不到行情欄位；官方格式可能已變更：{summary}")

    mapping, rows = selected
    records = []
    for row in rows:
        if not isinstance(row, (list, tuple)):
            continue
        stock_id = str(row[mapping["stock_id"]]).strip()
        if not re.fullmatch(r"[1-9]\d{3}", stock_id):
            continue
        records.append(
            {
                "market": market,
                "stock_id": stock_id,
                "stock_name": str(row[mapping["stock_name"]]).strip(),
                "trade_date": pd.Timestamp(requested_date),
                "open": clean_number(row[mapping["open"]]),
                "high": clean_number(row[mapping["high"]]),
                "low": clean_number(row[mapping["low"]]),
                "close": clean_number(row[mapping["close"]]),
                "volume": clean_number(row[mapping["volume"]]),
                "turnover": clean_number(row[mapping["turnover"]])
                if "turnover" in mapping
                else np.nan,
            }
        )

    frame = pd.DataFrame(records)
    if frame.empty:
        return frame
    numeric = ["open", "high", "low", "close", "volume", "turnover"]
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="coerce")
    frame = frame.dropna(subset=["open", "high", "low", "close"])
    frame = frame[(frame["close"] > 0) & (frame["high"] >= frame["low"])]
    return frame.drop_duplicates(["market", "stock_id", "trade_date"])


def extract_twse_index(payload: object, requested_date: date) -> pd.DataFrame:
    for fields, rows in iter_tables(payload):
        labels = [clean_label(value) for value in fields]
        name_index = next((i for i, label in enumerate(labels) if label in {"指數", "指數名稱"}), None)
        close_index = next((i for i, label in enumerate(labels) if label in {"收盤指數", "收盤"}), None)
        if name_index is None or close_index is None:
            continue
        for row in rows:
            if not isinstance(row, (list, tuple)):
                continue
            if "發行量加權股價指數" in str(row[name_index]):
                close = clean_number(row[close_index])
                if pd.notna(close):
                    return pd.DataFrame(
                        [{"trade_date": pd.Timestamp(requested_date), "close": close}]
                    )
    return pd.DataFrame(columns=["trade_date", "close"])


def fetch_twse(day: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    payload = get_json(
        TWSE_URL,
        {"response": "json", "date": day.strftime("%Y%m%d"), "type": "ALLBUT0999"},
    )
    return table_to_frame(payload, "TWSE", day), extract_twse_index(payload, day)


def fetch_tpex(day: date) -> pd.DataFrame:
    payload = get_json(
        TPEX_URL,
        {"date": day.strftime("%Y/%m/%d"), "id": "", "response": "json"},
    )
    return table_to_frame(payload, "TPEx", day)


def collect_history(today: date) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, str]]]:
    start = today - timedelta(days=BACKFILL_CALENDAR_DAYS)
    price_frames: list[pd.DataFrame] = []
    index_frames: list[pd.DataFrame] = []
    errors: list[dict[str, str]] = []

    weekdays = [day.date() for day in pd.date_range(start, today, freq="D") if day.weekday() < 5]
    for position, day in enumerate(weekdays, 1):
        try:
            prices, index_frame = fetch_twse(day)
            if not prices.empty:
                price_frames.append(prices)
            if not index_frame.empty:
                index_frames.append(index_frame)
        except Exception as exc:
            errors.append({"date": day.isoformat(), "market": "TWSE", "error": str(exc)})
        time.sleep(REQUEST_INTERVAL_SECONDS)

        try:
            prices = fetch_tpex(day)
            if not prices.empty:
                price_frames.append(prices)
        except Exception as exc:
            errors.append({"date": day.isoformat(), "market": "TPEx", "error": str(exc)})
        time.sleep(REQUEST_INTERVAL_SECONDS)

        if position % 20 == 0 or position == len(weekdays):
            print(f"下載進度 {position}/{len(weekdays)}")

    if not price_frames:
        raise RuntimeError("沒有取得任何股價資料")
    prices = pd.concat(price_frames, ignore_index=True).drop_duplicates(
        ["market", "stock_id", "trade_date"], keep="last"
    )
    index_data = (
        pd.concat(index_frames, ignore_index=True).drop_duplicates("trade_date", keep="last")
        if index_frames
        else pd.DataFrame(columns=["trade_date", "close"])
    )
    return prices, index_data, errors


def kd_values(rsv_series: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    k_values, d_values = [], []
    k_previous = d_previous = 50.0
    for rsv in rsv_series:
        value = 50.0 if pd.isna(rsv) else float(rsv)
        k_now = (2 * k_previous + value) / 3
        d_now = (2 * d_previous + k_now) / 3
        k_values.append(k_now)
        d_values.append(d_now)
        k_previous, d_previous = k_now, d_now
    return np.asarray(k_values), np.asarray(d_values)


def calculate_indicators(price_df: pd.DataFrame) -> pd.DataFrame:
    df = price_df.sort_values(["market", "stock_id", "trade_date"]).copy()
    keys = ["market", "stock_id"]
    grouped = df.groupby(keys, group_keys=False)

    df["low9"] = grouped["low"].transform(lambda s: s.rolling(9, min_periods=9).min())
    df["high9"] = grouped["high"].transform(lambda s: s.rolling(9, min_periods=9).max())
    span = (df["high9"] - df["low9"]).replace(0, np.nan)
    df["RSV"] = ((df["close"] - df["low9"]) / span * 100).clip(0, 100)
    df["K"] = np.nan
    df["D"] = np.nan
    for _, indices in df.groupby(keys, sort=False).groups.items():
        k_series, d_series = kd_values(df.loc[indices, "RSV"])
        df.loc[indices, "K"] = k_series
        df.loc[indices, "D"] = d_series

    grouped = df.groupby(keys, group_keys=False)
    df["K_prev"] = grouped["K"].shift(1)
    df["K_prev2"] = grouped["K"].shift(2)
    df["D_prev"] = grouped["D"].shift(1)
    previous_close = grouped["close"].shift(1)
    df["TR"] = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - previous_close).abs(),
            (df["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    grouped = df.groupby(keys, group_keys=False)
    df["ATR14"] = grouped["TR"].transform(lambda s: s.rolling(14, min_periods=14).mean())
    df["MA5"] = grouped["close"].transform(lambda s: s.rolling(5, min_periods=5).mean())
    df["MA20"] = grouped["close"].transform(lambda s: s.rolling(20, min_periods=20).mean())
    df["STD20"] = grouped["close"].transform(lambda s: s.rolling(20, min_periods=20).std())
    df["BB_WIDTH"] = 4 * df["STD20"] / df["MA20"].replace(0, np.nan)
    df["ATR_PCT"] = df["ATR14"] / df["close"].replace(0, np.nan)

    grouped = df.groupby(keys, group_keys=False)
    df["ATR_Q30_60"] = grouped["ATR_PCT"].transform(
        lambda s: s.rolling(60, min_periods=40).quantile(0.30)
    )
    df["BBW_Q30_60"] = grouped["BB_WIDTH"].transform(
        lambda s: s.rolling(60, min_periods=40).quantile(0.30)
    )
    df["VOL5"] = grouped["volume"].transform(lambda s: s.rolling(5, min_periods=5).mean())
    df["VOL20"] = grouped["volume"].transform(lambda s: s.rolling(20, min_periods=20).mean())
    df["TURNOVER20"] = grouped["turnover"].transform(
        lambda s: s.rolling(20, min_periods=20).mean()
    )
    df["HIGH20_PREV"] = grouped["high"].transform(
        lambda s: s.shift(1).rolling(20, min_periods=20).max()
    )
    df["HIGH10_PREV"] = grouped["high"].transform(
        lambda s: s.shift(1).rolling(10, min_periods=10).max()
    )
    df["pct_change"] = grouped["close"].pct_change(fill_method=None) * 100
    df["return_5d"] = grouped["close"].pct_change(5, fill_method=None) * 100
    df["return_20d"] = grouped["close"].pct_change(20, fill_method=None) * 100
    df["return_60d"] = grouped["close"].pct_change(60, fill_method=None) * 100
    df["volume_ratio"] = df["volume"] / df["VOL20"].replace(0, np.nan)
    df["volume_dry_ratio"] = df["VOL5"] / df["VOL20"].replace(0, np.nan)
    df["distance_to_high20_pct"] = (
        (df["HIGH20_PREV"] - df["close"]) / df["HIGH20_PREV"] * 100
    )
    df["golden_cross"] = (df["K_prev"] <= df["D_prev"]) & (df["K"] > df["D"])
    df["breakout_20d"] = df["close"] >= df["HIGH20_PREV"]
    df["volatility_compression"] = (df["ATR_PCT"] <= df["ATR_Q30_60"]) | (
        df["BB_WIDTH"] <= df["BBW_Q30_60"]
    )
    grouped = df.groupby(keys, group_keys=False)
    previous_compression = grouped["volatility_compression"].shift(1)
    df["volatility_release"] = previous_compression.eq(True) & (
        df["BB_WIDTH"] > df["BBW_Q30_60"]
    )
    df["liquid"] = df["TURNOVER20"] >= MIN_AVG_TURNOVER_20
    return df


def shared_latest_date(prices: pd.DataFrame) -> pd.Timestamp:
    latest_by_market = prices.groupby("market")["trade_date"].max()
    missing = {"TWSE", "TPEx"} - set(latest_by_market.index)
    if missing:
        raise RuntimeError(f"缺少市場資料：{', '.join(sorted(missing))}")
    return pd.Timestamp(latest_by_market.min())


def add_market_context(
    latest: pd.DataFrame, benchmark: pd.DataFrame, latest_date: pd.Timestamp
) -> tuple[pd.DataFrame, dict[str, object]]:
    benchmark = benchmark[benchmark["trade_date"] <= latest_date].sort_values("trade_date").copy()
    if len(benchmark) >= 60:
        benchmark["return_5d"] = benchmark["close"].pct_change(5, fill_method=None) * 100
        benchmark["return_20d"] = benchmark["close"].pct_change(20, fill_method=None) * 100
        benchmark["MA60"] = benchmark["close"].rolling(60, min_periods=60).mean()
        last = benchmark.iloc[-1]
        market_return_5d = float(last["return_5d"])
        market_return_20d = float(last["return_20d"])
        market_above_ma60 = bool(last["close"] > last["MA60"])
        source = "TAIEX"
    else:
        market_return_5d = float(latest["return_5d"].median())
        market_return_20d = float(latest["return_20d"].median())
        market_above_ma60 = bool(latest["return_60d"].median() > 0)
        source = "全市場中位數"

    latest = latest.copy()
    latest["relative_return_5d"] = latest["return_5d"] - market_return_5d
    latest["relative_return_20d"] = latest["return_20d"] - market_return_20d
    latest["market_above_ma60"] = market_above_ma60
    context = {
        "benchmark_source": source,
        "market_return_5d": market_return_5d,
        "market_return_20d": market_return_20d,
        "market_above_ma60": market_above_ma60,
    }
    return latest, context


def score_setup(latest: pd.DataFrame) -> pd.DataFrame:
    latest = latest.copy()
    latest["trend_turn"] = (latest["close"] > latest["MA5"]) & (latest["MA5"] > latest["MA20"])
    latest["kd_acceleration"] = (
        (latest["K"] > latest["K_prev"])
        & (latest["K_prev"] > latest["K_prev2"])
        & (latest["K"] > latest["D"])
    )
    latest["return_5d_momentum"] = latest["return_5d"].between(1, 8)
    latest["relative_strength_5d"] = latest["relative_return_5d"] > 0
    latest["volume_momentum"] = latest["volume_ratio"].between(1.0, 2.5)
    latest["early_breakout"] = (
        (latest["close"] >= latest["HIGH10_PREV"])
        & (latest["close"] < latest["HIGH20_PREV"])
    )
    latest["near_breakout_zone"] = latest["distance_to_high20_pct"].between(0, 5)
    latest["excluded_as_extended"] = (
        (latest["return_5d"] > 10)
        | (latest["return_20d"] > 20)
        | (latest["close"] > latest["MA20"] * 1.12)
        | (latest["volume_ratio"] > 4)
    )
    latest["setup_score"] = (
        latest["trend_turn"].astype(int) * 2
        + latest["kd_acceleration"].astype(int) * 2
        + latest["return_5d_momentum"].astype(int) * 2
        + latest["relative_strength_5d"].astype(int) * 2
        + latest["volume_momentum"].astype(int) * 2
        + latest["early_breakout"].astype(int) * 2
        + latest["volatility_release"].astype(int)
        + latest["near_breakout_zone"].astype(int)
    )

    valid = (
        latest["liquid"]
        & latest["return_20d"].notna()
        & latest["volume_ratio"].notna()
        & latest["MA20"].notna()
    )
    setup_mask = (
        valid
        & ~latest["breakout_20d"]
        & ~latest["excluded_as_extended"]
        & (latest["setup_score"] >= SETUP_MIN_SCORE)
    )

    setup = latest.loc[setup_mask].sort_values(
        ["setup_score", "relative_return_5d", "distance_to_high20_pct"],
        ascending=[False, False, True],
    )
    return setup


def reason_labels(row: pd.Series) -> list[str]:
    mapping = [
        ("trend_turn", "收盤 > MA5 > MA20"),
        ("kd_acceleration", "KD 動能加速"),
        ("return_5d_momentum", "5 日漲幅 1%～8%"),
        ("relative_strength_5d", "5 日相對強勢"),
        ("volume_momentum", "量比 1.0～2.5"),
        ("early_breakout", "突破 10 日高點"),
        ("volatility_release", "前日收斂、今日帶寬回升"),
        ("near_breakout_zone", "距 20 日高點不超過 5%"),
    ]
    return [label for field, label in mapping if bool(row.get(field, False))]


def finite(value: object, digits: int = 2) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, digits) if math.isfinite(number) else None


def records_for_web(frame: pd.DataFrame, limit: int) -> list[dict[str, object]]:
    records = []
    for rank, (_, row) in enumerate(frame.head(limit).iterrows(), 1):
        records.append(
            {
                "rank": rank,
                "market": row["market"],
                "stock_id": row["stock_id"],
                "stock_name": row["stock_name"],
                "industry": row.get("industry", "未分類"),
                "close": finite(row["close"]),
                "pct_change": finite(row["pct_change"]),
                "score": int(row["setup_score"]),
                "k": finite(row["K"], 1),
                "d": finite(row["D"], 1),
                "volume_ratio": finite(row["volume_ratio"]),
                "volume_dry_ratio": finite(row["volume_dry_ratio"]),
                "return_5d": finite(row["return_5d"]),
                "return_20d": finite(row["return_20d"]),
                "relative_return_5d": finite(row["relative_return_5d"]),
                "distance_to_high20_pct": finite(row["distance_to_high20_pct"]),
                "reasons": reason_labels(row),
            }
        )
    return records


def write_results(
    trade_date: pd.Timestamp,
    setup: pd.DataFrame,
    context: dict[str, object],
    universe_count: int,
    errors: list[dict[str, str]],
) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    date_text = trade_date.strftime("%Y-%m-%d")
    payload = {
        "status": "ready",
        "meta": {
            "trade_date": date_text,
            "generated_at": datetime.now(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds"),
            "benchmark_source": context["benchmark_source"],
            "market_return_5d": finite(context["market_return_5d"]),
            "market_return_20d": finite(context["market_return_20d"]),
            "market_above_ma60": bool(context["market_above_ma60"]),
            "universe_count": universe_count,
            "download_errors": len(errors),
        },
        "setup": records_for_web(setup, SETUP_LIMIT),
    }
    encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    (DATA_DIR / "latest.json").write_text(encoded, encoding="utf-8")
    (ARCHIVE_DIR / f"{date_text}.json").write_text(encoded, encoding="utf-8")

    setup.to_csv(DATA_DIR / "setup_latest.csv", index=False, encoding="utf-8-sig")
    (DATA_DIR / "trigger_latest.csv").unlink(missing_ok=True)
    archive_dates = sorted((path.stem for path in ARCHIVE_DIR.glob("*.json")), reverse=True)
    (DATA_DIR / "index.json").write_text(
        json.dumps({"dates": archive_dates}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if errors:
        (DATA_DIR / "download_errors.json").write_text(
            json.dumps(errors, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def main() -> None:
    today = datetime.now(ZoneInfo("Asia/Taipei")).date()
    prices, benchmark, errors = collect_history(today)
    profiles, profile_errors = collect_company_profiles()
    errors.extend(profile_errors)
    sessions = prices.groupby("market")["trade_date"].nunique()
    if any(sessions.get(market, 0) < 70 for market in ("TWSE", "TPEx")):
        raise RuntimeError(f"有效歷史交易日不足，停止發布：{sessions.to_dict()}")
    latest_date = shared_latest_date(prices)
    prices = prices[prices["trade_date"] <= latest_date]
    indicators = calculate_indicators(prices)
    latest = indicators[indicators["trade_date"] == latest_date].copy()
    latest = latest.merge(profiles, on=["market", "stock_id"], how="left")
    latest["industry"] = latest["industry"].fillna("未分類")
    latest["industry_code"] = latest["industry_code"].fillna("")
    latest, context = add_market_context(latest, benchmark, latest_date)
    setup = score_setup(latest)
    write_results(latest_date, setup, context, len(latest), errors)
    print(
        f"完成 {latest_date.date()}：蓄勢 {min(len(setup), SETUP_LIMIT)} 檔，"
        f"下載錯誤 {len(errors)} 筆"
    )


if __name__ == "__main__":
    main()
