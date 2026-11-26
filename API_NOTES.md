# What the CMC API made possible, and where it got in the way

Written while building, updated with each real measurement. Facts only.

## Made possible

- **One request for 76 tokens.** `/v3/cryptocurrency/quotes/historical` takes a comma-separated `id` list and `interval=10m`, so the incremental scan of the whole universe is one call of 1 credit (measured on 26/11). With exchange APIs the live bot needs one call per token.
- **10-minute history on the free plan.** One month of intraday quotes on Basic covers the RSI warm-up, an hourly market mean (1-hour bars derived from the same 10-minute series) and a 30-day replay.
- **Stable ids.** `/v1/cryptocurrency/map` turns exchange tickers (`PF_XBTUSD`, `PF_SOLUSD`, …) into CMC ids once; after that nothing depends on tickers that collide (there are three active `ADA`, three `XRP`, three `PEPE`).
- **Keyless endpoints.** The symbol map, Fear & Greed and CMC100 work with no key, which made the first steps testable before any signup.
- **Credit cost in every response.** `status.credit_count` lets the tool log exactly what each call cost.

## Got in the way

- **Case-sensitive symbols.** `symbol=XAUT` returns nothing; CMC lists Tether Gold as `XAUt`. A case-insensitive lookup (or a note in the docs) would help.
- **Two shapes for the same response.** The historical-data guide shows `data` as a list; the OpenAPI spec says v3 always returns an object map keyed by the ids sent, and symbol lookups return arrays. The parser accepts all three.
- **Quotes are snapshots, not closes.** At each interval the API returns "the quote closest in time", which can be a few seconds before or after the boundary. For an RSI on closes, each quote is snapped to the bar that ends at the nearest boundary.
- **No intraday OHLCV below Startup.** `/v5/cryptocurrency/ohlcv/historical` is not on Basic or Builder, and its smallest interval is 15 minutes; the 10-minute rule therefore uses `quotes/historical`.
- **Keyless has no history.** Historical quotes need a key, so the screener itself cannot run keyless.

## Measured on the real API

Keyed runs, 26/11/2026, free Basic key (15 000 credits/month, 50 requests/minute), example settings:

| Run | Calls | Credits |
|---|---|---|
| First scan (76 tokens, ~2 days of 10-minute quotes + daily history for the trend means) | 16 | 366 |
| Next scan, one new 10-minute bar (all 76 tokens in one request) | 1 | 1 |
| Replay 30 days (76 tokens) | 50 | 3 435 |

- Median latency about 0.56 s, worst 1.37 s.
- 4 × HTTP 429 (error 1008, per-minute limit) during the replay, while another tool used the same key; all recovered by back-off and retry.
- The 10-minute series came back complete: every token complete, **no gap**, and every timestamp exactly on the 10-minute boundary.
- **10 000 data points per request, across all ids.** The OpenAPI text says the `count` limit is 10 000 periods; the real limit counts points for all ids together (`HTTP 400 "max datapoints allowed is 10000"` with 10 ids × 4 320 points). The client now sizes each batch to stay under it.
