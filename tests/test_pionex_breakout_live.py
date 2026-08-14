from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from unittest.mock import patch
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

    def test_leverage_auth_unavailable_blocks_entry_with_actionable_context(self) -> None:
        class PermissionDeniedClient:
            @staticmethod
            def leverage(_symbol: str) -> Decimal:
                raise bot.PionexAPIError("派網 API 失敗（HTTP 200）：AUTH_UNAVAILABLE have no right")

        with patch.object(bot, "log_event") as log_event:
            allowed = bot.symbol_leverage_matches(PermissionDeniedClient(), "BTC_USDT_PERP")

        self.assertFalse(allowed)
        log_event.assert_called_once()
        args, context = log_event.call_args
        self.assertEqual(args[0], "ENTRY_BLOCKED")
        self.assertIn("AUTH_UNAVAILABLE", args[1])
        self.assertEqual(args[2], "BTC_USDT_PERP")
        self.assertEqual(context["endpoint"], "GET /uapi/v1/account/leverage")
        self.assertEqual(context["required_permission"], "Enable reading")
        self.assertEqual(context["required_for_order"], "Enable trading")

    def test_leverage_trade_type_denied_blocks_entry_with_whitelist_context(self) -> None:
        class TradeTypeDeniedClient:
            @staticmethod
            def leverage(_symbol: str) -> Decimal:
                raise bot.PionexAPIError(
                    "派網 API 失敗（HTTP 200）：TRADE_TYPE_DENIED user denied not in whitelist"
                )

        with patch.object(bot, "log_event") as log_event:
            allowed = bot.symbol_leverage_matches(TradeTypeDeniedClient(), "BTC_USDT_PERP")

        self.assertFalse(allowed)
        log_event.assert_called_once()
        args, context = log_event.call_args
        self.assertEqual(args[0], "ENTRY_BLOCKED")
        self.assertIn("TRADE_TYPE_DENIED", args[1])
        self.assertEqual(args[2], "BTC_USDT_PERP")
        self.assertEqual(context["endpoint"], "GET /uapi/v1/account/leverage")
        self.assertEqual(context["exchange_code"], "TRADE_TYPE_DENIED")
        self.assertEqual(context["blocked_product"], "USDT 永續合約（Futures／Perpetual）")

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

    def test_scan_keeps_tradable_symbol_without_bulk_book_ticker_quote(self) -> None:
        client = bot.PionexClient("", "")
        client.tradable_usdt_perp_symbols = lambda: {
            "BTC_USDT_PERP": {"symbol": "BTC_USDT_PERP"},
            "APR_USDT_PERP": {"symbol": "APR_USDT_PERP"},
        }
        client.public_get = lambda _path, _params=None: {
            "data": {
                "tickers": [
                    {"symbol": "APR_USDT_PERP", "amount": "1000"},
                    {"symbol": "BTC_USDT_PERP", "amount": "100"},
                ]
            }
        }

        ranked = client.top_tradable_usdt_perps(2)

        self.assertEqual([item[0] for item in ranked], ["APR_USDT_PERP", "BTC_USDT_PERP"])

    def test_book_ticker_uses_depth_endpoint(self) -> None:
        client = bot.PionexClient("", "")
        calls: list[tuple[str, dict[str, str] | None]] = []

        def public_get(path: str, params: dict[str, str] | None = None) -> dict:
            calls.append((path, params))
            return {
                "data": {
                    "bids": [["499", "2"]],
                    "asks": [["500", "3"]],
                }
            }

        client.public_get = public_get

        quote = client.book_ticker("BTC_USDT_PERP")

        self.assertEqual(quote["askPrice"], "500")
        self.assertEqual(quote["bidPrice"], "499")
        self.assertEqual(calls, [("/api/v1/market/depth", {"symbol": "BTC_USDT_PERP"})])

    def test_symbol_filter_accepts_observed_type_perp_shape(self) -> None:
        client = bot.PionexClient("", "")
        client.public_get = lambda _path, _params=None: {
            "data": {
                "symbols": [
                    {
                        "symbol": "BTC_USDT_PERP",
                        "status": "TRADING",
                        "quoteCurrency": "USDT",
                        "type": "PERP",
                    },
                    {
                        "symbol": "ETH_USDT_PERP",
                        "status": "TRADING",
                        "quoteCurrency": "USDT",
                        "contractType": "PERPETUAL",
                    },
                    {
                        "symbol": "BTC_USDC_PERP",
                        "status": "TRADING",
                        "quoteCurrency": "USDC",
                        "type": "PERP",
                    },
                    {
                        "symbol": "BTC_USDT_PERP",
                        "status": "PAUSED",
                        "quoteCurrency": "USDT",
                        "type": "PERP",
                    },
                ]
            }
        }
        allowed = client.tradable_usdt_perp_symbols()
        self.assertEqual(set(allowed), {"BTC_USDT_PERP", "ETH_USDT_PERP"})

    def test_entry_size_accepts_observed_type_perp_shape(self) -> None:
        client = bot.PionexClient("", "")
        client.symbol_info = lambda _symbol: {
            "symbol": "BTC_USDT_PERP",
            "status": "TRADING",
            "quoteCurrency": "USDT",
            "type": "PERP",
            "baseStep": "0.001",
            "minSizeMarket": "0.001",
            "maxSizeMarket": "1000",
            "minNotional": "1",
        }
        client.book_ticker = lambda _symbol: {"askPrice": "500", "bidPrice": "499"}

        qty, reference_price, actual_notional = bot.calculate_entry_size(
            client,
            "BTC_USDT_PERP",
            "LONG",
            Decimal("50"),
            Decimal("50"),
        )

        self.assertEqual(qty, Decimal("0.5"))
        self.assertEqual(reference_price, Decimal("500"))
        self.assertEqual(actual_notional, Decimal("250"))


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

    def test_high_daily_counter_does_not_block_new_entry(self) -> None:
        state = bot.BotState(trades_today=999)
        with (
            patch.object(bot, "symbol_leverage_matches", return_value=True),
            patch.object(bot, "get_free_usdt", return_value=Decimal("50")),
            patch.object(
                bot,
                "calculate_entry_size",
                return_value=(Decimal("1"), Decimal("100"), Decimal("100")),
            ),
        ):
            opened = bot.open_position(
                self.client,
                state,
                "BTC_USDT_PERP",
                1234567890,
                "LONG",
            )

        self.assertTrue(opened)
        self.assertEqual(len(self.client.orders), 1)
        self.assertEqual(state.trades_today, 999)


class TelegramNotificationTests(unittest.TestCase):
    def test_disabled_telegram_never_makes_network_request(self) -> None:
        with patch.object(bot, "TELEGRAM_ENABLED", False), patch.object(bot.requests, "post") as post:
            self.assertFalse(bot.send_telegram("不應送出的測試"))
            post.assert_not_called()

    def test_enabled_telegram_posts_to_expected_endpoint(self) -> None:
        class FakeResponse:
            status_code = 200

            @staticmethod
            def json() -> dict[str, bool]:
                return {"ok": True}

        with (
            patch.object(bot, "TELEGRAM_ENABLED", True),
            patch.object(bot, "TELEGRAM_BOT_TOKEN", "test-token"),
            patch.object(bot, "TELEGRAM_CHAT_ID", "12345"),
            patch.object(bot.requests, "post", return_value=FakeResponse()) as post,
        ):
            self.assertTrue(bot.send_telegram("測試訊息"))
            post.assert_called_once_with(
                "https://api.telegram.org/bottest-token/sendMessage",
                json={"chat_id": "12345", "text": "測試訊息"},
                timeout=8,
            )


class MonitorTelemetryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_event_log_path = bot.EVENT_LOG_PATH
        bot.EVENT_LOG_PATH = Path(self.temp_dir.name) / "events.csv"

    def tearDown(self) -> None:
        bot.EVENT_LOG_PATH = self.original_event_log_path
        self.temp_dir.cleanup()

    def test_csv_events_are_reduced_to_the_monitoring_whitelist(self) -> None:
        with bot.EVENT_LOG_PATH.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=["time_taipei", "event", "symbol", "detail", "live_trading", "context_json"],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "time_taipei": "2026-08-14 16:00:40",
                    "event": "ENTRY_BLOCKED",
                    "symbol": "BNB_USDT_PERP",
                    "detail": "槓桿不一致",
                    "live_trading": "true",
                    "context_json": '{"apiSecret":"must-not-leave-local"}',
                }
            )

        events = bot.telemetry_events_from_csv()

        self.assertEqual(len(events), 1)
        self.assertEqual(set(events[0]), {"occurredAt", "eventType", "symbol", "detail", "mode"})
        self.assertEqual(events[0]["eventType"], "ENTRY_BLOCKED")
        self.assertNotIn("apiSecret", str(events))

    def test_position_snapshot_and_upload_exclude_credentials(self) -> None:
        snapshot = bot.MonitorLoopSnapshot(
            reported_at="2026-08-14T08:00:00.000Z",
            trades_today=2,
            last_scan_epoch=0,
            position_risk={"BTC_USDT_PERP:p-1": {"peak_roe_pct": "15", "protection_activated": True}},
            positions=(
                {
                    "symbol": "BTC_USDT_PERP",
                    "positionId": "p-1",
                    "netSize": "0.01",
                    "avgPrice": "60000",
                    "markPrice": "61000",
                    "initialMargin": "50",
                    "unrealizedPnL": "5",
                    "apiSecret": "must-not-leave-local",
                },
            ),
        )
        position = bot.telemetry_position(snapshot, dict(snapshot.positions[0]))
        self.assertEqual(
            set(position),
            {
                "symbol", "direction", "entryPrice", "markPrice", "roePct", "unrealizedPnl",
                "protectionActivated", "peakRoePct", "lockProfitPeakReached", "managedByBot",
            },
        )

        reporter = bot.MonitorTelemetryReporter()
        reporter._last_free_usdt = "60"
        with (
            patch.object(bot, "MONITOR_DASHBOARD_INGEST_URL", "https://monitor.example/api/monitor/ingest"),
            patch.object(bot, "MONITOR_INGEST_TOKEN", "test-monitor-token"),
            patch.object(bot.requests, "post") as post,
        ):
            post.return_value.status_code = 202
            reporter._upload(snapshot)

        sent_payload = post.call_args.kwargs["json"]
        self.assertNotIn("apiSecret", str(sent_payload))
        self.assertEqual(post.call_args.kwargs["headers"], {"X-Monitor-Ingest-Token": "test-monitor-token"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
