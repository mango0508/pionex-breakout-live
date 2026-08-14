# Pionex Signal Bot 實盤前置核對紀錄

核對時間：2026-08-15（使用者登入的派網網頁，只讀檢視）

## 已確認帳戶狀態

| 項目 | 觀察結果 | 對實盤準備的意義 |
|---|---:|---|
| 合約帳戶可用 USDT | 60.00 USDT | 足以覆蓋使用者指定的單筆 50 USDT 保證金，但僅餘約 10 USDT 緩衝，需在啟用前再次確認。 |
| PUSD | 573,742.38 PUSD | 此為模擬資產，不能視為實盤保證金。 |
| 當前合約持倉 | 無 | 可避免 Signal Bot 設定時與既有倉位混淆。 |
| 合約帳戶權益 | 1,892.15 TWD | 僅供介面顯示，不作為程式風控的 USDT 餘額依據。 |

## 已確認的實盤參數（使用者確認）

- 商品：BTC USDT 永續合約。
- 週期：5 分鐘。
- 單筆保證金：50 USDT。
- 槓桿：5 倍。
- 風控規則：ROE -8% 硬停損；ROE +10% 啟動 +5% 保護；曾達 +15% 後，ROE 回落至 +10% 平倉。

## 安全邊界

本紀錄不含 API Key、Secret、Webhook URL、TradingView 帳戶資訊或派網帳戶識別資訊。它僅用於後續在最後啟用前，重新核對資金、商品、保證金、槓桿與風控設定。

## 派網官方 Signal Bot 前置條件（2026-08-15 查核）

來源：[Pionex Signal Bot Help Center](https://support.pionex.com/hc/en-us/articles/52606266734105-Signal-Bot) 及 [Pionex Signal Bot + TradingView tutorial](https://www.pionex.com/blog/signal-bot-and-tradingview-tutorial/)。

- Signal Bot 會把 TradingView 的 webhook 警報轉為派網期貨實盤交易；它不是一般 Public Trade API 的直接下單功能。
- TradingView 需要 Essential 或更高方案才能使用 webhook 警報。
- 建立順序為：派網新增 Signal listener → 將派網提供的訊息／webhook 套用至 Pionex 相容的 TradingView strategy → 在 TradingView 建立警報 → 在派網以「Automate signal」建立 Signal Bot。
- 策略輸入、週期或風控參數改變後，官方要求重建 TradingView 警報，因警報會保留建立時的策略設定。
- 一個 Signal Bot 同一時間只支援一個交易對；訊號已接收但 Bot 不活動時，派網會忽略訊號。
- 官方對 100 USDT 策略回測資金建議 1–100 USDT 的策略訂單大小；50 USDT 對應 Signal Bot 資金的 50% 使用率。實盤建立頁的實際投資額與槓桿仍須在最終確認時逐項核對。
- 官方提醒 Signal Bot 的 TradingView 訊號與 Bot 內建 TPSL 以先觸發者為準；為避免規則衝突，啟用時只能選定一套出場邏輯。

## 官方相容策略與實盤串接限制（2026-08-15 補充）

來源：[Pionex Signal Bot Help Center](https://support.pionex.com/hc/en-us/articles/52606266734105-Signal-Bot) 與 [Signal Bot + TradingView tutorial](https://www.pionex.com/blog/signal-bot-and-tradingview-tutorial/)。

- 現有 `BTC_5M_Breakout_SignalBot_Validation.pine` 是**回測專用**，刻意不含派網 Signal Bot toolkit 產生的 `Pionex Message` 欄位與相容警報訊息；不能直接把它的回測 alert 連到實盤。
- 官方要求先使用 Pionex Signal Bot toolkit 把已驗證的指標條件轉為「Pionex-compatible strategy」，再把派網產生的 Message 填入策略輸入欄。
- 相容策略在 TradingView 的預設下單量應使用 `strategy.cash` 的 1–100 USDT 範圍；官方定義 50 USDT 策略下單量對應 Signal Bot 資金的 50% 使用率，不等同於直接將 50 USDT 當作固定保證金。
- 一旦完成策略輸入設定、pair、資金或槓桿調整，TradingView 警報必須刪除後重建，因警報會保存建立當刻的 strategy 參數。
- 在 TradingView 警報建立頁必須使用派網提供的 webhook URL，並保留策略預設 JSON Message；URL 與 JSON Message 都視為敏感資料，不寫入本地文件或聊天室。
- 最終建立 Signal Bot 時，必須逐項核對 pair、投資金額、槓桿、position mode、strategy 訂單大小與出場規則是否相容。只有在最後「Create the bot」前取得使用者明確確認，才可進行建立操作。

## 官方 toolkit 與訊號生命週期的額外要求（2026-08-15）

來源：[Pionex Signal Bot Help Center](https://support.pionex.com/hc/en-us/articles/52606266734105-Signal-Bot)（2025-11-20 更新）與 [Pionex Signal Bot + TradingView tutorial](https://www.pionex.com/blog/signal-bot-and-tradingview-tutorial/)（2026-08-04 最後審閱）。

- 派網官方相容策略產生器（`pionex-signal-bot-toolkit.html`）目前透過官方 Telegram 群組的置頂訊息提供；此工具須將策略的完整、已移除衝突變數與現有 alert 程式碼的 Pine 內容，以及 Long/Short 條件分別輸入後產生相容策略。
- Toolkit 產出的策略才會包含派網需要的訊息欄位；現有回測策略不可自行猜測 JSON、Webhook URL 或訊息格式。
- 官方策略設定要求：初始資金 100、訂單大小 1–100 USDT、base currency 預設、long/short margin 為 0。其例示中 50 USDT 的策略訂單代表使用 Signal Bot 資金 50% 的訊號份額。
- Signal listener 建立順序：Futures → Futures Bot → Signal Bot → Add signal；建立 listener 本身尚未建立活動交易 Bot。完成該頁後，官方介面會提供 Message 與 Webhook URL 供 TradingView 端使用。
- TradingView 端需在官方相容策略輸入欄填入 Message；建立 Alert 時維持平台生成的 JSON Message，並填入派網提供的 Webhook URL。建立或更新 alert 可傳送真實訊號，但沒有活動 Signal Bot 時派網會收到後忽略。
- 活動交易只會在 Pionex Signal Bot 頁面選擇 Automate signal 並最後按 Create the bot 後開始；這是需再次逐項取得確認的敏感操作。
- 官方提醒 Signal Bot 只允許同一時間一個交易對；使用者目標是 BTC USDT 永續，因此不得同時建立另一個同對 Signal Bot。

## 已建立但尚未啟用的 Signal listener 草稿（2026-08-15）

- 已在使用者登入的派網帳戶建立名稱為 `BTC 5M Breakout Signal` 的客製化 TradingView Signal listener；派網顯示「新增成功，請先完成 TradingView 訊號配置」。此動作尚未建立 Signal Bot、尚未指定實際投資額或槓桿，亦未送出任何交易委託。
- Listener 說明僅記載核對用策略摘要：BTC USDT 永續、5 分 K、布林通道 + RSI 突破、預計 50 USDT 投資額、5×、ROE -8% / +10% / +15%。不含任何 Message 或 Webhook 值。
- 派網 listener 設定頁面顯示：當同方向最大下單次數為 1 時，TradingView strategy 的初始資金須設為 100 USDT、訂單數量須設為 **100 USDT**、金字塔式下單為 1。這個 `100` 是訊號相對於 Signal Bot 投資額的百分比標尺：每個 TradingView 訊號交易 1 USDT，Signal Bot 就使用實際投資額的 1%。
- 因此，使用者最終在派網 Signal Bot 設為 **50 USDT 投資額、5× 槓桿** 時，需將官方相容 TradingView strategy 的訂單大小設為 **100 USDT**，才能讓單一入場訊號使用 50 USDT 的 100% 投資額。不可把 strategy 的 `100 USDT` 誤解為 100 USDT 的固定實際保證金。
- 尚未勾選「我已完成腳本配置」或「我已完成各幣種訊號推送配置」，因為官方 toolkit 產生的相容 Pine Script 與 TradingView webhook Alert 尚未完成；這可確保 listener 仍維持非活動狀態。

## 官方 toolkit 取得確認（2026-08-15）

- 已確認官方文件指定的 Telegram 公開訊息可見，網址為 <https://t.me/pionexapi/12832>；訊息顯示由已驗證的 **Pionex API Support** 管理者發布的 `pionex-signal-bot-toolkit.html` 檔案（顯示大小 45.8 KB）。
- 此檔案的用途是依官方文件將現有 Pine 指標與 Long/Short 條件轉換為派網相容策略。下載或開啟前仍須以公開訊息的檔名與來源身分核對，且不得把派網 listener 的 Message、Webhook URL 或任何帳密記錄到專案或聊天室。

## Toolkit 產出檢核與衍生回測草稿（2026-08-15）

- 使用者已完成官方 toolkit 的原始碼產生，並確認瀏覽器翻譯已關閉；最初輸出中的 `close`、`and`、`not` 被翻譯為中文而無法編譯，屬於翻譯功能破壞程式碼，不是策略條件錯誤。
- 官方模板預設為 `pyramiding=100`、`default_qty_value=10`、`maxDCAEntries=10`，並使用固定 1% Take Profit／1% Stop Loss。這與使用者指定的單一 BTC 倉位及 ROE -8%／+10%／+15% 風控不相容，因此不得直接用此預設版本建立 Alert 或 Signal Bot。
- 已建立 `tradingview/BTC_5M_Breakout_Pionex_SignalBot_ROE_Draft.pine` 作為**僅供 Strategy Tester 驗證**的衍生草稿。它不包含 Pionex Message、Webhook URL、API Key 或任何帳密；固定 `pyramiding=1` 與策略訂單大小 100 USDT（代表 Signal Bot 實際投資額的 100% 訊號份額），停用 DCA 與反向開倉，並保留原始 5 分 K 布林通道 + RSI 入場、ROE -8% 硬停損、+10% 後回落 +5% 及達 +15% 後回落 +10% 的收線估算出場規則。
- 此草稿仍需由使用者在 TradingView 的 Pionex BTC USDT 永續 5 分鐘圖上編譯、加入圖表並檢查 Strategy Tester；在該驗證完成前不可建立 Webhook Alert、不可填入 listener Message，也不可建立活動 Signal Bot。

## TradingView Strategy Tester 驗證結果（2026-08-15）

- 使用者已將 `BTC_5M_Breakout_Pionex_SignalBot_ROE_Draft.pine` 加到 **Pionex BTC USDT Perpetual、5 分鐘**圖表；編輯器未顯示 Pine 編譯錯誤，Strategy Tester 的 List of trades 已顯示 LONG／SHORT 實際回測交易。
- 使用者已將 Strategy Tester 的 Initial capital 設回 **100 USDT**。交易清單顯示約 **99.97–99.98 USDT** 的回測 size，與程式內 `default_qty_value = 100` 一致；此數字是派網 Signal Bot 的 100% 資金使用訊號比例，並非已送出的 100 USDT 實盤保證金。
- 程式內已直接固定 `pyramiding = 1`，入場僅在 `strategy.position_size == 0` 時發出，沒有 `strategy.entry` 的 DCA 邏輯或反向翻倉邏輯；因此同一時間只會產生一筆倉位訊號。
- 程式內估算 ROE 分別為：多單 `(close / avg_price - 1) × 100 × 5`，空單 `(avg_price / close - 1) × 100 × 5`。它在 5 分 K 收線時依序處理 **ROE ≤ -8%**、曾達 **+15%** 後回落至 **+10%**、以及曾達 **+10%** 後回落至 **+5%** 的全數平倉訊號。
- 截至此驗證，TradingView 未建立 Alert、Pine 的 Pionex Message 保持空白、派網僅有未活動的 listener 草稿，且沒有活動 Signal Bot、持倉或成交。下一步若建立 Alert，仍須先確認 Pionex Bot 端不存在活動 Bot，並在建立後以 TradingView／Pionex Signal Log 做無交易送達驗證。

## 非活動 Alert 設定中的安全檢核（2026-08-15）

- 使用者已重新授權其已登入的 TradingView 瀏覽器，並明確同意「僅建立非活動 Alert、驗證訊號送達」；此授權不涵蓋派網的 `Automate signal`、`Create the bot`、資金轉移或任何真實交易。
- TradingView 圖表已重新核對為 **Pionex BTC USDT Perpetual、5 分鐘**，已載入 `BTC 5M Breakout — Pionex Signal Bot ROE Draft`，且 Strategy Tester 顯示 100 USDT 初始資金與有效回測交易。
- 在 TradingView Alert 建立表單中，尚未建立價格 crossing Alert；必須改用上述策略的「Order fills／策略訂單成交」事件，並在建立前填入派網 listener 畫面提供的私密 webhook URL 與策略產生的訊息欄位。
- 私密 Webhook URL 僅透過派網介面的複製控制項暫存於使用者瀏覽器剪貼簿；本文件、Git 儲存庫與對話均不記錄其值。Alert 建立成功前不得按下任何 Pionex 活動 Bot 建立按鈕。
- 已在 TradingView Alert 表單將 Condition 由預設的價格 `Crossing` 切換為 **BTC 5M Breakout — Pionex Signal Bot ROE Draft** 策略；Interval 已保持「Same as chart / 5 minutes」，Message 已自動保留 `{{strategy.order.alert_message}}`。這可避免用價格條件替代策略訂單事件，且不會將 JSON 內容改寫為手動文字。
- 下一步僅需在 Alert 的 Webhook URL 欄位貼入派網 listener 的受控剪貼簿值，並在確認 Condition、Interval、Message 與 Webhook 已完整時建立 Alert。此步不會建立 Pionex 活動 Signal Bot。
- **2026-08-15 方案限制發現：** 在 TradingView Alert 的 Notifications 區啟用「Webhook URL」時，TradingView 顯示「React instantly with webhook notifications」升級提示，且目前帳戶方案為 **Basic**；介面未提供可輸入 Webhook URL 的欄位，而是導向 Essential 的「30-day free trial」。因此 Webhook Alert 尚未建立、任何 Pionex URL 未輸入 TradingView，且未有訊號送達或真實交易。此限制由 TradingView 畫面直接顯示，無法透過 Pionex listener 或 Pine 程式安全繞過。
- Notifications 清單原本僅勾選 TradingView App 與 Toast；Webhook 為未勾選狀態。升級提示已關閉，未按任何試用、升級、付款或 Alert 建立按鈕。
