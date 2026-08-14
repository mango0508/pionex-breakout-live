# 自訂策略自動化交易所研究筆記

> 研究範圍僅限官方文件所載的訊號與 API 自動化能力；不代表開戶資格、地區可用性、資產安全或策略獲利保證。資料核對日期：2026-08-15。

## 已核對的官方來源

| 平台 | 官方能力與關鍵條件 | 對目前 BTC 5 分 K Breakout 的意義 | 原始來源 |
|---|---|---|---|
| Pionex | Signal Bot 透過 TradingView webhook 將策略 alert 轉為 Pionex Futures 交易；官方列出需 TradingView Essential 或更高方案。Signal Bot 僅支援 Futures、同一時間僅能有一個活躍交易對；關閉的 Bot 會接收但忽略訊號。官方建議只使用 TradingView 或 Signal Bot 其中一方的 TP/SL，以免衝突。 | 可直接沿用已完成的 listener 與 Pine 策略，但仍受 TradingView webhook 方案限制。 | https://support.pionex.com/hc/en-us/articles/52606266734105-Signal-Bot |
| Bybit | 官方 Webhook Signal Trading 可用 TradingView 訊號自動交易 Derivatives，包括 USDT/USDC/Inverse Perpetual 與 Inverse Futures；需 TradingView Essential/Plus/Premium。只支援 One-way position mode，且每個交易對要各自建立 webhook。官方提供 pause/terminate；每個 symbol 最多 5 個執行中的 webhook strategy、每 UID 最多 30 個。 | 為 Pionex 的直接官方替代方案，但同樣無法避開 TradingView 付費 webhook；需改用 Bybit 的訊息模板與單位規則，不能直接複用 Pionex listener。 | https://www.bybit.com/en/help-center/article/How-to-Use-and-Setup-Webhook-Signal-Trading-on-Bybit |
| TradingView | Webhook 在 alert 觸發時以 HTTP POST 送至外部 URL；Webhook 需啟用 2FA。服務可能發生送達失敗，Alert Log 有 Webhook status 可檢查；服務端處理超過 3 秒時請求會取消。官方安全提醒不要把登入憑證或密碼放在 body。 | 即使改用 Bybit 等官方 webhook 路線，仍需具備 webhook 權限的 TradingView 方案；應以 Alert Log 和交易所 signal log 雙重驗證送達。 | https://www.tradingview.com/support/solutions/43000529348-how-to-configure-webhook-alerts/ |
| Bitget | Futures Signal Bot 將 TradingView alert 直接連至 Bitget，支援自訂策略與 USDT-M perpetual futures；每個 webhook 只能連一個 TradingView alert。官方列出 TradingView webhook 需付費方案，採 One-way mode，並提供固定保證金、保證金比例或依 TradingView positionSize 的下單方式。終止 bot 會以市價平掉所有開放持倉。另有 Spot/Futures Trading API 可供自建程式使用。 | 具備交易所內建 signal bot 與 API 兩條路徑，但 TradingView 路線同樣無法避免 webhook 方案。終止行為會強制市價平倉，需事前理解。 | https://www.bitget.com/support/articles/12560603823395；https://www.bitget.com/promotion/bitget-api |
| OKX | Signal Bot 僅支援 perpetual swaps，不支援現貨；可用 TradingView strategy 或一般 custom alert 格式。官方提供 TradingView Alert Log 與 OKX Events History 雙重診斷，並有 Demo Trading 的 Signal Bot。可於一個 bot 選多個交易對，但會濾掉未選交易對訊號。官方 REST/WebSocket API 可下單與管理設定；交易 API key 應綁 IP，且不同註冊地區須使用相對應 API domain。 | 功能上最適合先以 demo Signal Bot 驗證訊號與出場行為，再決定是否實盤；但 TradingView 路線仍需 webhook。自建 API 路線技術與密鑰維運要求較高。 | https://www.okx.com/en-us/help/trading-signal-bot-faqs；https://www.okx.com/en-us/help/how-to-set-up-signal-trading-bot-with-tradingview；https://www.okx.com/docs-v5/en/ |
| Binance | Webhook Signal Trading 可讓 TradingView 策略或 Alert 自動執行 USDⓈ-M Futures；支援 One-Way 與 Hedge mode，訊號可自行停用、編輯、刪除。官方要求 TradingView Pro、Pro+ 或 Premium，且用戶須先在 Binance 建立 signal，再在 TradingView 放入 webhook URL 與訊息。官方 USDⓈ-M Futures REST API 也可簽名下單與管理倉位模式，並提供 futures testnet 端點。 | 具備成熟的交易所原生 signal 與 API 路線，但 TradingView 路線仍無法避免付費 webhook。官方訊號服務受地區與 USDⓈ-M 可用性限制，且公告與 FAQ 的訂單型別描述不完全一致；啟用前必須在實際帳戶頁再確認。 | https://www.binance.com/en/support/faq/detail/3f57291b56474f5e900cc4b754f61ff3；https://www.binance.com/en/support/announcement/detail/0508c94932e74f0a8b0788c085573044；https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api |

## 初步結論

Pionex、Bybit、Bitget、OKX 與 Binance 都提供官方 TradingView webhook 路線，且已核對的官方資料皆不能消除 TradingView 的付費 webhook 方案條件。Bitget、Bybit、OKX 與 Binance 均另有官方 Futures Trading API，可走自建程式接收訊號並下單的技術路線；這會把持續運行、密鑰保管、交易所 API 限制與故障處理責任交由使用者系統承擔。OKX 是目前唯一在已核對資料中明確提供 Demo Trading Signal Bot 的候選；所有平台也都須在實際帳戶與所在地規則下再次確認產品可用性。
