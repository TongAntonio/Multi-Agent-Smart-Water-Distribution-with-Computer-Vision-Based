| link | scenario | phase | runs | users | success (mean ± std over runs) | low-tank | high-tank | via forward | latency mean / p50 / p95 (s) | dashboard PUT/min |
|---|---|---|---|---|---|---|---|---|---|---|
| lora | baseline | before | 5 | 178 | 100.0 ± 0.0 % | 100 % | 100 % | 34 % | 2.1 / 0.1 / 5.6 | 48.9 |
| lora | baseline | during | 5 | 147 | 100.0 ± 0.0 % | 100 % | 100 % | 50 % | 2.7 / 1.1 / 5.6 | 48.9 |
| lora | baseline | after | 5 | 183 | 100.0 ± 0.0 % | 100 % | 100 % | 52 % | 2.8 / 5.0 / 5.8 | 49.0 |
| lora | broker_whole | before | 5 | 178 | 100.0 ± 0.0 % | 100 % | 100 % | 34 % | 2.1 / 0.1 / 5.7 | 0.0 |
| lora | broker_whole | during | 5 | 147 | 100.0 ± 0.0 % | 100 % | 100 % | 50 % | 2.7 / 1.1 / 5.6 | 0.0 |
| lora | broker_whole | after | 5 | 183 | 100.0 ± 0.0 % | 100 % | 100 % | 52 % | 2.8 / 5.0 / 5.6 | 0.0 |
| lora | broker_window | before | 5 | 178 | 100.0 ± 0.0 % | 100 % | 100 % | 34 % | 2.1 / 0.1 / 5.6 | 48.9 |
| lora | broker_window | during | 5 | 147 | 100.0 ± 0.0 % | 100 % | 100 % | 50 % | 2.7 / 1.1 / 5.6 | 0.0 |
| lora | broker_window | after | 5 | 183 | 100.0 ± 0.0 % | 100 % | 100 % | 52 % | 2.9 / 5.0 / 6.0 | 24.9 |
| lora | gateway_window | before | 5 | 178 | 100.0 ± 0.0 % | 100 % | 100 % | 34 % | 2.1 / 0.1 / 5.7 | 48.9 |
| lora | gateway_window | during | 5 | 147 | 100.0 ± 0.0 % | 100 % | 100 % | 50 % | 2.7 / 1.2 / 5.6 | 0.0 |
| lora | gateway_window | after | 5 | 183 | 100.0 ± 0.0 % | 100 % | 100 % | 52 % | 2.8 / 5.0 / 5.6 | 49.1 |
| mqtt | baseline | before | 5 | 178 | 100.0 ± 0.0 % | 100 % | 100 % | 34 % | 2.1 / 0.1 / 5.7 | 51.9 |
| mqtt | baseline | during | 5 | 147 | 100.0 ± 0.0 % | 100 % | 100 % | 50 % | 2.7 / 1.1 / 5.7 | 52.0 |
| mqtt | baseline | after | 5 | 183 | 100.0 ± 0.0 % | 100 % | 100 % | 52 % | 2.8 / 5.0 / 5.8 | 52.0 |
| mqtt | bridge_window | before | 5 | 178 | 100.0 ± 0.0 % | 100 % | 100 % | 34 % | 2.3 / 0.1 / 5.8 | 51.9 |
| mqtt | bridge_window | during | 5 | 147 | 100.0 ± 0.0 % | 100 % | 100 % | 50 % | 2.6 / 1.1 / 5.5 | 0.0 |
| mqtt | bridge_window | after | 5 | 183 | 100.0 ± 0.0 % | 100 % | 100 % | 52 % | 2.8 / 5.0 / 5.8 | 52.0 |
| mqtt | broker_whole | before | 5 | 178 | 65.2 ± 8.1 % | 29 % | 100 % | 0 % | 0.4 / 0.1 / 4.1 | 0.0 |
| mqtt | broker_whole | during | 5 | 147 | 50.6 ± 6.9 % | 2 % | 100 % | 0 % | 0.1 / 0.1 / 0.1 | 0.0 |
| mqtt | broker_whole | after | 5 | 183 | 48.8 ± 4.9 % | 0 % | 100 % | 0 % | 0.1 / 0.1 / 0.5 | 0.0 |
| mqtt | broker_window | before | 5 | 178 | 100.0 ± 0.0 % | 100 % | 100 % | 34 % | 2.3 / 0.1 / 5.8 | 51.9 |
| mqtt | broker_window | during | 5 | 147 | 88.3 ± 3.1 % | 76 % | 100 % | 43 % | 30.0 / 0.1 / 109.4 | 0.0 |
| mqtt | broker_window | after | 5 | 183 | 100.0 ± 0.0 % | 100 % | 100 % | 52 % | 22.9 / 5.2 / 72.0 | 26.0 |
