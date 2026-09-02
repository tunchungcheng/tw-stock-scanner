from datetime import date

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


def test_dual_list_pipeline():
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
    setup, trigger = scanner.score_lists(latest)
    assert context["benchmark_source"] == "TAIEX"
    assert "setup_score" in setup.columns
    assert "trigger_score" in trigger.columns

