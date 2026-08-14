# 派網下單權限診斷紀錄

## 2026-08-15 使用者本機日誌（截圖逐段核對）

已確認掃描器在同一輪中可正常完成多個交易對的 K 線訊號判讀。`BRENTOIL_USDT_PERP` 出現 `LONG` 後，下一行記錄為：

```text
SCAN_SYMBOL_ERROR | BRENTOIL_USDT_PERP | 掃描此交易對時已跳過：派網 API 失敗（HTTP 200）：TRADE_TYPE_DENIED user denied not in whitelist
```

此回覆與先前的 `AUTH_UNAVAILABLE` 不同：它表示請求已通過基本 API 驗證與讀取權限階段，但交易所拒絕此 API Key 對目前請求的交易類型執行操作。仍待依派網官方文件／API Key 設定頁確認精確的白名單標籤與啟用步驟；在確認前，程式必須維持不送出替代訂單的安全行為。

## 已核對的官方文件

- 派網的 API Key Permissions 文件列出 `POST /uapi/v1/trade/order` 需要 `Enable trading`；讀取永續合約帳戶、持倉與槓桿的 `/uapi/v1/` GET 端點需要 `Enable reading`。
- 派網的 API Key Guide 指示使用者從 Account menu 進入 API Management 管理 API Key。
- 目前官方公開文件沒有對 `TRADE_TYPE_DENIED user denied not in whitelist` 提供可核對的逐字設定名稱。因此最安全的下一步是請使用者在既有 API Key 的編輯介面中確認是否另有 Futures／USDT Perpetual／Contract 交易類型選項，而不是更動程式以繞過交易所限制。

官方文件：

1. https://www.pionex.com/docs/api-docs/references/api-key-permissions
2. https://www.pionex.com/docs/api-docs/references/api-key-guide

## 已核對的帳戶設定頁（僅讀取）

2026-08-15 以已登入的派網 API 管理頁確認：API Key 列表會顯示「讀取、交易、機器人讀取、機器人交易」等通用權限，並提供「詳情」與「編輯」操作。列表層級未顯示「交易類型」或「USDT 永續合約」白名單欄位；若平台提供該限制，其設定應位於 API Key 的詳細／編輯頁、帳戶風險控制或另行審核的產品開通狀態。此頁面含敏感 API Key 資料，故不記錄任何 Key 值、帳戶識別資料或 IP 資訊。

進一步以只讀方式開啟既有 API Key 的「編輯」介面後，畫面只提供 API 備註、一般「交易」、機器人讀取、機器人交易與 IP 地址權限欄位，未顯示 Futures、USDT 永續、交易類型或白名單切換項。此結果支持以下結論：`TRADE_TYPE_DENIED` 無法僅靠此一般 API Key 編輯表單排除；可能與合約帳戶產品開通、風險／交易資格限制，或派網後端尚未同步更新的產品類授權有關。未更改或儲存任何 API Key 設定。

## 合約帳戶只讀檢查

合約帳戶頁可正常讀取，頁面未顯示明確的「合約尚未開通」、「資格未完成」或地區限制提示，且顯示 USDT 與模擬 PUSD 資產列。但同一時點合約帳戶中的可用真實 USDT 顯示為 0；這不會造成 `TRADE_TYPE_DENIED`，但在白名單限制排除後，程式仍會因既有的最低 50 USDT 保證金規則而拒絕開倉，直到合約帳戶中有足夠的真實 USDT。

另以只讀方式開啟預設 USDT 永續合約手動交易 URL；頁面沒有提供可讀取的資格限制訊息或交易面板內容，因此不能從該頁確認產品類型白名單的具體控制項。未輸入任何訂單，也未執行交易、劃轉或設定變更。

## 官方客服的最終限制確認（2026-08-15）

使用者提供的派網官方客服回覆已確認：

1. 合約讀取權限（槓桿、保證金模式、持倉、餘額等）皆位於 `/uapi/v1`，只要 API Key 具有一般讀取權限即可呼叫，不需要額外申請白名單。
2. 透過 Public Trade API 直接進行永續合約下單的功能，現階段未對所有帳戶開放；官方不設白名單申請、名額候補或透過客服開通的流程。
3. 合約自動化的官方替代方式為透過 Bot API 建立合約網格機器人，或使用 Signal Bot 串接訊號執行。

因此，`TRADE_TYPE_DENIED` 並非使用者可在一般 API Key 編輯頁修復的設定錯誤。現有使用 `/uapi/v1/trade/order` 的直接市價下單與直接平倉路徑不可用於實盤，應先被明確封鎖，並將策略遷移至官方支援的 Bot API 或 Signal Bot 路線。

## 官方遷移路線研究（2026-08-15）

### Bot API 的 Futures Grid

官方文件提供 Futures Grid Bot 的建立、查詢與參數檢查端點。建立端點是 `POST /api/v1/bot/orders/futuresGrid/create`；參數檢查端點是 `POST /api/v1/bot/orders/futuresGrid/checkParams`，可在建立前驗證價格區間、網格數、槓桿與投入金額。合約標的格式使用 `base=BTC.PERP`、`quote=USDT`；策略類型僅限 `long`、`short` 或 `no_trend`，且網格數必須為 2 至 500。

這條路線可取代「建立合約網格機器人」，但不是原 Breakout 策略的等價執行器：原策略需要跨前 30 個標的掃描、布林＋RSI 單次進場，以及以 ROE 高水位為條件的兩段式平倉；Futures Grid API 的核心是配置一個價格區間、網格數與趨勢方向的網格機器人。因此不應將現有突破訊號直接轉為自動建立網格機器人，除非使用者另行確認網格交易本身就是想採用的策略。

來源：https://www.pionex.com/docs/api-docs/bot-api/futures-grid

### Signal Bot（最接近既有策略）

官方說明指出 Signal Bot 會將 TradingView 策略警示透過 webhook 送至 Pionex Futures 執行。它可以依策略訊號開倉、反向或平倉；官方 FAQ 說明支援多次進出，但同一 Signal Bot 同時間只支援一個交易對，並且 Signal Bot 為 Futures 產品。官方設定流程要求：在 Pionex 建立 signal／Signal Bot、在 TradingView 使用可由 Strategy Tester 驗證的 strategy、把 Pionex webhook URL 放入 TradingView alert，然後對照兩端的信號日誌。

對目前 Breakout 策略的限制：它掃描前 30 個合約，所以不能由「一個」Signal Bot 完整承接；若採用此路線，需要為每個想交易的標的建立獨立的 Signal Bot 與 TradingView alert。官方文件還指出 TradingView webhook 需要 Essential 或更高訂閱方案；建立或修改 Signal Bot 時應使用 Pionex 端的保證金、槓桿與風控設定，避免與 Pine Script 的 TPSL 同時控制而互相衝突。

官方 Bot API 另提供 `POST /api/v1/bot/signal/listener` 用於推送 custom trading signal，但文件說明除一般讀取權限外，帳戶仍必須取得 Signal sending access，需聯絡 `open@pionex.com` 申請。這與「使用 Pionex 建立的 TradingView webhook」不同；不應假設現有 Python 程式可立即呼叫這個端點。

來源：https://support.pionex.com/hc/en-us/articles/52606266734105-Signal-Bot
來源：https://www.pionex.com/blog/signal-bot-and-tradingview-tutorial/
來源：https://www.pionex.com/docs/api-docs/bot-api/signal

官方 Bot API 的權限矩陣進一步確認：Futures Grid 的參數檢查與機器人資料讀取需要 Bot reading；建立、調整、減倉與取消 Futures Grid 則需要 Bot trading。`POST /api/v1/bot/signal/listener` 在 API Key 層只標示為 Enable reading，但 Signal 文件另要求帳戶層已啟用 custom signal sending。因此在尚未取得該帳戶級存取前，現有 Python 程式不可用它取代 TradingView webhook。

來源：https://www.pionex.com/docs/api-docs/bot-api/general-info/authentication
來源：https://www.pionex.com/docs/api-docs/references/api-key-permissions
