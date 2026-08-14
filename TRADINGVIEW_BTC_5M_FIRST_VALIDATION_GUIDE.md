# TradingView：BTC 5 分 K Breakout 首次驗證指南

**這一輪的唯一目標：** 在 TradingView 圖表中成功看到本策略的歷史回測交易標記。它**不會**建立警示、貼上 webhook、連到派網 API，或開任何實盤倉位。

> 請先完成本指南，再談 Signal Bot。Pionex Signal Bot 會將 TradingView 警示轉為 Futures 交易；不要把兩個步驟混在一起。[1]

## 開始前確認

| 項目 | 本輪正確狀態 |
|---|---|
| 派網 Python 程式 | 可以停止；不需要執行。原本的直接合約下單路徑已被封鎖。 |
| TradingView 帳戶 | 任一帳戶皆可先用 Strategy Tester；此輪不需要 webhook。 |
| 圖表 | Pionex 的 BTC USDT 永續合約圖表，週期 **5m**。 |
| Pine 檔案 | `tradingview/BTC_5M_Breakout_SignalBot_Validation.pine`。 |
| 成功定義 | 圖表顯示布林通道與 LONG／SHORT 標記，且 Strategy Tester 顯示交易清單。 |
| 禁止動作 | 不建立 Alert、不開啟 Webhook URL、不新增／自動化 Signal Bot、不存入交易資金。 |

## 第 1 步：取得最新檔案

先在 PowerShell 執行下列指令。這些指令只下載 GitHub 的策略檔，不會啟動交易機器人。

```powershell
cd C:\Users\UserPC_01\Desktop\pionex-breakout-live
git pull origin main
git log -1 --oneline
```

完成後，在 VS Code 左側檔案總管開啟：

```text
tradingview/BTC_5M_Breakout_SignalBot_Validation.pine
```

按 `Ctrl + A`，再按 `Ctrl + C`，將整個檔案複製到剪貼簿。不要只複製其中一段。

## 第 2 步：在 TradingView 加入策略

使用桌面版瀏覽器打開 TradingView。若從 Pionex Signal Bot 畫面看到 **Launch chart**，可由該處開啟 BTC 永續圖表；否則自行搜尋派網的 BTC USDT 永續合約。重點是選擇**派網的 BTC Perpetual／BTC USDT Futures**，而不是現貨 BTC。

把圖表時間週期設定為 **5m**。接著在下方點 **Pine Editor**，將內容全部清除，按 `Ctrl + V` 貼上剛才複製的檔案，最後按 **Add to chart**。

| 畫面現象 | 含義與處理方式 |
|---|---|
| 看見灰色中軌、青綠色上軌與橘色下軌 | 正常，這是 20 期、2 倍標準差的布林通道。 |
| 看見圖表上的 `LONG` 或 `SHORT` 小標記 | 正常，這是收線後通過布林通道與 RSI 雙重條件的歷史訊號。 |
| Strategy Tester 顯示「需要交易數據」，但圖上有 LONG／SHORT 標記 | 請先更新到最新 Pine 檔再重新貼上。舊版以固定 1 BTC 回測，但初始資金只有 1,000 USDT，會因資金不足而無法登錄交易。新版使用預設 **50 USDT** 回測名義部位。 |
| 圖表整片淡紅色 | 週期錯誤；請確認左上週期是 **5m**。 |
| Pine Editor 顯示紅色編譯錯誤 | 不要建立 alert；截圖整個錯誤訊息與前後程式行即可。 |
| 完全沒有交易標記 | 先確認策略名稱出現在圖表左上，再切換到足夠長的歷史區間；這不代表帳戶或 API 有問題。 |

## 第 3 步：查看回測結果

在圖表下方點 **Strategy Tester**。本策略的預設值與既有 Python Breakout 的核心設定一致：布林 20 期、2 倍標準差、RSI 14、做多 RSI 至少 55、做空 RSI 至多 45、ROE 估算槓桿為 5×、硬停損 -8%、第一段保護 +10%／+5%、第二段鎖利 +15%／+10%。

回測中的 ROE 使用每根已收線 K 棒的收盤價與 5× 估算，並非派網逐秒標記價格或實盤結果。策略預設的 50 USDT 僅是歷史驗證用名義部位，不會轉移或使用真實資金。因此，回測只能用來檢查規則與歷史行為，不能用來預測未來報酬。

請在 **List of Trades** 選一筆 LONG 與一筆 SHORT，回到圖表核對：LONG 進場時收盤價應高於上軌且 RSI ≥ 55；SHORT 進場時收盤價應低於下軌且 RSI ≤ 45。出場理由應與 ROE 硬停損、第一段保護或第二段鎖利其中之一相符。

## 本輪到此結束

在您確認「圖表有策略、Strategy Tester 有交易清單、未建立 alert」之前，請不要點 TradingView 的鬧鐘圖示，也不要在 Pionex 按 **Automate signal**。

下一個階段會是「只驗證警示是否傳到 Pionex Signal Log」。這一步要求 TradingView Essential 或更高方案才可使用 webhook，並且會使用 Pionex 官方 Signal Bot strategy 所提供的訊息格式。[1] 在您主動確認要做該階段前，不會建立任何活動 Bot。

## 已驗證紀錄：2026-08-15

| 項目 | 已驗證結果 |
|---|---|
| 修正前現象 | 圖表可顯示 LONG／SHORT 訊號，但 Strategy Tester 回報需要交易數據。 |
| 原因 | 舊版固定以 1 BTC 下回測單；在 1,000 USDT 初始資金下，BTC 單位數量超過可負擔範圍，因此訊號沒有轉為登錄交易。 |
| 修正版本 | GitHub commit `d34a41a`，以 `validationNotionalUsdt / close` 將每筆回測調整為預設 50 USDT 名義部位。 |
| 使用者實測 | 使用者已在 Pionex 的 BTC USDT Perpetual、5 分 K 圖表重新載入策略；Strategy Tester 的 **List of trades** 已顯示至少一筆 short 交易及其 Entry／Exit 時間。 |
| 安全狀態 | 驗證期間未建立 Alert、未設定 webhook、未建立活動 Signal Bot，亦未發出實盤交易。 |

## References

[1] [Pionex Help Center — Signal Bot](https://support.pionex.com/hc/en-us/articles/52606266734105-Signal-Bot)
