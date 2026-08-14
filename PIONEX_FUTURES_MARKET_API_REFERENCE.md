# 派網 USDT 永續合約公開市場 API 參考

> 本文件僅保存本次修正所需的外部官方文件摘要；不包含使用者帳戶、API Key、Secret 或任何交易資料。

| 用途 | 官方端點 | 相關參數與結論 |
|---|---|---|
| 取得可交易合約資料 | `GET /api/v1/common/symbols` | `type=PERP`、`status=TRADING` 可過濾永續合約；回傳資料包含 `symbol`、`contractType`、`quoteCurrency`、`status`。 |
| 取得 24 小時成交資訊 | `GET /api/v1/market/tickers` | 未指定 `symbol` 時以 `type=PERP` 取得永續合約 24 小時統計，適合作為候選排名來源。 |
| 取得最佳 bid/ask | `GET /api/v1/market/bookTicker` | 可傳單一 `symbol`；若不傳 symbol，`type=PERP` 可取得永續合約最佳 bid/ask 清單。此清單可作為候選行情可用性過濾來源。 |

## 修正依據

使用者日誌顯示 `APR_USDT_PERP` 可在成交統計與 K 線流程出現，但個別 `bookTicker?symbol=APR_USDT_PERP` 回覆 HTTP 404。官方文件指出 `bookTicker` 可用 `type=PERP` 取得永續合約報價清單，因此候選清單應額外和該清單交集，避免將沒有可用最佳 bid/ask 的標的交給進場流程。

## 來源

1. [Pionex Futures API — Market](https://www.pionex.com/docs/api-docs/futures-api/market)，擷取時間 2026-08-15。
2. [Pionex Futures API — Common](https://www.pionex.com/docs/api-docs/futures-api/common)，擷取時間 2026-08-15。
