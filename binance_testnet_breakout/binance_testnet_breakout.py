#!/usr/bin/env python3
"""Binance USDⓈ-M Futures Testnet BTC 5 分 K Breakout 執行器。

安全界線：
1. 僅接受 Binance USDⓈ-M Futures Testnet 網址。
2. 預設 TESTNET_TRADING=false，絕不送單。
3. 即使改為 true，仍只會對 Testnet 端點送出請求；程式拒絕主網網址。
4. 真實帳戶、Pionex API 與任何 Webhook 均不在此程式範圍內。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import json
import logging
import math
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal
from urllib.parse import urlencode

import pandas as pd
import requests
from dotenv import load_dotenv


SAFE_TESTNET_BASE_URL = "https://testnet.binancefuture.com"
DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_INTERVAL = "5m"

Signal = Literal["LONG", "SHORT", "HOLD"]
ExitReason = Literal["STOP", "PROTECTION_FLOOR", "LOCK_PROFIT", "NONE"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def require_safe_testnet_base_url(base_url: str) -> str:
    """拒絕任何主網或非官方 Testnet URL，避免誤接真實資金端點。"""
    normalised = base_url.rstrip("/")
    if normalised != SAFE_TESTNET_BASE_URL:
        raise ValueError(
            "安全停止：BINANCE_TESTNET_BASE_URL 必須精確為 "
            f"{SAFE_TESTNET_BASE_URL}，程式拒絕使用其他端點。"
        )
    return normalised


@dataclass(frozen=True)
class Settings:
    symbol: str
    interval: str
    leverage: int
    margin_usdt: float
    bb_length: int
    bb_multiplier: float
    rsi_length: int
    rsi_long_min: float
    rsi_short_max: float
    stop_roe_pct: float
    protection_activation_roe_pct: float
    protection_floor_roe_pct: float
    lock_profit_peak_roe_pct: float
    lock_profit_exit_roe_pct: float
    loop_seconds: int
    testnet_trading: bool
    base_url: str
    api_key: str
    api_secret: str
    state_path: Path
    log_path: Path


def load_settings() -> Settings:
    load_dotenv()
    project_dir = Path(__file__).resolve().parent
    base_url = require_safe_testnet_base_url(
        os.getenv("BINANCE_TESTNET_BASE_URL", SAFE_TESTNET_BASE_URL)
    )
    return Settings(
        symbol=os.getenv("BINANCE_SYMBOL", DEFAULT_SYMBOL).upper(),
        interval=os.getenv("KLINE_INTERVAL", DEFAULT_INTERVAL),
        leverage=int(os.getenv("LEVERAGE", "5")),
        margin_usdt=float(os.getenv("MARGIN_USDT", "50")),
        bb_length=int(os.getenv("BB_LENGTH", "20")),
        bb_multiplier=float(os.getenv("BB_MULTIPLIER", "2")),
        rsi_length=int(os.getenv("RSI_LENGTH", "14")),
        rsi_long_min=float(os.getenv("RSI_LONG_MIN", "55")),
        rsi_short_max=float(os.getenv("RSI_SHORT_MAX", "45")),
        stop_roe_pct=float(os.getenv("STOP_ROE_PCT", "-8")),
        protection_activation_roe_pct=float(
            os.getenv("PROTECTION_ACTIVATION_ROE_PCT", "10")
        ),
        protection_floor_roe_pct=float(os.getenv("PROTECTION_FLOOR_ROE_PCT", "5")),
        lock_profit_peak_roe_pct=float(os.getenv("LOCK_PROFIT_PEAK_ROE_PCT", "15")),
        lock_profit_exit_roe_pct=float(os.getenv("LOCK_PROFIT_EXIT_ROE_PCT", "10")),
        loop_seconds=max(int(os.getenv("LOOP_SECONDS", "10")), 5),
        testnet_trading=parse_bool(os.getenv("TESTNET_TRADING"), False),
        base_url=base_url,
        api_key=os.getenv("BINANCE_TESTNET_API_KEY", "").strip(),
        api_secret=os.getenv("BINANCE_TESTNET_API_SECRET", "").strip(),
        state_path=Path(os.getenv("STATE_FILE", project_dir / "binance_testnet_state.json")),
        log_path=Path(os.getenv("EVENT_LOG_FILE", project_dir / "binance_testnet_events.csv")),
    )


@dataclass
class PositionRiskState:
    side: Literal["LONG", "SHORT"]
    entry_price: float
    quantity: float
    protection_activated: bool = False
    lock_profit_peak_reached: bool = False


@dataclass
class BotState:
    position: PositionRiskState | None = None
    last_action: str = "START"

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "BotState":
        position = data.get("position")
        return cls(
            position=PositionRiskState(**position) if position else None,
            last_action=str(data.get("last_action", "START")),
        )


def load_state(path: Path) -> BotState:
    if not path.exists():
        return BotState()
    try:
        return BotState.from_json(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise RuntimeError(f"安全停止：無法讀取狀態檔 {path}: {exc}") from exc


def save_state(path: Path, state: BotState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    payload = {"position": asdict(state.position) if state.position else None, "last_action": state.last_action}
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def configure_logger(log_path: Path) -> logging.Logger:
    logger = logging.getLogger("binance_testnet_breakout")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        logger.addHandler(stream)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    return logger


def append_event(log_path: Path, event: str, details: dict[str, Any]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    first_write = not log_path.exists()
    with log_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["timestamp_utc", "event", "details"])
        if first_write:
            writer.writeheader()
        writer.writerow({"timestamp_utc": utc_now(), "event": event, "details": json.dumps(details, ensure_ascii=False)})


def rsi(series: pd.Series, length: int) -> pd.Series:
    changes = series.diff()
    gains = changes.clip(lower=0)
    losses = -changes.clip(upper=0)
    average_gain = gains.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    average_loss = losses.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    relative_strength = average_gain / average_loss.replace(0, pd.NA)
    values = 100 - (100 / (1 + relative_strength))
    return values.mask((average_loss == 0) & (average_gain > 0), 100.0).mask(
        (average_loss == 0) & (average_gain == 0), 50.0
    )


def breakout_signal(candles: pd.DataFrame, settings: Settings) -> Signal:
    """僅使用最後一根已收盤 K 線，避免以尚未收盤 K 線發訊號。"""
    minimum_rows = max(settings.bb_length, settings.rsi_length) + 2
    if len(candles) < minimum_rows:
        return "HOLD"
    close = candles["close"].astype(float)
    basis = close.rolling(settings.bb_length).mean()
    deviation = close.rolling(settings.bb_length).std(ddof=0) * settings.bb_multiplier
    upper = basis + deviation
    lower = basis - deviation
    rsi_value = rsi(close, settings.rsi_length)
    index = candles.index[-1]
    if any(pd.isna(value) for value in (upper.loc[index], lower.loc[index], rsi_value.loc[index])):
        return "HOLD"
    if close.loc[index] > upper.loc[index] and rsi_value.loc[index] >= settings.rsi_long_min:
        return "LONG"
    if close.loc[index] < lower.loc[index] and rsi_value.loc[index] <= settings.rsi_short_max:
        return "SHORT"
    return "HOLD"


def estimated_roe_pct(position: PositionRiskState, current_price: float, leverage: int) -> float:
    if position.side == "LONG":
        return ((current_price / position.entry_price) - 1) * leverage * 100
    return ((position.entry_price / current_price) - 1) * leverage * 100


def evaluate_risk(position: PositionRiskState, current_price: float, settings: Settings) -> tuple[ExitReason, float]:
    roe = estimated_roe_pct(position, current_price, settings.leverage)
    if roe >= settings.protection_activation_roe_pct:
        position.protection_activated = True
    if roe >= settings.lock_profit_peak_roe_pct:
        position.lock_profit_peak_reached = True
    tolerance = 1e-9
    if roe <= settings.stop_roe_pct + tolerance:
        return "STOP", roe
    if position.lock_profit_peak_reached and roe <= settings.lock_profit_exit_roe_pct + tolerance:
        return "LOCK_PROFIT", roe
    if position.protection_activated and roe <= settings.protection_floor_roe_pct + tolerance:
        return "PROTECTION_FLOOR", roe
    return "NONE", roe


def decimal_places(step_size: str) -> int:
    value = step_size.rstrip("0")
    return len(value.split(".")[1]) if "." in value else 0


def round_down_to_step(value: float, step_size: str) -> float:
    step = float(step_size)
    rounded = math.floor((value + 1e-12) / step) * step
    return round(rounded, decimal_places(step_size))


def order_quantity_for_margin(
    margin_usdt: float,
    leverage: int,
    price: float,
    step_size: str,
    min_qty: float,
) -> float:
    if price <= 0 or margin_usdt <= 0 or leverage <= 0:
        raise ValueError("保證金、槓桿與價格必須大於 0。")
    quantity = round_down_to_step((margin_usdt * leverage) / price, step_size)
    if quantity < min_qty:
        raise ValueError(f"計算數量 {quantity} 小於交易規格最小數量 {min_qty}。")
    return quantity


class BinanceTestnetClient:
    def __init__(self, settings: Settings, session: requests.Session | None = None):
        self.settings = settings
        self.base_url = require_safe_testnet_base_url(settings.base_url)
        self.session = session or requests.Session()

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _signature(self, params: dict[str, Any]) -> str:
        if not self.settings.api_secret:
            raise RuntimeError("缺少 BINANCE_TESTNET_API_SECRET；認證請求已安全停止。")
        query = urlencode(params, doseq=True)
        return hmac.new(self.settings.api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        signed: bool = False,
    ) -> Any:
        payload = dict(params or {})
        headers: dict[str, str] = {}
        if signed:
            if not self.settings.api_key:
                raise RuntimeError("缺少 BINANCE_TESTNET_API_KEY；認證請求已安全停止。")
            payload["timestamp"] = int(time.time() * 1000)
            payload["recvWindow"] = 5000
            payload["signature"] = self._signature(payload)
            headers["X-MBX-APIKEY"] = self.settings.api_key
        response = self.session.request(method, self._url(path), params=payload, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json()

    def get_klines(self, limit: int = 120) -> pd.DataFrame:
        data = self._request(
            "GET",
            "/fapi/v1/klines",
            {"symbol": self.settings.symbol, "interval": self.settings.interval, "limit": limit},
        )
        records = []
        for item in data[:-1]:  # 移除最新尚未收盤 K 線。
            records.append({"open_time": int(item[0]), "open": float(item[1]), "high": float(item[2]), "low": float(item[3]), "close": float(item[4]), "volume": float(item[5])})
        return pd.DataFrame(records)

    def exchange_symbol_rules(self) -> dict[str, Any]:
        info = self._request("GET", "/fapi/v1/exchangeInfo")
        symbol_info = next((item for item in info["symbols"] if item["symbol"] == self.settings.symbol), None)
        if not symbol_info:
            raise RuntimeError(f"Testnet exchangeInfo 未找到 {self.settings.symbol}。")
        filters = {item["filterType"]: item for item in symbol_info.get("filters", [])}
        lot_filter = filters.get("MARKET_LOT_SIZE") or filters.get("LOT_SIZE")
        if not lot_filter:
            raise RuntimeError("Testnet exchangeInfo 未提供 LOT_SIZE 規格。")
        return {"step_size": lot_filter["stepSize"], "min_qty": float(lot_filter["minQty"])}

    def set_leverage(self) -> Any:
        return self._request("POST", "/fapi/v1/leverage", {"symbol": self.settings.symbol, "leverage": self.settings.leverage}, signed=True)

    def get_position(self) -> dict[str, Any] | None:
        positions = self._request("GET", "/fapi/v2/positionRisk", signed=True)
        for position in positions:
            if position.get("symbol") == self.settings.symbol and abs(float(position.get("positionAmt", 0))) > 0:
                return position
        return None

    def place_market_order(self, side: Literal["BUY", "SELL"], quantity: float, reduce_only: bool = False) -> Any:
        if not self.settings.testnet_trading:
            raise RuntimeError("TESTNET_TRADING=false；下單已安全停止。")
        params: dict[str, Any] = {"symbol": self.settings.symbol, "side": side, "type": "MARKET", "quantity": quantity}
        if reduce_only:
            params["reduceOnly"] = "true"
        return self._request("POST", "/fapi/v1/order", params, signed=True)


def direction_to_order_side(direction: Literal["LONG", "SHORT"], closing: bool = False) -> Literal["BUY", "SELL"]:
    if direction == "LONG":
        return "SELL" if closing else "BUY"
    return "BUY" if closing else "SELL"


def exchange_position_to_risk_state(position: dict[str, Any]) -> PositionRiskState:
    """將 Binance positionRisk 回應轉為本機風控狀態，拒絕不完整的持倉資料。"""
    amount = float(position.get("positionAmt", 0))
    entry_price = float(position.get("entryPrice", 0))
    if amount == 0:
        raise ValueError("交易所回傳的 positionAmt 為 0，不能建立持倉狀態。")
    if entry_price <= 0:
        raise ValueError("交易所回傳的 entryPrice 無效，不能建立持倉狀態。")
    return PositionRiskState(
        side="LONG" if amount > 0 else "SHORT",
        entry_price=entry_price,
        quantity=abs(amount),
    )


def synchronise_exchange_position(
    settings: Settings,
    state: BotState,
    client: BinanceTestnetClient,
    logger: logging.Logger,
) -> BotState:
    """在 Testnet 送單模式中以交易所倉位為唯一真實來源。

    唯讀掃描模式不呼叫受認證倉位端點，因此仍可在未設定 API Key 時安全執行。
    """
    if not settings.testnet_trading:
        return state

    exchange_position = client.get_position()
    if exchange_position is None:
        if state.position is not None:
            details = {
                "previous_side": state.position.side,
                "previous_quantity": state.position.quantity,
            }
            state.position = None
            state.last_action = "EXCHANGE_POSITION_CLOSED_EXTERNALLY"
            logger.warning("EXCHANGE_POSITION_CLOSED_EXTERNALLY | %s", details)
            append_event(settings.log_path, "EXCHANGE_POSITION_CLOSED_EXTERNALLY", details)
        return state

    exchange_state = exchange_position_to_risk_state(exchange_position)
    if state.position is None:
        state.position = exchange_state
        state.last_action = "EXCHANGE_POSITION_ADOPTED"
        details = {
            "side": exchange_state.side,
            "entry_price": exchange_state.entry_price,
            "quantity": exchange_state.quantity,
        }
        logger.warning("EXCHANGE_POSITION_ADOPTED | %s", details)
        append_event(settings.log_path, "EXCHANGE_POSITION_ADOPTED", details)
        return state

    local = state.position
    same_position = (
        local.side == exchange_state.side
        and math.isclose(local.entry_price, exchange_state.entry_price, rel_tol=0, abs_tol=1e-8)
        and math.isclose(local.quantity, exchange_state.quantity, rel_tol=0, abs_tol=1e-12)
    )
    if same_position:
        return state

    if local.side == exchange_state.side:
        exchange_state.protection_activated = local.protection_activated
        exchange_state.lock_profit_peak_reached = local.lock_profit_peak_reached
    state.position = exchange_state
    state.last_action = "EXCHANGE_POSITION_RESYNCED"
    details = {
        "side": exchange_state.side,
        "entry_price": exchange_state.entry_price,
        "quantity": exchange_state.quantity,
    }
    logger.warning("EXCHANGE_POSITION_RESYNCED | %s", details)
    append_event(settings.log_path, "EXCHANGE_POSITION_RESYNCED", details)
    return state


def run_once(settings: Settings, state: BotState, client: BinanceTestnetClient, logger: logging.Logger) -> BotState:
    state = synchronise_exchange_position(settings, state, client, logger)
    candles = client.get_klines()
    if candles.empty:
        raise RuntimeError("Testnet 未回傳已收盤 K 線。")
    current_price = float(candles.iloc[-1]["close"])
    signal = breakout_signal(candles, settings)
    logger.info("SIGNAL | %s | close=%.2f | %s", settings.symbol, current_price, signal)
    append_event(settings.log_path, "SIGNAL", {"symbol": settings.symbol, "price": current_price, "signal": signal})

    if state.position:
        exit_reason, roe = evaluate_risk(state.position, current_price, settings)
        logger.info("POSITION | %s | roe=%.2f%% | risk=%s", state.position.side, roe, exit_reason)
        if exit_reason != "NONE":
            details = {"reason": exit_reason, "roe_pct": round(roe, 4), "price": current_price}
            if settings.testnet_trading:
                client.place_market_order(direction_to_order_side(state.position.side, closing=True), state.position.quantity, reduce_only=True)
                state.position = None
                state.last_action = f"TESTNET_EXIT_{exit_reason}"
                append_event(settings.log_path, "TESTNET_EXIT", details)
            else:
                state.last_action = f"DRY_RUN_EXIT_{exit_reason}"
                append_event(settings.log_path, "DRY_RUN_EXIT", details)
            return state
        return state

    if signal == "HOLD":
        state.last_action = "HOLD"
        return state
    rules = client.exchange_symbol_rules()
    quantity = order_quantity_for_margin(settings.margin_usdt, settings.leverage, current_price, rules["step_size"], rules["min_qty"])
    details = {"signal": signal, "price": current_price, "quantity": quantity, "margin_usdt": settings.margin_usdt, "leverage": settings.leverage}
    if settings.testnet_trading:
        client.set_leverage()
        client.place_market_order(direction_to_order_side(signal), quantity)
        state.position = PositionRiskState(side=signal, entry_price=current_price, quantity=quantity)
        state.last_action = f"TESTNET_ENTRY_{signal}"
        append_event(settings.log_path, "TESTNET_ENTRY", details)
    else:
        state.last_action = f"DRY_RUN_ENTRY_{signal}"
        append_event(settings.log_path, "DRY_RUN_ENTRY", details)
    logger.info("%s | %s", state.last_action, details)
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description="Binance Futures Testnet BTC 5 分 K Breakout 執行器")
    parser.add_argument("--once", action="store_true", help="只執行一次市場／策略檢查")
    args = parser.parse_args()
    settings = load_settings()
    logger = configure_logger(settings.log_path)
    state = load_state(settings.state_path)
    client = BinanceTestnetClient(settings)
    logger.warning(
        "START | Binance Futures Testnet only | TESTNET_TRADING=%s | mainnet is refused by code.",
        settings.testnet_trading,
    )
    while True:
        try:
            state = run_once(settings, state, client, logger)
            save_state(settings.state_path, state)
        except requests.RequestException as exc:
            logger.error("NETWORK_ERROR | %s", exc)
        except Exception as exc:  # Keep local dry-run loop observable; do not hide a safety stop.
            logger.error("SAFETY_STOP | %s", exc)
            if args.once:
                raise
        if args.once:
            break
        time.sleep(settings.loop_seconds)


if __name__ == "__main__":
    main()
