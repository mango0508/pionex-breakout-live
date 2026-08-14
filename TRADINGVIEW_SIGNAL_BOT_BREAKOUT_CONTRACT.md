# BTC 5 分 K Breakout → TradingView Strategy 規則契約

**用途：** 這份契約定義既有 Python Breakout 程式與第一版 TradingView Pine Script strategy 的對應關係。它只用於 **BTC 單一標的的圖表回測與訊號核對**，不包含 webhook URL，也不會觸發任何派網實盤下單。

## 固定測試環境

| 項目 | 第一版固定值 | 理由 |
|---|---:|---|
| TradingView 商品 | `PIONEX:BTC.PERP_USDT`（若圖表代碼不同，請選派網 BTC USDT 永續合約） | 必須使用與派網 Signal Bot 相同的合約商品，不能用 BTC 現貨替代。 |
| 圖表週期 | **5 分鐘** | 對應 Python `.env` 的 `KLINE_INTERVAL=5M`。 |
| 同時持倉 | 一筆 | 對應 Python 偵測到任一活動倉位就不開新倉的安全規則。 |
| 訊號時點 | 收線確認後 | Python 明確排除進行中的最後一根 K 線；Pine 只在 `barstate.isconfirmed` 時建立或關閉策略單。 |
| 執行模式 | Strategy Tester、無 webhook | 首階段的唯一目的，是核對圖上的訊號與出場邏輯。 |

## 入場條件對照

| 規則 | Python 實作 | Pine 第一版對應 |
|---|---|---|
| 布林中軌 | 最近 20 根已完成 K 線的收盤價 SMA | `ta.sma(close, 20)` |
| 布林上下軌 | 中軌 ± 2 × 母體標準差（`ddof=0`） | `ta.stdev(close, 20)`；TradingView 的 `ta.stdev` 使用對應的母體標準差模式。 |
| RSI | 14 期 Wilder RSI | `ta.rsi(close, 14)` |
| 做多 | 收盤價嚴格高於上軌，且 RSI ≥ 55 | `close > upperBand and rsi >= 55` |
| 做空 | 收盤價嚴格低於下軌，且 RSI ≤ 45 | `close < lowerBand and rsi <= 45` |
| 無訊號 | 其他全部情況 | 不產生進場單。 |

同一根已確認 K 線同時不能合理地高於上軌又低於下軌；因此做多與做空條件互斥。Pine 策略也會要求策略目前為平倉，避免在相同方向或反向持倉上疊加部位。

## ROE 風控對照

Python 是以派網回傳的 `unrealizedPnL / initialMargin × 100` 作為 ROE。對於 5× 槓桿、忽略手續費、資金費率、滑點與保證金模式差異的圖表回測，Pine 可用下列估算：

```text
long ROE  ≈ (close / entryPrice - 1) × 100 × 5
short ROE ≈ (entryPrice / close - 1) × 100 × 5
```

| Python 既有規則 | Pine 第一版對應 | 注意事項 |
|---|---|---|
| ROE ≤ -8% 硬停損 | 估算 ROE ≤ -8 時 `strategy.close` | 原程式每 10 秒看派網未實現損益；Pine 第一版只在 5 分 K 收線確認，**不是逐秒等價**。 |
| ROE ≥ +10% 啟動保護 | 將 `protectionActivated` 設為 `true` | 只記錄狀態，不立即出場。 |
| 已啟動保護後，ROE 回落至 ≤ +5% | `strategy.close` | 入場後狀態由 Pine 的 `var` 狀態旗標保存。 |
| ROE 曾達 ≥ +15% | 將 `reachedLockProfitPeak` 設為 `true` | 不立即出場。 |
| 曾達 +15% 後，ROE 回落至 ≤ +10% | `strategy.close` | 此條件優先於 +5% 保護線，原因文字會區分。 |

> **重要限制：** Python 版本使用派網的實際 `initialMargin` 與未實現 PnL；TradingView strategy 只以圖表收盤價與固定 5× 做回測估算。因此回測結果不可視為實際成交、實際 ROE 或未來收益預測。

## 不會在第一版遷移的功能

前 30 個交易對掃描、階梯保證金 50 至 6400 USDT、派網 API 持倉核對、直接調整槓桿、直接市價單與 `reduceOnly` 平倉均**不**會放入第一版 Pine strategy。Signal Bot 一次只處理一個交易對；第一版刻意固定 BTC，以降低設定、風控與訊號追查複雜度。

## 完成條件

只有在以下條件都完成後，才可進入下一步的 Signal Bot 設定核對：

1. 策略被加入派網 BTC 永續合約的 5 分鐘圖表，且 Strategy Tester 可正常產生交易清單。
2. 使用者抽查至少五筆圖上進場／出場，確認均發生在收線後且符合本文件規則。
3. 未建立有效的 Pionex webhook alert，也未啟用會影響資產的 Signal Bot。
4. 使用者明確確認要進行「訊號送達驗證」後，才會建立下一階段的 alert 設定。
