# 本機更新、掃描修正與雲端監控指引

本指引不會要求您貼出派網 API Key、API Secret、Telegram Token 或雲端監控權杖。請只在自己的 `.env` 檔內填入這些值；`.env` 不可上傳 GitHub。

## 一、先套用本次掃描修正

本次修正統一派網合約資料的兩種欄位格式：`type=PERP` 與 `contractType=PERPETUAL`。有效的 USDT 永續合約不會再因這兩種等價格式的差異被誤判為不可交易；真正下架、暫停、非 USDT 或非永續合約仍會被安全跳過。

1. 在正在執行機器人的黑色終端機按 `Ctrl + C` 停止程式。
2. 在新的終端機輸入：

   ```bat
   cd C:\Users\UserPC_01\Desktop\pionex-breakout-live
   git pull origin main
   ```

3. 正常情況會看到下載更新，不應要求您輸入任何 API Key。
4. 重新啟動：

   ```bat
   .venv\Scripts\python.exe pionex_breakout_live.py
   ```

5. 程式只會使用**已收線**的 5 分鐘 K 棒判斷；重新啟動後請等待下一根 5 分 K 線收線與下一輪掃描。它不會追溯地對已過去的訊號補下單。

## 二、如何閱讀下一輪日誌

| 日誌事件 | 代表意思 | 是否需要您處理 |
|---|---|---|
| `SIGNAL ... HOLD` | 布林突破與 RSI 雙重確認尚未同時成立。 | 不需要；這是正常觀望。 |
| `SIGNAL ... LONG` 或 `SHORT` | 策略在已收線 K 棒找到方向訊號。 | 繼續查看後續行。 |
| `ENTRY_BLOCKED` | 通常是該交易對的派網槓桿不是設定的 5×，或可用 USDT 未達 50。 | 若顯示槓桿不符，僅在派網手動把**該交易對**調整為 5× 後再觀察。 |
| `ENTRY_BLOCKED ... TRADE_TYPE_DENIED` | 派網拒絕該 API Key 存取 USDT 永續合約的產品類型白名單；程式尚未送單。 | 依下一節聯絡派網客服確認 Futures／Perpetual API 授權，不要關閉安全檢查。 |
| `SCAN_SYMBOL_ERROR` | 交易所資料顯示該標的已下架、暫停或不屬於可交易的 USDT 永續合約。 | 不需要；程式安全跳過，不會下單。 |
| `ENTRY_SENT` | 市價開倉指令已送出；成交與持倉須以派網 App／網站為準。 | 立即在派網核對委託與持倉。 |

## 三、出現 `AUTH_UNAVAILABLE` 時的處理方式

如果日誌先顯示 `SIGNAL ... LONG` 或 `SHORT`，接著出現 `AUTH_UNAVAILABLE have no right`，目前已可確認它發生在程式的**槓桿讀取安全檢查**：`GET /uapi/v1/account/leverage`。這不是策略沒有訊號，也不是公開價格端點故障；在無法確認派網實際槓桿為 5× 時，程式會刻意停止這一筆開倉。

派網官方文件規定，讀取槓桿、倉位與餘額需要 **Enable reading**；送出永續合約訂單需要 **Enable trading**。因此，請只在派網官方 App／網站的 API 管理頁面，找到**目前 `.env` 正在使用的同一把 API Key**，確認下列兩項皆已開啟：

| 設定 | 本程式用途 | 必要性 |
|---|---|---|
| `Enable reading` | 確認倉位模式、查詢持倉與餘額、讀回該交易對的實際槓桿。 | 必要 |
| `Enable trading` | 只有通過所有安全檢查後，才可送出開倉與 `reduceOnly` 平倉指令。 | 必要 |
| `Enable transfer` | 資金轉帳。 | **不需要，請維持關閉** |

若 API Key 啟用了 IP 白名單，也必須確認目前本機網路的**對外 IP**已列入允許名單。請不要把 API Key、API Secret、IP 白名單畫面或任何權杖貼到聊天室。不要因為此錯誤而關閉槓桿驗證或隨意重建 API Key；先修正既有 Key 的讀取與交易權限即可。

套用本次程式更新後，若權限仍未修正，日誌會改為清楚的 `ENTRY_BLOCKED`，並寫明 `GET /uapi/v1/account/leverage`、`Enable reading` 與「未送出訂單」。權限修正後，下一次符合條件的已收線 5 分 K 訊號才會繼續通過槓桿、餘額、數量與下單檢查。

## 四、出現 `TRADE_TYPE_DENIED user denied not in whitelist` 時的處理方式

派網官方客服已確認：`/uapi/v1` 的合約讀取功能（槓桿、保證金模式、持倉、餘額）只需要一般讀取權限；但是 **Public Trade API 目前不對所有帳戶開放直接 USDT 永續合約下單**。官方也明確表示，沒有 API Key 白名單申請、名額候補或透過客服開通直接下單功能的流程。

因此，`TRADE_TYPE_DENIED user denied not in whitelist` 不是可在一般 API Key 編輯頁修好的設定錯誤。請不要反覆重建 API Key、不要移除 IP 白名單、不要啟用轉帳權限，也不要停用程式的安全檢查；這些動作都不能使直接合約下單功能開通。

請立刻在仍執行中的舊版黑色視窗按 `Ctrl + C` 停止程式，避免後續訊號繼續觸發不支援的直接下單流程。新版程式已加入不可繞過的保護：即使 `.env` 保留 `LIVE_TRADING=true`，它也只會掃描、讀取與上傳監控資料，不會呼叫直接開倉或 `reduceOnly` 平倉端點。

派網官方提供的合約自動化替代方案為 **Bot API 的合約網格機器人** 或 **Signal Bot（訊號機器人）**。本機 Breakout 程式可先維持為安全的掃描／訊號／監控來源；真正的合約執行邏輯必須依官方支援的 Bot API 或 Signal Bot 介面重新設計與驗證後，才可恢復自動化。

另外，合約帳戶仍必須保有至少 **50 USDT 的真實可用 USDT** 才可能建立未來的官方合約機器人。模擬用的 PUSD 不可替代真實 USDT。

## 五、啟用雲端唯讀監控

請先在雲端監控專案的秘密設定中設定 `MONITOR_INGEST_TOKEN`，再把**同一個值**只填入本機 `.env`。此權杖僅允許本機將去敏感化監控資料上傳到儀表板，不是派網 API Key，也不能用來下單。

在本機 `.env` 最下方加入：

```dotenv
MONITOR_TELEMETRY_ENABLED=true
MONITOR_DASHBOARD_INGEST_URL=https://pionexdash-x73yw8sp.manus.space/api/telemetry/ingest
MONITOR_INGEST_TOKEN=請填入與雲端完全相同的權杖
```

儲存後重新啟動機器人。請勿將最後一行的真實值貼到聊天室、截圖、GitHub 或任何公開文件。

## 六、首次連線驗證

約 30 秒後登入 https://pionexdash-x73yw8sp.manus.space 。如果儀表板出現「實盤／唯讀模式」、可用 USDT、最後掃描時間，或包含 `SCAN_START`／`SIGNAL` 的事件串流，即表示遙測連線成功。

若網站仍顯示「等待資料」，請先確認 `.env` 的三行均已儲存、網址含有 `/api/telemetry/ingest`、並且本機與雲端的 `MONITOR_INGEST_TOKEN` 完全相同。若本機出現 `TELEMETRY_ERROR`，監控上傳失敗不會中斷交易主迴圈或持倉風控；只需修正監控設定後重啟即可。
