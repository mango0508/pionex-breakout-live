# 派網官方合約執行遷移方案

**更新日期：2026-08-15**  
**狀態：直接 Public Trade API 合約下單已停止；尚未建立新的自動執行器。**

> 派網客服已確認，一般帳戶目前無法透過 Public Trade API 直接進行 USDT 永續合約下單，且沒有白名單或名額候補流程。本文件只規劃改用官方支援的機器人路線；不會繞過平台限制。

## 1. 目前程式的安全狀態

原本的 Python 程式仍可使用公開市場資料掃描前 30 個 USDT 永續合約、計算布林通道與 RSI、寫入日誌、發送 Telegram 通知，以及將去敏感化狀態上傳至私人監控網站。不過，任何直接建立或平倉永續合約的 Public Trade API 呼叫均已在程式內硬性封鎖。

即使 `.env` 仍為 `LIVE_TRADING=true`，新版亦只會掃描與監控，不會呼叫直接開倉、`reduceOnly` 平倉或調整槓桿端點。這個設計避免在平台未支援時誤以為策略正在實盤交易。

## 2. 官方路線比較

| 路線 | 官方可用功能 | 與既有 Breakout 的相容性 | 必要條件 | 結論 |
|---|---|---|---|---|
| **Signal Bot + TradingView** | 將 TradingView strategy alert 透過 Pionex webhook 交由 Futures Signal Bot 執行 | **最高**。可表達 LONG、SHORT、平倉與反向訊號；但一個 Signal Bot 同時只支援一個交易對。 | Pionex Futures／Signal Bot 存取、可驗證的 TradingView strategy、TradingView webhook 功能。 | **建議優先評估。** |
| **Bot API Futures Grid** | 用 API 建立、查詢、調整、減倉與取消 Futures Grid Bot | **低**。Futures Grid 是區間網格，不能等價重現「前 30 個標的掃描＋單次突破進場＋ROE 追蹤止盈」。 | API Key 的 Bot reading 與 Bot trading 權限。 | 只在使用者願意改採網格策略時考慮。 |
| **Python → custom signal listener** | Python 將自訂訊號送至官方 Signal listener | **理論上最高**，可保留 Python 掃描器；但目前不應假設可直接使用。 | 一般讀取權限外，帳戶還需 Pionex 開啟 Signal sending access。 | 只有在 Pionex 明確授予 custom signal sending access 後才研究實作。 |

Signal Bot 是派網官方為外部策略訊號設計的 Futures 執行器；官方流程是先在 Pionex 建立 signal，再將 Pionex 產生的 webhook URL 與訊息模板放入 TradingView strategy alert。[1] Futures Grid Bot API 則提供價格區間、網格數、趨勢與槓桿等參數的建立與驗證接口，但其交易模型本質上不同於單次突破策略。[2]

## 3. 建議的最小可行驗證：Signal Bot 路線

此方案並不會立刻恢復自動實盤交易。第一階段先將既有 Breakout 邏輯轉為**單一交易對**的 TradingView Pine Script `strategy`，只確認圖表上的 LONG、SHORT、出場訊號是否與既有 Python 規則一致。因為派網要求 Signal Bot 連接可在 TradingView Strategy Tester 中驗證的 strategy，因此指標版本不足以直接用於 webhook。[1]

第二階段只建立 Signal 與 TradingView alert，**先不要啟用有效的實盤 Signal Bot**。使用 TradingView 與 Pionex 的 Signal Log 比對訊號時間、標的、方向、進出場與重複訊號，確認訊息送達並由派網正確解析。TradingView 策略輸入值變更後，官方要求重新建立 alert，否則 alert 仍會使用舊參數。[3]

第三階段由使用者自行確認平台上的 Signal Bot 風控設定，包括標的、槓桿上限、保證金、單次曝險、最大虧損與是否由 Pionex 或 Pine Script 管理停損／停利。官方警告兩邊的 TPSL 誰先觸發就會執行，因此同一保護規則不應在兩邊重複控制。[1]

最後才在使用者確認後啟用**單一標的、單一 Signal Bot**。此階段仍不能保證成交、利潤或策略表現；訊號可能因 webhook、可用保證金、交易對、持倉模式或平台規則而被拒絕。[3]

## 4. 既有策略哪些部分可遷移

| 既有規則 | Signal Bot 遷移方式 | 需要重新驗證的原因 |
|---|---|---|
| 布林通道 20 期 + RSI 14 期確認 | 在 Pine Script strategy 中重建 LONG／SHORT 條件 | TradingView 的資料來源、K 線收線時機與 Python `pandas` 計算可能有差異。 |
| 5 分 K 收線才判斷 | 以 strategy 的已確認 K 線條件與 alert 設定實作 | 必須避免未收線 K 棒觸發造成 repaint／重複訊號。 |
| 單一活動倉位 | 在 Signal Bot 及 Pine strategy 設定中限制 pyramiding 或建立明確的持倉狀態 | Pionex Signal Bot 的持倉模式與策略訊號需一致。 |
| -8% ROE 停損 | 在**單一來源**設定風控：Pionex Signal Bot 或 strategy 訊號其一 | 避免雙重 TPSL 互相覆蓋。 |
| +10%／+15% 兩段式追蹤鎖利 | 以 Pine strategy 的狀態與 `strategy.exit` 邏輯表達，並與 Pionex 設定擇一管理 | 需要用歷史與前向測試檢查回落判斷是否與原 Python 規則一致。 |
| 前 30 個熱門合約掃描 | 暫時不直接遷移 | 一個 Signal Bot 一次只處理一個交易對；多標的會需要多組 Signal Bot／alert，增加設定與風控複雜度。 |
| 階梯保證金 50 → 6400 | 暫時不直接遷移 | Signal Bot 的部位大小語意與平台保證金模型不同，不能直接沿用數字。 |

## 5. 使用者需要先決定的事項

請在開始任何新實盤自動化前，先明確選擇下列其中一項。

| 選項 | 代表的下一步 | 本機 Python 程式的角色 |
|---|---|---|
| **A. 保持現況：只掃描與監控** | 不建立新的交易執行路徑。 | 前 30 掃描、日誌、Telegram、雲端監控。 |
| **B. 改用 Signal Bot（建議）** | 先製作與回測 BTC 單一標的的 Pine Script strategy，再做無下單訊號驗證。 | 僅作為參考掃描／監控來源；不直接下單。 |
| **C. 改用 Futures Grid Bot API** | 接受策略改為區間網格，先只驗證 API 參數，不建立 bot。 | 將舊 Breakout 策略停止作為執行規則。 |
| **D. 申請 custom signal sending access** | 先取得 Pionex 明確書面確認，再設計 Python 訊號轉接層。 | 可能保留掃描與訊號引擎，但不得在核准前呼叫 listener。 |

## 6. 安全與隱私規則

請不要把 API Key、API Secret、Signal Bot webhook URL、Telegram Token、雲端監控 Token 或完整 IP 白名單貼入聊天、程式碼庫或截圖。新的 Pionex webhook URL 應視同交易控制憑證處理。

任何具備資產控制效果的設定，例如啟用 Signal Bot、建立 Futures Grid Bot、修改槓桿或儲存 webhook，均應由使用者親自在 Pionex／TradingView 頁面完成並確認。新的整合完成前，仍要保留可手動關閉 Signal Bot／平倉的操作程序。

## References

[1] [Pionex Signal Bot — Help Center](https://support.pionex.com/hc/en-us/articles/52606266734105-Signal-Bot)

[2] [Pionex Futures Grid — Bot API Docs](https://www.pionex.com/docs/api-docs/bot-api/futures-grid)

[3] [Pionex Signal Bot and TradingView Tutorial](https://www.pionex.com/blog/signal-bot-and-tradingview-tutorial/)

[4] [Pionex Signal — Bot API Docs](https://www.pionex.com/docs/api-docs/bot-api/signal)

[5] [Pionex Bot API Authentication and Permissions](https://www.pionex.com/docs/api-docs/bot-api/general-info/authentication)
