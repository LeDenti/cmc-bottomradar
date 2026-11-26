"""Real order books: best bid and best ask of USDT perpetuals, read from the
exchanges' own public endpoints. Public market data only: no key, no account, no order.

    one_round(["BTC", "ETH"]) -> {"t": epoch, "books": {token: {exchange: [bid, ask]}}, "errors": {...}}
"""
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ALIASES = {"GRAM": "TON"}   # Toncoin perpetuals are listed as GRAM on most exchanges
MAX_AGE = 30                # seconds: an exchange tick older than this is not a live quote


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "bottomradar-cmc/0.2", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read())


def _f(x):
    try:
        v = float(x)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _pick(tokens, rows, key, sym, bid, ask):
    want = {sym(t): t for t in tokens}
    for alias, t in ALIASES.items():
        if t in tokens:
            want.setdefault(sym(alias), t)
    out = {}
    for r in rows:
        t = want.get(r.get(key))
        if t:
            b, a = _f(r.get(bid)), _f(r.get(ask))
            if b and a and a >= b:
                out[t] = [b, a]
    return out


def binance(tk):
    return _pick(tk, _get("https://fapi.binance.com/fapi/v1/ticker/bookTicker"), "symbol", lambda t: t + "USDT", "bidPrice", "askPrice")


def bybit(tk):
    return _pick(tk, _get("https://api.bybit.com/v5/market/tickers?category=linear")["result"]["list"], "symbol",
                 lambda t: t + "USDT", "bid1Price", "ask1Price")


def okx(tk):
    return _pick(tk, _get("https://www.okx.com/api/v5/market/tickers?instType=SWAP")["data"], "instId",
                 lambda t: t + "-USDT-SWAP", "bidPx", "askPx")


def bitget(tk):
    return _pick(tk, _get("https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES")["data"], "symbol",
                 lambda t: t + "USDT", "bidPr", "askPr")


def kucoin(tk):
    return _pick(tk, _get("https://api-futures.kucoin.com/api/v1/allTickers")["data"], "symbol",
                 lambda t: ("XBT" if t == "BTC" else t) + "USDTM", "bestBidPrice", "bestAskPrice")


def mexc(tk):
    return _pick(tk, _get("https://contract.mexc.com/api/v1/contract/ticker")["data"], "symbol", lambda t: t + "_USDT", "bid1", "ask1")


def gate(tk):
    return _pick(tk, _get("https://api.gateio.ws/api/v4/futures/usdt/tickers"), "contract", lambda t: t + "_USDT",
                 "highest_bid", "lowest_ask")


def htx(tk):
    worst = None
    for host in ("api.hbdm.vn", "api.hbdm.com"):   # one HTX host was seen serving a frozen snapshot
        rows = _get("https://%s/linear-swap-ex/market/detail/batch_merged" % host)["ticks"]
        age = time.time() - max(r.get("ts") or 0 for r in rows) / 1000
        if age <= MAX_AGE:
            rows = [{"c": r.get("contract_code"), "b": (r.get("bid") or [None])[0], "a": (r.get("ask") or [None])[0]}
                    for r in rows if time.time() - (r.get("ts") or 0) / 1000 <= 2 * MAX_AGE]
            return _pick(tk, rows, "c", lambda t: t + "-USDT", "b", "a")
        worst = age
    raise RuntimeError("HTX feed frozen: newest tick is %.0f s old" % worst)


def whitebit(tk):
    return _pick(tk, _get("https://whitebit.com/api/v4/public/futures")["result"], "ticker_id", lambda t: t + "_PERP", "bid", "ask")


def zoomex(tk):
    return _pick(tk, _get("https://openapi.zoomex.com/cloud/trade/v3/market/tickers?category=linear")["result"]["list"], "symbol",
                 lambda t: t + "USDT", "bid1Price", "ask1Price")


def phemex(tk):
    return _pick(tk, _get("https://api.phemex.com/md/v3/ticker/24hr/all")["result"], "symbol", lambda t: t + "USDT", "bidRp", "askRp")


# keys are CoinMarketCap exchange slugs
EXCHANGES = {"binance": binance, "bybit": bybit, "okx": okx, "bitget": bitget, "kucoin": kucoin, "mexc": mexc,
             "gate": gate, "htx": htx, "whitebit": whitebit, "zoomex": zoomex, "phemex": phemex}


def one_round(tokens):
    t0 = time.time()
    books, errors = {t: {} for t in tokens}, {}

    def call(name):
        try:
            return name, EXCHANGES[name](tokens), None
        except Exception as e:   # one exchange down must not stop the round
            return name, {}, str(e)[:120]

    with ThreadPoolExecutor(len(EXCHANGES)) as ex:
        for name, res, err in ex.map(call, EXCHANGES):
            if err:
                errors[name] = err
            for tok, ba in res.items():
                books[tok][name] = ba
    return {"t": round(t0 + (time.time() - t0) / 2, 1), "span_s": round(time.time() - t0, 2), "books": books, "errors": errors}
