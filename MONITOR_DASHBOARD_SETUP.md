# 私人雲端監控網站：本機遙測啟用步驟

本文件說明如何讓本機的 Pionex 機器人把**唯讀監控資料**傳到私人雲端儀表板。這項功能不是遠端交易控制，也不會把派網或 Telegram 憑證傳出本機。

> 請先完成雲端監控網站的發佈，再執行本文件的設定。未完成前請保持 `MONITOR_TELEMETRY_ENABLED=false`。

## 上傳資料與禁止資料

| 類別 | 雲端可接收 | 絕不上傳 |
| --- | --- | --- |
| 執行摘要 | 實盤／唯讀模式、可用 USDT、當日實盤開倉統計、最後掃描時間 | Pionex API Key、Pionex API Secret、簽名、完整帳戶回應 |
| 持倉摘要 | 交易對、方向、開倉／標記價格、ROE、未實現損益、保護狀態與峰值 | 下單或平倉指令、修改槓桿功能 |
| 事件 | 時間、類型、交易對、可讀說明 | `context_json`、Telegram Bot Token、Chat ID、原始錯誤回應 |

## 設定順序

1. 在雲端監控網站的設定頁建立一組至少 32 字元的 `MONITOR_INGEST_TOKEN`，並安全保存。
2. 發佈雲端監控網站，複製其網址，例如 `https://your-monitor.manus.space`。
3. 在本機 `.env` 最後加入下列三行，並將值換成自己的資料：

   ```dotenv
   MONITOR_TELEMETRY_ENABLED=true
   MONITOR_DASHBOARD_INGEST_URL=https://your-monitor.manus.space/api/monitor/ingest
   MONITOR_INGEST_TOKEN=與雲端設定完全相同的長隨機權杖
   ```

4. 確認 `.env` 仍在 `.gitignore` 中，且不要把它截圖、貼到聊天或推送至 GitHub。
5. 在本機正在執行的終端機按 `Ctrl+C`；這會停止程式但不會平倉。若已有持倉，先在派網確認持倉狀態。
6. 在同一個資料夾重新啟動：

   ```powershell
   python pionex_breakout_live.py
   ```

7. 啟動後應看到 `MONITOR_TELEMETRY_START`。它表示唯讀遙測背景工作者已啟動，不代表雲端有交易權限。
8. 使用您的私人登入帳號開啟雲端網站。最多等待約 30 秒，應會看到模式、餘額、掃描時間與近期事件。

## 異常處理

| 情況 | 代表意義與處理 |
| --- | --- |
| 日誌出現「雲端監控遙測設定不完整」 | 檢查三個 `MONITOR_` 設定是否都已填寫；網址必須是 `https://` 開頭。 |
| 日誌出現 HTTP 401 或「上傳被拒絕」 | 本機與雲端的 `MONITOR_INGEST_TOKEN` 不一致，請在兩邊設定為相同的新值後重新啟動。 |
| 雲端沒有更新 | 先確認本機程式仍在運行、網路正常，並等待 10 秒刷新週期。 |
| 想停止雲端遙測 | 將 `MONITOR_TELEMETRY_ENABLED=false` 後重新啟動本機程式；不會影響本機交易與風控。 |

雲端服務中斷只會造成監控頁面延遲或無法更新；本機的下單邏輯、持倉監控與風控不會因遙測失敗而停止。
