from datetime import date
import json

import numpy as np
import pandas as pd

import scanner


def test_twse_parser_and_index():
    payload = {
        "tables": [
            {
                "fields": ["指數", "收盤指數"],
                "data": [["發行量加權股價指數", "22,345.67"]],
            },
            {
                "fields": [
                    "證券代號", "證券名稱", "成交股數", "成交金額",
                    "開盤價", "最高價", "最低價", "收盤價",
                ],
                "data": [
                    ["2330", "台積電", "1,000", "100,000", "100", "105", "99", "104"],
                    ["0050", "ETF", "1,000", "100,000", "1", "1", "1", "1"],
                ],
            },
        ]
    }
    frame = scanner.table_to_frame(payload, "TWSE", date(2026, 9, 1))
    index = scanner.extract_twse_index(payload, date(2026, 9, 1))
    assert frame["stock_id"].tolist() == ["2330"]
    assert index.iloc[0]["close"] == 22345.67


def test_company_profile_normalization():
    twse_payload = [
        {"公司代號": "2330", "公司名稱": "台積電", "產業別": "24"},
        {"公司代號": "0050", "公司名稱": "元大台灣50", "產業別": ""},
    ]
    tpex_payload = [
        {
            "SecuritiesCompanyCode": "6488",
            "CompanyName": "環球晶",
            "SecuritiesIndustryCode": "24",
        },
        {
            "SecuritiesCompanyCode": "9999",
            "CompanyName": "測試公司",
            "SecuritiesIndustryCode": "99",
        },
    ]
    profiles = scanner.normalize_company_profiles(twse_payload, tpex_payload)
    assert profiles.set_index("stock_id").loc["2330", "industry"] == "半導體業"
    assert profiles.set_index("stock_id").loc["6488", "market"] == "TPEx"
    assert profiles.set_index("stock_id").loc["9999", "industry"] == "產業代碼 99"
    assert "0050" not in profiles["stock_id"].tolist()


def test_monthly_revenue_normalization():
    payload = [
        {
            "資料年月": "11507",
            "公司代號": "2330",
            "營業收入-去年同月增減(%)": "32.5",
            "累計營業收入-前期比較增減(%)": "18.2",
        },
        {
            "資料年月": "11507",
            "公司代號": "0050",
            "營業收入-去年同月增減(%)": "99",
            "累計營業收入-前期比較增減(%)": "99",
        },
    ]
    revenue = scanner.normalize_monthly_revenue(payload, [])
    row = revenue.iloc[0]
    assert row["stock_id"] == "2330"
    assert row["revenue_month"] == "2026-07"
    assert row["revenue_available_date"] == pd.Timestamp("2026-08-11")
    assert row["revenue_yoy"] == 32.5
    assert "0050" not in revenue["stock_id"].tolist()


def synthetic_prices() -> pd.DataFrame:
    rows = []
    dates = pd.bdate_range("2026-01-01", periods=100)
    specs = [
        ("2330", "TWSE", 100, 0.08),
        ("6488", "TPEx", 200, 0.03),
        ("1101", "TWSE", 40, -0.01),
        ("3008", "TWSE", 800, 0.20),
    ]
    for stock_id, market, base, slope in specs:
        for index, day in enumerate(dates):
            close = base + index * slope + np.sin(index / 5) * 1.5
            if index == 99 and stock_id == "2330":
                close += 1.5
            rows.append(
                {
                    "market": market,
                    "stock_id": stock_id,
                    "stock_name": stock_id,
                    "trade_date": day,
                    "open": close - 0.5,
                    "high": close + 1,
                    "low": close - 1,
                    "close": close,
                    "volume": 1_000_000 * (1.5 if index == 99 and stock_id == "2330" else 0.8),
                    "turnover": 100_000_000,
                }
            )
    return pd.DataFrame(rows)


def test_setup_pipeline():
    prices = synthetic_prices()
    latest_date = scanner.shared_latest_date(prices)
    indicators = scanner.calculate_indicators(prices)
    latest = indicators[indicators["trade_date"] == latest_date]
    benchmark = pd.DataFrame(
        {
            "trade_date": pd.bdate_range("2026-01-01", periods=100),
            "close": 22000 + np.arange(100) * 8,
        }
    )
    latest, context = scanner.add_market_context(latest, benchmark, latest_date)
    latest["revenue_yoy"] = 40.0
    latest["revenue_ytd_yoy"] = 20.0
    latest["revenue_available_date"] = pd.Timestamp("2026-02-11")
    latest["industry"] = ["半導體業", "半導體業", "水泥工業", "光電業"]
    latest = scanner.add_industry_context(latest)
    setup = scanner.score_setup(latest)
    assert context["benchmark_source"] == "TWSE/TPEx 分流"
    assert set(context["market_contexts"]) == {"TWSE", "TPEx"}
    assert context["market_regime"] in {"bull", "neutral", "bear"}
    assert 0 <= context["market_breadth_pct"] <= 100
    assert "setup_score" in setup.columns
    assert setup["revenue_yoy"].ge(scanner.MIN_REVENUE_YOY).all()
    assert setup["revenue_ytd_yoy"].ge(scanner.MIN_REVENUE_YTD_YOY).all()
    assert setup["setup_score"].le(9).all()


def test_industry_cap():
    frame = pd.DataFrame(
        {
            "industry": ["半導體業"] * 5 + ["航運業"] * 2,
            "setup_score": [8, 7, 6, 5, 4, 3, 2],
        }
    )
    selected = scanner.diversified_top(frame, 5)
    assert len(selected) == 5
    assert selected["industry"].value_counts().max() == 3


def test_forward_signal_tracking(tmp_path, monkeypatch):
    archive_dir = tmp_path / "archive"
    data_dir = tmp_path / "data"
    archive_dir.mkdir()
    data_dir.mkdir()
    payload = {
        "meta": {"trade_date": "2026-09-01"},
        "setup": [{
            "market": "TWSE", "stock_id": "2330", "stock_name": "台積電",
            "industry": "半導體業", "score": 8, "close": 100,
            "entry_trigger": 102, "max_next_open": 103,
            "cancel_below": 97, "initial_stop_reference": 96,
            "reasons": ["產業相對強勢"],
        }],
    }
    (archive_dir / "2026-09-01.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    prices = pd.DataFrame([
        {"market": "TWSE", "stock_id": "2330", "trade_date": pd.Timestamp("2026-09-02"),
         "open": 101, "high": 103, "low": 99, "close": 104},
        {"market": "TWSE", "stock_id": "2330", "trade_date": pd.Timestamp("2026-09-03"),
         "open": 104, "high": 106, "low": 103, "close": 105},
    ])
    monkeypatch.setattr(scanner, "ARCHIVE_DIR", archive_dir)
    monkeypatch.setattr(scanner, "DATA_DIR", data_dir)
    result = scanner.track_archived_signals(prices)
    signal = result["signals"][0]
    assert signal["status"] == "entered"
    assert signal["entry_price"] == 102
    assert signal["return_1d"] == 1.26
    assert (data_dir / "performance.json").exists()
