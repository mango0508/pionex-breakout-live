# Binance Futures Testnet：BTC 5 分 K Breakout

> **安全範圍：** 此資料夾是與 Pionex 專案隔離的 Binance USDⓈ-M Futures Testnet 驗證器。程式只允許 `https://testnet.binancefuture.com`，任何主網端點都會直接拒絕。初始設定為 `TESTNET_TRADING=false`，因此只讀取公開 K 線並輸出 DRY_RUN 事件，不會下 Testnet 訂單。

## 保留的策略規則

| 項目 | 設定 |
|---|---:|
| 交易對 | BTCUSDT（USDⓈ-M Futures Testnet） |
| K 線 | 5 分鐘，僅使用已收盤 K 線 |
| 進場 | 布林通道 20／2 + RSI 14；突破上軌且 RSI ≥ 55 做多，跌破下軌且 RSI ≤ 45 做空 |
| 保證金與槓桿 | 50 USDT、5×；約 250 USDT 名義價值 |
| 倉位 | 單一倉位，不加碼 |
| 出場 | ROE ≤ -8% 停損；達 +10% 後跌回 +5% 退出；曾達 +15% 後跌回 +10% 退出 |

## Testnet 倉位同步與手動平倉

當 `TESTNET_TRADING=true` 時，程式每一輪會先向 **Testnet** 查詢 BTCUSDT 的實際持倉，再決定是否執行風控或尋找新訊號。這讓本機狀態檔不會凌駕交易所狀態。

| Testnet 帳戶狀態 | 程式行為 |
|---|---|
| 本機有倉位，但您已在 Testnet 網站手動完整平倉 | 清除本機持倉，記錄 `EXCHANGE_POSITION_CLOSED_EXTERNALLY`，下一輪可繼續找新訊號。 |
| 本機沒有倉位，但 Testnet 帳戶已有 BTCUSDT 持倉 | 採用交易所的方向、均價與數量，記錄 `EXCHANGE_POSITION_ADOPTED`，不會再疊加開倉。 |
| 您手動部分平倉或調整數量 | 以交易所數量更新本機狀態，並保留同方向倉位已觸發的保護／鎖利紀錄。 |
| `TESTNET_TRADING=false` 的唯讀掃描 | 不讀取私密倉位，也不需要 API Key；程式只抓公開 K 線。 |

若您在 Testnet 網站手動做了**反向開倉**，程式會以新方向重新建立本機風控狀態；這是為了避免沿用舊方向的追蹤停利旗標。請避免在機器人運行時同時手動建立新倉位，以免混淆策略驗證結果。

## 第一次離線驗證

請在本機命令列進入這個資料夾，再安裝依賴並執行測試：

```powershell
cd C:\Users\UserPC_01\Desktop\pionex-breakout-live\binance_testnet_breakout
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m unittest -v
```

測試完全離線，不需要 Binance API Key。

## 讀取 Testnet K 線的乾跑模式

將 `.env.example` 複製為 `.env`，維持 `TESTNET_TRADING=false`，然後執行：

```powershell
python binance_testnet_breakout.py --once
```

成功時會顯示 `SIGNAL`。出現 `DRY_RUN_ENTRY_LONG` 或 `DRY_RUN_ENTRY_SHORT` 時，只代表策略算出可進場訊號；因為乾跑模式，程式不會送出任何 API 下單請求。

## 需要使用者明確確認後才能進行的 Testnet 動作

1. 在 Binance Demo Trading 建立**專用的 Demo API Key**。
2. 將 Key 與 Secret 存到本機 `.env`，而非貼到聊天、GitHub 或任何網站。
3. 將 `TESTNET_TRADING` 改為 `true`。
4. 送出第一筆 Testnet 訂單，並確認倉位、手動平倉同步與風控退出。

即使是 Testnet，第一筆訂單也需要使用者再確認。此程式不支援且不允許切換成真實資金 URL。

## 官方參考

* [Binance Futures Demo Trading FAQ](https://www.binance.com/en/support/faq/detail/9be58f73e5e14338809e3b705b9687dd)
* [USDⓈ-M Futures REST API](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/trade)
