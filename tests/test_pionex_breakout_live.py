from __future__ import annotations

import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
import pionex_breakout_live as bot  # noqa: E402


class MarginTierTests(unittest.TestCase):
    def test_margin_tier_boundaries(self) -> None:
        cases = {
            "0": "0",
            "49.99": "0",
            "50": "50",
            "119.99": "50",
            "120": "100",
            "239.99": "100",
            "240": "200",
            "479.99": "200",
            "480": "400",
            "959.99": "400",
            "960": "800",
            "1919.99": "800",
            "1920": "1600",
            "3839.99": "1600",
            "3840": "3200",
            "7679.99": "3200",
            "7680": "6400",
            "10000": "6400",
            "50000": "6400",
        }
        for free_usdt, expected_margin in cases.items():
            with self.subTest(free_usdt=free_usdt):
                self.assertEqual(
                    bot.margin_for_free_balance(Decimal(free_usdt)),
                    Decimal(expected_margin),
                )

    def test_negative_free_balance_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            bot.margin_for_free_balance(Decimal("-0.01"))


class APIParsingAndScanningTests(unittest.TestCase):
    def test_parse_leverage_supports_documented_and_observed_shapes(self) -> None:
        self.assertEqual(
            bot.parse_account_leverage({"symbol": "BTC_USDT_PERP", "leverage": "5"}, "BTC_USDT_PERP"),
            Decimal("5"),
        )
        self.assertEqual(
            bot.parse_account_leverage(
                {"leverages": [{"symbol": "ETH_USDT_PERP", "leverage": "5"}]},
                "ETH_USDT_PERP",
            ),
            Decimal("5"),
        )

    def test_parse_leverage_rejects_wrong_symbol(self) -> None:
        with self.assertRaises(RuntimeError):
            bot.parse_account_leverage(
                {"leverages": [{"symbol": "BTC_USDT_PERP", "leverage": "5"}]},
                "ETH_USDT_PERP",
            )

    def test_scan_keeps_only_tradable_usdt_perps_and_ranks_by_amount(self) -> None:
        client = bot.PionexClient("", "")
        client.tradable_usdt_perp_symbols = lambda: {
            "BTC_USDT_PERP": {"symbol": "BTC_USDT_PERP"},
            "ETH_USDT_PERP": {"symbol": "ETH_USDT_PERP"},
        }
        client.public_get = lambda _path, _params=None: {
            "data": {
                "tickers": [
                    {"symbol": "DOGE_USDT_PERP", "amount": "999999"},
                    {"symbol": "ETH_USDT_PERP", "amount": "200"},
                    {"symbol": "BTC_USDT_PERP", "amount": "500"},
                    {"symbol": "BTC_USDT_PERP", "amount": "0"},
                ]
            }
        }

        ranked = client.top_tradable_usdt_perps(2)
        self.assertEqual([item[0] for item in ranked], ["BTC_USDT_PERP", "ETH_USDT_PERP"])
        self.assertEqual([item[2] for item in ranked], [Decimal("500"), Decimal("200")])


class SignalTests(unittest.TestCase):
    @staticmethod
    def candles(closes: list[float]) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "time": list(range(len(closes))),
                "open": closes,
                "high": closes,
                "low": closes,
                "close": closes,
                "volume": [1.0] * len(closes),
            }
        )

    def test_long_requires_upper_break_and_rsi_confirmation(self) -> None:
        closes = [100.0 + index for index in range(30)] + [170.0]
        result = bot.breakout_signal(self.candles(closes))
        self.assertEqual(result.signal, "LONG")
        self.assertGreaterEqual(result.rsi, bot.RSI_LONG_MIN)
        self.assertGreater(result.close, result.upper_band)

    def test_short_requires_lower_break_and_rsi_confirmation(self) -> None:
        closes = [200.0 - index for index in range(30)] + [120.0]
        result = bot.breakout_signal(self.candles(closes))
        self.assertEqual(result.signal, "SHORT")
        self.assertLessEqual(result.rsi, bot.RSI_SHORT_MAX)
        self.assertLess(result.close, result.lower_band)

    def test_neutral_series_holds(self) -> None:
        closes = [100.0 + (0.1 if index % 2 else -0.1) for index in range(40)]
        result = bot.breakout_signal(self.candles(closes))
        self.assertEqual(result.signal, "HOLD")


class FakeClient:
    def __init__(self) -> None:
        self.orders: list[dict] = []

    def place_market_order(self, **kwargs):
        self.orders.append(kwargs)
        request = {
            "clientOrderId": kwargs["client_order_id"],
            "symbol": kwargs["symbol"],
            "side": kwargs["side"],
            "size": bot.decimal_string(kwargs["size"]),
            "reduceOnly": kwargs["reduce_only"],
        }
        return {"data": {"orderId": "DRY-RUN"}, "request": request}


class ManualPositionClient(FakeClient):
    def __init__(self, position: dict) -> None:
        super().__init__()
        self.position = position

    def position_mode(self) -> str:
        return "BUYSELL"

    def positions(self, _symbol=None) -> list[dict]:
        return [self.position]


class RiskManagementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_state_path = bot.STATE_PATH
        self.original_event_log_path = bot.EVENT_LOG_PATH
        self.original_live_trading = bot.LIVE_TRADING
        bot.STATE_PATH = Path(self.temp_dir.name) / "state.json"
        bot.EVENT_LOG_PATH = Path(self.temp_dir.name) / "events.csv"
        bot.LIVE_TRADING = False
        self.client = FakeClient()

    def tearDown(self) -> None:
        bot.STATE_PATH = self.original_state_path
        bot.EVENT_LOG_PATH = self.original_event_log_path
        bot.LIVE_TRADING = self.original_live_trading
        self.temp_dir.cleanup()

    @staticmethod
    def position(unrealized_pnl: str) -> dict:
        return {
            "symbol": "BTC_USDT_PERP",
            "positionId": "position-1",
            "netSize": "1",
            "initialMargin": "100",
            "unrealizedPnL": unrealized_pnl,
            "positionSide": "BOTH",
            "avgPrice": "100000",
            "markPrice": "100000",
        }

    def test_first_protection_closes_after_10_then_5(self) -> None:
        state = bot.BotState()
        bot.monitor_position(self.client, state, self.position("10"))
        self.assertEqual(self.client.orders, [])
        bot.monitor_position(self.client, state, self.position("5"))
        self.assertEqual(len(self.client.orders), 1)
        self.assertTrue(self.client.orders[0]["reduce_only"])
        self.assertEqual(self.client.orders[0]["side"], "SELL")

    def test_second_lock_profit_closes_after_15_then_10(self) -> None:
        state = bot.BotState()
        bot.monitor_position(self.client, state, self.position("15"))
        self.assertEqual(self.client.orders, [])
        bot.monitor_position(self.client, state, self.position("10"))
        self.assertEqual(len(self.client.orders), 1)
        self.assertTrue(self.client.orders[0]["reduce_only"])

    def test_hard_stop_closes_at_minus_8(self) -> None:
        state = bot.BotState()
        bot.monitor_position(self.client, state, self.position("-8"))
        self.assertEqual(len(self.client.orders), 1)
        self.assertTrue(self.client.orders[0]["reduce_only"])

    def test_manual_position_is_not_automatically_closed(self) -> None:
        client = ManualPositionClient(self.position("-20"))
        state = bot.BotState()
        bot.run_once(client, state)
        self.assertEqual(client.orders, [])
        self.assertIn("UNMANAGED_POSITION", bot.EVENT_LOG_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
