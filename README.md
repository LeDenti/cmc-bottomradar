# BottomRadar on CoinMarketCap

**A crypto dip screener built on the structure of a live trading bot.** BottomRadar runs a 10-minute RSI ladder on a small real account since September 2026. This tool rebuilds that structure on CoinMarketCap data: paper positions, the three regime filters that decide how deep it buys, and a replay that shows what the rule did over the last 30 days, open losses included.

> **Example values.** The levels, rebuy zone and exit shipped in this repository are example values chosen for the demo. The live bot's settings are private and are not published here. You can load your own from `private/rule.json` (git-ignored).

Track: **Markets and Trading Tools** (screener + alerts). Bonus: an MCP server so an AI agent can ask it questions.

> Paper positions only. No orders, no wallet, no exchange keys. Not financial advice.

## What it answers

- **Which tokens are about to hit a ladder step right now?** RSI(14, Wilder) on 10-minute closes for 74 liquid tokens, with the gap to the next step.
- **Would the rule buy deep or shallow?** The deep ladder is allowed only when three filters agree, otherwise the shallow ladder is used:
  1. ETH/BTC closed yesterday above its long trend mean;
  2. the token closed yesterday above its own long trend mean;
  3. the market is falling *together*: an equal-weight index of 33 liquid tokens is below its short mean on 10-minute **and** 1-hour bars.
- **Which paper positions are open, at what average price, and where is the exit?** Exit when RSI crosses back up through the exit level **and** the position is in gain; rebuys when price keeps falling below the last buy, with a cap.
- **Did it work lately?** `replay 30` runs the rule bar by bar over the last 30 days and reports the numbers that matter together: closed trades, median and weighted return, open cost, open latent loss, and market value. Because exits only happen in gain, the win rate of closed trades is always 100 %; the market value is the honest number.

## The rule — structure, with EXAMPLE values

| | Example value shipped here |
|---|---|
| Signal | RSI(14, Wilder) on 10-minute closes; a step fires when RSI crosses **down** through its level |
| Deep ladder | RSI 30, 25, 20, 15, 10 — weights 1 … 5 (× 10 $) |
| Shallow ladder | RSI 25, 20, 15, 10 — weights 1 … 4 (× 10 $) |
| Rebuy | each −12 % below the last buy, weight of the last step, max 3 |
| Exit | RSI crosses **up** through 70 and price ≥ average + 1 % |
| Trend / market means | 100 days / 30 bars |
| Unknown filter | counts as "no" → shallow ladder |

These are **not** the live bot's settings. `bottomradar_cmc/rules.py` holds the structure and the example values; a git-ignored `private/rule.json` with the same keys overrides them, and the outputs then show "private settings" instead of the numbers.

## CoinMarketCap endpoints used

| Endpoint | Why | Cost |
|---|---|---|
| `GET /v1/cryptocurrency/map` | resolve the 76 symbols to stable CMC ids once (ties broken by rank; `XAUt` is case-sensitive) | 1 credit, keyless |
| `GET /v3/cryptocurrency/quotes/historical` `interval=10m` | 10-minute closes for RSI and the market index; 1-hour bars are derived from the same series | 1 credit / 100 points |
| `GET /v3/cryptocurrency/quotes/historical` `interval=daily` | trend means for ETH/BTC and each token | 1 credit / 100 points |
| `GET /v3/fear-and-greed/latest` | context card (not part of the rule) | 1 credit, keyless |
| `GET /v3/index/cmc100-latest` | context card (not part of the rule) | 1 credit, keyless |

Quotes are cached on disk: the first scan loads ~2 days of 10-minute quotes and a few months of daily quotes (enough for the trend means), then each scan only asks for the new points of all tokens in one request (1 call, 1 credit, measured). Every call is logged in `runs/calls.jsonl` (endpoint, parameters, HTTP status, `credit_count`, latency) and one real response per endpoint is kept in `runs/evidence/`.

## Evidence of real API calls

The `evidence/` folder holds a real run of 26 Nov 2026 on the free Basic key, with the example settings:

- `evidence/calls.jsonl` — every call: endpoint, parameters, HTTP status, `credit_count`, latency (the key is never logged);
- `evidence/v3_cryptocurrency_quotes_historical.json` and three more — one real response per endpoint, trimmed;
- `evidence/scan_output.txt`, `evidence/replay_output.txt`, `evidence/report.html`, `evidence/report.png` — what the tool printed from those responses.

The call, in `bottomradar_cmc/market.py`:

```python
doc = cmc.get("/v3/cryptocurrency/quotes/historical", id=",".join(map(str, part)),
              interval=interval, time_start=_iso(now - span_s), time_end=_iso(now),
              aux="price", skip_invalid="true")
```

The response (`status` block, as received):

```json
{
 "timestamp": "2026-11-26T03:22:14.925Z",
 "error_code": 0,
 "error_message": null,
 "elapsed": 19,
 "credit_count": 1,
 "notice": null
}
```

It runs on the **free Basic key**: intraday history of `quotes/historical` is one month on Basic, enough for the 10-minute RSI, the hourly market mean and a 30-day replay.

## Run it

Python 3.9+ and the standard library only (the MCP server needs the `mcp` package).

```bash
cp .env.example .env          # then paste your own key after CMC_API_KEY=
python3 -m bottomradar_cmc map       # symbol -> CMC id (works without a key)
python3 -m bottomradar_cmc context   # Fear & Greed + CMC100 (works without a key)
python3 -m bottomradar_cmc scan      # signals now, paper positions, filters
python3 -m bottomradar_cmc replay 30 # last 30 days, bar by bar
python3 -m bottomradar_cmc report    # runs/report.html
python3 -m bottomradar_cmc calls     # calls and credits used
python3 -m bottomradar_cmc watch 20  # scan every 20 minutes
```

MCP server (tools `scan_now`, `explain`, `replay`, `market_context`):

```bash
uv run --python 3.12 --with mcp python -m bottomradar_cmc mcp
```

Tests (offline, against a fake CMC that answers in the documented v3 shape):

```bash
python3 -m unittest discover -s tests -v
```

## Credits budget

| Action | Credits |
|---|---|
| First scan (76 tokens, ~2 days of 10 min + daily history for the trend means) | 366 (measured) |
| Each following scan | 1 (measured) |
| Daily refresh of the trend means | ~1 |
| Replay 30 days | 3 435 (measured) |

On the free Basic plan (15 000 credits a month), a scan every 20 minutes and a replay a week fit.

## Files

```
bottomradar_cmc/
  client.py     CMC client: key from .env, keyless fallback, 429 back-off, call log and evidence
  market.py     symbol map, disk cache, incremental fetch
  rules.py      the rule structure and its example values
  engine.py     bar-by-bar run, market index, the three filters
  screener.py   scan, replay, context
  report.py     static HTML report
  mcp_server.py MCP tools for agents
  data/         token universe (74 + 33 liquid) and the resolved CMC ids
tests/test_all.py
evidence/       real calls and real responses (26 Nov 2026, example settings)
API_NOTES.md    what the API made possible, and where it got in the way
```

## License

MIT. Built by matter-x- for Build with CMC: API Hackathon Round 2.
