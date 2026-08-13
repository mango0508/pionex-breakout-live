# 派網前 30 熱門合約 Breakout 執行器

本專案是派網（Pionex）USDT 永續合約的 **唯讀優先** 執行器。它會從可交易的 USDT 永續合約中，以 24 小時成交額挑選前 30 名，再用 20 期布林通道與 14 期 RSI 尋找突破訊號。預設 `LIVE_TRADING=false`；在這個狀態下，程式**不會送出下單、平倉或修改槓桿的請求**。

> **風險提示：** 本程式是技術工具，並不保證獲利。槓桿交易可能使損失快速擴大；在完整的唯讀、模擬與小額風險測試完成前，不應啟用實盤交易。

## 1. 目前版本的固定安全限制

| 項目 | 行為 |
| --- | --- |
| 實盤開關 | 預設為 `LIVE_TRADING=false`。唯讀模式只寫入 `DRY_RUN_ORDER` 日誌。 |
| 倉位數 | 一次只允許一筆活動倉位；只要帳戶有任何非零持倉，程式都不開新倉。 |
| 持倉隔離 | 只有本程式成功開倉後已登錄的持倉才會進入自動 ROE 風控；手動或其他策略建立、以及狀態遺失的倉位只會顯示 `UNMANAGED_POSITION`，絕不自動平倉。 |
| 倉位模式 | 僅支援派網單向 `BUYSELL` 與 `positionSide=BOTH`。 |
| 槓桿 | 僅在某交易對產生訊號時檢查其槓桿是否為 5 倍；不一致就跳過該交易對，絕不自動修改。 |
| 每日限制 | 實盤送出開倉後才計入每日最多 3 筆；唯讀模式不消耗此額度。 |
| 機密保護 | `.env`、狀態檔及交易日誌均列入 `.gitignore`，不可上傳 GitHub。 |

系統從派網的交易對資訊端點篩選 `TRADING`、`PERPETUAL`、`USDT` 合約，並以 ticker 的 24 小時 `amount` 成交額取前 30 名。[1] [2]

## 2. 策略規則

| 類別 | 規則 |
| --- | --- |
| 掃描標的 | 所有可交易 USDT 永續合約中，依 24 小時成交額排序取前 30 名。 |
| K 線 | 預設 5 分鐘；只用已收線 K 棒，最後一根進行中的 K 棒不參與訊號。 |
| 做多訊號 | 收盤價大於布林上軌，且 RSI ≥ 55。 |
| 做空訊號 | 收盤價小於布林下軌，且 RSI ≤ 45。 |
| 第一段保護 | ROE 曾達或目前達 +10% 後，ROE 回落至 +5% 或以下則平倉。 |
| 第二段鎖利 | ROE 曾達 +15% 後，ROE 回落至 +10% 或以下則平倉。 |
| 硬停損 | ROE ≤ -8% 時平倉。 |

ROE 以派網持倉回傳的未實現損益除以初始保證金計算。程式只在程序正常運作並保有狀態檔時能記得「曾達 +15%」；因此 Render 免費版的重啟與無持久化磁碟限制，使它**不適合實盤使用**。[3]

## 3. A 倍增保證金階梯

下表的金額是保證金，不是下單數量。實際名目額約為「保證金 × 5 倍槓桿」，最終數量仍需依派網即時 `baseStep`、市價單最小／最大數量與最小名目額調整。[2]

| 可用 USDT | 單筆保證金 |
| ---: | ---: |
| 少於 50 | 禁止開倉 |
| 50–119.99 | 50 USDT |
| 120–239.99 | 100 USDT |
| 240–479.99 | 200 USDT |
| 480–959.99 | 400 USDT |
| 960–1,919.99 | 800 USDT |
| 1,920–3,839.99 | 1,600 USDT |
| 3,840–7,679.99 | 3,200 USDT |
| 7,680 以上 | 6,400 USDT（封頂） |

## 4. 本機第一次安全啟動

請依下列順序操作；先完成當前一步並看見預期結果，再進入下一步。

| 步驟 | 操作 | 預期結果 |
| --- | --- | --- |
| 1 | 在 VS Code 開啟本資料夾。 | 可以看到 `pionex_breakout_live.py` 與 `.env.example`。 |
| 2 | 複製 `.env.example` 並改名為 `.env`。 | `.env` 只存在本機，Git 不會追蹤它。 |
| 3 | 在 `.env` 填入新建立的 Pionex API Key／Secret；權限只開 **Read + Trade**，不要開 Transfer。 | API 機密不會寫進任何 `.py` 或 README。 |
| 4 | 確認 `LIVE_TRADING=false` 與 `LEVERAGE=5`。 | 程式仍是唯讀模式。 |
| 5 | 安裝套件：`python -m pip install -r requirements.txt`。 | 安裝 `requests`、`pandas`、`python-dotenv`。 |
| 6 | 執行：`python pionex_breakout_live.py`。 | 終端機與 `pionex_live_events.csv` 出現啟動與掃描日誌。 |

第一次唯讀驗證時，請在派網帳戶確認倉位模式是 `BUYSELL`。當某個候選幣出現突破訊號時，若派網實際槓桿不是 5 倍，日誌會顯示 `ENTRY_BLOCKED`；這是正確的安全行為，沒有任何訂單送出。

## 5. 如何讀日誌

`pionex_live_events.csv` 是 UTF-8 CSV，可直接用 Excel 或 VS Code 開啟。欄位 `context_json` 保存該事件的附加資料。

| 事件 | 意義 |
| --- | --- |
| `START` | 程式已啟動並寫入目前風控設定。 |
| `SCAN_START` | 開始新的前 30 熱門合約掃描輪次。 |
| `SIGNAL` | 某已收線 K 棒已計算出 LONG、SHORT 或 HOLD。 |
| `ENTRY_BLOCKED` | 有訊號但被安全檢核阻擋，例如槓桿不符、餘額不足或達到每日上限。 |
| `DRY_RUN_ORDER` | 唯讀模式產生的假設訂單；**沒有發送給派網**。 |
| `POSITION_MONITOR` | 現有持倉的 ROE、峰值與保護狀態。 |
| `EXIT_SENT` | 實盤或唯讀模式的平倉指令／模擬平倉紀錄。 |
| `ERROR` | 本輪流程出錯；程式會等待下一輪再重試。 |

## 6. Render 部署的重要限制

Render 免費 Web Service 沒有持久化磁碟，重新部署或重啟後，`pionex_live_state.json` 和日誌都可能遺失。這會讓系統忘記每日交易計數與「曾達 +15% ROE」的高水位狀態。因此目前 Render 免費方案只能作為 **`LIVE_TRADING=false` 的唯讀雷達**；不可作為持續實盤風控服務。

在 Render 的環境變數中應個別新增 API Key、API Secret 與各設定值，**不要**上傳 `.env`。在正式實盤之前，需要先改用具持久化儲存與可靠重啟機制的環境，並完成所有離線與唯讀驗證。

## 7. 可執行的離線測試

不需 API Key，也不會連網：

```bash
python -m unittest discover -s tests -v
```

測試覆蓋保證金階梯邊界、交易對熱門排序、槓桿解析、布林／RSI 訊號與兩段式 ROE 風控。每次修改策略後都應先執行這個命令。

## References

[1]: https://www.pionex.com/docs/api-docs/futures-api/market "Pionex Futures API — Market"
[2]: https://www.pionex.com/docs/api-docs/futures-api/common "Pionex Futures API — Common"
[3]: https://www.pionex.com/docs/api-docs/futures-api/account "Pionex Futures API — Account"
