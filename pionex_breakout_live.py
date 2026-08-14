#!/usr/bin/env python3
"""派網 USDT 永續合約 Breakout 執行器（唯讀安全版）。

重要安全界線：
1. LIVE_TRADING 預設為 false。該模式不會呼叫任何下單或設定槓桿端點。
2. 本程式只支援派網單向 BUYSELL 模式，使用 positionSide=BOTH。
3. 系統一次只管理一筆活動倉位；有任一非零持倉時只做風控，不開新倉。
4. 雲端重新啟動可能遺失本機狀態。若沒有可靠持久化儲存，不可切換為實盤。

必要 .env：
    PIONEX_API_KEY=...
    PIONEX_API_SECRET=...

絕不可提交 .env、pionex_live_state.json 或 pionex_live_events.csv 至 GitHub。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlencode

import pandas as pd
import requests
from dotenv import load_dotenv


PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_DIR / ".env", override=True)

BASE_URL = "https://api.pionex.com"
KLINE_INTERVAL = os.getenv("KLINE_INTERVAL", "5M")
LOOP_SECONDS = int(os.getenv("LOOP_SECONDS", "10"))
SCAN_COOLDOWN_SECONDS = int(os.getenv("SCAN_COOLDOWN_SECONDS", "60"))
SCAN_TOP_N = int(os.getenv("SCAN_TOP_N", "30"))
KLINE_LIMIT = int(os.getenv("KLINE_LIMIT", "150"))

LEVERAGE = Decimal(os.getenv("LEVERAGE", "5"))
STOP_ROE_PCT = Decimal(os.getenv("STOP_ROE_PCT", "-8"))
PROTECTION_ACTIVATION_ROE_PCT = Decimal(os.getenv("PROTECTION_ACTIVATION_ROE_PCT", "10"))
PROTECTION_FLOOR_ROE_PCT = Decimal(os.getenv("PROTECTION_FLOOR_ROE_PCT", "5"))
LOCK_PROFIT_PEAK_ROE_PCT = Decimal(os.getenv("LOCK_PROFIT_PEAK_ROE_PCT", "15"))
LOCK_PROFIT_EXIT_ROE_PCT = Decimal(os.getenv("LOCK_PROFIT_EXIT_ROE_PCT", "10"))
# 預設為 0，才精確符合「可用 USDT 至少 50 即可進入第一階」的規則。
MIN_FREE_BALANCE_BUFFER = Decimal(os.getenv("MIN_FREE_BALANCE_BUFFER", "0"))

BOLLINGER_PERIOD = int(os.getenv("BOLLINGER_PERIOD", "20"))
BOLLINGER_STDDEV = Decimal(os.getenv("BOLLINGER_STDDEV", "2"))
RSI_PERIOD = int(os.getenv("RSI_PERIOD", "14"))
RSI_LONG_MIN = Decimal(os.getenv("RSI_LONG_MIN", "55"))
RSI_SHORT_MAX = Decimal(os.getenv("RSI_SHORT_MAX", "45"))

LIVE_TRADING = os.getenv("LIVE_TRADING", "false").strip().lower() == "true"
API_KEY = os.getenv("PIONEX_API_KEY", "").strip()
API_SECRET = os.getenv("PIONEX_API_SECRET", "").strip()
# 派網客服於 2026-08-15 明確確認：Public Trade API 的直接 USDT 永續合約下單
# 並未對所有帳戶開放，也沒有可申請的白名單流程。因此不得以環境變數繞過此封鎖。
# 唯讀掃描與 DRY_RUN 模擬維持可用；實盤執行須改採官方支援的 Bot API 或 Signal Bot。
DIRECT_FUTURES_ORDERING_SUPPORTED = False
# Telegram 為可選通知；預設停用，且不影響下單與風控邏輯。
TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "false").strip().lower() == "true"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# 私人雲端監控為選配且預設停用。權杖僅用於本機向監控端驗證，絕非派網 API Key。
# 上傳工作者與交易主迴圈分離；任何雲端、網路或監控端失敗都不可影響下單與風控。
MONITOR_TELEMETRY_ENABLED = os.getenv("MONITOR_TELEMETRY_ENABLED", "false").strip().lower() == "true"
MONITOR_DASHBOARD_INGEST_URL = os.getenv("MONITOR_DASHBOARD_INGEST_URL", "").strip()
MONITOR_INGEST_TOKEN = os.getenv("MONITOR_INGEST_TOKEN", "").strip()
MONITOR_UPLOAD_INTERVAL_SECONDS = 10
MONITOR_BALANCE_REFRESH_SECONDS = 30


def project_path_from_env(variable: str, default_name: str) -> Path:
    value = Path(os.getenv(variable, default_name))
    return value if value.is_absolute() else PROJECT_DIR / value


STATE_PATH = project_path_from_env("BOT_STATE_FILE", "pionex_live_state.json")
EVENT_LOG_PATH = project_path_from_env("EVENT_LOG_FILE", "pionex_live_events.csv")
TAIPEI_TZ = timezone(timedelta(hours=8))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
LOG = logging.getLogger("pionex_live")

# 以可用 USDT 決定單筆保證金。由高到低比對，7,680 以上固定封頂 6,400。
MARGIN_TIERS: tuple[tuple[Decimal, Decimal], ...] = (
    (Decimal("7680"), Decimal("6400")),
    (Decimal("3840"), Decimal("3200")),
    (Decimal("1920"), Decimal("1600")),
    (Decimal("960"), Decimal("800")),
    (Decimal("480"), Decimal("400")),
    (Decimal("240"), Decimal("200")),
    (Decimal("120"), Decimal("100")),
    (Decimal("50"), Decimal("50")),
)


class PionexAPIError(RuntimeError):
    """派網拒絕請求、連線失敗或回傳無效資料時拋出。"""


@dataclass
class PositionRiskState:
    """依 positionId 保存的兩段式鎖利狀態。"""

    peak_roe_pct: str = "0"
    protection_activated: bool = False
    reached_lock_profit_peak: bool = False
    dry_run_exit_logged: bool = False

    @property
    def peak_roe(self) -> Decimal:
        return Decimal(self.peak_roe_pct)


@dataclass
class BotState:
    """僅保存非機密執行狀態；API Key 不會寫入此檔。"""

    last_processed_candles: dict[str, int] = field(default_factory=dict)
    position_risk: dict[str, dict[str, Any]] = field(default_factory=dict)
    trades_today: int = 0
    trade_day_utc: str = ""
    last_scan_epoch: int = 0
    last_entry_client_order_id: str = ""
    last_exit_client_order_id: str = ""


@dataclass(frozen=True)
class MonitorLoopSnapshot:
    """傳遞給背景監控工作者的去敏感化本機快照，不保存任何 API 憑證。"""

    reported_at: str
    trades_today: int
    last_scan_epoch: int
    position_risk: dict[str, dict[str, Any]]
    positions: tuple[dict[str, Any], ...]


def load_state() -> BotState:
    """載入狀態，並安全忽略舊版單一交易對狀態檔的過時欄位。"""
    if not STATE_PATH.exists():
        return BotState()
    try:
        raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("狀態檔根物件不是 JSON 物件")
        return BotState(
            last_processed_candles={
                str(key): int(value)
                for key, value in dict(raw.get("last_processed_candles", {})).items()
            },
            position_risk={
                str(key): dict(value)
                for key, value in dict(raw.get("position_risk", {})).items()
                if isinstance(value, dict)
            },
            trades_today=int(raw.get("trades_today", 0)),
            trade_day_utc=str(raw.get("trade_day_utc", "")),
            last_scan_epoch=int(raw.get("last_scan_epoch", 0)),
            last_entry_client_order_id=str(raw.get("last_entry_client_order_id", "")),
            last_exit_client_order_id=str(raw.get("last_exit_client_order_id", "")),
        )
    except (OSError, ValueError, TypeError) as exc:
        raise RuntimeError(f"無法讀取狀態檔 {STATE_PATH}: {exc}") from exc


def save_state(state: BotState) -> None:
    """以暫存檔原子取代，降低程序中斷時損壞狀態檔的機率。"""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = STATE_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(asdict(state), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(STATE_PATH)


def taipei_now() -> str:
    return datetime.now(TAIPEI_TZ).strftime("%Y-%m-%d %H:%M:%S")


def send_telegram(message: str) -> bool:
    """傳送可選 Telegram 通知；失敗只記錄警告，絕不影響交易風控流程。"""
    if not TELEGRAM_ENABLED:
        return False
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        LOG.warning("Telegram 已啟用但缺少 Bot Token 或 Chat ID；略過通知。")
        return False

    safe_message = str(message).strip()[:3500]
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": safe_message},
            timeout=8,
        )
        payload = response.json()
        if response.status_code >= 400 or not payload.get("ok", False):
            LOG.warning("Telegram 通知失敗：HTTP %s。", response.status_code)
            return False
    except (requests.RequestException, ValueError) as exc:
        LOG.warning("Telegram 通知連線失敗：%s", exc)
        return False
    return True


def log_event(event: str, detail: str, symbol: str = "", **context: Any) -> None:
    """以固定欄位寫 CSV，其他內容封裝 JSON，避免不同事件遺失欄位。"""
    EVENT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    is_new = not EVENT_LOG_PATH.exists()
    fieldnames = ["time_taipei", "event", "detail", "symbol", "live_trading", "context_json"]
    row = {
        "time_taipei": taipei_now(),
        "event": event,
        "detail": detail,
        "symbol": symbol,
        "live_trading": LIVE_TRADING,
        "context_json": json.dumps(context, ensure_ascii=False, sort_keys=True, default=str),
    }
    with EVENT_LOG_PATH.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        if is_new:
            writer.writeheader()
        writer.writerow(row)
    LOG.info("%s | %s | %s", event, symbol or "帳戶", detail)


def utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def taipei_event_time_to_utc_iso(value: str) -> str | None:
    """將本機 CSV 的台北時間轉為固定 UTC 字串；不可信的舊列直接略過。"""
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=TAIPEI_TZ)
    except (TypeError, ValueError):
        return None
    return parsed.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def telemetry_events_from_csv(limit: int = 100) -> list[dict[str, Any]]:
    """僅讀取事件 CSV 的固定安全欄位，永不上傳 context_json、API 憑證或原始 API 回應。"""
    if limit < 1 or not EVENT_LOG_PATH.exists():
        return []
    try:
        with EVENT_LOG_PATH.open("r", newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))[-limit:]
    except (OSError, csv.Error) as exc:
        LOG.warning("讀取監控事件 CSV 失敗：%s", exc)
        return []

    events: list[dict[str, Any]] = []
    for row in rows:
        occurred_at = taipei_event_time_to_utc_iso(str(row.get("time_taipei", "")))
        event_type = str(row.get("event", "")).strip().upper()
        detail = str(row.get("detail", "")).strip()
        if occurred_at is None or not event_type.replace("_", "").isalpha() or not detail:
            continue
        events.append({
            "occurredAt": occurred_at,
            "eventType": event_type[:64],
            "symbol": str(row.get("symbol", "")).strip()[:80] or None,
            "detail": detail[:1500],
            "mode": "LIVE" if str(row.get("live_trading", "")).lower() == "true" else "READ_ONLY",
        })
    return events


def decimal_string(value: Decimal) -> str:
    """避免 API payload 或日誌出現科學記號。"""
    return format(value.normalize(), "f")


def as_decimal(value: Any, label: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise RuntimeError(f"{label} 不是可解析的數字：{value!r}") from exc
    if not parsed.is_finite():
        raise RuntimeError(f"{label} 必須是有限數字。")
    return parsed


def is_tradable_usdt_perp(info: dict[str, Any]) -> bool:
    """統一驗證派網兩種已觀察到的合約類型格式。"""
    symbol = str(info.get("symbol", "")).upper()
    status = str(info.get("status", "")).upper()
    quote_currency = str(info.get("quoteCurrency", "")).upper()
    contract_type = str(info.get("contractType", "")).upper()
    api_type = str(info.get("type", "")).upper()
    is_perpetual = contract_type == "PERPETUAL" or api_type == "PERP"
    return (
        bool(symbol)
        and status == "TRADING"
        and quote_currency == "USDT"
        and is_perpetual
        and symbol.endswith("_USDT_PERP")
    )


def round_down_to_step(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        raise ValueError("交易對回傳了無效的 baseStep")
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def margin_for_free_balance(free_usdt: Decimal) -> Decimal:
    """依使用者指定 A 階梯，回傳單筆保證金；不足 50 USDT 則為 0。"""
    if free_usdt < 0:
        raise ValueError("可用 USDT 不可為負數")
    for minimum, margin in MARGIN_TIERS:
        if free_usdt >= minimum:
            return margin
    return Decimal("0")


def position_state_key(position: dict[str, Any]) -> str:
    """以交易對與 positionId 分離不同持倉週期的鎖利高水位。"""
    symbol = str(position.get("symbol", "UNKNOWN"))
    position_id = str(position.get("positionId", "UNKNOWN"))
    return f"{symbol}:{position_id}"


def risk_state_for(state: BotState, position: dict[str, Any]) -> tuple[str, PositionRiskState]:
    key = position_state_key(position)
    raw = state.position_risk.get(key, {})
    try:
        risk = PositionRiskState(
            peak_roe_pct=str(raw.get("peak_roe_pct", "0")),
            protection_activated=bool(raw.get("protection_activated", False)),
            reached_lock_profit_peak=bool(raw.get("reached_lock_profit_peak", False)),
            dry_run_exit_logged=bool(raw.get("dry_run_exit_logged", False)),
        )
        _ = risk.peak_roe
    except (AttributeError, InvalidOperation, ValueError) as exc:
        raise RuntimeError(f"持倉風控狀態格式錯誤（{key}）：{exc}") from exc
    return key, risk


def store_risk_state(state: BotState, key: str, risk: PositionRiskState) -> None:
    state.position_risk[key] = asdict(risk)
    save_state(state)


def remove_risk_state(state: BotState, position: dict[str, Any]) -> None:
    key = position_state_key(position)
    if key in state.position_risk:
        del state.position_risk[key]
        save_state(state)


class PionexClient:
    """最小化的派網 Futures REST 用戶端。

    私有請求自行建立 URL 並以同一份精確字串簽名，避免 requests 的參數序列化與簽名字串不同。
    """

    def __init__(self, api_key: str, api_secret: str) -> None:
        self.api_key = api_key
        self.api_secret = api_secret.encode("utf-8")
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def _signed_request(
        self,
        method: Literal["GET", "POST", "DELETE"],
        path: str,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.api_key or not self.api_secret:
            raise RuntimeError("找不到 PIONEX_API_KEY 或 PIONEX_API_SECRET；請確認 .env 或雲端環境變數。")

        params = {str(key): str(value) for key, value in dict(query or {}).items()}
        params["timestamp"] = str(int(time.time() * 1000))
        canonical_query = urlencode(sorted(params.items()))
        path_url = f"{path}?{canonical_query}"
        raw_body = json.dumps(body, separators=(",", ":"), ensure_ascii=False) if body is not None else ""
        payload = f"{method}{path_url}{raw_body}"
        signature = hmac.new(self.api_secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        headers = {
            "PIONEX-KEY": self.api_key,
            "PIONEX-SIGNATURE": signature,
            "Content-Type": "application/json",
        }

        try:
            response = self.session.request(
                method=method,
                url=f"{BASE_URL}{path_url}",
                data=raw_body if body is not None else None,
                headers=headers,
                timeout=12,
            )
        except requests.RequestException as exc:
            raise PionexAPIError(f"派網連線失敗：{exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise PionexAPIError(f"派網回傳非 JSON（HTTP {response.status_code}）：{response.text[:400]}") from exc

        if response.status_code >= 400 or not data.get("result", False):
            code = str(data.get("code", ""))
            message = data.get("message", data)
            if code == "INVALID_SIGNATURE":
                raise PionexAPIError(
                    "派網 API 失敗：INVALID_SIGNATURE。請確認 API Key 與 Secret 是否為同一組；"
                    "不要把任一機密貼到聊天室或 GitHub。"
                )
            raise PionexAPIError(f"派網 API 失敗（HTTP {response.status_code}）：{code} {message}")
        return data

    def private_get(self, path: str, query: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._signed_request("GET", path, query=query)

    def private_post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._signed_request("POST", path, body=body)

    def public_get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            response = self.session.get(f"{BASE_URL}{path}", params=params, timeout=12)
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise PionexAPIError(f"派網公開資料讀取失敗：{exc}") from exc
        if not data.get("result", False):
            raise PionexAPIError(f"派網公開 API 失敗：{data}")
        return data

    def tradable_usdt_perp_symbols(self) -> dict[str, dict[str, Any]]:
        data = self.public_get(
            "/api/v1/common/symbols",
            {"type": "PERP", "status": "TRADING"},
        ).get("data", {})
        symbols = data.get("symbols", [])
        allowed: dict[str, dict[str, Any]] = {}
        parsed_items = 0
        trading_items = 0
        usdt_items = 0
        perp_items = 0

        for item in symbols:
            if not isinstance(item, dict):
                continue
            parsed_items += 1
            symbol = str(item.get("symbol", "")).upper()
            status = str(item.get("status", "")).upper()
            quote_currency = str(item.get("quoteCurrency", "")).upper()
            # 派網公開端點目前回傳 type=PERP；部分文件／舊版格式則使用
            # contractType=PERPETUAL，因此兩者都接受，但仍要求正式的 _PERP 後綴。
            contract_type = str(item.get("contractType", "")).upper()
            api_type = str(item.get("type", "")).upper()
            is_perpetual = contract_type == "PERPETUAL" or api_type == "PERP"

            if status == "TRADING":
                trading_items += 1
            if quote_currency == "USDT":
                usdt_items += 1
            if is_perpetual:
                perp_items += 1
            if is_tradable_usdt_perp(item):
                allowed[symbol] = item

        if not allowed:
            raise PionexAPIError(
                "派網未回傳任何可交易 USDT 永續合約。"
                f"診斷：原始筆數={len(symbols)}、可解析={parsed_items}、"
                f"TRADING={trading_items}、USDT={usdt_items}、PERP={perp_items}。"
            )
        return allowed

    def top_tradable_usdt_perps(self, top_n: int) -> list[tuple[str, dict[str, Any], Decimal]]:
        if top_n < 1:
            raise ValueError("SCAN_TOP_N 必須至少為 1")
        allowed = self.tradable_usdt_perp_symbols()
        data = self.public_get("/api/v1/market/tickers", {"type": "PERP"}).get("data", {})
        ranked: list[tuple[str, dict[str, Any], Decimal]] = []
        for ticker in data.get("tickers", []):
            if not isinstance(ticker, dict):
                continue
            symbol = str(ticker.get("symbol", ""))
            # 成交統計可能短暫保留剛下架的標的，因此仍必須先通過官方合約
            # 清單的 TRADING/USDT/PERP 驗證。派網實測中批次 bookTicker 路徑會回覆
            # 404，不能把它當候選清單的唯一過濾條件；真正的 bid/ask 會在送單前
            # 透過此交易對的深度端點再次驗證。
            if symbol not in allowed:
                continue
            try:
                amount = as_decimal(ticker.get("amount", "0"), f"{symbol} 的 24h amount")
            except RuntimeError:
                continue
            if amount > 0:
                ranked.append((symbol, allowed[symbol], amount))
        ranked.sort(key=lambda row: row[2], reverse=True)
        if not ranked:
            raise PionexAPIError("找不到成交額大於零的可交易 USDT 永續合約。")
        return ranked[:top_n]

    def symbol_info(self, symbol: str) -> dict[str, Any]:
        data = self.public_get("/api/v1/common/symbols", {"symbols": symbol}).get("data", {})
        records = data.get("symbols", [])
        matches = [item for item in records if isinstance(item, dict) and item.get("symbol") == symbol]
        if len(matches) != 1:
            raise PionexAPIError(f"無法取得 {symbol} 的唯一交易對規格。")
        return matches[0]

    def book_ticker(self, symbol: str) -> dict[str, Any]:
        """從派網永續合約深度端點讀取最佳買一與賣一。

        實測顯示 `/api/v1/market/bookTicker` 對 PERP 批次請求會回覆 404；
        深度端點則會回傳 bids/asks 的價格、數量陣列。因此此處只在真正準備
        計算下單數量時查詢指定交易對，並拒絕空簿或非正數報價。
        """
        data = self.public_get("/api/v1/market/depth", {"symbol": symbol}).get("data", {})
        bids = data.get("bids", [])
        asks = data.get("asks", [])
        if not isinstance(bids, list) or not isinstance(asks, list) or not bids or not asks:
            raise PionexAPIError(f"{symbol} 沒有有效的深度 bid/ask 報價。")

        try:
            best_bid = bids[0][0]
            best_ask = asks[0][0]
        except (IndexError, TypeError) as exc:
            raise PionexAPIError(f"{symbol} 深度報價格式無法辨識。") from exc

        bid = as_decimal(best_bid, f"{symbol} best bid")
        ask = as_decimal(best_ask, f"{symbol} best ask")
        if bid <= 0 or ask <= 0:
            raise PionexAPIError(f"{symbol} 深度端點回傳無效的 bid/ask 報價。")
        return {
            "symbol": symbol,
            "bidPrice": decimal_string(bid),
            "askPrice": decimal_string(ask),
        }

    def klines(self, symbol: str, limit: int = KLINE_LIMIT) -> list[dict[str, Any]]:
        data = self.public_get(
            "/api/v1/market/klines",
            {"symbol": symbol, "interval": KLINE_INTERVAL, "limit": limit},
        ).get("data", {})
        rows = data.get("klines", [])
        if not isinstance(rows, list):
            raise PionexAPIError(f"{symbol} K 線資料格式無法辨識。")
        return rows

    def positions(self, symbol: str | None = None) -> list[dict[str, Any]]:
        query = {"symbol": symbol} if symbol else None
        data = self.private_get("/uapi/v1/account/positions", query).get("data", {})
        positions = data.get("positions", [])
        if not isinstance(positions, list):
            raise PionexAPIError("派網持倉資料格式無法辨識。")
        return [item for item in positions if isinstance(item, dict)]

    def balances(self) -> list[dict[str, Any]]:
        data = self.private_get("/uapi/v1/account/balances").get("data", {})
        balances = data.get("balances", [])
        if not isinstance(balances, list):
            raise PionexAPIError("派網餘額資料格式無法辨識。")
        return [item for item in balances if isinstance(item, dict)]

    def leverage(self, symbol: str) -> Decimal:
        response = self.private_get("/uapi/v1/account/leverage", {"symbol": symbol})
        return parse_account_leverage(response.get("data"), symbol)

    def position_mode(self) -> str:
        data = self.private_get("/uapi/v1/account/positionMode").get("data", {})
        mode = data.get("positionMode")
        if not mode:
            raise PionexAPIError("派網未回傳 positionMode。")
        return str(mode)

    def place_market_order(
        self,
        symbol: str,
        side: Literal["BUY", "SELL"],
        size: Decimal,
        reduce_only: bool,
        client_order_id: str,
    ) -> dict[str, Any]:
        body = {
            "clientOrderId": client_order_id,
            "symbol": symbol,
            "positionSide": "BOTH",
            "side": side,
            "type": "MARKET_QTY",
            "size": decimal_string(size),
            "reduceOnly": reduce_only,
        }
        if not LIVE_TRADING:
            log_event("DRY_RUN_ORDER", "LIVE_TRADING=false，僅記錄假設訂單，未送出派網請求。", symbol, order=body)
            return {"data": {"orderId": "DRY-RUN", "clientOrderId": client_order_id}, "request": body}
        result = self.private_post("/uapi/v1/trade/order", body)
        result["request"] = body
        return result

    def get_order(self, symbol: str, order_id: str | int) -> dict[str, Any]:
        data = self.private_get("/uapi/v1/trade/order", {"symbol": symbol, "orderId": order_id}).get("data", {})
        if not isinstance(data, dict):
            raise PionexAPIError("派網訂單資料格式無法辨識。")
        return data


def _parse_decimal_leverage(value: Any, source: str) -> Decimal:
    if value is None or not str(value).strip():
        raise RuntimeError(f"派網 {source} 沒有有效槓桿數值；程式已停止該交易對的開倉流程。")
    parsed = as_decimal(value, f"派網 {source} 的槓桿")
    if parsed <= 0:
        raise RuntimeError(f"派網 {source} 的槓桿必須大於 0。")
    return parsed


def _field_names(value: Any) -> str:
    if isinstance(value, dict):
        return ", ".join(sorted(str(key) for key in value.keys())) or "（無欄位）"
    return f"型別={type(value).__name__}"


def _parse_leverage_record(record: Any, source: str) -> Decimal:
    if not isinstance(record, dict):
        return _parse_decimal_leverage(record, source)
    if record.get("leverage") is not None:
        return _parse_decimal_leverage(record["leverage"], source + ".leverage")
    long_value = record.get("longLeverage")
    short_value = record.get("shortLeverage")
    if long_value is not None and short_value is not None:
        long_leverage = _parse_decimal_leverage(long_value, source + ".longLeverage")
        short_leverage = _parse_decimal_leverage(short_value, source + ".shortLeverage")
        if long_leverage == short_leverage:
            return long_leverage
        raise RuntimeError("派網回傳的 longLeverage 與 shortLeverage 不一致；本程式只支援單向 BUYSELL。")
    raise RuntimeError(f"派網 {source} 找不到槓桿欄位；收到的欄位名稱：{_field_names(record)}。")


def parse_account_leverage(data: Any, symbol: str) -> Decimal:
    """安全支援官方單數 leverage 與已觀察到的複數 leverages 格式。"""
    if not isinstance(data, dict):
        raise RuntimeError("派網槓桿端點 data 不是物件；已停止該交易對的開倉流程。")
    if data.get("leverage") is not None:
        return _parse_decimal_leverage(data["leverage"], "data.leverage")

    leverages = data.get("leverages")
    if leverages is None:
        raise RuntimeError(
            "派網槓桿端點找不到 leverage 或 leverages 欄位；"
            f"收到的欄位名稱：{_field_names(data)}。"
        )
    if isinstance(leverages, list):
        matches = [
            item for item in leverages
            if isinstance(item, dict) and str(item.get("symbol", "")) == symbol
        ]
        if len(matches) != 1:
            detail = "找不到" if not matches else "找到多筆"
            first_fields = _field_names(leverages[0]) if leverages else "（空清單）"
            raise RuntimeError(f"派網 leverages 清單{detail} {symbol} 的唯一資料；項目欄位：{first_fields}。")
        return _parse_leverage_record(matches[0], f"leverages[{symbol}]")
    if isinstance(leverages, dict):
        if symbol in leverages:
            return _parse_leverage_record(leverages[symbol], f"leverages[{symbol}]")
        if str(leverages.get("symbol", "")) == symbol:
            return _parse_leverage_record(leverages, "leverages")
        raise RuntimeError(f"派網 leverages 物件找不到 {symbol}；欄位名稱：{_field_names(leverages)}。")
    raise RuntimeError(f"派網 leverages 型別無法辨識；收到：{_field_names(leverages)}。")


def get_free_usdt(client: PionexClient) -> Decimal:
    for balance in client.balances():
        if balance.get("coin") == "USDT":
            free = as_decimal(balance.get("free", "0"), "可用 USDT")
            if free < 0:
                raise RuntimeError("派網回傳負的可用 USDT。")
            return free
    return Decimal("0")


def active_positions(client: PionexClient) -> list[dict[str, Any]]:
    active: list[dict[str, Any]] = []
    for position in client.positions():
        size = as_decimal(position.get("netSize", "0"), f"{position.get('symbol', '未知交易對')} netSize")
        if size != 0:
            active.append(position)
    return active


def telemetry_decimal(value: Any) -> str:
    """監控欄位只接受有限的十進位數；缺值以 0 呈現而不影響實盤程式。"""
    try:
        return decimal_string(as_decimal(value, "監控數值"))
    except RuntimeError:
        return "0"


def telemetry_position(state: MonitorLoopSnapshot, position: dict[str, Any]) -> dict[str, Any]:
    size = telemetry_decimal(position.get("netSize", "0"))
    try:
        direction = "LONG" if Decimal(size) > 0 else "SHORT" if Decimal(size) < 0 else "UNKNOWN"
    except InvalidOperation:
        direction = "UNKNOWN"
    key = position_state_key(position)
    risk = state.position_risk.get(key, {})
    try:
        roe = decimal_string(current_roe_pct(position))
    except RuntimeError:
        roe = "0"
    return {
        "symbol": str(position.get("symbol", "UNKNOWN"))[:80],
        "direction": direction,
        "entryPrice": telemetry_decimal(position.get("avgPrice", "0")),
        "markPrice": telemetry_decimal(position.get("markPrice", "0")),
        "roePct": roe,
        "unrealizedPnl": telemetry_decimal(position.get("unrealizedPnL", "0")),
        "protectionActivated": bool(risk.get("protection_activated", False)),
        "peakRoePct": telemetry_decimal(risk.get("peak_roe_pct", "0")),
        "lockProfitPeakReached": bool(risk.get("reached_lock_profit_peak", False)),
        "managedByBot": key in state.position_risk,
    }


class MonitorTelemetryReporter:
    """監控專用背景工作者；絕不呼叫交易下單或平倉端點。"""

    def __init__(self) -> None:
        self.enabled = MONITOR_TELEMETRY_ENABLED
        self._snapshot_lock = threading.Lock()
        self._snapshot: MonitorLoopSnapshot | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_free_usdt: str | None = None
        self._last_balance_refresh_epoch = 0.0

    def start(self) -> None:
        if not self.enabled:
            LOG.info("雲端監控遙測未啟用；不會傳送任何資料。")
            return
        if not MONITOR_DASHBOARD_INGEST_URL.startswith("https://") or not MONITOR_INGEST_TOKEN:
            LOG.warning("雲端監控遙測設定不完整；已停用遙測，交易與風控不受影響。")
            self.enabled = False
            return
        self._thread = threading.Thread(target=self._run, name="monitor-telemetry", daemon=True)
        self._thread.start()
        log_event("MONITOR_TELEMETRY_START", "唯讀雲端監控遙測已啟動。")

    def submit_loop_snapshot(self, state: BotState, positions: list[dict[str, Any]]) -> None:
        if not self.enabled:
            return
        snapshot = MonitorLoopSnapshot(
            reported_at=utc_iso_now(),
            trades_today=max(0, int(state.trades_today)),
            last_scan_epoch=max(0, int(state.last_scan_epoch)),
            position_risk={key: dict(value) for key, value in state.position_risk.items()},
            positions=tuple(dict(position) for position in positions),
        )
        with self._snapshot_lock:
            self._snapshot = snapshot

    def _current_snapshot(self) -> MonitorLoopSnapshot | None:
        with self._snapshot_lock:
            return self._snapshot

    def _refresh_free_usdt(self, client: PionexClient) -> None:
        now = time.monotonic()
        if now - self._last_balance_refresh_epoch < MONITOR_BALANCE_REFRESH_SECONDS:
            return
        self._last_balance_refresh_epoch = now
        try:
            self._last_free_usdt = decimal_string(get_free_usdt(client))
        except Exception as exc:
            # 餘額快照失敗只保留上次成功值，絕不傳播到交易主迴圈。
            LOG.warning("雲端監控讀取可用 USDT 失敗：%s", exc)

    def _upload(self, snapshot: MonitorLoopSnapshot) -> None:
        payload = {
            "reportedAt": snapshot.reported_at,
            "mode": "LIVE" if LIVE_TRADING else "READ_ONLY",
            "freeUsdt": self._last_free_usdt,
            "balanceAsOf": utc_iso_now() if self._last_free_usdt is not None else None,
            "tradesToday": snapshot.trades_today,
            "lastScanAt": (
                datetime.fromtimestamp(snapshot.last_scan_epoch, timezone.utc)
                .isoformat(timespec="milliseconds").replace("+00:00", "Z")
                if snapshot.last_scan_epoch else None
            ),
            "positions": [telemetry_position(snapshot, position) for position in snapshot.positions],
            "events": telemetry_events_from_csv(),
        }
        try:
            response = requests.post(
                MONITOR_DASHBOARD_INGEST_URL,
                json=payload,
                headers={"X-Monitor-Ingest-Token": MONITOR_INGEST_TOKEN},
                timeout=5,
            )
            if response.status_code >= 400:
                LOG.warning("雲端監控上傳被拒絕：HTTP %s。", response.status_code)
        except requests.RequestException as exc:
            LOG.warning("雲端監控上傳失敗：%s", exc)

    def _run(self) -> None:
        # 使用獨立唯讀 API client，避免背景監控與交易主迴圈共用連線狀態。
        client = PionexClient(API_KEY, API_SECRET)
        while not self._stop_event.is_set():
            try:
                self._refresh_free_usdt(client)
                snapshot = self._current_snapshot()
                if snapshot is not None:
                    self._upload(snapshot)
            except Exception as exc:
                LOG.warning("雲端監控背景工作者錯誤：%s", exc)
            self._stop_event.wait(MONITOR_UPLOAD_INTERVAL_SECONDS)


def current_roe_pct(position: dict[str, Any]) -> Decimal:
    initial_margin = as_decimal(position.get("initialMargin", "0"), "持倉 initialMargin")
    unrealized = as_decimal(position.get("unrealizedPnL", "0"), "持倉 unrealizedPnL")
    if initial_margin <= 0:
        raise RuntimeError("派網持倉沒有有效 initialMargin，無法計算 ROE。")
    return (unrealized / initial_margin) * Decimal("100")


def completed_candles(client: PionexClient, symbol: str) -> pd.DataFrame:
    raw = client.klines(symbol)
    minimum = max(BOLLINGER_PERIOD + 1, RSI_PERIOD + 2)
    if len(raw) < minimum + 1:
        raise RuntimeError(f"{symbol} K 線數量不足，至少需要 {minimum + 1} 根（含進行中 K 線）。")
    df = pd.DataFrame(raw)
    for column in ("open", "high", "low", "close", "volume"):
        if column not in df:
            raise RuntimeError(f"{symbol} K 線缺少 {column} 欄位。")
        df[column] = pd.to_numeric(df[column], errors="raise")
    df["time"] = pd.to_numeric(df["time"], errors="raise").astype("int64")
    df = df.sort_values("time").drop_duplicates("time").reset_index(drop=True)
    # 最後一根可能尚未收線，嚴禁拿來判定突破。
    return df.iloc[:-1].copy()


def calculate_rsi(close: pd.Series, period: int) -> pd.Series:
    """採 Wilder 平滑概念的 RSI，並明確處理全漲或全跌的零除情況。"""
    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    avg_gain = gains.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = losses.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rsi = pd.Series(50.0, index=close.index, dtype="float64")
    normal = (avg_gain > 0) & (avg_loss > 0)
    rsi.loc[normal] = 100 - (100 / (1 + (avg_gain.loc[normal] / avg_loss.loc[normal])))
    rsi.loc[(avg_gain > 0) & (avg_loss == 0)] = 100.0
    rsi.loc[(avg_gain == 0) & (avg_loss > 0)] = 0.0
    return rsi


@dataclass(frozen=True)
class SignalResult:
    signal: Literal["LONG", "SHORT", "HOLD"]
    close: Decimal
    upper_band: Decimal
    lower_band: Decimal
    rsi: Decimal


def breakout_signal(candles: pd.DataFrame) -> SignalResult:
    """以 20 期布林通道與 14 期 RSI 對已完成 K 線做雙重確認。"""
    required = max(BOLLINGER_PERIOD, RSI_PERIOD + 1)
    if len(candles) < required:
        raise RuntimeError("已完成 K 線不足，無法計算布林通道與 RSI。")

    close = candles["close"].astype("float64")
    middle = close.rolling(BOLLINGER_PERIOD, min_periods=BOLLINGER_PERIOD).mean()
    std = close.rolling(BOLLINGER_PERIOD, min_periods=BOLLINGER_PERIOD).std(ddof=0)
    upper = middle + float(BOLLINGER_STDDEV) * std
    lower = middle - float(BOLLINGER_STDDEV) * std
    rsi = calculate_rsi(close, RSI_PERIOD)

    latest_close = as_decimal(close.iloc[-1], "最新收盤價")
    latest_upper = as_decimal(upper.iloc[-1], "布林上軌")
    latest_lower = as_decimal(lower.iloc[-1], "布林下軌")
    latest_rsi = as_decimal(rsi.iloc[-1], "RSI")
    if latest_upper.is_nan() or latest_lower.is_nan() or latest_rsi.is_nan():
        raise RuntimeError("布林通道或 RSI 尚未形成有效數值。")

    if latest_close > latest_upper and latest_rsi >= RSI_LONG_MIN:
        direction: Literal["LONG", "SHORT", "HOLD"] = "LONG"
    elif latest_close < latest_lower and latest_rsi <= RSI_SHORT_MAX:
        direction = "SHORT"
    else:
        direction = "HOLD"
    return SignalResult(direction, latest_close, latest_upper, latest_lower, latest_rsi)


def calculate_entry_size(
    client: PionexClient,
    symbol: str,
    signal: Literal["LONG", "SHORT"],
    margin_usdt: Decimal,
    free_usdt: Decimal,
) -> tuple[Decimal, Decimal, Decimal]:
    """依該交易對即時精度與 bid/ask，回傳數量、參考價與名目額。"""
    if margin_usdt <= 0:
        raise RuntimeError("目前可用 USDT 未達最低 50，禁止開倉。")
    if free_usdt < margin_usdt + MIN_FREE_BALANCE_BUFFER:
        raise RuntimeError(
            f"可用合約 USDT {free_usdt} 不足；本階保證金 {margin_usdt} 與緩衝 {MIN_FREE_BALANCE_BUFFER} 均需保留。"
        )

    info = client.symbol_info(symbol)
    if not is_tradable_usdt_perp(info):
        raise RuntimeError(f"{symbol} 不再是可交易的 USDT 永續合約。")

    ticker = client.book_ticker(symbol)
    price_key = "askPrice" if signal == "LONG" else "bidPrice"
    reference_price = as_decimal(ticker.get(price_key), f"{symbol} {price_key}")
    if reference_price <= 0:
        raise RuntimeError(f"{symbol} 取得無效 {price_key}。")

    desired_notional = margin_usdt * LEVERAGE
    step = as_decimal(info.get("baseStep"), f"{symbol} baseStep")
    qty = round_down_to_step(desired_notional / reference_price, step)
    min_qty = as_decimal(info.get("minSizeMarket"), f"{symbol} minSizeMarket")
    max_qty = as_decimal(info.get("maxSizeMarket"), f"{symbol} maxSizeMarket")
    min_notional = as_decimal(info.get("minNotional"), f"{symbol} minNotional")
    actual_notional = qty * reference_price

    if qty <= 0 or qty < min_qty or qty > max_qty:
        raise RuntimeError(f"{symbol} 數量 {qty} 不在市價單允許範圍 {min_qty} 至 {max_qty}。")
    if actual_notional < min_notional:
        raise RuntimeError(f"{symbol} 名目額 {actual_notional:.4f} USDT 低於派網最小值 {min_notional}。")
    return qty, reference_price, actual_notional


def ensure_account_preflight(client: PionexClient) -> None:
    """帳戶層級唯讀檢核；錯誤時停止全部策略流程。"""
    mode = client.position_mode()
    if mode != "BUYSELL":
        raise RuntimeError(f"帳戶倉位模式為 {mode}，本程式只支援單向 BUYSELL；不會送出訂單。")


def symbol_leverage_matches(client: PionexClient, symbol: str) -> bool:
    """僅在確有訊號的交易對檢查槓桿；不自行設定槓桿。"""
    try:
        current = client.leverage(symbol)
    except PionexAPIError as exc:
        error_text = str(exc)
        if "TRADE_TYPE_DENIED" in error_text:
            # 此拒絕出現在讀取槓桿之前；未能驗證 5x 時絕不能送單或假設權限已開通。
            log_event(
                "ENTRY_BLOCKED",
                "派網拒絕此 API Key 存取 USDT 永續合約（TRADE_TYPE_DENIED / not in whitelist）；"
                "未送出訂單。一般 API Key 編輯頁未提供此交易類型切換，請聯絡派網客服，"
                "要求確認此 API Key 的 USDT 永續合約（Futures／Perpetual）API 交易類型白名單／產品授權。"
                "不要傳送 API Key、Secret 或任何權杖給客服以外的第三方。",
                symbol,
                endpoint="GET /uapi/v1/account/leverage",
                exchange_code="TRADE_TYPE_DENIED",
                exchange_message="user denied not in whitelist",
                blocked_product="USDT 永續合約（Futures／Perpetual）",
                configured_leverage=decimal_string(LEVERAGE),
            )
            return False
        if "AUTH_UNAVAILABLE" not in error_text:
            raise
        # 絕不可在無法讀回交易所槓桿時，假設使用者已手動設為 5x 後繞過檢查。
        # 官方文件將此 GET 端點列為 Enable reading；真正送單另需要 Enable trading。
        log_event(
            "ENTRY_BLOCKED",
            "派網拒絕讀取槓桿（AUTH_UNAVAILABLE）；未送出訂單。請確認『同一把』API Key 已開啟 "
            "Enable reading 與 Enable trading，且沒有因 IP 白名單限制而失效。本程式不會繞過 5x 槓桿驗證。",
            symbol,
            endpoint="GET /uapi/v1/account/leverage",
            required_permission="Enable reading",
            required_for_order="Enable trading",
            configured_leverage=decimal_string(LEVERAGE),
        )
        return False
    if current != LEVERAGE:
        log_event(
            "ENTRY_BLOCKED",
            f"派網槓桿 {current}x 與設定 {LEVERAGE}x 不一致；請在派網手動設定後再驗證。",
            symbol,
            exchange_leverage=decimal_string(current),
            configured_leverage=decimal_string(LEVERAGE),
        )
        return False
    return True


def wait_for_order_resolution(client: PionexClient, symbol: str, order_id: str | int) -> dict[str, Any]:
    """派網下單非同步；只有實盤模式才輪詢確認成交。"""
    if not LIVE_TRADING:
        return {"orderId": order_id, "status": "DRY_RUN", "filledSize": "0"}
    deadline = time.monotonic() + 20
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        last = client.get_order(symbol, order_id)
        if last.get("status") == "CLOSED":
            filled = as_decimal(last.get("filledSize", "0"), "成交數量")
            if filled <= 0:
                raise RuntimeError(f"{symbol} 訂單已關閉但未成交：{last}")
            return last
        time.sleep(1)
    raise RuntimeError(f"{symbol} 訂單 {order_id} 在 20 秒內未確認完成；請立即在派網檢查委託與持倉：{last}")


def open_position(
    client: PionexClient,
    state: BotState,
    symbol: str,
    closed_candle_time: int,
    signal: Literal["LONG", "SHORT"],
) -> bool:
    """建立或模擬一筆開倉；成功送出／模擬時回傳 True。"""
    if LIVE_TRADING and not DIRECT_FUTURES_ORDERING_SUPPORTED:
        log_event(
            "ENTRY_BLOCKED",
            "派網官方已確認 Public Trade API 目前不支援此帳戶直接進行 USDT 永續合約下單；"
            "未呼叫槓桿或下單端點。請改採官方支援的 Bot API 或 Signal Bot 路線。",
            symbol,
            configured_mode="LIVE",
            direct_futures_orders_supported=False,
            migration_target="Bot API 或 Signal Bot",
        )
        return False
    if not symbol_leverage_matches(client, symbol):
        return False

    free_usdt = get_free_usdt(client)
    margin_usdt = margin_for_free_balance(free_usdt)
    if margin_usdt <= 0:
        log_event("ENTRY_BLOCKED", "可用 USDT 少於 50，未達最低保證金門檻。", symbol, free_usdt=decimal_string(free_usdt))
        return False

    qty, reference_price, actual_notional = calculate_entry_size(client, symbol, signal, margin_usdt, free_usdt)
    side: Literal["BUY", "SELL"] = "BUY" if signal == "LONG" else "SELL"
    safe_symbol = symbol.replace("_", "")
    client_order_id = f"brk-{safe_symbol}-{closed_candle_time}-{signal.lower()}"[:64]
    response = client.place_market_order(
        symbol=symbol,
        side=side,
        size=qty,
        reduce_only=False,
        client_order_id=client_order_id,
    )
    request = response["request"]
    state.last_entry_client_order_id = request["clientOrderId"]
    # 僅保留實盤成功送單的每日統計；不作為開倉次數限制。
    if LIVE_TRADING:
        state.trades_today += 1
    save_state(state)

    order_id = response["data"]["orderId"]
    resolution = wait_for_order_resolution(client, symbol, order_id)
    # 開倉前已確認帳戶無活動倉位。只有在實盤訂單確認後才登錄此持倉，
    # 使風控不會碰到使用者原本存在的手動倉位。
    if LIVE_TRADING:
        newly_opened = [
            position for position in client.positions(symbol)
            if as_decimal(position.get("netSize", "0"), f"{symbol} netSize") != 0
        ]
        if len(newly_opened) != 1:
            raise RuntimeError(
                f"{symbol} 開倉訂單已確認，但無法唯一辨識新持倉；"
                "已禁止後續自動平倉，請立即在派網檢查持倉。"
            )
        key, risk = risk_state_for(state, newly_opened[0])
        store_risk_state(state, key, risk)
    log_event(
        "ENTRY_SENT",
        f"{signal} 市價開倉已{'送出' if LIVE_TRADING else '模擬'}；最終成交與持倉以派網為準。",
        symbol,
        order_id=order_id,
        client_order_id=request["clientOrderId"],
        requested_qty=decimal_string(qty),
        reference_price=decimal_string(reference_price),
        expected_notional=decimal_string(actual_notional),
        tier_margin_usdt=decimal_string(margin_usdt),
        free_usdt=decimal_string(free_usdt),
        order_status=resolution.get("status"),
        filled_size=resolution.get("filledSize"),
    )
    if LIVE_TRADING:
        send_telegram(
            f"[派網實盤開倉] {symbol} {signal}\n"
            f"保證金階梯：{margin_usdt} USDT\n"
            f"預計名目額：{actual_notional:.4f} USDT\n"
            f"委託狀態：{resolution.get('status')}\n"
            "最終成交與持倉請以派網為準。"
        )
    return True


def close_position(client: PionexClient, state: BotState, position: dict[str, Any], reason: str) -> None:
    """以 reduceOnly 市價單平倉；唯讀模式只留下單一模擬平倉紀錄。"""
    symbol = str(position.get("symbol", ""))
    net_size = as_decimal(position.get("netSize", "0"), f"{symbol} netSize")
    if not symbol or net_size == 0:
        return

    key, risk = risk_state_for(state, position)
    if not LIVE_TRADING and risk.dry_run_exit_logged:
        return

    if LIVE_TRADING and not DIRECT_FUTURES_ORDERING_SUPPORTED:
        log_event(
            "EXIT_BLOCKED",
            "派網官方已確認 Public Trade API 不支援直接永續合約平倉；"
            "未送出 reduceOnly 指令，請在派網官方介面處理現有倉位。",
            symbol,
            configured_mode="LIVE",
            direct_futures_orders_supported=False,
            position_id=str(position.get("positionId", "unknown")),
            reason=reason,
        )
        return

    side: Literal["BUY", "SELL"] = "SELL" if net_size > 0 else "BUY"
    qty = abs(net_size)
    roe = current_roe_pct(position)
    unrealized = as_decimal(position.get("unrealizedPnL", "0"), f"{symbol} unrealizedPnL")
    safe_symbol = symbol.replace("_", "")
    position_id = str(position.get("positionId", "unknown")).replace("_", "")
    client_order_id = f"brk-close-{safe_symbol}-{position_id}"[:64]
    response = client.place_market_order(
        symbol=symbol,
        side=side,
        size=qty,
        reduce_only=True,
        client_order_id=client_order_id,
    )
    request = response["request"]
    state.last_exit_client_order_id = request["clientOrderId"]
    if not LIVE_TRADING:
        risk.dry_run_exit_logged = True
        store_risk_state(state, key, risk)
    else:
        remove_risk_state(state, position)
        save_state(state)

    order_id = response["data"]["orderId"]
    resolution = wait_for_order_resolution(client, symbol, order_id)
    log_event(
        "EXIT_SENT",
        f"平倉指令已{'送出' if LIVE_TRADING else '模擬'}：{reason}；已實現損益以派網歷史持倉為準。",
        symbol,
        order_id=order_id,
        client_order_id=request["clientOrderId"],
        requested_qty=decimal_string(qty),
        roe_pct=f"{roe:.2f}",
        pnl_before_close=decimal_string(unrealized),
        order_status=resolution.get("status"),
        filled_size=resolution.get("filledSize"),
    )
    if LIVE_TRADING:
        send_telegram(
            f"[派網實盤平倉] {symbol}\n原因：{reason}\n"
            f"平倉前 ROE：{roe:.2f}%\n"
            f"委託狀態：{resolution.get('status')}\n"
            "已實現損益請以派網歷史持倉為準。"
        )


def monitor_position(client: PionexClient, state: BotState, position: dict[str, Any]) -> None:
    """套用 -8% 停損、+10% 保護線與 +15%→+10% 鎖利規則。"""
    symbol = str(position.get("symbol", ""))
    roe = current_roe_pct(position)
    key, risk = risk_state_for(state, position)

    if roe > risk.peak_roe:
        risk.peak_roe_pct = decimal_string(roe)
    if roe >= PROTECTION_ACTIVATION_ROE_PCT:
        risk.protection_activated = True
    if roe >= LOCK_PROFIT_PEAK_ROE_PCT:
        risk.reached_lock_profit_peak = True
    store_risk_state(state, key, risk)

    if roe <= STOP_ROE_PCT:
        close_position(client, state, position, f"硬停損：ROE {roe:.2f}% ≤ {STOP_ROE_PCT}%")
        return
    if risk.reached_lock_profit_peak and roe <= LOCK_PROFIT_EXIT_ROE_PCT:
        close_position(
            client,
            state,
            position,
            f"第二段鎖利：曾達 {LOCK_PROFIT_PEAK_ROE_PCT}% 且 ROE 回落至 {roe:.2f}% ≤ {LOCK_PROFIT_EXIT_ROE_PCT}%",
        )
        return
    if risk.protection_activated and roe <= PROTECTION_FLOOR_ROE_PCT:
        close_position(
            client,
            state,
            position,
            f"第一段保護：ROE 曾達 {PROTECTION_ACTIVATION_ROE_PCT}% 且回落至 {roe:.2f}% ≤ {PROTECTION_FLOOR_ROE_PCT}%",
        )
        return

    log_event(
        "POSITION_MONITOR",
        "持倉監控中。",
        symbol,
        direction=position.get("positionSide"),
        avg_price=position.get("avgPrice"),
        mark_price=position.get("markPrice"),
        roe_pct=f"{roe:.2f}",
        unrealized_pnl=position.get("unrealizedPnL"),
        peak_roe_pct=risk.peak_roe_pct,
        protection_activated=risk.protection_activated,
        reached_lock_profit_peak=risk.reached_lock_profit_peak,
    )


def reset_daily_counter_if_needed(state: BotState) -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    if state.trade_day_utc != today:
        state.trade_day_utc = today
        state.trades_today = 0
        save_state(state)


def scan_for_entry(client: PionexClient, state: BotState) -> None:
    """掃描成交額前 N 合約，在第一個合格訊號上進行唯讀預檢與開倉模擬。"""
    now_epoch = int(time.time())
    if now_epoch - state.last_scan_epoch < SCAN_COOLDOWN_SECONDS:
        return
    state.last_scan_epoch = now_epoch
    save_state(state)

    candidates = client.top_tradable_usdt_perps(SCAN_TOP_N)
    log_event(
        "SCAN_START",
        f"開始掃描 24h 成交額前 {len(candidates)} 個可交易 USDT 永續合約。",
        candidate_count=len(candidates),
        interval=KLINE_INTERVAL,
    )

    for rank, (symbol, _symbol_info, amount) in enumerate(candidates, start=1):
        try:
            candles = completed_candles(client, symbol)
            closed_time = int(candles.iloc[-1]["time"])
            if state.last_processed_candles.get(symbol) == closed_time:
                continue

            result = breakout_signal(candles)
            state.last_processed_candles[symbol] = closed_time
            save_state(state)
            log_event(
                "SIGNAL",
                f"已完成 K 線訊號：{result.signal}。",
                symbol,
                rank_by_24h_amount=rank,
                amount_24h=decimal_string(amount),
                closed_candle_time=closed_time,
                close=decimal_string(result.close),
                upper_band=decimal_string(result.upper_band),
                lower_band=decimal_string(result.lower_band),
                rsi=f"{result.rsi:.2f}",
            )

            if result.signal in ("LONG", "SHORT"):
                if open_position(client, state, symbol, closed_time, result.signal):
                    # 單一活動倉位設計：本輪只處理第一個確實送出或模擬的訊號。
                    return
        except Exception as exc:
            log_event("SCAN_SYMBOL_ERROR", f"掃描此交易對時已跳過：{exc}", symbol, rank_by_24h_amount=rank)

    log_event("SCAN_COMPLETE", "本輪沒有可執行的突破訊號。")


def run_once(client: PionexClient, state: BotState) -> list[dict[str, Any]]:
    reset_daily_counter_if_needed(state)
    ensure_account_preflight(client)

    positions = active_positions(client)
    if positions:
        if len(positions) > 1:
            log_event(
                "MULTIPLE_POSITIONS",
                "偵測到多筆活動持倉；依安全限制只進行各倉風控，禁止任何新開倉。",
                active_position_count=len(positions),
            )
        for position in positions:
            symbol = str(position.get("symbol", ""))
            # 狀態遺失、手動建立或其他程式建立的倉位都不應由本程式平倉。
            # 此時僅封鎖新倉並要求使用者在派網自行檢查，避免跨策略干擾。
            if position_state_key(position) not in state.position_risk:
                log_event(
                    "UNMANAGED_POSITION",
                    "偵測到未由本程式記錄的活動倉位；已停止新開倉且不會自動平倉此倉位。",
                    symbol,
                    position_id=position.get("positionId"),
                )
                continue
            try:
                monitor_position(client, state, position)
            except Exception as exc:
                log_event("POSITION_MONITOR_ERROR", f"此持倉風控發生錯誤：{exc}", symbol)
        return positions

    scan_for_entry(client, state)
    return []


def main() -> None:
    if LEVERAGE <= 0:
        raise RuntimeError("LEVERAGE 必須大於 0。")
    if SCAN_TOP_N < 1 or KLINE_LIMIT < 30 or LOOP_SECONDS < 1 or SCAN_COOLDOWN_SECONDS < 1:
        raise RuntimeError("SCAN_TOP_N、KLINE_LIMIT、LOOP_SECONDS、SCAN_COOLDOWN_SECONDS 的設定值無效。")

    client = PionexClient(API_KEY, API_SECRET)
    state = load_state()
    monitor_reporter = MonitorTelemetryReporter()
    log_event(
        "START",
        "多幣 Breakout 執行器啟動；目前模式："
        + (
            "實盤設定已啟用，但派網 Public Trade API 的直接 USDT 永續合約下單已被安全封鎖；"
            "僅掃描與監控，待遷移至 Bot API 或 Signal Bot。"
            if LIVE_TRADING and not DIRECT_FUTURES_ORDERING_SUPPORTED
            else ("實盤" if LIVE_TRADING else "唯讀")
        ),
        mode=("LIVE_DIRECT_ORDERS_BLOCKED" if LIVE_TRADING and not DIRECT_FUTURES_ORDERING_SUPPORTED
              else ("LIVE" if LIVE_TRADING else "READ_ONLY")),
        direct_futures_orders_supported=DIRECT_FUTURES_ORDERING_SUPPORTED,
        leverage=decimal_string(LEVERAGE),
        scan_top_n=SCAN_TOP_N,
        stop_roe_pct=decimal_string(STOP_ROE_PCT),
        protection_activation_roe_pct=decimal_string(PROTECTION_ACTIVATION_ROE_PCT),
        protection_floor_roe_pct=decimal_string(PROTECTION_FLOOR_ROE_PCT),
        lock_profit_peak_roe_pct=decimal_string(LOCK_PROFIT_PEAK_ROE_PCT),
        lock_profit_exit_roe_pct=decimal_string(LOCK_PROFIT_EXIT_ROE_PCT),
    )
    startup_mode = (
        "實盤設定已啟用，但直接永續合約下單已封鎖"
        if LIVE_TRADING and not DIRECT_FUTURES_ORDERING_SUPPORTED
        else ("實盤" if LIVE_TRADING else "唯讀")
    )
    startup_policy = (
        "不會呼叫派網直接下單／平倉端點；待遷移至 Bot API 或 Signal Bot。"
        if LIVE_TRADING and not DIRECT_FUTURES_ORDERING_SUPPORTED
        else "每日實盤開倉次數：不限制（仍維持單一活動倉位與 ROE 風控）"
    )
    send_telegram(
        f"[派網機器人啟動] 模式：{startup_mode}\n"
        f"掃描：前 {SCAN_TOP_N} 個 USDT 永續合約\n"
        f"設定槓桿：{LEVERAGE}x\n"
        f"{startup_policy}"
    )
    monitor_reporter.start()

    while True:
        try:
            positions = run_once(client, state)
            monitor_reporter.submit_loop_snapshot(state, positions)
        except Exception as exc:
            LOG.exception("迴圈錯誤")
            log_event("ERROR", str(exc))
            if LIVE_TRADING:
                send_telegram(f"[派網機器人錯誤] {str(exc)[:800]}")
        time.sleep(LOOP_SECONDS)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="派網多幣 Breakout 執行器")
    parser.add_argument(
        "--telegram-test",
        action="store_true",
        help="只測試 Telegram 通知；不讀取派網帳戶、不掃描市場、不會下單。",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.telegram_test:
        if send_telegram("[派網機器人] Telegram 通知測試成功；未連線派網、未掃描市場、未送出訂單。"):
            LOG.info("Telegram 測試訊息已送出。")
        else:
            raise SystemExit("Telegram 測試失敗；請確認 TELEGRAM_ENABLED、Bot Token 與 Chat ID。")
    else:
        main()
