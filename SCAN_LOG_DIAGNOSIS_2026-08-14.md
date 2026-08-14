# 2026-08-14 掃描日誌診斷

本文件根據使用者提供的終端機截圖逐行整理；僅記錄已在畫面中清楚可辨識的內容，不含任何機密資料。

| 時間（截圖） | 交易對 | 事件／結果 | 判讀 |
|---|---|---|---|
| 22:05:40.151 | SKHX_USDT_PERP | `SIGNAL: LONG` | 策略已找到多頭突破訊號。 |
| 22:05:40.656 | SKHX_USDT_PERP | `SCAN_SYMBOL_ERROR`：不再是可交易的 USDT 永續合約 | 在進場前合約規格檢查被交易所資料攔下，未送單。 |
| 22:05:40.837–22:05:41.766 | MUX、SOXLX、SPCX、XAU、SNXXX | `SIGNAL: HOLD` | 該已完成 K 線未同時滿足布林突破與 RSI 確認，不應送單。 |
| 22:05:41.976 | HYPE_USDT_PERP | `SIGNAL: SHORT` | 策略已找到空頭突破訊號。 |
| 22:05:42.266 | HYPE_USDT_PERP | `SCAN_SYMBOL_ERROR`：不再是可交易的 USDT 永續合約 | 在進場前合約規格檢查被交易所資料攔下，未送單。 |
| 22:05:42.452–22:05:42.646 | ACE、XAG | ACE 為 `HOLD`；XAG 為 `LONG` | XAG 已找到多頭訊號，ACE 無訊號。 |
| 22:05:43.145 | XAG_USDT_PERP | `SCAN_SYMBOL_ERROR`：不再是可交易的 USDT 永續合約 | 在進場前合約規格檢查被交易所資料攔下，未送單。 |
| 22:05:43.328–22:05:43.699 | ADA、APR、WTI | `SIGNAL: HOLD` | 該已完成 K 線未同時滿足策略進場條件，不應送單。 |

## 結論

截圖證實本輪不是「完全沒有訊號」：SKHX 的 LONG、HYPE 的 SHORT 與 XAG 的 LONG 都有產生。這三個訊號在下單前被「不再是可交易的 USDT 永續合約」檢查攔下；其餘可見交易對是 HOLD。此前修正已統一接受派網可能回傳的 `type=PERP` 與 `contractType=PERPETUAL` 格式，避免有效永續合約因欄位格式不同被錯誤拒絕；真實已下架、暫停或非 USDT 永續合約仍會維持拒絕，不會嘗試下單。
