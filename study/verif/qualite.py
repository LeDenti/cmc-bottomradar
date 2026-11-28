"""Quality check of CoinMarketCap perpetual quotes against real order books.

Reads three files written by the samplers (no network call, 0 credit):
  runs/cmc_24h.jsonl       CMC quotes               (verif/cotes_cmc.py, every 150 s)
  runs/carnets_24h.jsonl   best bid / ask, last, mark, index on 11 exchanges (verif/carnets.py, every 30 s)
  runs/contexte_24h.jsonl  funding, depth for 1 000 $ and 10 000 $, deposits / withdrawals (verif/contexte.py, every 5 min)

    python3 verif/qualite.py                 # prints the report, writes runs/quality_report.md and .json

Sections
  A. Coverage and biases of our own measurement (slow answers caused by our second sampler, frozen feeds)
  B. The finding: how many CMC gaps exist in the books, at the top of the book, for 1 000 $ and for 10 000 $
  C. The causes, classified
  D. What CMC could publish: a freshness indicator and a "shared book" flag, computed here per exchange
  E. What is left once the data is right: real gaps in the books (do they close?) and funding carry
"""
import bisect, json, os, statistics, sys, time
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = os.path.join(ROOT, "runs")
ARGS = dict(x.lstrip("-").split("=", 1) for x in sys.argv[1:] if "=" in x)
F_CMC, F_BOOK, F_CTX = ARGS.get("cmc", "cmc_24h.jsonl"), ARGS.get("books", "carnets_24h.jsonl"), ARGS.get("ctx", "contexte_24h.jsonl")

TH = 0.20          # % : a "gap" is a quote at least this far from the median of the exchanges
SLOW = 5.0         # s : an answer slower than this is not "the same instant"
NEAR = 20          # s : a book round counts for a CMC quote if it is this close in time
FROZEN = 10        # rounds: BTC best bid and ask unchanged for 5 min = frozen feed
TOL = 0.02         # % : two prices closer than this are "the same price"
LAGS = list(range(0, 901, 30))                     # delays tried for one quote
LONG = LAGS + [1200, 1800, 2700, 3600, 5400, 7200, 10800]   # delays tried for a whole series
STILL = 290        # s : a CMC price unchanged this long while its last_updated moves on is a frozen quote
SIZES = (1000, 10000)
med = statistics.median


def load(name):
    p = os.path.join(RUNS, name)
    return [json.loads(l) for l in open(p)] if os.path.exists(p) else []


def pct(a, b):
    return (a / b - 1) * 100


def share(n, d):
    return "%d / %d (%.0f %%)" % (n, d, 100.0 * n / d) if d else "0 / 0"


# ------------------------------------------------------------------ load
books = sorted(load(F_BOOK), key=lambda r: r["t"])
kept = []                                       # two samplers overlapped for one minute on 26/11 10:12 UTC
for r in books:
    if kept and r["t"] - kept[-1]["t"] < 10:
        if "px" in r and "px" not in kept[-1]:
            kept[-1] = r
        continue
    kept.append(r)
books = kept
ctx = sorted(load(F_CTX), key=lambda r: r["t"])
cmc = sorted(load(F_CMC), key=lambda r: r["t"])
if not books or not cmc:
    sys.exit("need %s and %s in runs/" % (F_BOOK, F_CMC))
EXS = list(books[-1]["took"])
TOKENS = list(books[-1]["books"])
RT = [r["t"] for r in books]
N = len(books)
out = []          # report lines
J = {}            # same numbers as JSON


def say(s=""):
    out.append(s)
    print(s)


# ------------------------------------------------------------------ A. our own biases
slow = {e: [i for i, r in enumerate(books) if r["took"].get(e, 0) > SLOW] for e in EXS}
frozen = defaultdict(set)                       # exchange -> rounds where its feed did not move
for e in EXS:
    run, prev = [], None
    for i, r in enumerate(books + [None]):
        v = r["books"]["BTC"].get(e, [None, None])[:2] if r else "end"
        if v == prev and v != [None, None]:
            run.append(i)
        else:
            if len(run) >= FROZEN:
                frozen[e].update(run + [run[0] - 1])
            run = []
        prev = v
missing = {e: sum(1 for r in books if e not in r["books"]["BTC"]) for e in EXS}

# clean view used everywhere below: Q[i][token][exchange] = (bid, ask, last, mark, index)
Q = []
for i, r in enumerate(books):
    row = {}
    px = r.get("px") or {}
    for tok in TOKENS:
        d = {}
        for e, v in r["books"][tok].items():
            if r["took"].get(e, 0) > SLOW or i in frozen[e]:
                continue
            p = (px.get(tok) or {}).get(e) or [None, None, None]
            d[e] = (v[0], v[1], p[0], p[1], p[2])
        row[tok] = d
    Q.append(row)


def at(tok, e, t, near=NEAR):
    """Book of `e` in the round closest to time t, or None."""
    i = bisect.bisect_left(RT, t)
    best = min((j for j in (i - 1, i) if 0 <= j < N), key=lambda j: abs(RT[j] - t))
    return Q[best][tok].get(e) if abs(RT[best] - t) <= near else None


def ref(q, kind):
    """One reference price of a book entry: mid, last, mark or index (None if the exchange does not give it)."""
    if q is None:
        return None
    return (q[0] + q[1]) / 2 if kind == "mid" else q[{"last": 2, "mark": 3, "index": 4}[kind]]


span_h = (RT[-1] - RT[0]) / 3600
holes = sorted(((b - a, a) for a, b in zip(RT, RT[1:]) if b - a > 90), reverse=True)
cwin = [(c["t"] - 2, c["t"] + c["span_s"] + 2) for c in ctx]
cstart = [w[0] for w in cwin]


def in_ctx(t):
    i = bisect.bisect_right(cstart, t) - 1
    return i >= 0 and t <= cwin[i][1]


base = sum(1 for t in RT if in_ctx(t))
say("# CMC quote quality check — measured report")
say()
say("Generated %s UTC from the samplers' files. No order, no account, no exchange key; CMC is the only keyed API." % time.strftime("%Y-%m-%d %H:%M", time.gmtime()))
say()
say("## A. Coverage and our own biases")
say()
say("- Order books: %d rounds over %.1f h (%s → %s UTC), one every %.0f s, %d perpetuals × %d exchanges." % (
    N, span_h, time.strftime("%d/%m %H:%M", time.gmtime(RT[0])), time.strftime("%d/%m %H:%M", time.gmtime(RT[-1])),
    med(b - a for a, b in zip(RT, RT[1:])), len(TOKENS), len(EXS)))
say("- Holes longer than 90 s between two rounds: %d%s." % (len(holes), (" (longest %.0f s at %s UTC)" % (
    holes[0][0], time.strftime("%d/%m %H:%M", time.gmtime(holes[0][1])))) if holes else ""))
big = sorted((a_, d_) for d_, a_ in holes if d_ >= 600)
if big:
    say("- Holes of 10 min or more in the order books (our samplers were stopped): %s UTC. Nothing is paired across a hole: "
        "a CMC quote is only compared with a book read within %d s of it." % ("; ".join("%s → %s" % (
            time.strftime("%d/%m %H:%M", time.gmtime(a_)), time.strftime("%d/%m %H:%M", time.gmtime(a_ + d_))) for a_, d_ in big), NEAR))
say("- CMC: %d snapshots, %d credits. Context (funding, depth, deposits and withdrawals): %d cycles." % (
    len(cmc), sum(s.get("credits", 0) for s in cmc), len(ctx)))
cwins, _w = [], None                             # stretches of CMC sampling (a hole of 10 min or more ends a stretch)
for x in cmc:
    if _w and x["t"] - _w[1] < 600:
        _w[1], _w[2] = x["t"], _w[2] + 1
    else:
        _w = [x["t"], x["t"], 1]
        cwins.append(_w)
_f = lambda t: time.strftime("%d/%m %H:%M", time.gmtime(t))
say("- CMC was sampled over %.1f h in %d stretch%s: %s UTC. Sections B to D only cover those hours; section E covers "
    "the whole run of the order books." % (sum(w[1] - w[0] for w in cwins) / 3600, len(cwins), "" if len(cwins) == 1 else "es",
                                         "; ".join("%s → %s (%d snapshots)" % (_f(w[0]), _f(w[1]), w[2]) for w in cwins)))
if len(cwins) > 1:
    say("- No CMC quote exists between those stretches (%s UTC). Both holes are our own doing, not CMC's: on 26/11 at "
        "14:10 UTC our CMC sampler stopped on a dropped connection it did not catch (fixed, started again on 27/11 at "
        "07:29 UTC); on 27/11 from 13:26 to 15:04 UTC all four samplers were paused while the computer ran on battery." % (
            "; ".join("%s → %s" % (_f(x[1]), _f(y[0])) for x, y in zip(cwins, cwins[1:]))))
say("- Share of book rounds that overlap one of our own context cycles: %s." % share(base, N))
say()
say("**Bias 1 — slow answers, partly caused by our own second sampler.** While the context sampler reads 165 order "
    "books, some exchanges (first seen on Bybit and Gate) answer the book sampler late. An answer slower than %.0f s is "
    "dropped and never counted against the exchange or against CMC: it is a flaw of our set-up, not of their data. "
    "The third column shows how much of it falls inside our own context cycles; the share expected by chance is "
    "%.0f %%." % (SLOW, 100.0 * base / N))
say()
say("| Exchange | Rounds dropped as slow | Of which during our own context cycle | Rounds with no answer | Rounds dropped as frozen |")
say("|---|---|---|---|---|")
J["bias"] = {}
for e in EXS:
    inside = sum(1 for i in slow[e] if in_ctx(RT[i]))
    J["bias"][e] = {"slow": len(slow[e]), "slow_in_ctx": inside, "missing": missing[e], "frozen": len(frozen[e])}
    say("| %s | %s | %s | %d | %d |" % (e, share(len(slow[e]), N), share(inside, len(slow[e])), missing[e], len(frozen[e])))
say()
say("**Bias 2 — a frozen public feed.** A feed whose BTC best bid and ask do not move for %d rounds (5 min) is dropped. "
    "On 26/11/2026 the host `api.hbdm.com` of HTX served the same snapshot from 07:11 UTC; the sampler was moved to "
    "`api.hbdm.vn` at 10:12 UTC and now rejects any tick older than 30 s. HTX rows before that are excluded." % FROZEN)

# ------------------------------------------------------------------ B. the finding
# one record per CMC quote of an exchange we can check
recs, flagged = [], []
for s in cmc:
    for tok, blk in s["tokens"].items():
        tc = blk["t"]
        ms = {m[0]: m for m in blk["m"] if m[0] in EXS and m[5] == 0 and m[1]}
        now = {e: at(tok, e, tc) for e in ms}
        now = {e: q for e, q in now.items() if q}
        if len(now) < 5:
            continue
        cm = med(ms[e][1] for e in now)
        bm = med(ref(q, "mid") for q in now.values())
        for e, q in now.items():
            m = ms[e]
            st = at(tok, e, m[4]) if m[4] else None           # the same book at the quote's own timestamp
            oth = {x: at(tok, x, ms[x][4]) for x in now if ms[x][4]}
            oth = [ref(v, "mid") for v in oth.values() if v]
            recs.append({"tok": tok, "ex": e, "tc": tc, "p": m[1], "age": tc - m[4] if m[4] else None, "stamp": m[4],
                         "cmc_index": m[2], "dev": pct(m[1], cm), "book": pct(ref(q, "mid"), bm), "q": q,
                         "book_stamp": pct(ref(st, "mid"), med(oth)) if st and len(oth) >= 5 else None})
        for m in blk["m"]:                 # quotes CMC itself flags, measured against the same medians
            if m[0] in EXS and m[5] and m[1]:
                q = at(tok, m[0], tc)
                if q:
                    flagged.append({"tok": tok, "ex": m[0], "dev": pct(m[1], cm), "book": pct(ref(q, "mid"), bm)})


hist = defaultdict(list)                       # (token, exchange) -> [(call time, price, last_updated)]
for s in cmc:
    for tok, blk in s["tokens"].items():
        for m in blk["m"]:
            if m[0] in EXS and m[1]:
                hist[(tok, m[0])].append((blk["t"], m[1], m[4]))
still = {}                                     # (token, exchange, call time) -> seconds with the same price, stamp moving
for key, h in hist.items():
    first = 0
    for i, (tc, p, st) in enumerate(h):
        if i and (p != h[i - 1][1] or tc - h[i - 1][0] > 400):
            first = i
        still[key + (tc,)] = tc - h[first][0] if st and h[first][2] and st > h[first][2] else 0
for x in recs:
    x["still"] = still.get((x["tok"], x["ex"], x["tc"]), 0)


offs = defaultdict(list)                       # (token, exchange) -> [(call time, signed distance to the live price)]
for x in recs:
    offs[(x["tok"], x["ex"])].append((x["tc"], pct(x["p"], (x["q"][2] or (x["q"][0] + x["q"][1]) / 2))))


def off_for_long(x):
    """True when the quote was already off the live price, on the same side, at every call of the last 5 min."""
    now = pct(x["p"], (x["q"][2] or (x["q"][0] + x["q"][1]) / 2))
    prev = [o for t, o in offs[(x["tok"], x["ex"])] if x["tc"] - 460 <= t < x["tc"]]
    older = [t for t, o in offs[(x["tok"], x["ex"])] if t <= x["tc"] - STILL]
    return bool(older) and len(prev) >= 2 and all(o * now > 0 and abs(o) >= 0.5 * abs(now) for o in prev)


def tol_of(q):
    return max(TOL, 0.25 * pct(q[1], q[0]))


def live(q):
    return ref(q, "last") or ref(q, "mid")


def confirmed(dev, book):
    return book is not None and book * dev > 0 and abs(book) >= 0.5 * abs(dev)


gaps = [x for x in recs if abs(x["dev"]) >= TH]
conf = [x for x in gaps if confirmed(x["dev"], x["book"])]
false = [x for x in gaps if not confirmed(x["dev"], x["book"])]
conf_st = [x for x in gaps if confirmed(x["dev"], x["book_stamp"])]
J["finding"] = {"quotes": len(recs), "gaps": len(gaps), "confirmed": len(conf), "confirmed_at_stamp": len(conf_st)}
say()
say("## B. The finding")
say()
say("A **CMC gap** is a quote at least %.2f %% away from the median of the same token on the exchanges we can check "
    "(CMC flags `outlier_detected` and `exclusions` clear). It is **confirmed** when the exchange's own book, read "
    "within %d s of the CMC call, shows a deviation of the same sign and at least half the size." % (TH, NEAR))
say()
say("- CMC quotes compared with a live book: **%d**." % len(recs))
say("- CMC gaps of %.2f %% or more: **%d** (%.1f %% of the quotes)." % (TH, len(gaps), 100.0 * len(gaps) / max(1, len(recs))))
say("- Confirmed by the book at the same instant: **%s**." % share(len(conf), len(gaps)))
say("- Confirmed by the book at the quote's own `last_updated`: %s." % share(len(conf_st), len(gaps)))
if gaps:
    say("- Median size of a CMC gap: %.2f %%; median size of the same deviation in the book: %.3f %%." % (
        med(abs(x["dev"]) for x in gaps), med(abs(x["book"]) for x in gaps)))
say()
say("| Threshold | CMC gaps | Confirmed by the book |")
say("|---|---|---|")
for th in (0.10, 0.20, 0.50, 1.00):
    g = [x for x in recs if abs(x["dev"]) >= th]
    say("| %.2f %% | %d | %s |" % (th, len(g), share(sum(1 for x in g if confirmed(x["dev"], x["book"])), len(g))))
fg = [x for x in flagged if abs(x["dev"]) >= TH]
J["finding"]["flagged_quotes"] = len(flagged)
J["finding"]["flagged_gaps"] = len(fg)
say()
say("**What CMC's own flags already catch.** The quotes above carry no flag. The quotes CMC marks with `exclusions` "
    "or `outlier_detected` on the same exchanges, measured the same way:")
say()
say("| Quotes | Checked | Gaps of %.2f %% or more | Of which not confirmed by the book |" % TH)
say("|---|---|---|---|")
say("| No flag from CMC | %d | %s | %s |" % (len(recs), share(len(gaps), len(recs)), share(len(false), len(gaps))))
say("| Flagged by CMC | %d | %s | %s |" % (len(flagged), share(len(fg), len(flagged)),
    share(sum(1 for x in fg if not confirmed(x["dev"], x["book"])), len(fg))))
say()
say("| Token | CMC gaps | Confirmed | | Exchange | CMC gaps | Confirmed |")
say("|---|---|---|---|---|---|---|")
bt, be = defaultdict(list), defaultdict(list)
for x in gaps:
    bt[x["tok"]].append(x)
    be[x["ex"]].append(x)
lt = sorted(bt.items(), key=lambda kv: -len(kv[1]))
le = sorted(be.items(), key=lambda kv: -len(kv[1]))
for i in range(max(len(lt), len(le))):
    a = ("%s | %d | %s" % (lt[i][0], len(lt[i][1]), share(sum(1 for x in lt[i][1] if confirmed(x["dev"], x["book"])), len(lt[i][1])))) if i < len(lt) else " | | "
    b = ("%s | %d | %s" % (le[i][0], len(le[i][1]), share(sum(1 for x in le[i][1] if confirmed(x["dev"], x["book"])), len(le[i][1])))) if i < len(le) else " | | "
    say("| %s | | %s |" % (a, b))

# ---- at which sizes: pairs of exchanges, on CMC snapshots taken with a context cycle
CT = [c["t"] for c in ctx]
cfrozen = defaultdict(set)
for e in EXS:
    run, prev = [], None
    for i, c in enumerate(ctx + [None]):
        d = ((c["ex"].get(e) or {}).get("BTC") or {}).get("depth") if c else None
        v = (d["bid"], d["ask"]) if d else ("end" if c is None else None)
        if v == prev and v is not None:
            run.append(i)
        else:
            if len(run) >= 2:
                cfrozen[e].update(run + [run[0] - 1])
            run = []
        prev = v


def depth_at(tok, e, t):
    i = bisect.bisect_right(CT, t + 5) - 1
    if i < 0 or i in cfrozen[e]:
        return None
    d = (ctx[i]["ex"].get(e) or {}).get(tok) or {}
    when = d.get("at") or (ctx[i]["t"] + ctx[i]["took"].get(e, 30) / 2)
    return d.get("depth") if abs(when - t) <= 75 else None


pairs = []
for s in cmc:
    for tok, blk in s["tokens"].items():
        ms = {m[0]: m[1] for m in blk["m"] if m[0] in EXS and m[5] == 0 and m[1]}
        dp = {e: depth_at(tok, e, blk["t"]) for e in ms}
        dp = {e: d for e, d in dp.items() if d}
        for a in dp:                       # buy on a (cheap on CMC), sell on b (dear on CMC)
            for b in dp:
                g = pct(ms[b], ms[a]) if a != b else 0
                if g < TH:
                    continue
                row = {"tok": tok, "a": a, "b": b, "cmc": g, "top": pct(dp[b]["bid"], dp[a]["ask"])}
                for z in SIZES:
                    sell, buy = dp[b].get("sell%d" % z), dp[a].get("buy%d" % z)
                    row[z] = pct(sell, buy) if sell and buy else None
                pairs.append(row)
say()
say("**At which sizes.** Same test on pairs of exchanges (buy where CMC shows the token cheap, sell where CMC shows "
    "it dear), with the depth of both books read at most 75 s from the CMC call: sell at the average price of the "
    "bids, buy at the average price of the asks, 50 levels deep.")
say()
J["sizes"] = {"pairs": len(pairs)}
if pairs:
    say("CMC pair gaps of %.2f %% or more with both depths read: **%d** (median CMC gap %.2f %%)." % (
        TH, len(pairs), med(x["cmc"] for x in pairs)))
    say()
    say("| Size | Median executable gap | Still positive | Above %.2f %% (4 taker orders at 0.05 %%) | At least half the CMC gap | Not fillable in 50 levels |" % TH)
    say("|---|---|---|---|---|---|")
    for label, k in (("Best bid / best ask", "top"), ("1 000 $", 1000), ("10 000 $", 10000)):
        v = [x[k] for x in pairs if x[k] is not None]
        nf = sum(1 for x in pairs if x[k] is None)
        J["sizes"][str(k)] = {"median": med(v) if v else None, "positive": sum(1 for y in v if y > 0),
                              "above_fees": sum(1 for y in v if y > TH), "unfillable": nf}
        say("| %s | %s | %s | %s | %s | %s |" % (
            label, ("%+.3f %%" % med(v)) if v else "-", share(sum(1 for y in v if y > 0), len(pairs)),
            share(sum(1 for y in v if y > TH), len(pairs)),
            share(sum(1 for x in pairs if x[k] is not None and x[k] >= 0.5 * x["cmc"]), len(pairs)), share(nf, len(pairs))))
else:
    say("_No CMC snapshot coincides with a context cycle yet._")

# ------------------------------------------------------------------ C. causes
# C1. measured lag of each (token, exchange): the delay that best lines the CMC price up with the exchange's own price
series = defaultdict(list)
for x in recs:
    series[(x["tok"], x["ex"])].append(x)
lagstat = {}
for key, xs in series.items():
    tok, e = key
    best = {}
    for kind in ("last", "mid", "mark", "index"):
        cur = None
        for L in LONG:
            errs = []
            for x in xs:
                v = ref(at(tok, e, x["tc"] - L), kind)
                if v:
                    errs.append(abs(pct(x["p"], v)))
            if len(errs) >= max(8, len(xs) // 2):
                m = med(errs)
                if cur is None or m < cur[0] - 1e-9:
                    cur = (m, L)
        if cur:
            best[kind] = cur
    if best:
        lagstat[key] = best

# C2. shared books: two exchanges showing the same best bid and ask on fine-tick tokens
FINE = [t for t in ("BTC", "ETH", "SOL", "BNB") if t in TOKENS]
mirror = {}
for i, a in enumerate(EXS):
    for b in EXS[i + 1:]:
        same = tot = 0
        for row in Q:
            for tok in FINE:
                qa, qb = row[tok].get(a), row[tok].get(b)
                if qa and qb:
                    tot += 1
                    same += qa[:2] == qb[:2]
        if tot:
            mirror[(a, b)] = (same / tot, tot)
shared = {k: v for k, v in mirror.items() if v[0] >= 0.30 and v[1] >= 50}   # listed; a true shared book is above 80 %
truly = {k for k, v in shared.items() if v[0] >= 0.80}
bg = med(v[0] for v in mirror.values()) if mirror else 0
mirror_of = {}
for (a, b) in truly:
    mirror_of.setdefault(a, b)
    mirror_of.setdefault(b, a)


def depth_ratio(a, b):
    """Median ratio of the money in the 50 levels of a and b (1.00 = same book), fine-tick tokens."""
    v = []
    for i, c in enumerate(ctx):
        for tok in FINE:
            da = ((c["ex"].get(a) or {}).get(tok) or {}).get("depth")
            db = ((c["ex"].get(b) or {}).get(tok) or {}).get("depth")
            if da and db and i not in cfrozen[a] and i not in cfrozen[b] and db["usd_bids"] + db["usd_asks"] > 0:
                v.append((da["usd_bids"] + da["usd_asks"]) / (db["usd_bids"] + db["usd_asks"]))
    return med(v) if v else None

# C3. thin books: cost of a 1 000 $ and a 10 000 $ round trip, and money in the 50 levels read
thin = {}
for tok in TOKENS:
    for e in EXS:
        ds = [((c["ex"].get(e) or {}).get(tok) or {}).get("depth") for i, c in enumerate(ctx) if i not in cfrozen[e]]
        ds = [d for d in ds if d]
        if len(ds) < 3:
            continue
        rt = {}
        for z in SIZES:
            v = [pct(d["buy%d" % z], d["sell%d" % z]) for d in ds if d.get("buy%d" % z) and d.get("sell%d" % z)]
            rt[z] = (med(v) if v else None, 1 - len(v) / len(ds))
        thin[(tok, e)] = {"spread": med(pct(d["ask"], d["bid"]) for d in ds), "rt": rt,
                          "usd": med(min(d["usd_bids"], d["usd_asks"]) for d in ds), "n": len(ds)}


def is_thin(tok, e):
    t = thin.get((tok, e))
    return bool(t) and (t["rt"][10000][0] is None or t["rt"][10000][0] > TH or t["rt"][10000][1] > 0.10)


# C4. deposits and withdrawals
wal = defaultdict(lambda: [0, 0, 0])            # (exchange, coin) -> checks, deposit closed, withdrawal closed
wseen = set()
for c in ctx:
    for e, coins in (c.get("wallets") or {}).items():
        wseen.add(e)
        for coin, w in coins.items():
            if coin == "TON" and "GRAM" in coins:   # dead ticker kept by the exchange next to the live one
                continue
            k = wal[(e, "TON" if coin == "GRAM" else coin)]
            k[0] += 1
            k[1] += w.get("deposit") is False
            k[2] += w.get("withdraw") is False
closed = {k: v for k, v in wal.items() if v[1] or v[2]}


# C5. one cause per false gap
def cause(x):
    tok, e, p, q = x["tok"], x["ex"], x["p"], x["q"]
    tol = tol_of(q)
    off = abs(pct(p, live(q)))
    if off < 0.5 * abs(x["dev"]):
        return "others_late"       # this quote is right now: the median it is compared with is made of older quotes
    if x["still"] >= STILL:
        return "frozen"            # same price for 5 min or more while last_updated moves on and the book has moved
    if q[0] * (1 - TOL / 100) <= p <= q[1] * (1 + TOL / 100) and pct(q[1], q[0]) >= 0.5 * abs(x["dev"]):
        return "wide_spread"       # the price sits inside a wide bid-ask spread: a last trade, not a price one can get
    if x["stamp"]:
        st = at(tok, e, x["stamp"], near=45)
        for kind in ("last", "mid"):
            v = ref(st, kind)
            if v and abs(pct(p, v)) <= tol:
                return "late_as_stamped"   # right at its own last_updated, the market moved since
    for L in LAGS[1:]:
        back = at(tok, e, x["tc"] - L)
        for kind in ("last", "mid"):
            v = ref(back, kind)
            if v and abs(pct(p, v)) <= tol:
                return "late_other_time"   # equal to the exchange's price at another moment of the last 15 min
    for L in LAGS[:11]:
        back = at(tok, e, x["tc"] - L)
        for kind in ("mark", "index"):
            v = ref(back, kind)
            if v and abs(pct(p, v)) <= tol:
                return "mark_or_index"
    if off_for_long(x):
        return "off_for_long"      # on the same side of the live price for 5 min or more, and no match in 15 min
    return "unexplained"


LABEL = {
    "frozen": "Frozen quote: same price for 5 min or more, `last_updated` still moving, the book elsewhere",
    "late_as_stamped": "Late quote: right at its own `last_updated`, the market moved since",
    "late_other_time": "Late quote: equal to the exchange's price at another moment of the last 15 min",
    "others_late": "This quote is current; the other exchanges' quotes it is compared with are older",
    "wide_spread": "Last trade inside a wide bid-ask spread (thin book)",
    "mark_or_index": "Equal to the exchange's mark or index price, not to its last price",
    "off_for_long": "Off for long: on the same side of the live price for 5 min or more, no match in the last 15 min "
                    "(older than 15 min, or not this exchange's price)",
    "unexplained": "Unexplained one-off: matches no price of the exchange in the last 15 min",
}
for x in false:
    x["cause"] = cause(x)
cc = Counter(x["cause"] for x in false)
J["causes"] = dict(cc)
say()
say("## C. The causes, classified")
say()
say("Each CMC gap that the book does not confirm gets one cause, tested in this order. Prices are \"the same\" within "
    "%.2f %% or a quarter of the exchange's spread." % TOL)
say()
say("| Cause | False gaps | Share |")
say("|---|---|---|")
for k in LABEL:
    say("| %s | %d | %.0f %% |" % (LABEL[k], cc.get(k, 0), 100.0 * cc.get(k, 0) / max(1, len(false))))
say()
tags = Counter()
for x in gaps:
    c = confirmed(x["dev"], x["book"])
    if x["ex"] in mirror_of:
        tags[("mirror", c)] += 1
    if is_thin(x["tok"], x["ex"]):
        tags[("thin", c)] += 1
    if (x["ex"], x["tok"]) in closed:
        tags[("closed", c)] += 1
say("Three conditions can add to a cause. They are counted on all CMC gaps, confirmed or not:")
say()
say("| Condition | CMC gaps concerned | Of which not confirmed |")
say("|---|---|---|")
for k, label in (("mirror", "The exchange shows another exchange's order book (shared book)"),
                 ("thin", "Thin book: a 10 000 $ round trip costs more than %.2f %% or cannot be filled" % TH),
                 ("closed", "Deposits or withdrawals of the token closed at least once (5 exchanges readable)")):
    n = tags[(k, True)] + tags[(k, False)]
    say("| %s | %d | %s |" % (label, n, share(tags[(k, False)], n)))

say()
say("### C0. Frozen quotes stamped as fresh")
say()
say("A CMC price that stays exactly the same for %d s or more while its `last_updated` keeps moving, and while the "
    "exchange's live price is somewhere else (further than the tolerance)." % STILL)
say()
say("| Exchange | Quotes checked | Frozen | Longest run with the same price | Median distance to the live price when frozen |")
say("|---|---|---|---|---|")
J["frozen_quotes"] = {}
for e in EXS:
    xs = [x for x in recs if x["ex"] == e]
    fz = [x for x in xs if x["still"] >= STILL and abs(pct(x["p"], live(x["q"]))) > tol_of(x["q"])]
    if not xs:
        continue
    J["frozen_quotes"][e] = {"quotes": len(xs), "frozen": len(fz)}
    say("| %s | %d | %s | %.0f min | %s |" % (e, len(xs), share(len(fz), len(xs)), max(x["still"] for x in xs) / 60,
        ("%.2f %%" % med(abs(pct(x["p"], live(x["q"]))) for x in fz)) if fz else "-"))
ages = [x["age"] for x in recs if x["age"] is not None]
say()
say("### C1. Late quotes: claimed age against measured lag")
say()
if ages:
    qs = statistics.quantiles(ages, n=20) if len(ages) >= 20 else [min(ages)] * 19
    say("CMC's own `last_updated` says the quotes are %.0f s old in median (5 %% are younger than %.0f s, 5 %% older "
        "than %.0f s). The **measured lag** is the delay that best lines the CMC price up with the exchange's own "
        "price over the whole run (median absolute error, delays tried from 0 to 900 s by 30 s, then up to 3 h)." % (med(ages), qs[0], qs[-1]))
say()
say("| Exchange | Claimed age (median) | Measured lag (median over tokens) | Error left at that lag | Closest reference |")
say("|---|---|---|---|---|")
J["lag"] = {}
for e in EXS:
    ks = [k for k in lagstat if k[1] == e]
    if not ks:
        continue
    win = []
    for k in ks:
        b = lagstat[k]
        kind = min(b, key=lambda z: (round(b[z][0], 3), ("last", "mid", "mark", "index").index(z)))
        win.append((kind, b[kind][0], b[kind][1]))
    kinds = Counter(w[0] for w in win)
    a = [x["age"] for x in recs if x["ex"] == e and x["age"] is not None]
    J["lag"][e] = {"claimed": med(a) if a else None, "measured": med(w[2] for w in win), "err": med(w[1] for w in win),
                   "ref": dict(kinds)}
    say("| %s | %s | %.0f s | %.3f %% | %s |" % (e, ("%.0f s" % med(a)) if a else "-", med(w[2] for w in win),
        med(w[1] for w in win), ", ".join("%s ×%d" % kv for kv in kinds.most_common())))
say()
say("### C2. Mark or index instead of the last price")
say()
rows = []
for (tok, e), b in sorted(lagstat.items()):
    if "last" in b and ("mark" in b or "index" in b):
        alt = min((k for k in ("mark", "index") if k in b), key=lambda k: b[k][0])
        if b[alt][0] + 0.01 < b["last"][0]:
            rows.append((tok, e, alt, b[alt][0], b["last"][0]))
if rows:
    say("Token and exchange pairs where the CMC price follows the mark or the index more closely than the last price:")
    say()
    say("| Token | Exchange | Follows | Error against it | Error against the last price |")
    say("|---|---|---|---|---|")
    for r in rows:
        say("| %s | %s | %s | %.3f %% | %.3f %% |" % r)
else:
    say("No token and exchange pair where the CMC price follows the exchange's mark or index more closely than its "
        "last price (%d pairs tested where the exchange publishes them)." % sum(1 for b in lagstat.values() if "last" in b and ("mark" in b or "index" in b)))
ci = [abs(pct(x["cmc_index"], x["q"][4])) for x in recs if x["cmc_index"] and x["q"][4]]
if ci:
    say()
    say("CMC also carries an `index_price` per quote: against the exchange's own index it is off by %.3f %% in median "
        "(%d points)." % (med(ci), len(ci)))
say()
say("### C3. Shared order books")
say()
say("Two exchanges with exactly the same best bid and best ask at the same instant, on fine-tick tokens (%s). "
    "Between independent exchanges this happens in %.1f %% of the rounds (median of all pairs)." % (", ".join(FINE), 100 * bg))
say()
J["shared"] = {"%s=%s" % k: v[0] for k, v in shared.items()}
if shared:
    say("Above 80 % with the same money in the book, the two exchanges show **one and the same order book**. Between 30 and "
        "80 %, the best prices are pegged by market makers but the books differ.")
    say()
    say("| Pair | Rounds with an identical best bid and ask | Money in the book, first / second | Reading | CMC price difference between the two (median) | Gaps of %.2f %% between them on CMC |" % TH)
    say("|---|---|---|---|---|---|")
    for (a, b), v in sorted(shared.items(), key=lambda kv: -kv[1][0]):
        d = defaultdict(dict)
        for x in recs:
            if x["ex"] in (a, b):
                d[(x["tok"], x["tc"])][x["ex"]] = x["p"]
        diffs = [abs(pct(v2[a], v2[b])) for v2 in d.values() if a in v2 and b in v2]
        dr = depth_ratio(a, b)
        say("| %s = %s | %.0f %% of %d | %s | %s | %s | %s |" % (a, b, 100 * v[0], v[1], ("%.2f" % dr) if dr else "-",
            "shared book" if (a, b) in truly else "pegged best prices", ("%.3f %%" % med(diffs)) if diffs else "-",
            share(sum(1 for y in diffs if y >= TH), len(diffs))))
else:
    say("_No pair above 30 % yet._")
say()
say("### C4. Thin books")
say()
say("Median over the run, from 50 levels of each book. Listed: a 10 000 $ round trip (buy then sell at once) costs more "
    "than %.2f %%, or cannot be filled in more than 10 %% of the readings." % TH)
say()
say("| Token | Exchange | Spread | 1 000 $ round trip | 10 000 $ round trip | 10 000 $ not fillable | Money in the thinner side | CMC gaps here |")
say("|---|---|---|---|---|---|---|---|")
J["thin"] = {}
gcount = Counter((x["tok"], x["ex"]) for x in gaps)
for (tok, e), t in sorted(thin.items(), key=lambda kv: -(kv[1]["rt"][10000][0] or 99)):
    if not is_thin(tok, e):
        continue
    J["thin"]["%s/%s" % (tok, e)] = {"spread": t["spread"], "rt1000": t["rt"][1000][0], "rt10000": t["rt"][10000][0], "usd": t["usd"]}
    f = lambda v: ("%.3f %%" % v) if v is not None else "-"
    say("| %s | %s | %.3f %% | %s | %s | %.0f %% | %s $ | %d |" % (tok, e, t["spread"], f(t["rt"][1000][0]), f(t["rt"][10000][0]),
        100 * t["rt"][10000][1], format(int(t["usd"]), ",").replace(",", " "), gcount.get((tok, e), 0)))
say()
say("### C5. Deposits and withdrawals")
say()
unread = [e for e in EXS if e not in wseen]
say("Read once an hour where the exchange publishes it without an account: %s. Not readable without an account: %s." % (
    ", ".join(sorted(wseen)) or "none yet", ", ".join(unread) or "none"))
say()
if closed:
    say("| Exchange | Coin | Checks | Deposit closed | Withdrawal closed |")
    say("|---|---|---|---|---|")
    for (e, coin), v in sorted(closed.items()):
        say("| %s | %s | %d | %d | %d |" % (e, coin, v[0], v[1], v[2]))
else:
    say("No closure seen on %d exchange and coin pairs." % len(wal))

# ------------------------------------------------------------------ D. what CMC could publish
say()
say("## D. Two indicators CMC could publish, computed here")
say()
say("**Freshness** = how far the CMC quote is from the exchange's live last price at the instant of the API call, the "
    "delay that explains it, and whether the price is frozen. **Shared book** = the exchange shows another exchange's "
    "order book, so it is not a second market.")
say()
say("| Exchange | Quotes checked | Median distance to the live price | Measured lag | Frozen quotes | Shared book with | CMC gaps | Confirmed |")
say("|---|---|---|---|---|---|---|---|")
J["indicators"] = {}
for e in EXS:
    xs = [x for x in recs if x["ex"] == e]
    if not xs:
        continue
    dist = med(abs(pct(x["p"], live(x["q"]))) for x in xs)
    fz = J["frozen_quotes"].get(e, {}).get("frozen", 0)
    g = [x for x in gaps if x["ex"] == e]
    J["indicators"][e] = {"quotes": len(xs), "distance": dist, "frozen": fz, "lag": J["lag"].get(e, {}).get("measured"),
                          "shared_with": mirror_of.get(e), "gaps": len(g), "confirmed": sum(1 for x in g if confirmed(x["dev"], x["book"]))}
    say("| %s | %d | %.3f %% | %s | %s | %s | %d | %s |" % (e, len(xs), dist,
        ("%.0f s" % J["lag"][e]["measured"]) if e in J["lag"] else "-", share(fz, len(xs)), mirror_of.get(e, "-"), len(g),
        share(sum(1 for x in g if confirmed(x["dev"], x["book"])), len(g))))

# ------------------------------------------------------------------ E. what is left once the data is right
FEES = 0.20        # % : 4 taker orders at 0.05 % (in and out, two exchanges)
say()
say("## E. What is left once the data is right")
say()
say("Sections B to D are about CMC's quotes. This one uses only the exchanges' own data over the whole run "
    "(%.1f h of order books, %d context cycles): the gaps that do exist in the books, and the funding paid on each side." % (span_h, len(ctx)))

# ---- E1. real gaps in the books: do they close?
series = {}        # (token, sell on a, buy on b) -> [(round, gap you lock, cost of undoing it)]
for tok in TOKENS:
    for a in EXS:
        for b in EXS:
            if a == b or mirror_of.get(a) == b or mirror_of.get(b) == a:
                continue
            pts = []
            for i in range(N):
                qa, qb = Q[i][tok].get(a), Q[i][tok].get(b)
                if not qa or not qb or not (qa[0] and qa[1] and qb[0] and qb[1]):
                    continue
                mid = (qa[0] + qa[1] + qb[0] + qb[1]) / 4
                pts.append((i, (qa[0] - qb[1]) / mid * 100, (qa[1] - qb[0]) / mid * 100))
            if len(pts) >= N // 4:
                series[(tok, a, b)] = pts
allg = [g for pts in series.values() for _, g, _ in pts]
say()
say("### E1. Real gaps between two order books")
say()
say("Executable gap = sell at the best bid of one exchange, buy at the best ask of the other, same round "
    "(%d token and exchange pairs, %d measures; Bybit and Zoomex are one book and are not paired)." % (len(series) // 2, len(allg)))
say()
say("- Median executable gap: %.3f %%." % med(allg))
say("- Measures above %.2f %% (the fees of 4 taker orders): %s." % (FEES, share(sum(1 for g in allg if g >= FEES), len(allg))))
top = sorted(((sum(1 for _, g, _ in pts if g >= FEES) / len(pts), k, pts) for k, pts in series.items()), reverse=True)[:8]
say()
say("| Token | Sell on | Buy on | Rounds with a gap above %.2f %% | Median gap | Lowest | Highest |" % FEES)
say("|---|---|---|---|---|---|---|")
J["real_gaps"] = {"pairs": len(series) // 2, "measures": len(allg), "median_pct": med(allg),
                  "above_fees": sum(1 for g in allg if g >= FEES), "most_persistent": []}
for sh, (tok, a, b), pts in top:
    if sh == 0:
        break
    gs = [g for _, g, _ in pts]
    J["real_gaps"]["most_persistent"].append({"token": tok, "sell": a, "buy": b, "rounds": len(pts), "share_above_fees": sh,
                                              "median_pct": med(gs), "min_pct": min(gs), "max_pct": max(gs)})
    say("| %s | %s | %s | %s | %+.3f %% | %+.3f %% | %+.3f %% |" % (tok, a, b, share(sum(1 for g in gs if g >= FEES), len(gs)),
                                                                    med(gs), min(gs), max(gs)))


def dur(sec):
    return "%.0f s" % sec if sec < 600 else "%.0f min" % (sec / 60) if sec < 7200 else "%.1f h" % (sec / 3600)


def replay(entry, lag):
    """A gap of `entry` is seen; the position opens at once (lag 0) or at the next round, 30 s later (lag 1), at
    whatever the gap is then. It closes as soon as undoing both legs leaves a profit after fees; otherwise it is
    valued at the last round. The most favourable exit rule for the trader."""
    tr = []
    for (tok, a, b), pts in series.items():
        pos, due = None, None
        for i, g, back in pts:
            if pos is None:
                if due is not None and RT[i] - due > 90:      # a hole in our sampling: the signal is void
                    due = None
                if due is not None:
                    pos, due = (i, g), None
                elif g >= entry:
                    if lag:
                        due = RT[i]
                    else:
                        pos = (i, g)
            elif pos[1] - back - FEES > 0:
                tr.append((pos[1] - back - FEES, RT[i] - RT[pos[0]], True))
                pos = None
        if pos is not None:
            tr.append((pos[1] - pts[-1][2] - FEES, RT[pts[-1][0]] - RT[pos[0]], False))
    return tr


say()
say("Replay on the books. A gap of the entry level is seen; the position opens, and closes as soon as undoing both legs "
    "leaves a profit after %.2f %% of fees; otherwise it is valued at the last round. One position at a time per token "
    "and pair, best bid and ask only (size unknown), no slippage. Inside one round the two books are read up to %.0f s "
    "apart, so a gap seen in a single round can be an effect of our own reading order: the second half of the table "
    "opens the position one round later (30 s), at the gap found then." % (FEES, SLOW))
say()
say("| Entry | Gap seen at | Positions | Closed with a profit | Median time to close | Left open at the end | Median result of those left open | Sum of all results | Mean per position |")
say("|---|---|---|---|---|---|---|---|---|")
J["replay"] = {}
for lag in (0, 1):
    for entry in (0.20, 0.30, 0.50):
        tr = replay(entry, lag)
        if not tr:
            continue
        won = [x for x in tr if x[2]]
        op = [x for x in tr if not x[2]]
        J["replay"]["%.2f_lag%d" % (entry, lag)] = {
            "positions": len(tr), "closed_with_profit": len(won), "left_open": len(op),
            "median_close_s": med(x[1] for x in won) if won else None,
            "median_open_result_pct": med(x[0] for x in op) if op else None,
            "sum_pct": sum(x[0] for x in tr), "mean_pct": sum(x[0] for x in tr) / len(tr),
            "median_pct": med(x[0] for x in tr), "winners": sum(1 for x in tr if x[0] > 0)}
        say("| %.2f %% | %s | %d | %s | %s | %d | %s | %+.1f %% | %+.3f %% |" % (
            entry, "the same round" if lag == 0 else "30 s later", len(tr), share(len(won), len(tr)),
            dur(med(x[1] for x in won)) if won else "-", len(op),
            ("%+.3f %%" % med(x[0] for x in op)) if op else "-", sum(x[0] for x in tr), sum(x[0] for x in tr) / len(tr)))
say()
say("The sum is in % of one position's size, all positions added. Each position ties up its size on two exchanges.")

# ---- E2. funding carry between two exchanges
pay = defaultdict(list)            # (exchange, token) -> [(time of the payment, rate in %)]
for e in EXS:
    for tok in TOKENS:
        prev = None
        for c in ctx:
            d = (c["ex"].get(e) or {}).get(tok) or {}
            if d.get("next") is None or d.get("fr") is None:
                continue
            if prev and d["next"] > prev[0] and c["t"] >= prev[0] and prev[0] - prev[2] <= 900:
                pay[(e, tok)].append((prev[0], prev[1] * 100))     # last rate published before the payment
            prev = (d["next"], d["fr"], c["t"])                    # a payment inside a hole of our sampling is dropped
rtc = {}                           # (exchange, token) -> {size: median cost of a round trip in the book, %}
for e in EXS:
    for tok in TOKENS:
        v = {}
        for s_ in SIZES:
            xs = [pct(d["buy%d" % s_], d["sell%d" % s_]) for c in ctx
                  for d in [((c["ex"].get(e) or {}).get(tok) or {}).get("depth") or {}]
                  if d.get("buy%d" % s_) and d.get("sell%d" % s_)]
            if xs:
                v[s_] = med(xs)
        if len(v) == len(SIZES):
            rtc[(e, tok)] = v
cdays = sum(y["t"] - x["t"] for x, y in zip(ctx, ctx[1:]) if y["t"] - x["t"] <= 900) / 86400   # holes are not days
carry = []
for tok in TOKENS:
    es = [e for e in EXS if pay.get((e, tok)) and (e, tok) in rtc]
    for i, a in enumerate(es):
        for b in es[i + 1:]:
            if mirror_of.get(a) == b or mirror_of.get(b) == a:
                continue
            sa, sb = sum(r for _, r in pay[(a, tok)]), sum(r for _, r in pay[(b, tok)])
            sh, lg = (a, b) if sa >= sb else (b, a)          # short where the funding is higher
            # did the sign hold? funding difference of each 8 h window, seen from the chosen side
            win = defaultdict(float)
            for e_, sign in ((sh, 1), (lg, -1)):
                for t_, r in pay[(e_, tok)]:
                    win[int((t_ - 1) // 28800)] += sign * r
            cost = {s_: FEES + rtc[(sh, tok)][s_] + rtc[(lg, tok)][s_] for s_ in SIZES}
            day = abs(sa - sb) / cdays if cdays else 0
            carry.append({"token": tok, "short": sh, "long": lg, "payments_short": len(pay[(sh, tok)]),
                          "payments_long": len(pay[(lg, tok)]), "per_day_pct": day,
                          "windows": len(win), "windows_positive": sum(1 for v in win.values() if v > 0),
                          "cost_pct": {str(s_): cost[s_] for s_ in SIZES},
                          "days_to_pay": {str(s_): (cost[s_] / day if day > 0 else None) for s_ in SIZES}})
nopay = sorted({e for e in EXS if not any(pay.get((e, t)) for t in TOKENS)})
say()
say("### E2. Funding carry between two exchanges")
say()
say("Short the perpetual where the funding is higher, long where it is lower, and collect the difference at each payment. "
    "Payments are rebuilt from each exchange's own schedule: the last rate published before each payment time, over %.1f days "
    "(%d payments read). Cost of getting in and out = %.2f %% of fees plus one round trip in each of the two books "
    "(median of the run).%s" % (cdays, sum(len(v) for v in pay.values()), FEES,
                                (" No payment time published without an account: %s, left out." % ", ".join(nopay)) if nopay else ""))
J["carry"] = {"days": cdays, "payments": sum(len(v) for v in pay.values()), "left_out": nopay, "pairs": len(carry)}
if carry:
    days = [x["per_day_pct"] for x in carry]
    say()
    say("- Token and exchange pairs with funding and depth on both sides: **%d**." % len(carry))
    say("- Funding difference collected per day: median %.4f %%, highest %.4f %%." % (med(days), max(days)))
    for s_ in SIZES:
        k = str(s_)
        d1 = sum(1 for x in carry if x["days_to_pay"][k] is not None and x["days_to_pay"][k] <= 1)
        d7 = sum(1 for x in carry if x["days_to_pay"][k] is not None and x["days_to_pay"][k] <= 7)
        dd = [x["days_to_pay"][k] for x in carry if x["days_to_pay"][k] is not None]
        J["carry"][k] = {"pays_back_in_1_day": d1, "pays_back_in_7_days": d7, "median_days": med(dd) if dd else None}
        say("- For %s $: the cost is paid back within one day on %s, within a week on %s; median %s days, "
            "if the funding stayed what it was during the run." % ("{:,}".format(s_).replace(",", " "), share(d1, len(carry)),
                                                                  share(d7, len(carry)), ("%.0f" % med(dd)) if dd else "-"))
    best = sorted(carry, key=lambda x: -x["per_day_pct"])[:10]
    J["carry"]["best"] = best
    say()
    say("| Token | Short on | Long on | Payments (short / long) | Funding collected per day | 8 h windows in our favour | Cost in and out, 1 000 $ | 10 000 $ | Days to pay back, 1 000 $ | 10 000 $ |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    for x in best:
        say("| %s | %s | %s | %d / %d | %.4f %% | %d / %d | %.2f %% | %.2f %% | %.0f | %.0f |" % (
            x["token"], x["short"], x["long"], x["payments_short"], x["payments_long"], x["per_day_pct"],
            x["windows_positive"], x["windows"], x["cost_pct"]["1000"], x["cost_pct"]["10000"],
            x["days_to_pay"]["1000"], x["days_to_pay"]["10000"]))
    say()
    say("Limits: one to two days of funding say nothing of next week's rates; the price gap between the two exchanges "
        "at entry and at exit is not counted; margin has to sit on both exchanges.")

# raw counts for whoever reuses the report: nothing here is rounded
J["params"] = {"gap_threshold_pct": TH, "slow_s": SLOW, "near_s": NEAR, "frozen_rounds": FROZEN, "same_price_tol_pct": TOL,
               "frozen_quote_s": STILL, "sizes_usd": list(SIZES)}
J["coverage"] = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "book_rounds": N,
                 "first_round": RT[0], "last_round": RT[-1], "holes_over_90s": len(holes),
                 "longest_hole_s": holes[0][0] if holes else 0, "rounds_inside_context_cycle": base,
                 "cmc_snapshots": len(cmc), "cmc_credits": sum(x.get("credits", 0) for x in cmc),
                 "cmc_first": cmc[0]["t"], "cmc_last": cmc[-1]["t"], "context_cycles": len(ctx),
                 "tokens": TOKENS, "exchanges": EXS}
J["thresholds"] = {}
for th in (0.10, 0.20, 0.50, 1.00):
    gth = [x for x in recs if abs(x["dev"]) >= th]
    J["thresholds"]["%.2f" % th] = {"gaps": len(gth), "confirmed": sum(1 for x in gth if confirmed(x["dev"], x["book"]))}


def _count(key):
    res = {}
    for k in sorted({x[key] for x in recs}):
        g = [x for x in gaps if x[key] == k]
        res[k] = {"quotes": sum(1 for x in recs if x[key] == k), "gaps": len(g),
                  "confirmed": sum(1 for x in g if confirmed(x["dev"], x["book"])),
                  "false_by_cause": dict(Counter(x["cause"] for x in false if x[key] == k))}
    return res


J["by_exchange"] = _count("ex")
J["by_token"] = _count("tok")
J["finding"]["false"] = len(false)
J["finding"]["median_gap_pct"] = med(abs(x["dev"]) for x in gaps) if gaps else None
J["finding"]["median_book_pct"] = med(abs(x["book"]) for x in gaps) if gaps else None
J["conditions"] = {k: {"gaps": tags[(k, True)] + tags[(k, False)], "not_confirmed": tags[(k, False)]}
                   for k in ("mirror", "thin", "closed")}
J["wallets"] = {"readable": sorted(wseen), "not_readable": [e for e in EXS if e not in wseen], "pairs_checked": len(wal),
                "closures": {"%s/%s" % k: {"checks": v[0], "deposit_closed": v[1], "withdraw_closed": v[2]}
                             for k, v in closed.items()}}

with open(os.path.join(RUNS, "quality_report.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(out) + "\n")
with open(os.path.join(RUNS, "quality_report.json"), "w", encoding="utf-8") as f:
    json.dump(J, f, indent=1)
