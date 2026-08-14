# 派網 USDT 永續合約公開市場 API 參考

> 本文件僅保存本次修正所需的外部官方文件摘要；不包含使用者帳戶、API Key、Secret 或任何交易資料。

| 用途 | 官方端點 | 相關參數與結論 |
|---|---|---|
| 取得可交易合約資料 | `GET /api/v1/common/symbols` | `type=PERP`、`status=TRADING` 可過濾永續合約；回傳資料包含 `symbol`、`contractType`、`quoteCurrency`、`status`。 |
| 取得 24 小時成交資訊 | `GET /api/v1/market/tickers` | 未指定 `symbol` 時以 `type=PERP` 取得永續合約 24 小時統計，適合作為候選排名來源。 |
| 取得最佳 bid/ask | `GET /api/v1/market/bookTicker` | 可傳單一 `symbol`；若不傳 symbol，`type=PERP` 可取得永續合約最佳 bid/ask 清單。此清單可作為候選行情可用性過濾來源。 |

## 修正依據

使用者日誌顯示 `APR_USDT_PERP` 可在成交統計與 K 線流程出現，但個別 `bookTicker?symbol=APR_USDT_PERP` 回覆 HTTP 404。官方文件指出 `bookTicker` 可用 `type=PERP` 取得永續合約報價清單，因此候選清單應額外和該清單交集，避免將沒有可用最佳 bid/ask 的標的交給進場流程。

## 2026-08-15 官方文件與公開端點實測註記

派網官方永續合約市場文件列出：

- `GET /api/v1/market/tickers?type=PERP`：取得 24 小時統計；回傳 `open`、`close`、`high`、`low`、`volume`、`amount`、`count`，**不包含 bid/ask**。
- `GET /api/v1/market/bookTicker`：文件宣稱可取得最佳 bid/ask，並可帶 `symbol` 或 `type=PERP`。
- `GET /api/v1/market/depth?symbol=BTC_USDT_PERP`：取得單一永續合約的委託簿，回傳 `bids` 與 `asks`；可作為文件化的 bid/ask 替代來源。

以 `https://api.pionex.com` 為基底，實測下列請求均回傳 HTTP 404 與 `{"error_msg":"404 Route Not Found"}`：

```text
/api/v1/market/ticker?type=PERP
/api/v1/market/bookTicker?type=PERP
```

第一個請求使用單數 `ticker`；程式實際用於成交統計的是複數 `/api/v1/market/tickers`，不可混淆。第二個端點的 404 與使用者在個別 `bookTicker` 流程看到的現象一致。因此，在以批次 `bookTicker` 做候選過濾前，必須再用目前可用的公開回應驗證，不能把它當作唯一的可交易判定來源。

本次實測的複數 `/api/v1/market/tickers?type=PERP` 回傳 HTTP 200 與 600 筆統計資料，包含 `APR_USDT_PERP`；這只能證明該標的仍在統計資料內，不能證明它必有可用 bid/ask 或可立即送單。

## 來源

1. [Pionex Futures API — Market](https://www.pionex.com/docs/api-docs/futures-api/market)，擷取時間 2026-08-15；該頁標示最後更新於三個月前。
2. [Pionex Futures API — Common](https://www.pionex.com/docs/api-docs/futures-api/common)，擷取時間 2026-08-15。
