"""Check against real order books: best bid and best ask of USDT perpetuals,
read from the exchanges' own public endpoints at the same instant.

Public market data only: no key, no account, no order.

    python3 verif/carnets.py --rounds 40 --every 30

Each round is written to runs/carnets.jsonl:
  {t, books: {token: {exchange: [bid, ask(, funding)]}},
      px:    {token: {exchange: [last, mark, index]}}}   (None where the exchange does not give it)
"""
import argparse, json, os, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKENS = ["BTC", "ETH", "XRP", "BNB", "SOL", "DOGE", "ADA", "TRX", "LINK", "AVAX", "SUI", "LTC", "DOT", "TON", "HBAR"]


ALIASES = {"GRAM": "TON"}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "spread-scanner/0.1", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read())


def _f(x):
    try:
        v = float(x)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


PX = {}   # exchange -> {token: [last, mark, index]}, filled by _pick during a round


def _pick(rows, key, sym, bid, ask, funding=None, ex=None, last=None, mark=None, index=None):
    out = {}
    want = {sym(t): t for t in TOKENS}
    for alias, t in ALIASES.items():   # Toncoin perps are listed as GRAM on most exchanges
        want.setdefault(sym(alias), t)
    for r in rows:
        t = want.get(r.get(key))
        if t:
            b, a = _f(r.get(bid)), _f(r.get(ask))
            if ex and b and a and a >= b and t not in out:
                PX.setdefault(ex, {})[t] = [_f(r.get(k)) if k else None for k in (last, mark, index)]
            if b and a and a >= b:
                out[t] = [b, a]
                if funding:   # funding rate of the current period, as a fraction (None if not given)
                    try:
                        out[t].append(float(r.get(funding)))
                    except (TypeError, ValueError):
                        out[t].append(None)
    return out


def binance():
    rows = {r["symbol"]: r for r in get("https://fapi.binance.com/fapi/v1/ticker/bookTicker")}
    try:   # last price, mark and index come from two other bulk calls
        for r in get("https://fapi.binance.com/fapi/v1/ticker/price"):
            rows.get(r["symbol"], {})["last"] = r.get("price")
        for r in get("https://fapi.binance.com/fapi/v1/premiumIndex"):
            rows.get(r["symbol"], {}).update(mark=r.get("markPrice"), index=r.get("indexPrice"))
    except Exception:
        pass
    return _pick(rows.values(), "symbol", lambda t: t + "USDT", "bidPrice", "askPrice",
                 ex="binance", last="last", mark="mark", index="index")

def bybit():
    return _pick(get("https://api.bybit.com/v5/market/tickers?category=linear")["result"]["list"], "symbol", lambda t: t + "USDT", "bid1Price", "ask1Price", "fundingRate",
                 ex="bybit", last="lastPrice", mark="markPrice", index="indexPrice")

def okx():
    return _pick(get("https://www.okx.com/api/v5/market/tickers?instType=SWAP")["data"], "instId", lambda t: t + "-USDT-SWAP", "bidPx", "askPx", ex="okx", last="last")

def bitget():
    return _pick(get("https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES")["data"], "symbol", lambda t: t + "USDT", "bidPr", "askPr", "fundingRate",
                 ex="bitget", last="lastPr", mark="markPrice", index="indexPrice")

def kucoin():
    return _pick(get("https://api-futures.kucoin.com/api/v1/allTickers")["data"], "symbol", lambda t: ("XBT" if t == "BTC" else t) + "USDTM", "bestBidPrice", "bestAskPrice", ex="kucoin", last="price")

def mexc():
    return _pick(get("https://contract.mexc.com/api/v1/contract/ticker")["data"], "symbol", lambda t: t + "_USDT", "bid1", "ask1", "fundingRate",
                 ex="mexc", last="lastPrice", mark="fairPrice", index="indexPrice")

def gate():
    return _pick(get("https://api.gateio.ws/api/v4/futures/usdt/tickers"), "contract", lambda t: t + "_USDT", "highest_bid", "lowest_ask", "funding_rate",
                 ex="gate", last="last", mark="mark_price", index="index_price")

HTX_HOSTS = ["api.hbdm.vn", "api.hbdm.com"]   # api.hbdm.com served a frozen snapshot on 26/11/2026 (07:11 UTC onwards)
MAX_AGE = 30                                   # seconds: an exchange tick older than this is not a live quote


def htx():
    worst = None
    for host in HTX_HOSTS:
        rows = get("https://%s/linear-swap-ex/market/detail/batch_merged" % host)["ticks"]
        age = time.time() - max(r.get("ts") or 0 for r in rows) / 1000
        if age <= MAX_AGE:
            rows = [{"c": r.get("contract_code"), "b": (r.get("bid") or [None])[0], "a": (r.get("ask") or [None])[0],
                     "l": r.get("close")} for r in rows if time.time() - (r.get("ts") or 0) / 1000 <= 2 * MAX_AGE]
            return _pick(rows, "c", lambda t: t + "-USDT", "b", "a", ex="htx", last="l")
        worst = age
    raise RuntimeError("HTX feed frozen: newest tick is %.0f s old" % worst)

def whitebit():
    return _pick(get("https://whitebit.com/api/v4/public/futures")["result"], "ticker_id", lambda t: t + "_PERP", "bid", "ask", "funding_rate",
                 ex="whitebit", last="last_price", index="index_price")

def zoomex():
    return _pick(get("https://openapi.zoomex.com/cloud/trade/v3/market/tickers?category=linear")["result"]["list"], "symbol", lambda t: t + "USDT", "bid1Price", "ask1Price", "fundingRate",
                 ex="zoomex", last="lastPrice", mark="markPrice", index="indexPrice")

def phemex():
    return _pick(get("https://api.phemex.com/md/v3/ticker/24hr/all")["result"], "symbol", lambda t: t + "USDT", "bidRp", "askRp", "fundingRateRr",
                 ex="phemex", last="lastRp", mark="markRp", index="indexRp")

EXCHANGES = {"binance": binance, "bybit": bybit, "okx": okx, "bitget": bitget, "kucoin": kucoin, "mexc": mexc,
             "gate": gate, "htx": htx, "whitebit": whitebit, "zoomex": zoomex, "phemex": phemex}


def one_round():
    t0 = time.time()
    PX.clear()
    books, errors, took = {t: {} for t in TOKENS}, {}, {}
    def call(name):
        s = time.time()
        try:
            return name, EXCHANGES[name](), None, time.time() - s
        except Exception as e:  # one exchange down must not stop the round
            return name, {}, str(e)[:120], time.time() - s
    with ThreadPoolExecutor(len(EXCHANGES)) as ex:
        for name, res, err, dt in ex.map(call, EXCHANGES):
            took[name] = round(dt, 2)
            if err:
                errors[name] = err
            for tok, ba in res.items():
                books[tok][name] = ba
    px = {t: {e: v[t] for e, v in PX.items() if t in v} for t in TOKENS}
    return {"t": round(t0, 1), "span_s": round(time.time() - t0, 2), "took": took, "errors": errors,
            "books": books, "px": px}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--every", type=int, default=30)
    ap.add_argument("--out", default="carnets.jsonl", help="file name inside runs/")
    a = ap.parse_args()
    path = os.path.join(ROOT, "runs", a.out)
    for i in range(a.rounds):
        t0 = time.time()
        try:
            r = one_round()
        except Exception as e:   # never stop a long run on one bad round
            print("[%d/%d] round failed: %s" % (i + 1, a.rounds, str(e)[:200]), flush=True)
            time.sleep(a.every)
            continue
        with open(path, "a") as f:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")
        n = {ex: sum(1 for t in TOKENS if ex in r["books"][t]) for ex in EXCHANGES}
        print("[%d/%d] %s  %.1fs  %s  erreurs: %s" % (i + 1, a.rounds, time.strftime("%H:%M:%S", time.gmtime(r["t"])),
              r["span_s"], n, r["errors"] or "aucune"), flush=True)
        if i < a.rounds - 1:
            time.sleep(max(0, a.every - (time.time() - t0)))
