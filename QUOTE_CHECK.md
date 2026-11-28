# Quote check: two fields that would make cross-exchange quotes checkable

**Status: Final figures.** Generated from `evidence/quote_check/quality_report.json` (2026-11-28T05:19:02Z).

CoinMarketCap's `/v5/cryptocurrency/derivatives/market-pairs/list/latest` returns every exchange's quote of a perpetual in one call, for one credit. That is what makes a cross-exchange view possible at all. This study asks one question about that view: **when two exchanges look 0.20% apart on CMC, is the gap in their order books?** It then proposes two small fields that would let any user answer it without doing this work.

It is a data-quality check, not a trading tool. It sends no order and uses no exchange account or exchange key. The only keyed API is CoinMarketCap.

## The sample

- 15 USDT perpetuals: BTC, ETH, XRP, BNB, SOL, DOGE, ADA, TRX, LINK, AVAX, SUI, LTC, DOT, TON, HBAR.
- 11 exchanges whose public order book we can read without an account: binance, bybit, okx, bitget, kucoin, mexc, gate, htx, whitebit, zoomex, phemex.
- 23.9 hours of CMC quotes in 3 stretches between 26 Nov 10:08 and 28 Nov 05:03 UTC 2026, next to 46 hours of order-book readings.
- 578 CMC snapshots (8,661 credits), 5,277 order-book rounds (one every 30 s), 529 depth and funding cycles (one every 5 min).

Everything below is true **in this sample**. It is not a census of CoinMarketCap.

## What we measured

Two different questions, kept apart:

1. **Is the gap in the book?** A *CMC gap* is a quote at least 0.20% away from the median of the same token on the exchanges we can check, on quotes that carry no CMC flag. It is *confirmed* when the exchange's own book, read within 20 s of the CMC call, shows a deviation of the same sign and at least half the size.
2. **Could one trade it at size?** For pairs of exchanges 0.20% apart on CMC, we sell into the bids of one book and buy from the asks of the other, 50 levels deep, for $1,000 and for $10,000, and keep what is left after 0.20% (four taker orders at 0.05%).

| | In our sample |
|---|---|
| CMC quotes compared with a live order book | 70,637 |
| Quotes at least 0.20% away from the median of their token ("CMC gaps") | 5,545 of 70,637 (7.8%) |
| CMC gaps confirmed by the exchange's own book at the same instant | **547 of 5,545 (10%)** |
| CMC gaps not confirmed by the book | **4,998 of 5,545 (90%)** |
| Pairs of exchanges 0.20% apart on CMC that still leave more than 0.20% in the books for $1,000 | 377 of 19,649 (2%) |
| The same for $10,000 | 0 of 19,649 (0%) |

The median CMC gap is 0.49%; for the same quotes, the median deviation in the book is 0.011%.

The median executable gap is -0.028% for $1,000 and -0.057% for $10,000. It is negative because crossing two bid-ask spreads costs more than the difference between the two books: for a typical pair there is nothing to take.

**Quotes CMC already flags.** The table above is about quotes with no flag. Measured the same way, the quotes CMC marks with `exclusions` or `outlier_detected` show 5,152 of 15,947 (32%) gaps, of which 5,027 of 5,152 (98%) are not in the book. The flags do catch many bad quotes; the unflagged ones are where a user has no warning.

## Why a gap is not in the book

Each unconfirmed gap gets one cause, tested in a fixed order. Two prices are "the same" within 0.02% or a quarter of the exchange's spread.

| Cause | Unconfirmed gaps | Share |
|---|---|---|
| Frozen quote: the same price for 5 minutes or more while `last_updated` keeps moving and the live book is elsewhere | 2,456 | 49% |
| Late quote: equal to the exchange's own price at its `last_updated`, or at another moment of the last 15 minutes | 1,812 | 36% |
| The quote is current; the other exchanges' quotes it is compared with are older (a late median) | 339 | 7% |
| Off for long: on the same side of the live price for 5 minutes or more, with no match in the last 15 minutes | 151 | 3% |
| Last trade inside a wide bid-ask spread (thin book) | 15 | 0% |
| Equal to the exchange's mark or index price, not to its last price | 1 | 0% |
| Unexplained one-off: matches no price of the exchange in the last 15 minutes | 224 | 4% |

Three conditions can add to a cause (counted on all CMC gaps, confirmed or not):

- **Shared order book**: 2,170 of 2,170 (100%) such gaps are unconfirmed.
- **Thin book** (a $10,000 round trip costs more than 0.20%, or cannot be filled): 874 of 1,414 (62%) unconfirmed.
- **Deposits or withdrawals closed**: 8 gaps, on the 5 exchanges that publish it without an account (bitget, gate, htx, kucoin, whitebit).

### Where the gaps come from

| Exchange | Quotes checked | CMC gaps | Confirmed by the book | Frozen quotes | Measured lag |
|---|---|---|---|---|---|
| zoomex | 2,818 | 2,153 | 0 of 2,153 (0%) | 2,249 of 2,818 (80%) | 5400 s |
| okx | 7,386 | 1,881 | 0 of 1,881 (0%) | 446 of 7,386 (6%) | 840 s |
| whitebit | 3,965 | 793 | 536 of 793 (68%) | 194 of 3,965 (5%) | 180 s |
| htx | 7,153 | 493 | 1 of 493 (0%) | 524 of 7,153 (7%) | 150 s |
| phemex | 7,912 | 78 | 8 of 78 (10%) | 326 of 7,912 (4%) | 150 s |
| kucoin | 7,926 | 58 | 0 of 58 (0%) | 212 of 7,926 (3%) | 150 s |
| binance | 8,389 | 38 | 0 of 38 (0%) | 317 of 8,389 (4%) | 150 s |
| bybit | 8,406 | 17 | 0 of 17 (0%) | 397 of 8,406 (5%) | 120 s |
| bitget | 7,909 | 14 | 2 of 14 (14%) | 338 of 7,909 (4%) | 120 s |
| mexc | 7,921 | 14 | 0 of 14 (0%) | 238 of 7,921 (3%) | 150 s |
| gate | 852 | 6 | 0 of 6 (0%) | 48 of 852 (6%) | 150 s |

Three things stand out in this sample:

- **A shared order book listed as two markets.** Zoomex shows the same best bid and best ask as Bybit in 92% of the rounds. A gap between the two on CMC is a gap between two views of one book: 0 of 2,153 (0%) of the Zoomex gaps are confirmed.
- **A frozen feed stamped as fresh.** On 26 Nov 2026 the HTX public host `api.hbdm.com` served a snapshot frozen at 07:11:38 UTC (BTC last price 60,430.2), while HTX's other host `api.hbdm.vn` was live near 60,885. From 10:08 to 10:14 UTC, CMC's HTX quote for BTC was that same 60,430.2, with a `last_updated` two to four minutes old and no flag, about 0.7% below the other large exchanges. The rows are in `evidence/quote_check/htx_frozen_feed.json`. Our own sampler was caught by the same feed (see "Our own biases"), which is how we noticed.
- **A lag larger than the timestamp says.** For OKX, `last_updated` claims a median age of 147 s; the delay that best lines the CMC price up with OKX's own price is 840 s.

Most confirmed gaps sit on one exchange: whitebit confirms 536 of 793 (68%), mostly on TON, where the book is thin.

## Two fields CMC could publish

CoinMarketCap already sees every exchange's feed. Two fields would turn the cross-exchange view into something a user can trust at a glance, and both are computed per exchange in section D of the report.

1. **A freshness indicator per quote.** `last_updated` moves even when the price does not, so a live quote and a frozen one look the same. Proposal: the time of the exchange's own last tick, and a flag when a price has not changed for N minutes while the same token moved elsewhere.
2. **A "shared book" flag per market.** Two markets that show the same best bid and ask most of the time are one book. Proposal: a field naming the exchange whose book it is, so that a gap between the two is known to be an artefact and the liquidity is not counted twice.

## Our own biases

A quality check has to check itself. These flaws are ours, are measured in section A of the report, and are removed from every figure.

1. **Slow answers, partly caused by our own second sampler.** While the depth sampler reads 165 order books, some exchanges answer the book sampler late. Any answer slower than 5 s is dropped and never counted against the exchange or against CMC. Bybit: 169 rounds dropped; Gate: 1,362 of 5,277.
2. **A frozen feed on our side too.** Our first sampler read HTX through `api.hbdm.com` and recorded the frozen snapshot for hours on 26 Nov. Those 324 rounds are excluded; the sampler now reads `api.hbdm.vn` and rejects any tick older than 30 s.
3. **Holes in the CMC series.** The CMC sampler stopped on a dropped connection on 26 Nov and was restarted the next morning; the samplers were also paused for about 1 h 40 on 27 Nov while the laptop was on battery. No CMC quote is paired with a book across a hole (longest hole in the books: 97 min).

## Limits

- 15 tokens, 11 exchanges, 24 hours of CMC quotes: a sample.
- CMC is read every 150 s and the books every 30 s; a gap that lives less than that is invisible.
- Depth is read on 50 levels every 5 minutes.
- Perpetuals only: `/v2/cryptocurrency/market-pairs/latest` (spot pairs) answers HTTP 403 on the Basic and Startup plans.

## Reproduce it

- One live snapshot, 8 credits: `python3 -m bottomradar_cmc gaps` (see the main README).
- The full analysis on the 45-minute sample shipped in `study/runs/` (no network, 0 credit):

```bash
cd study
python3 verif/qualite.py cmc=sample_cmc.jsonl books=sample_books.jsonl ctx=sample_ctx.jsonl
```

- The samplers that produced the data are in `study/verif/` (`cotes_cmc.py` for CMC, 15 credits per snapshot; `carnets.py`, `contexte.py` and `htx_hotes.py` for the public exchange endpoints). See `study/README.md`.
- The complete measured report: [`evidence/quote_check/quality_report.md`](evidence/quote_check/quality_report.md) and its raw numbers in `quality_report.json`.
