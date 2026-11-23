| link | scenario | phase | runs | users | success (mean ± std over runs) | low-tank | high-tank | via forward | latency mean / p50 / p95 (s) | dashboard PUT/min |
|---|---|---|---|---|---|---|---|---|---|---|
| mqtt | broker_window | before | 5 | 178 | 100.0 ± 0.0 % | 100 % | 100 % | 34 % | 1.9 / 0.0 / 5.4 | 51.9 |
| mqtt | broker_window | during | 5 | 147 | 95.9 ± 0.9 % | 92 % | 100 % | 48 % | 36.2 / 0.1 / 115.6 | 0.0 |
| mqtt | broker_window | after | 5 | 183 | 100.0 ± 0.0 % | 100 % | 100 % | 52 % | 13.2 / 5.0 / 49.6 | 32.5 |
