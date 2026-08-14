import unittest
import logging
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from binance_testnet_breakout import (
    BotState,
    SAFE_TESTNET_BASE_URL,
    PositionRiskState,
    Settings,
    breakout_signal,
    exchange_position_to_risk_state,
    evaluate_risk,
    order_quantity_for_margin,
    require_safe_testnet_base_url,
    synchronise_exchange_position,
)


def settings() -> Settings:
    return Settings(
        symbol="BTCUSDT", interval="5m", leverage=5, margin_usdt=50,
        bb_length=3, bb_multiplier=1.0, rsi_length=2, rsi_long_min=55, rsi_short_max=45,
        stop_roe_pct=-8, protection_activation_roe_pct=10, protection_floor_roe_pct=5,
        lock_profit_peak_roe_pct=15, lock_profit_exit_roe_pct=10, loop_seconds=10,
        testnet_trading=False, base_url=SAFE_TESTNET_BASE_URL, api_key="", api_secret="",
        state_path=Path("state.json"), log_path=Path("events.csv"),
    )


class FakePositionClient:
    def __init__(self, position):
        self.position = position
        self.calls = 0

    def get_position(self):
        self.calls += 1
        return self.position


class TestTestnetSafety(unittest.TestCase):
    def test_only_exact_testnet_url_is_allowed(self):
        self.assertEqual(require_safe_testnet_base_url(SAFE_TESTNET_BASE_URL), SAFE_TESTNET_BASE_URL)
        with self.assertRaises(ValueError):
            require_safe_testnet_base_url("https://fapi.binance.com")

    def test_quantity_uses_margin_times_leverage_and_rounds_down(self):
        self.assertEqual(order_quantity_for_margin(50, 5, 100_000, "0.001", 0.001), 0.002)

    def test_hard_stop(self):
        position = PositionRiskState(side="LONG", entry_price=100_000, quantity=0.002)
        reason, roe = evaluate_risk(position, 98_400, settings())
        self.assertEqual(reason, "STOP")
        self.assertLessEqual(roe, -8)

    def test_protection_floor_after_activation(self):
        position = PositionRiskState(side="LONG", entry_price=100_000, quantity=0.002)
        self.assertEqual(evaluate_risk(position, 102_000, settings())[0], "NONE")
        reason, roe = evaluate_risk(position, 101_000, settings())
        self.assertEqual(reason, "PROTECTION_FLOOR")
        self.assertAlmostEqual(roe, 5.0)

    def test_lock_profit_exit_after_peak(self):
        position = PositionRiskState(side="SHORT", entry_price=100_000, quantity=0.002)
        self.assertEqual(evaluate_risk(position, 97_000, settings())[0], "NONE")
        reason, roe = evaluate_risk(position, 98_040, settings())
        self.assertEqual(reason, "LOCK_PROFIT")
        self.assertLessEqual(roe, 10.0)

    def test_breakout_signal_long(self):
        candles = pd.DataFrame({"close": [100, 100, 100, 100, 110]})
        self.assertEqual(breakout_signal(candles, settings()), "LONG")

    def test_exchange_position_maps_negative_amount_to_short(self):
        position = exchange_position_to_risk_state({"positionAmt": "-0.003", "entryPrice": "101234.5"})
        self.assertEqual(position.side, "SHORT")
        self.assertEqual(position.quantity, 0.003)
        self.assertEqual(position.entry_price, 101234.5)

    def test_read_only_mode_never_requests_authenticated_position(self):
        local = BotState(position=PositionRiskState(side="LONG", entry_price=100_000, quantity=0.002))
        client = FakePositionClient(None)
        result = synchronise_exchange_position(settings(), local, client, logging.getLogger("test_read_only_mode"))
        self.assertIsNotNone(result.position)
        self.assertEqual(client.calls, 0)

    def test_external_close_clears_local_position(self):
        with TemporaryDirectory() as temporary:
            local = BotState(position=PositionRiskState(side="LONG", entry_price=100_000, quantity=0.002))
            testnet_settings = replace(settings(), testnet_trading=True, log_path=Path(temporary) / "events.csv")
            result = synchronise_exchange_position(
                testnet_settings,
                local,
                FakePositionClient(None),
                logging.getLogger("test_external_close"),
            )
        self.assertIsNone(result.position)
        self.assertEqual(result.last_action, "EXCHANGE_POSITION_CLOSED_EXTERNALLY")

    def test_exchange_position_is_adopted_when_local_state_is_empty(self):
        with TemporaryDirectory() as temporary:
            testnet_settings = replace(settings(), testnet_trading=True, log_path=Path(temporary) / "events.csv")
            result = synchronise_exchange_position(
                testnet_settings,
                BotState(),
                FakePositionClient({"positionAmt": "0.004", "entryPrice": "100500"}),
                logging.getLogger("test_adopt_exchange_position"),
            )
        self.assertIsNotNone(result.position)
        self.assertEqual(result.position.side, "LONG")
        self.assertEqual(result.position.quantity, 0.004)
        self.assertEqual(result.last_action, "EXCHANGE_POSITION_ADOPTED")


if __name__ == "__main__":
    unittest.main()
