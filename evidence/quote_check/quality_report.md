# CMC quote quality check — measured report

Generated 2026-11-28 05:18 UTC from the samplers' files. No order, no account, no exchange key; CMC is the only keyed API.

## A. Coverage and our own biases

- Order books: 5277 rounds over 45.7 h (26/11 07:24 → 28/11 05:04 UTC), one every 30 s, 15 perpetuals × 11 exchanges.
- Holes longer than 90 s between two rounds: 3 (longest 5842 s at 27/11 13:26 UTC).
- Holes of 10 min or more in the order books (our samplers were stopped): 27/11 13:26 → 27/11 15:04 UTC. Nothing is paired across a hole: a CMC quote is only compared with a book read within 20 s of it.
- CMC: 578 snapshots, 8661 credits. Context (funding, depth, deposits and withdrawals): 529 cycles.
- CMC was sampled over 23.9 h in 3 stretches: 26/11 10:08 → 26/11 14:09 (98 snapshots); 27/11 07:29 → 27/11 13:24 (143 snapshots); 27/11 15:03 → 28/11 05:03 (337 snapshots) UTC. Sections B to D only cover those hours; section E covers the whole run of the order books.
- No CMC quote exists between those stretches (26/11 14:09 → 27/11 07:29; 27/11 13:24 → 27/11 15:03 UTC). Both holes are our own doing, not CMC's: on 26/11 at 14:10 UTC our CMC sampler stopped on a dropped connection it did not catch (fixed, started again on 27/11 at 07:29 UTC); on 27/11 from 13:26 to 15:04 UTC all four samplers were paused while the computer ran on battery.
- Share of book rounds that overlap one of our own context cycles: 576 / 5277 (11 %).

**Bias 1 — slow answers, partly caused by our own second sampler.** While the context sampler reads 165 order books, some exchanges (first seen on Bybit and Gate) answer the book sampler late. An answer slower than 5 s is dropped and never counted against the exchange or against CMC: it is a flaw of our set-up, not of their data. The third column shows how much of it falls inside our own context cycles; the share expected by chance is 11 %.

| Exchange | Rounds dropped as slow | Of which during our own context cycle | Rounds with no answer | Rounds dropped as frozen |
|---|---|---|---|---|
| binance | 167 / 5277 (3 %) | 37 / 167 (22 %) | 64 | 0 |
| bybit | 169 / 5277 (3 %) | 38 / 169 (22 %) | 70 | 0 |
| okx | 88 / 5277 (2 %) | 23 / 88 (26 %) | 73 | 0 |
| bitget | 127 / 5277 (2 %) | 31 / 127 (24 %) | 75 | 0 |
| kucoin | 90 / 5277 (2 %) | 22 / 90 (24 %) | 78 | 0 |
| mexc | 129 / 5277 (2 %) | 30 / 129 (23 %) | 77 | 0 |
| gate | 1362 / 5277 (26 %) | 185 / 1362 (14 %) | 83 | 0 |
| htx | 191 / 5277 (4 %) | 36 / 191 (19 %) | 81 | 324 |
| whitebit | 79 / 5277 (1 %) | 19 / 79 (24 %) | 72 | 0 |
| zoomex | 137 / 5277 (3 %) | 33 / 137 (24 %) | 71 | 0 |
| phemex | 79 / 5277 (1 %) | 19 / 79 (24 %) | 65 | 0 |

**Bias 2 — a frozen public feed.** A feed whose BTC best bid and ask do not move for 10 rounds (5 min) is dropped. On 26/11/2026 the host `api.hbdm.com` of HTX served the same snapshot from 07:11 UTC; the sampler was moved to `api.hbdm.vn` at 10:12 UTC and now rejects any tick older than 30 s. HTX rows before that are excluded.

## B. The finding

A **CMC gap** is a quote at least 0.20 % away from the median of the same token on the exchanges we can check (CMC flags `outlier_detected` and `exclusions` clear). It is **confirmed** when the exchange's own book, read within 20 s of the CMC call, shows a deviation of the same sign and at least half the size.

- CMC quotes compared with a live book: **70637**.
- CMC gaps of 0.20 % or more: **5545** (7.8 % of the quotes).
- Confirmed by the book at the same instant: **547 / 5545 (10 %)**.
- Confirmed by the book at the quote's own `last_updated`: 944 / 5545 (17 %).
- Median size of a CMC gap: 0.49 %; median size of the same deviation in the book: 0.011 %.

| Threshold | CMC gaps | Confirmed by the book |
|---|---|---|
| 0.10 % | 9909 | 1055 / 9909 (11 %) |
| 0.20 % | 5545 | 547 / 5545 (10 %) |
| 0.50 % | 2743 | 399 / 2743 (15 %) |
| 1.00 % | 1413 | 26 / 1413 (2 %) |

**What CMC's own flags already catch.** The quotes above carry no flag. The quotes CMC marks with `exclusions` or `outlier_detected` on the same exchanges, measured the same way:

| Quotes | Checked | Gaps of 0.20 % or more | Of which not confirmed by the book |
|---|---|---|---|
| No flag from CMC | 70637 | 5545 / 70637 (8 %) | 4998 / 5545 (90 %) |
| Flagged by CMC | 15947 | 5152 / 15947 (32 %) | 5027 / 5152 (98 %) |

| Token | CMC gaps | Confirmed | | Exchange | CMC gaps | Confirmed |
|---|---|---|---|---|---|---|
| TON | 1362 | 539 / 1362 (40 %) | | zoomex | 2153 | 0 / 2153 (0 %) |
| SUI | 827 | 0 / 827 (0 %) | | okx | 1881 | 0 / 1881 (0 %) |
| HBAR | 741 | 0 / 741 (0 %) | | whitebit | 793 | 536 / 793 (68 %) |
| DOT | 695 | 2 / 695 (0 %) | | htx | 493 | 1 / 493 (0 %) |
| LINK | 261 | 0 / 261 (0 %) | | phemex | 78 | 8 / 78 (10 %) |
| LTC | 235 | 0 / 235 (0 %) | | kucoin | 58 | 0 / 58 (0 %) |
| SOL | 197 | 0 / 197 (0 %) | | binance | 38 | 0 / 38 (0 %) |
| ADA | 193 | 0 / 193 (0 %) | | bybit | 17 | 0 / 17 (0 %) |
| DOGE | 189 | 0 / 189 (0 %) | | bitget | 14 | 2 / 14 (14 %) |
| ETH | 171 | 0 / 171 (0 %) | | mexc | 14 | 0 / 14 (0 %) |
| XRP | 169 | 0 / 169 (0 %) | | gate | 6 | 0 / 6 (0 %) |
| AVAX | 163 | 1 / 163 (1 %) | |  | |  |
| BTC | 150 | 0 / 150 (0 %) | |  | |  |
| BNB | 146 | 5 / 146 (3 %) | |  | |  |
| TRX | 46 | 0 / 46 (0 %) | |  | |  |

**At which sizes.** Same test on pairs of exchanges (buy where CMC shows the token cheap, sell where CMC shows it dear), with the depth of both books read at most 75 s from the CMC call: sell at the average price of the bids, buy at the average price of the asks, 50 levels deep.

CMC pair gaps of 0.20 % or more with both depths read: **19649** (median CMC gap 0.48 %).

| Size | Median executable gap | Still positive | Above 0.20 % (4 taker orders at 0.05 %) | At least half the CMC gap | Not fillable in 50 levels |
|---|---|---|---|---|---|
| Best bid / best ask | -0.015 % | 5033 / 19649 (26 %) | 1041 / 19649 (5 %) | 336 / 19649 (2 %) | 0 / 19649 (0 %) |
| 1 000 $ | -0.028 % | 4433 / 19649 (23 %) | 377 / 19649 (2 %) | 184 / 19649 (1 %) | 0 / 19649 (0 %) |
| 10 000 $ | -0.057 % | 2144 / 19649 (11 %) | 0 / 19649 (0 %) | 33 / 19649 (0 %) | 4 / 19649 (0 %) |

## C. The causes, classified

Each CMC gap that the book does not confirm gets one cause, tested in this order. Prices are "the same" within 0.02 % or a quarter of the exchange's spread.

| Cause | False gaps | Share |
|---|---|---|
| Frozen quote: same price for 5 min or more, `last_updated` still moving, the book elsewhere | 2456 | 49 % |
| Late quote: right at its own `last_updated`, the market moved since | 276 | 6 % |
| Late quote: equal to the exchange's price at another moment of the last 15 min | 1536 | 31 % |
| This quote is current; the other exchanges' quotes it is compared with are older | 339 | 7 % |
| Last trade inside a wide bid-ask spread (thin book) | 15 | 0 % |
| Equal to the exchange's mark or index price, not to its last price | 1 | 0 % |
| Off for long: on the same side of the live price for 5 min or more, no match in the last 15 min (older than 15 min, or not this exchange's price) | 151 | 3 % |
| Unexplained one-off: matches no price of the exchange in the last 15 min | 224 | 4 % |

Three conditions can add to a cause. They are counted on all CMC gaps, confirmed or not:

| Condition | CMC gaps concerned | Of which not confirmed |
|---|---|---|
| The exchange shows another exchange's order book (shared book) | 2170 | 2170 / 2170 (100 %) |
| Thin book: a 10 000 $ round trip costs more than 0.20 % or cannot be filled | 1414 | 874 / 1414 (62 %) |
| Deposits or withdrawals of the token closed at least once (5 exchanges readable) | 8 | 8 / 8 (100 %) |

### C0. Frozen quotes stamped as fresh

A CMC price that stays exactly the same for 290 s or more while its `last_updated` keeps moving, and while the exchange's live price is somewhere else (further than the tolerance).

| Exchange | Quotes checked | Frozen | Longest run with the same price | Median distance to the live price when frozen |
|---|---|---|---|---|
| binance | 8389 | 317 / 8389 (4 %) | 23 min | 0.10 % |
| bybit | 8406 | 397 / 8406 (5 %) | 27 min | 0.09 % |
| okx | 7386 | 446 / 7386 (6 %) | 15 min | 0.13 % |
| bitget | 7909 | 338 / 7909 (4 %) | 28 min | 0.12 % |
| kucoin | 7926 | 212 / 7926 (3 %) | 10 min | 0.09 % |
| mexc | 7921 | 238 / 7921 (3 %) | 13 min | 0.10 % |
| gate | 852 | 48 / 852 (6 %) | 10 min | 0.11 % |
| htx | 7153 | 524 / 7153 (7 %) | 96 min | 0.16 % |
| whitebit | 3965 | 194 / 3965 (5 %) | 23 min | 0.10 % |
| zoomex | 2818 | 2249 / 2818 (80 %) | 840 min | 1.12 % |
| phemex | 7912 | 326 / 7912 (4 %) | 20 min | 0.10 % |

### C1. Late quotes: claimed age against measured lag

CMC's own `last_updated` says the quotes are 136 s old in median (5 % are younger than 44 s, 5 % older than 291 s). The **measured lag** is the delay that best lines the CMC price up with the exchange's own price over the whole run (median absolute error, delays tried from 0 to 900 s by 30 s, then up to 3 h).

| Exchange | Claimed age (median) | Measured lag (median over tokens) | Error left at that lag | Closest reference |
|---|---|---|---|---|
| binance | 132 s | 150 s | 0.026 % | mid ×10, last ×5 |
| bybit | 133 s | 120 s | 0.024 % | last ×8, mid ×7 |
| okx | 147 s | 840 s | 0.030 % | last ×8, mid ×7 |
| bitget | 133 s | 120 s | 0.021 % | last ×10, mid ×4 |
| kucoin | 130 s | 150 s | 0.027 % | last ×9, mid ×5 |
| mexc | 133 s | 150 s | 0.025 % | mid ×9, last ×4, mark ×1 |
| gate | 130 s | 150 s | 0.014 % | last ×2 |
| htx | 158 s | 150 s | 0.026 % | last ×12, mid ×1 |
| whitebit | 196 s | 180 s | 0.031 % | last ×7 |
| zoomex | 144 s | 5400 s | 0.753 % | mid ×2, last ×1, mark ×1, index ×1 |
| phemex | 133 s | 150 s | 0.022 % | mid ×7, last ×7 |

### C2. Mark or index instead of the last price

Token and exchange pairs where the CMC price follows the mark or the index more closely than the last price:

| Token | Exchange | Follows | Error against it | Error against the last price |
|---|---|---|---|---|
| ADA | binance | mark | 0.048 % | 0.066 % |
| DOT | zoomex | index | 0.647 % | 0.692 % |
| LTC | mexc | mark | 0.023 % | 0.044 % |
| TON | binance | mark | 0.051 % | 0.100 % |

CMC also carries an `index_price` per quote: against the exchange's own index it is off by 0.127 % in median (48017 points).

### C3. Shared order books

Two exchanges with exactly the same best bid and best ask at the same instant, on fine-tick tokens (BTC, ETH, SOL, BNB). Between independent exchanges this happens in 1.1 % of the rounds (median of all pairs).

Above 80 % with the same money in the book, the two exchanges show **one and the same order book**. Between 30 and 80 %, the best prices are pegged by market makers but the books differ.

| Pair | Rounds with an identical best bid and ask | Money in the book, first / second | Reading | CMC price difference between the two (median) | Gaps of 0.20 % between them on CMC |
|---|---|---|---|---|---|
| bybit = zoomex | 92 % of 20272 | 0.80 | shared book | 0.936 % | 2153 / 2808 (77 %) |
| binance = mexc | 54 % of 20248 | 0.11 | pegged best prices | 0.011 % | 25 / 7826 (0 %) |
| binance = phemex | 44 % of 20316 | 0.43 | pegged best prices | 0.015 % | 152 / 7827 (2 %) |
| mexc = phemex | 35 % of 20436 | 5.04 | pegged best prices | 0.015 % | 26 / 7341 (0 %) |

### C4. Thin books

Median over the run, from 50 levels of each book. Listed: a 10 000 $ round trip (buy then sell at once) costs more than 0.20 %, or cannot be filled in more than 10 % of the readings.

| Token | Exchange | Spread | 1 000 $ round trip | 10 000 $ round trip | 10 000 $ not fillable | Money in the thinner side | CMC gaps here |
|---|---|---|---|---|---|---|---|
| TON | phemex | 0.105 % | 0.371 % | 1.581 % | 0 % | 43 607 $ | 63 |
| TON | whitebit | 0.577 % | 0.665 % | 0.919 % | 0 % | 234 318 $ | 544 |
| HBAR | htx | 0.235 % | 0.307 % | 0.649 % | 0 % | 20 151 $ | 0 |
| TON | htx | 0.172 % | 0.276 % | 0.560 % | 0 % | 37 130 $ | 0 |
| TON | kucoin | 0.083 % | 0.165 % | 0.517 % | 0 % | 58 600 $ | 0 |
| DOT | htx | 0.180 % | 0.344 % | 0.513 % | 0 % | 77 936 $ | 45 |
| AVAX | htx | 0.252 % | 0.315 % | 0.446 % | 0 % | 217 056 $ | 35 |
| DOT | whitebit | 0.074 % | 0.144 % | 0.402 % | 0 % | 932 817 $ | 0 |
| ADA | whitebit | 0.135 % | 0.195 % | 0.356 % | 0 % | 3 397 945 $ | 0 |
| DOT | gate | 0.149 % | 0.151 % | 0.278 % | 0 % | 3 190 605 $ | 0 |
| DOT | phemex | 0.149 % | 0.150 % | 0.258 % | 0 % | 1 196 679 $ | 0 |
| TON | gate | 0.084 % | 0.122 % | 0.245 % | 0 % | 78 617 $ | 0 |
| TON | bybit | 0.103 % | 0.104 % | 0.231 % | 0 % | 396 835 $ | 14 |
| TON | zoomex | 0.103 % | 0.104 % | 0.230 % | 0 % | 397 117 $ | 564 |
| TON | okx | 0.010 % | 0.074 % | 0.217 % | 0 % | 42 523 $ | 149 |

### C5. Deposits and withdrawals

Read once an hour where the exchange publishes it without an account: bitget, gate, htx, kucoin, whitebit. Not readable without an account: binance, bybit, okx, mexc, zoomex, phemex.

| Exchange | Coin | Checks | Deposit closed | Withdrawal closed |
|---|---|---|---|---|
| kucoin | HBAR | 45 | 9 | 9 |

## D. Two indicators CMC could publish, computed here

**Freshness** = how far the CMC quote is from the exchange's live last price at the instant of the API call, the delay that explains it, and whether the price is frozen. **Shared book** = the exchange shows another exchange's order book, so it is not a second market.

| Exchange | Quotes checked | Median distance to the live price | Measured lag | Frozen quotes | Shared book with | CMC gaps | Confirmed |
|---|---|---|---|---|---|---|---|
| binance | 8389 | 0.056 % | 150 s | 317 / 8389 (4 %) | - | 38 | 0 / 38 (0 %) |
| bybit | 8406 | 0.054 % | 120 s | 397 / 8406 (5 %) | zoomex | 17 | 0 / 17 (0 %) |
| okx | 7386 | 0.122 % | 840 s | 446 / 7386 (6 %) | - | 1881 | 0 / 1881 (0 %) |
| bitget | 7909 | 0.050 % | 120 s | 338 / 7909 (4 %) | - | 14 | 2 / 14 (14 %) |
| kucoin | 7926 | 0.054 % | 150 s | 212 / 7926 (3 %) | - | 58 | 0 / 58 (0 %) |
| mexc | 7921 | 0.053 % | 150 s | 238 / 7921 (3 %) | - | 14 | 0 / 14 (0 %) |
| gate | 852 | 0.068 % | 150 s | 48 / 852 (6 %) | - | 6 | 0 / 6 (0 %) |
| htx | 7153 | 0.059 % | 150 s | 524 / 7153 (7 %) | - | 493 | 1 / 493 (0 %) |
| whitebit | 3965 | 0.075 % | 180 s | 194 / 3965 (5 %) | - | 793 | 536 / 793 (68 %) |
| zoomex | 2818 | 0.936 % | 5400 s | 2249 / 2818 (80 %) | bybit | 2153 | 0 / 2153 (0 %) |
| phemex | 7912 | 0.052 % | 150 s | 326 / 7912 (4 %) | - | 78 | 8 / 78 (10 %) |

## E. What is left once the data is right

Sections B to D are about CMC's quotes. This one uses only the exchanges' own data over the whole run (45.7 h of order books, 529 context cycles): the gaps that do exist in the books, and the funding paid on each side.

### E1. Real gaps between two order books

Executable gap = sell at the best bid of one exchange, buy at the best ask of the other, same round (810 token and exchange pairs, 7780410 measures; Bybit and Zoomex are one book and are not paired).

- Median executable gap: -0.018 %.
- Measures above 0.20 % (the fees of 4 taker orders): 51350 / 7780410 (1 %).

| Token | Sell on | Buy on | Rounds with a gap above 0.20 % | Median gap | Lowest | Highest |
|---|---|---|---|---|---|---|
| TON | whitebit | bitget | 4815 / 5116 (94 %) | +0.321 % | -0.061 % | +0.557 % |
| TON | whitebit | okx | 4821 / 5147 (94 %) | +0.291 % | -0.072 % | +0.506 % |
| TON | whitebit | binance | 4709 / 5079 (93 %) | +0.255 % | -0.133 % | +0.446 % |
| TON | whitebit | mexc | 4733 / 5109 (93 %) | +0.257 % | -0.238 % | +0.472 % |
| TON | whitebit | gate | 3227 / 3884 (83 %) | +0.248 % | -0.289 % | +0.608 % |
| TON | whitebit | phemex | 3823 / 5154 (74 %) | +0.244 % | -0.249 % | +0.388 % |
| TON | whitebit | zoomex | 3413 / 5107 (67 %) | +0.239 % | -0.135 % | +0.435 % |
| TON | whitebit | bybit | 3389 / 5073 (67 %) | +0.239 % | -0.135 % | +0.435 % |

Replay on the books. A gap of the entry level is seen; the position opens, and closes as soon as undoing both legs leaves a profit after 0.20 % of fees; otherwise it is valued at the last round. One position at a time per token and pair, best bid and ask only (size unknown), no slippage. Inside one round the two books are read up to 5 s apart, so a gap seen in a single round can be an effect of our own reading order: the second half of the table opens the position one round later (30 s), at the gap found then.

| Entry | Gap seen at | Positions | Closed with a profit | Median time to close | Left open at the end | Median result of those left open | Sum of all results | Mean per position |
|---|---|---|---|---|---|---|---|---|
| 0.20 % | the same round | 419 | 368 / 419 (88 %) | 30 s | 51 | -0.248 % | +17.2 % | +0.041 % |
| 0.30 % | the same round | 128 | 106 / 128 (83 %) | 30 s | 22 | -0.373 % | +7.7 % | +0.060 % |
| 0.50 % | the same round | 13 | 9 / 13 (69 %) | 150 s | 4 | -0.614 % | -2.0 % | -0.152 % |
| 0.20 % | 30 s later | 361 | 46 / 361 (13 %) | 10.4 h | 315 | -0.266 % | -93.2 % | -0.258 % |
| 0.30 % | 30 s later | 117 | 16 / 117 (14 %) | 13.9 h | 101 | -0.330 % | -36.9 % | -0.316 % |
| 0.50 % | 30 s later | 13 | 9 / 13 (69 %) | 120 s | 4 | -0.792 % | -2.7 % | -0.206 % |

The sum is in % of one position's size, all positions added. Each position ties up its size on two exchanges.

### E2. Funding carry between two exchanges

Short the perpetual where the funding is higher, long where it is lower, and collect the difference at each payment. Payments are rebuilt from each exchange's own schedule: the last rate published before each payment time, over 1.8 days (816 payments read). Cost of getting in and out = 0.20 % of fees plus one round trip in each of the two books (median of the run). No payment time published without an account: phemex, left out.

- Token and exchange pairs with funding and depth on both sides: **660**.
- Funding difference collected per day: median 0.0090 %, highest 0.0839 %.
- For 1 000 $: the cost is paid back within one day on 0 / 660 (0 %), within a week on 28 / 660 (4 %); median 31 days, if the funding stayed what it was during the run.
- For 10 000 $: the cost is paid back within one day on 0 / 660 (0 %), within a week on 12 / 660 (2 %); median 37 days, if the funding stayed what it was during the run.

| Token | Short on | Long on | Payments (short / long) | Funding collected per day | 8 h windows in our favour | Cost in and out, 1 000 $ | 10 000 $ | Days to pay back, 1 000 $ | 10 000 $ |
|---|---|---|---|---|---|---|---|---|---|
| TRX | htx | kucoin | 5 / 11 | 0.0839 % | 7 / 7 | 0.33 % | 0.45 % | 4 | 5 |
| SUI | whitebit | htx | 5 / 5 | 0.0668 % | 5 / 5 | 0.35 % | 0.43 % | 5 | 6 |
| TRX | htx | bybit | 5 / 5 | 0.0633 % | 5 / 5 | 0.32 % | 0.34 % | 5 | 5 |
| TRX | htx | zoomex | 5 / 5 | 0.0633 % | 5 / 5 | 0.32 % | 0.34 % | 5 | 5 |
| SUI | okx | htx | 5 / 5 | 0.0587 % | 4 / 5 | 0.23 % | 0.31 % | 4 | 5 |
| TRX | htx | whitebit | 5 / 5 | 0.0582 % | 5 / 5 | 0.33 % | 0.45 % | 6 | 8 |
| SUI | bitget | htx | 5 / 5 | 0.0578 % | 5 / 5 | 0.23 % | 0.33 % | 4 | 6 |
| TRX | htx | binance | 5 / 5 | 0.0575 % | 5 / 5 | 0.29 % | 0.32 % | 5 | 6 |
| TRX | htx | mexc | 5 / 5 | 0.0574 % | 5 / 5 | 0.29 % | 0.31 % | 5 | 5 |
| SUI | bybit | htx | 5 / 5 | 0.0570 % | 5 / 5 | 0.23 % | 0.31 % | 4 | 5 |

Limits: one to two days of funding say nothing of next week's rates; the price gap between the two exchanges at entry and at exit is not counted; margin has to sit on both exchanges.
