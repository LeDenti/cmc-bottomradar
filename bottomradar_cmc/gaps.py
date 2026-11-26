"""Do the price gaps CoinMarketCap shows between exchanges exist in the real order books?

For a few perpetuals, take the CMC quote of every exchange
(GET /v5/cryptocurrency/derivatives/market-pairs/list/latest, 1 credit per token),
read the public order books of the same exchanges at the same instant, and compare:

  CMC gap   = exchange price on CMC  vs the median of the exchanges on CMC
  book gap  = exchange mid in its own book vs the median of the books

A CMC gap of at least GAP_PCT is "confirmed" when the book shows a gap of the same
sign and at least half the size. Everything else is a data artefact (late or frozen
quote), not something one could trade. This is a data-quality check, not a trading signal.
"""
import calendar
import statistics
import time

from . import books as bk

TOKENS = {"BTC": 1, "ETH": 1027, "SOL": 5426, "XRP": 52, "SUI": 20947, "TON": 11419, "HBAR": 4642, "DOT": 6636}
USDT = 825
GAP_PCT = 0.20          # a "gap": a quote at least this far from the median of the same token
MIN_VOLUME_USD = 1e6    # ignore markets below this 24 h volume when taking the CMC median
MAX_AGE_S = 600         # ignore CMC quotes older than this


def _epoch(s):
    if not s:
        return None
    try:
        return calendar.timegm(time.strptime(s.rstrip("Z").split(".")[0], "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        return None


def fetch_cmc(cmc, tokens=None):
    """{token: {"t": call time, "quotes": [{exchange, price, last_updated, volume_usd, flagged}]}}"""
    out = {}
    for sym, cid in (tokens or TOKENS).items():
        t = time.time()
        doc = cmc.get("/v5/cryptocurrency/derivatives/market-pairs/list/latest", crypto_id=cid, category="perpetual",
                      matched_id=USDT, center_type="cex", limit=250, sort="volume_24h_strict")
        rows = []
        for m in (doc.get("data") or {}).get("market_pairs") or []:
            rep = (m.get("exchange_reported_quotes") or [{}])[0]
            q = (m.get("quotes") or [{}])[0]
            try:
                price = float(rep.get("price"))
            except (TypeError, ValueError):
                continue
            if price <= 0:
                continue
            rows.append({"exchange": (m.get("exchange") or {}).get("exchange_slug"), "price": price,
                         "last_updated": _epoch(rep.get("last_updated") or q.get("last_updated")),
                         "volume_usd": q.get("volume_24h") or 0,
                         "flagged": bool(m.get("outlier_detected")) or bool(m.get("exclusions"))})
        out[sym] = {"t": t, "quotes": rows}
    return out


def judge(cmc_quotes, rounds, gap_pct=GAP_PCT):
    """Compare CMC quotes with order-book rounds. Pure function, no network.

    cmc_quotes: output of fetch_cmc. rounds: list of books.one_round results.
    Returns {"rows": [...], "summary": {...}}.
    """
    rows = []
    for sym, snap in cmc_quotes.items():
        t = snap["t"]
        live = [q for q in snap["quotes"] if q["volume_usd"] >= MIN_VOLUME_USD
                and (q["last_updated"] is None or t - q["last_updated"] <= MAX_AGE_S)]
        if len(live) < 5:
            continue
        cmc_med = statistics.median(q["price"] for q in live)
        rnd = min(rounds, key=lambda r: abs(r["t"] - t)) if rounds else None
        book = (rnd or {}).get("books", {}).get(sym, {})
        mids = {ex: (b + a) / 2 for ex, (b, a) in book.items()}
        book_med = statistics.median(mids.values()) if len(mids) >= 3 else None
        for q in live:
            ex = q["exchange"]
            if ex not in mids or book_med is None:
                continue
            cmc_gap = (q["price"] / cmc_med - 1) * 100
            book_gap = (mids[ex] / book_med - 1) * 100
            is_gap = abs(cmc_gap) >= gap_pct
            confirmed = is_gap and cmc_gap * book_gap > 0 and abs(book_gap) >= abs(cmc_gap) / 2
            rows.append({"token": sym, "exchange": ex, "cmc_price": q["price"], "cmc_gap_pct": round(cmc_gap, 3),
                         "book_mid": mids[ex], "book_gap_pct": round(book_gap, 3),
                         "spread_pct": round((book[ex][1] / book[ex][0] - 1) * 100, 3),
                         "quote_age_s": int(t - q["last_updated"]) if q["last_updated"] else None,
                         "book_skew_s": round(rnd["t"] - t, 1), "flagged_by_cmc": q["flagged"],
                         "is_gap": is_gap, "confirmed": confirmed})
    gaps = [r for r in rows if r["is_gap"]]
    conf = [r for r in gaps if r["confirmed"]]
    ages = sorted(r["quote_age_s"] for r in rows if r["quote_age_s"] is not None)
    rows.sort(key=lambda r: (not r["is_gap"], -abs(r["cmc_gap_pct"])))
    return {"rows": rows, "summary": {
        "quotes_checked": len(rows), "gap_threshold_pct": gap_pct, "cmc_gaps": len(gaps), "confirmed_in_book": len(conf),
        "not_in_book": len(gaps) - len(conf), "median_quote_age_s": ages[len(ages) // 2] if ages else None,
        "tokens": sorted({r["token"] for r in rows}), "exchanges": sorted({r["exchange"] for r in rows})}}


def check(cmc, tokens=None):
    """One live check: a round of books, the CMC quotes, another round of books."""
    tokens = tokens or TOKENS
    c0 = cmc.credits
    before = bk.one_round(list(tokens))
    quotes = fetch_cmc(cmc, tokens)
    after = bk.one_round(list(tokens))
    out = judge(quotes, [before, after])
    out["generated"] = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    out["book_errors"] = {**before["errors"], **after["errors"]}
    out["api"] = {"credits": cmc.credits - c0, "calls": len(tokens)}
    return out
