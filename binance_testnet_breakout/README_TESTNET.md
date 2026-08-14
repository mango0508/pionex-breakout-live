# Binance Futures Demo/Testnet：BTC 5 分 K Breakout

> **安全範圍：** 此資料夾是與 Pionex 專案隔離的 Binance USDⓈ-M Futures Demo/Testnet 驗證器。程式只允許官方目前的 `https://demo-fapi.binance.com`，舊 Testnet URL、任何主網端點與其他網址都會直接拒絕。初始設定為 `TESTNET_TRADING=false`，因此只讀取公開 K 線並輸出 DRY_RUN 事件，不會下 Demo/Testnet 訂單。

## 保留的策略規則

| 項目 | 設定 |
|---|---:|
| 交易對 | BTCUSDT（USDⓈ-M Futures Demo/Testnet） |
| K 線 | 5 分鐘，僅使用已收盤 K 線 |
| 進場 | 布林通道 20／2 + RSI 14；突破上軌且 RSI ≥ 55 做多，跌破下軌且 RSI ≤ 45 做空 |
| 保證金與槓桿 | 50 USDT、5×；約 250 USDT 名義價值 |
| 倉位 | 單一倉位，不加碼 |
| 出場 | ROE ≤ -8% 停損；達 +10% 後跌回 +5% 退出；曾達 +15% 後跌回 +10% 退出 |

## Demo/Testnet 倉位同步與手動平倉

當 `TESTNET_TRADING=true` 時，程式每一輪會先向 **Demo/Testnet** 查詢 BTCUSDT 的實際持倉，再決定是否執行風控或尋找新訊號。這讓本機狀態檔不會凌駕交易所狀態。

| Demo/Testnet 帳戶狀態 | 程式行為 |
|---|---|
| 本機有倉位，但您已在 Demo/Testnet 網站手動完整平倉 | 清除本機持倉，記錄 `EXCHANGE_POSITION_CLOSED_EXTERNALLY`，下一輪可繼續找新訊號。 |
| 本機沒有倉位，但 Demo/Testnet 帳戶已有 BTCUSDT 持倉 | 採用交易所的方向、均價與數量，記錄 `EXCHANGE_POSITION_ADOPTED`，不會再疊加開倉。 |
| 您手動部分平倉或調整數量 | 以交易所數量更新本機狀態，並保留同方向倉位已觸發的保護／鎖利紀錄。 |
| `TESTNET_TRADING=false` 的唯讀掃描 | 不讀取私密倉位，也不需要 API Key；程式只抓公開 K 線。 |

若您在 Demo/Testnet 網站手動做了**反向開倉**，程式會以新方向重新建立本機風控狀態；這是為了避免沿用舊方向的追蹤停利旗標。請避免在機器人運行時同時手動建立新倉位，以免混淆策略驗證結果。

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

## 讀取 Demo/Testnet K 線的乾跑模式

乾跑模式不需要 API Key，也不需要先建立 `.env`。直接執行：

```powershell
python binance_testnet_breakout.py --once
```

成功時會顯示 `SIGNAL`。出現 `DRY_RUN_ENTRY_LONG` 或 `DRY_RUN_ENTRY_SHORT` 時，只代表策略算出可進場訊號；因為乾跑模式，程式不會送出任何 API 下單請求。

若您已經建立 `.env`，請確認其中的 `BINANCE_TESTNET_BASE_URL` 是 `https://demo-fapi.binance.com`；程式會拒絕舊網址 `https://testnet.binancefuture.com`，以避免新建的 Demo API Key 被誤送往錯誤環境。

## 需要使用者明確確認後才能進行的 Testnet 動作

1. 在 Binance Demo Trading 建立**專用的 Demo API Key**。
2. 將 Key 與 Secret 存到本機 `.env`，而非貼到聊天、GitHub 或任何網站。
3. 將 `TESTNET_TRADING` 改為 `true`。
4. 送出第一筆 Testnet 訂單，並確認倉位、手動平倉同步與風控退出。

即使是 Demo/Testnet，第一筆訂單也需要使用者再確認。此程式不支援且不允許切換成真實資金 URL。

## 官方參考

* [Binance Futures Demo Trading FAQ](https://www.binance.com/en/support/faq/detail/9be58f73e5e14338809e3b705b9687dd)
* [USDⓈ-M Futures API General Info（含官方 Demo/Testnet REST 網域）](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/general-info)
