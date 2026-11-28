# BottomRadar on CoinMarketCap

**A crypto dip screener built on the structure of a live trading bot.** BottomRadar runs a 10-minute RSI ladder on a small real account since September 2026. This tool rebuilds that structure on CoinMarketCap data: paper positions, the three regime filters that decide how deep it buys, and a replay that shows what the rule did over the last 30 days, open losses included.

> **Example values.** The levels, rebuy zone and exit shipped in this repository are example values chosen for the demo. The live bot's settings are private and are not published here. You can load your own from `private/rule.json` (git-ignored).

It also runs a second scan built on CoinMarketCap's derivatives data: **when two exchanges look apart on CMC, is the gap in their order books?** It measures it, explains it, and proposes two small fields that would make every cross-exchange quote checkable ([QUOTE_CHECK.md](QUOTE_CHECK.md)).

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

## The second scan: are the gaps real?

CoinMarketCap returns every exchange's quote of a perpetual in one call, for one credit. A screener can turn that into "BTC is 0.6 % cheaper on exchange X", which invites people to trade a gap. Before showing one, this tool checks it.

`python3 -m bottomradar_cmc gaps` takes, for 8 perpetuals, the quote of every exchange from CoinMarketCap, reads the best bid and best ask of the same exchanges from their own public endpoints at the same instant (no account, no key, no order), and compares:

- **CMC gap**: the exchange's price on CMC against the median of the exchanges on CMC;
- **book gap**: the exchange's mid price in its own order book against the median of the books.

A CMC gap of at least 0.20 % is *confirmed* when the book shows a gap of the same sign and at least half the size. A real run (26 Nov 2026, 10:26 UTC, 8 credits):

```
CMC quotes vs real order books, 2026-11-26 10:26 UTC
80 quotes checked on 11 exchanges, 8 tokens | median CMC quote age 116 s
CMC gaps of at least 0.20 %: 13 | confirmed in the book: 2 | not in the book: 11
token  exchange     CMC gap   book gap   age s  verdict
SUI    zoomex        +1.93%     +0.00%     118  not in the book
TON    whitebit      +0.85%     +0.66%     121  confirmed
ETH    htx           -0.81%     +0.00%     115  not in the book
TON    zoomex        +0.62%     +0.07%     120  not in the book
BTC    htx           -0.60%     +0.01%     114  not in the book
HBAR   zoomex        -0.45%     +0.00%     121  not in the book
DOT    zoomex        -0.34%     +0.01%     122  not in the book
XRP    zoomex        +0.33%     +0.00%     117  not in the book
DOT    whitebit      -0.24%     -0.20%     123  confirmed
ETH    okx           +0.22%     +0.00%     101  not in the book
DOT    okx           +0.22%     +0.02%     108  not in the book
SOL    okx           +0.21%     +0.00%     102  not in the book
BTC    okx           +0.20%     -0.00%     100  not in the book
API: 8 calls, 8 credits this run
```

In this snapshot 2 of 13 gaps were in the book. The quotes were about two minutes old by CMC's own `last_updated`, and a late or frozen quote looks the same as a live one in the response. This is a data-quality check, not a trading signal: the two confirmed gaps sit on thin books.

<!-- QC:START -->
### The longer measurement

One snapshot is an anecdote, so the same check ran for longer: 23.9 hours of CMC quotes in 3 stretches between 26 Nov 10:08 and 28 Nov 05:03 UTC 2026, next to 46 hours of order-book readings, on 15 perpetuals and 11 exchanges (final figures).

| | In our sample |
|---|---|
| CMC quotes compared with a live order book | 70,637 |
| Quotes at least 0.20% away from the median of their token ("CMC gaps") | 5,545 of 70,637 (7.8%) |
| CMC gaps confirmed by the exchange's own book at the same instant | **547 of 5,545 (10%)** |
| CMC gaps not confirmed by the book | **4,998 of 5,545 (90%)** |
| Pairs of exchanges 0.20% apart on CMC that still leave more than 0.20% in the books for $1,000 | 377 of 19,649 (2%) |
| The same for $10,000 | 0 of 19,649 (0%) |

Of the unconfirmed gaps, 49% are frozen quotes whose `last_updated` keeps moving and 36% are late quotes. The write-up, with the causes, our own biases and **two fields CoinMarketCap could publish to make these quotes checkable** (a freshness indicator and a shared-book flag), is in [QUOTE_CHECK.md](QUOTE_CHECK.md); the scripts and a data sample are in [`study/`](study/).
<!-- QC:END -->

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
| `GET /v5/cryptocurrency/derivatives/market-pairs/list/latest` | every exchange's quote of a perpetual, for the gap check | 1 credit per token |
| `GET /v3/fear-and-greed/latest` | context card (not part of the rule) | 1 credit, keyless |
| `GET /v3/index/cmc100-latest` | context card (not part of the rule) | 1 credit, keyless |

Quotes are cached on disk: the first scan loads ~2 days of 10-minute quotes and a few months of daily quotes (enough for the trend means), then each scan only asks for the new points of all tokens in one request (1 call, 1 credit, measured). Every call is logged in `runs/calls.jsonl` (endpoint, parameters, HTTP status, `credit_count`, latency) and one real response per endpoint is kept in `runs/evidence/`.

## Evidence of real API calls

The `evidence/` folder holds a real run of 26 Nov 2026 on the free Basic key, with the example settings:

- `evidence/calls.jsonl` — every call: endpoint, parameters, HTTP status, `credit_count`, latency (the key is never logged);
- `evidence/v3_cryptocurrency_quotes_historical.json` and three more — one real response per endpoint, trimmed;
- `evidence/scan_output.txt`, `evidence/replay_output.txt`, `evidence/gaps_output.txt`, `evidence/gaps.json`, `evidence/report.html`, `evidence/report.png` — what the tool printed from those responses.

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
python3 -m bottomradar_cmc gaps      # are the gaps CMC shows in the real order books?
python3 -m bottomradar_cmc report    # runs/report.html
python3 -m bottomradar_cmc calls     # calls and credits used
python3 -m bottomradar_cmc watch 20  # scan every 20 minutes
```

MCP server (tools `scan_now`, `explain`, `replay`, `market_context`, `check_gaps`):

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
| Gap check, 8 perpetuals | 8 (measured) |

On the free Basic plan (15 000 credits a month), a scan every 20 minutes and a replay a week fit.

## Files

```
bottomradar_cmc/
  client.py     CMC client: key from .env, keyless fallback, 429 back-off, call log and evidence
  market.py     symbol map, disk cache, incremental fetch
  rules.py      the rule structure and its example values
  engine.py     bar-by-bar run, market index, the three filters
  screener.py   scan, replay, context, gap check
  gaps.py       CMC quotes of perpetuals against the order books
  books.py      best bid / ask from 11 exchanges' public endpoints (no key)
  report.py     static HTML report
  mcp_server.py MCP tools for agents
  data/         token universe (74 + 33 liquid) and the resolved CMC ids
tests/test_all.py
evidence/       real calls and real responses (26 Nov 2026, example settings); quote_check/ holds the measured report
QUOTE_CHECK.md  the longer measurement: findings, causes, two fields CMC could publish, our own biases
study/          the samplers and the analysis behind it, with a 45-minute data sample
API_NOTES.md    what the API made possible, and where it got in the way
```

## License

MIT. Built by matter-x- for Build with CMC: API Hackathon Round 2.
