# Pionex Signal Bot：無下單訊號驗證流程

**版本：** 2026-08-15  
**目標：** 驗證 TradingView 的訊號是否符合 BTC 5 分 K Breakout 規則，以及訊號是否能抵達 Pionex；在本流程完成前，**不得建立或啟用任何會執行交易的 Signal Bot**。

## 安全界線

派網 Signal Bot 的定位是將 TradingView 策略警示轉為 Pionex Futures 交易；它不是唯讀通知功能。[1] 第一階段只使用 TradingView Strategy Tester。第二階段雖可驗證傳遞紀錄，但須保持「未建立活動 Signal Bot」狀態。派網官方 FAQ 表示，沒有活動 Signal Bot 時，收到的訊號會被忽略，不會執行。[1]

> 不要在 GitHub、Python `.env`、雲端儀表板、截圖或聊天室儲存／貼出 Pionex Signal webhook URL。它具有觸發訊號流程的安全敏感性。

## 兩階段驗證設計

| 階段 | 目的 | 可做事項 | 明確禁止事項 | 通過標準 |
|---|---|---|---|---|
| 1. 圖表回測 | 核對策略邏輯 | 把 `tradingview/BTC_5M_Breakout_SignalBot_Validation.pine` 加到派網 BTC 永續合約的 5 分 K 圖表，查看 Strategy Tester | 建立 alert、輸入 webhook URL、建立自動化 Signal Bot | 策略編譯成功；抽查至少 5 筆進／出場符合 `TRADINGVIEW_SIGNAL_BOT_BREAKOUT_CONTRACT.md`。 |
| 2. 訊號送達 | 只核對 TradingView 與 Pionex 的傳遞紀錄 | 依派網介面新增 Signal，使用**派網官方提供的 Signal Bot strategy／toolkit 產生的訊息格式**建立 alert，檢查雙方日誌 | 按「Automate signal」、建立活動 Bot、轉入資金、啟用交易 | TradingView Alert Log 與 Pionex Signal Log 各出現同一筆對應紀錄，且 Pionex 沒有活動 Bot、沒有倉位、沒有成交。 |

## 階段 1：只做 TradingView Strategy Tester

1. 使用桌面瀏覽器打開 TradingView，搜尋派網 **BTC USDT 永續合約**圖表；若商品代碼顯示不同，以 Pionex 圖表中的 BTC Perpetual 為準。
2. 把圖表週期改為 **5 分鐘**。
3. 打開 Pine Editor，貼上 `tradingview/BTC_5M_Breakout_SignalBot_Validation.pine` 的完整內容，按 **Add to chart**。
4. 若畫面顯示紅色背景，代表週期不是 5 分鐘，請不要判讀任何交易。
5. 打開 **Strategy Tester**，確認出現交易清單。這只是一個圖表回測，既沒有 webhook，也不會連到派網帳戶。
6. 在圖表上抽查至少五筆 `LONG`、`SHORT` 或關倉標記；所有進出場應在 K 線收線後才出現。

## 階段 2：只驗證訊號送達，不建立活動 Bot

本階段必須等階段 1 的人工核對完成後才可開始。要使用 Pionex webhook，派網目前文件要求 TradingView Essential 或更高方案。[1] 這項需求是 TradingView 訂閱條件，不是 Python 或 API Key 可以繞過的限制。

1. 進入 Pionex：**Futures → Futures Bot → Signal Bot → Add signal**，建立一個明確標示 `BTC_BREAKOUT_TEST_NO_BOT` 的 Signal。[1]
2. **停在 Signal 設定完成的階段，不要按「Automate signal」，不要建立 Bot。**
3. 派網要求的策略訊息須由其官方 Signal Bot strategy 或 toolkit 生成；不要自行猜測 JSON 欄位，也不要把本檔的驗證版 `.pine` 直接當成派網執行腳本。[1]
4. 在 TradingView 以派網官方產生的策略建立 alert。訊息欄保持該官方策略提供的預設 JSON，Webhook URL 僅貼到 TradingView 的 Webhook URL 欄位；不可另存、不可分享。[1]
5. 當下一筆策略警示發生後，打開 TradingView **Alert Log** 及 Pionex **Signal Log**，核對時間、商品和訊號方向。派網官方也建議以這兩個日誌比對傳遞結果。[1]
6. 確認 Pionex 沒有任何**活動** Signal Bot、沒有持倉、沒有成交。若出現任何活動 Bot 或倉位，立刻在 Pionex 官方介面停止該 Bot 並手動確認倉位，之後才進行後續診斷。

## 不能略過的限制

| 限制 | 對本專案的影響 |
|---|---|
| Signal Bot 一次只允許一個活動交易對 | 因此第一版固定 BTC；Python 的前 30 幣掃描不會直接遷移。 [1] |
| 派網規則可將策略訂單數量解讀為 Signal Bot 資金使用比例 | 不可把原 Python 的「50 USDT 階梯保證金」直接照抄為 Pine `qty=50`，必須先依派網提供的策略範本與小額驗證重新校準。 [1] |
| TradingView 回測是收線策略，Python 原版則每 10 秒讀取派網未實現 PnL | 首版回測的進、出場價格及 ROE 都是近似值，不能當作實盤結果或績效預測。 |
| Direct Public Trade API 已被官方確認不支援直接永續合約下單 | 既有 Python 實盤送單路徑已安全封鎖；Signal Bot 是不同的官方執行產品。 |

## 何時才可討論啟用交易

只有在以下四項同時成立時，才可進行**另一個獨立確認流程**：策略回測已完成、訊號日誌已雙向比對、使用者已自行理解杠桿與清算風險、且使用者明確要求建立活動 Signal Bot。本文件不授權或指示建立活動 Bot。

## References

[1] [Pionex Help Center — Signal Bot](https://support.pionex.com/hc/en-us/articles/52606266734105-Signal-Bot)
