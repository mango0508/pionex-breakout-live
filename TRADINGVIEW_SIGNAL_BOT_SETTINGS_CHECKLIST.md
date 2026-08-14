# BTC 5M Breakout：TradingView 與 Pionex Signal Bot 設定核對表

> **狀態：僅供回測與非活動設定驗證。** 本文件不包含派網 Message、Webhook URL、API Key 或任何可直接操作帳戶的資訊。

派網官方將 TradingView 策略的 `Order size` 解讀為 **Signal Bot 資金使用率**，而不是獨立存入 TradingView 的真實 USDT。官方要求 `Initial capital` 維持 100，並將 1–100 USDT 的訂單大小轉成 Signal Bot 資金的 1%–100% 使用率。[1]

## 正確設定

| 設定位置 | 欄位 | 正確值 | 為何如此設定 |
|---|---|---:|---|
| TradingView 策略屬性 | Initial capital | **100** | 派網官方指定此欄維持 100；它是策略訊號的比例基準，並非合約帳戶實際餘額。 |
| TradingView 策略屬性 | Base currency | **Default** | 依派網官方建議。 |
| TradingView 策略屬性 | Order size | **100 USDT** | 表示每個訊號使用 Signal Bot 資金的 **100%**。 |
| TradingView 策略屬性 | Pyramiding | **1** | 禁止同方向加碼；同時僅允許一筆 BTC 倉位。 |
| TradingView 策略屬性 | Margin for long／short | **0** | 依派網官方建議，實際槓桿由 Signal Bot 設定控制。 |
| Pionex（最終啟用頁） | Investment | **50 USDT** | 使用者已確認的單筆保證金／Bot 資金。 |
| Pionex（最終啟用頁） | Leverage | **5×** | 使用者已確認。 |
| Pionex（最終啟用頁） | 額外固定 TP／SL | **停用** | 出場由已驗證的 Pine ROE 規則發送平倉訊號；同時啟用兩組 TP／SL 可能先後衝突。 |

以這組設定為例，Signal Bot 投資額為 50 USDT、槓桿為 5×，可用名義倉位約為 250 USDT。TradingView 的 Order size = 100 表示使用該 Signal Bot 資金的 100%，也就是對應 50 USDT 保證金的完整單筆倉位；若填 50，則只使用 50% 資金，即約 25 USDT 保證金。[1]

## 保留的策略風控

| 事件 | Pine 草稿處理 |
|---|---|
| 做多 | 5 分 K 收線高於布林上軌且 RSI ≥ 55。 |
| 做空 | 5 分 K 收線低於布林下軌且 RSI ≤ 45。 |
| 同時持倉 | 僅在無持倉時開倉；沒有 DCA，也不以反向訊號直接翻倉。 |
| 硬停損 | 5 分 K 收線估算 ROE ≤ -8% 時發出全數平倉訊號。 |
| 第一段保護 | 曾達估算 ROE +10% 後，回落至 +5% 時全數平倉。 |
| 第二段鎖利 | 曾達估算 ROE +15% 後，回落至 +10% 時全數平倉。 |

> Pine 的 ROE 是以 5 分 K 收盤價與固定 5× 的估算值，不含實際滑點、手續費、資金費率與派網保證金模式差異。因此它用於策略一致性驗證，不保證實盤成交結果或報酬。

## 目前不應進行的操作

完成上述屬性核對前，請勿建立 TradingView Alert、勿在 Pine 的 `Pionex Message` 欄位填入派網資料、勿貼入 Webhook URL，亦勿按 Pionex 的 `Automate signal` 或 `Create the bot`。這些步驟會留到回測設定與出場邏輯驗證完成，且必須在最終逐項確認後才進行。

## 參考資料

[1]: https://support.pionex.com/hc/en-us/articles/52606266734105-Signal-Bot "Pionex Help Center — Signal Bot"
