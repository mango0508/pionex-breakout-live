# Binance Futures Demo Trading 研究紀錄

> 範圍：本文件僅記錄 Binance 官方的 Demo Trading／Testnet 研究資訊，**不包含**任何帳戶、API Key、Secret、Webhook、測試資金餘額或交易資料。

## 官方環境與 API Key

Binance 官方 FAQ 說明，開發交易功能可免費使用 **Futures Demo Trading** 進行測試；此環境受 Demo Trading Terms of Use 約束。Futures Demo Trading 的 API Key 應在登入後前往 API Management 建立，並為該 Key 指定名稱。這不是現貨 Testnet 的 GitHub 登入／測試資產流程。

官方 FAQ：<https://www.binance.com/en/support/faq/detail/ab78f9a1b8824cf0a106b4229c76496d>

Futures Demo Trading：<https://demo.binance.com/en/futures>

API Management：<https://demo.binance.com/en/my/settings/api-management>

## 官方 Demo Trading 限制與驗證意義

官方說明 Demo Trading 可以使用虛擬資金練習 USDⓈ-M 與 COIN-M Futures，並可透過 API 存取。使用者可在 Demo Trading 的 Assets 中為 Futures 帳戶重設虛擬資金，但重設前必須取消待處理訂單。Demo Trading 僅在部分國家與地區可用；登入成功不代表其所有產品均可使用。

Futures Demo Trading 不支援 Webhook、Grid、TWAP 等部分功能，這與本路線直接由 Python API 執行策略的目標相符。官方亦明確提醒 Demo 環境與實盤在圖表資料、訂單簿、實際成交與功能上可能不同；Demo 表現不代表未來實盤績效。

官方 Demo Trading FAQ：<https://www.binance.com/en/support/faq/detail/9be58f73e5e14338809e3b705b9687dd>

## API 文件確認

USDⓈ-M Futures 官方 General Info 文件列出真實 base URL `https://fapi.binance.com`，以及目前 Demo/Testnet REST base URL `https://demo-fapi.binance.com`。交易與帳戶資料端點為 signed endpoint，需有 `X-MBX-APIKEY`、毫秒時間戳與 HMAC SHA256 簽名。此專案會先用 public market-data 路徑及離線簽名測試；收到使用者確認並建立 **Demo 專用** API Key 前，不呼叫任何認證端點。

USDⓈ-M Futures General Info：<https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/general-info>

## 技術實作邊界

1. 實作時只能使用 Demo Trading／Testnet 的 API URL 與 **Demo API Key**，不得使用 `fapi.binance.com` 等真實資金端點或真實 API Key。
2. API Secret 僅由使用者在本機 `.env` 保存；不可貼入聊天室、Git、雲端監控站或任何文件。
3. 在取得 API Key 前，先建立離線策略測試與 request 簽名測試；不呼叫需要認證的端點。
4. API Key 建立與第一筆 Testnet 訂單都需要使用者的單次明確確認。

## 待補證的官方技術細節

已確認 Demo REST base URL 為 `https://demo-fapi.binance.com`。後續仍需在唯讀驗證時從 USDⓈ-M Futures API Reference 取得並驗證 `exchangeInfo` 的 BTCUSDT minQty／stepSize／minNotional，以及在使用者確認 Testnet 下單後驗證槓桿設定、下單、持倉端點與請求簽名格式。官方文件入口：<https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/general-info>。
