"""Context of the price gaps, read from the exchanges' public endpoints.

Every cycle (default 5 min), for 15 USDT perpetuals on 11 exchanges:
- funding: current rate, time of the next payment, period in hours,
  index price and mark price;
- depth: average price to buy and to sell 1 000 $ and 10 000 $ (50 levels);
Every hour: deposit / withdrawal status of each token and of USDT, where the
exchange publishes it without an account.

Public market data only: no key, no account, no order.

    python3 verif/contexte.py --cycles 1
    python3 verif/contexte.py --cycles 288 --every 300 --out contexte_24h.jsonl
"""
import argparse, json, os, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKENS = ["BTC", "ETH", "XRP", "BNB", "SOL", "DOGE", "ADA", "TRX", "LINK", "AVAX", "SUI", "LTC", "DOT", "TON", "HBAR"]
NAMES = {"TON": ["GRAM", "TON"]}       # Toncoin perps are listed as GRAM; the old TON ticker is often a dead listing
SIZES = [1000, 10000]


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "spread-scanner/0.1", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _ms(x):
    """Timestamp in seconds from seconds or milliseconds."""
    v = _f(x)
    if not v:
        return None
    return int(v / 1000) if v > 1e11 else int(v)


def resolve(rows, key, fmt):
    """{token: (native symbol, row)}; first name of NAMES that the exchange lists."""
    by = {r.get(key): r for r in rows}
    out = {}
    for t in TOKENS:
        for name in NAMES.get(t, [t]):
            s = fmt(name)
            if s in by:
                out[t] = (s, by[s])
                break
    return out


def vwap(levels, usd):
    """Average price to trade `usd` dollars through `levels` [(price, base qty)], best first."""
    left, base = usd, 0.0
    for p, q in levels:
        take = min(left, p * q)
        base += take / p
        left -= take
        if left <= 1e-9:
            return usd / base
    return None      # the 50 levels read do not hold that much


def book_stats(bids, asks):
    out = {"bid": bids[0][0] if bids else None, "ask": asks[0][0] if asks else None}
    for n in SIZES:
        out["buy%d" % n] = vwap(asks, n)
        out["sell%d" % n] = vwap(bids, n)
    out["usd_bids"] = round(sum(p * q for p, q in bids))
    out["usd_asks"] = round(sum(p * q for p, q in asks))
    return out


def _lv(rows, mult=1.0, pk=0, qk=1):
    out = []
    for r in rows:
        p, q = _f(r[pk]), _f(r[qk])
        if p and q:
            out.append((p, abs(q) * mult))
    return out


# ---------------------------------------------------------------- exchanges
# each returns {token: {"sym", "fr", "next", "period_h", "index", "mark", "depth": {...}}}

def _depths(found, fetch):
    for t, d in found.items():
        try:
            bids, asks = fetch(d["sym"], d)
            bids.sort(key=lambda x: -x[0]); asks.sort(key=lambda x: x[0])
            d["depth"] = book_stats(bids, asks)
            d["at"] = round(time.time(), 1)   # when this book was read
        except Exception as e:
            d["depth_error"] = str(e)[:100]
        d.pop("_mult", None)
        time.sleep(0.12)
    return found


def binance():
    rows = get("https://fapi.binance.com/fapi/v1/premiumIndex")
    try:
        period = {r["symbol"]: r.get("fundingIntervalHours") for r in get("https://fapi.binance.com/fapi/v1/fundingInfo")}
    except Exception:
        period = {}
    found = {t: {"sym": s, "fr": _f(r.get("lastFundingRate")), "next": _ms(r.get("nextFundingTime")),
                 "period_h": period.get(s, 8), "index": _f(r.get("indexPrice")), "mark": _f(r.get("markPrice"))}
             for t, (s, r) in resolve(rows, "symbol", lambda n: n + "USDT").items()}
    def fetch(s, d):
        b = get("https://fapi.binance.com/fapi/v1/depth?symbol=%s&limit=50" % s)
        return _lv(b["bids"]), _lv(b["asks"])
    return _depths(found, fetch)


def _bybit_like(base):
    def run():
        rows = get(base + "/tickers?category=linear")["result"]["list"]
        found = {t: {"sym": s, "fr": _f(r.get("fundingRate")), "next": _ms(r.get("nextFundingTime")),
                     "period_h": _f(r.get("fundingIntervalHour")), "index": _f(r.get("indexPrice")), "mark": _f(r.get("markPrice"))}
                 for t, (s, r) in resolve(rows, "symbol", lambda n: n + "USDT").items()}
        def fetch(s, d):
            b = get(base + "/orderbook?category=linear&symbol=%s&limit=50" % s)["result"]
            return _lv(b["b"]), _lv(b["a"])
        return _depths(found, fetch)
    return run

bybit = _bybit_like("https://api.bybit.com/v5/market")
zoomex = _bybit_like("https://openapi.zoomex.com/cloud/trade/v3/market")


def okx():
    inst = get("https://www.okx.com/api/v5/public/instruments?instType=SWAP")["data"]
    found = {}
    for t, (s, r) in resolve(inst, "instId", lambda n: n + "-USDT-SWAP").items():
        d = {"sym": s, "_mult": (_f(r.get("ctVal")) or 1) * (_f(r.get("ctMult")) or 1)}
        try:
            fr = get("https://www.okx.com/api/v5/public/funding-rate?instId=" + s)["data"][0]
            nxt, after = _ms(fr.get("fundingTime")), _ms(fr.get("nextFundingTime"))
            d.update({"fr": _f(fr.get("fundingRate")), "next": nxt,
                      "period_h": round((after - nxt) / 3600, 2) if nxt and after else None})
        except Exception as e:
            d["funding_error"] = str(e)[:100]
        found[t] = d
        time.sleep(0.12)
    try:
        for r in get("https://www.okx.com/api/v5/public/mark-price?instType=SWAP")["data"]:
            for d in found.values():
                if d["sym"] == r.get("instId"):
                    d["mark"] = _f(r.get("markPx"))
    except Exception:
        pass
    def fetch(s, d):
        b = get("https://www.okx.com/api/v5/market/books?instId=%s&sz=50" % s)["data"][0]
        return _lv(b["bids"], d["_mult"]), _lv(b["asks"], d["_mult"])
    return _depths(found, fetch)


def bitget():
    rows = get("https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES")["data"]
    found = {}
    for t, (s, r) in resolve(rows, "symbol", lambda n: n + "USDT").items():
        d = {"sym": s, "fr": _f(r.get("fundingRate")), "index": _f(r.get("indexPrice")), "mark": _f(r.get("markPrice"))}
        try:
            ft = get("https://api.bitget.com/api/v2/mix/market/funding-time?productType=usdt-futures&symbol=" + s)["data"][0]
            d.update({"next": _ms(ft.get("nextFundingTime")), "period_h": _f(ft.get("ratePeriod"))})
        except Exception as e:
            d["funding_error"] = str(e)[:100]
        found[t] = d
        time.sleep(0.12)
    def fetch(s, d):
        b = get("https://api.bitget.com/api/v2/mix/market/merge-depth?productType=usdt-futures&symbol=%s&limit=50" % s)["data"]
        return _lv(b["bids"]), _lv(b["asks"])
    return _depths(found, fetch)


def kucoin():
    rows = get("https://api-futures.kucoin.com/api/v1/contracts/active")["data"]
    found = {t: {"sym": s, "fr": _f(r.get("fundingFeeRate")), "next": _ms(r.get("nextFundingRateDateTime")),
                 "period_h": (_f(r.get("fundingRateGranularity")) or 0) / 3600000 or None,
                 "index": _f(r.get("indexPrice")), "mark": _f(r.get("markPrice")), "_mult": _f(r.get("multiplier")) or 1}
             for t, (s, r) in resolve(rows, "symbol", lambda n: ("XBT" if n == "BTC" else n) + "USDTM").items()}
    def fetch(s, d):
        b = get("https://api-futures.kucoin.com/api/v1/level2/depth100?symbol=" + s)["data"]
        return _lv(b["bids"][:50], d["_mult"]), _lv(b["asks"][:50], d["_mult"])
    return _depths(found, fetch)


def mexc():
    det = get("https://contract.mexc.com/api/v1/contract/detail")["data"]
    tick = {r["symbol"]: r for r in get("https://contract.mexc.com/api/v1/contract/ticker")["data"]}
    found = {}
    for t, (s, r) in resolve(det, "symbol", lambda n: n + "_USDT").items():
        k = tick.get(s, {})
        d = {"sym": s, "fr": _f(k.get("fundingRate")), "index": _f(k.get("indexPrice")), "mark": _f(k.get("fairPrice")),
             "_mult": _f(r.get("contractSize")) or 1}
        try:
            fr = get("https://contract.mexc.com/api/v1/contract/funding_rate/" + s)["data"]
            d.update({"fr": _f(fr.get("fundingRate")), "next": _ms(fr.get("nextSettleTime")), "period_h": _f(fr.get("collectCycle"))})
        except Exception as e:
            d["funding_error"] = str(e)[:100]
        found[t] = d
        time.sleep(0.12)
    def fetch(s, d):
        b = get("https://contract.mexc.com/api/v1/contract/depth/%s?limit=50" % s)["data"]
        return _lv(b["bids"], d["_mult"]), _lv(b["asks"], d["_mult"])
    return _depths(found, fetch)


def gate():
    rows = get("https://api.gateio.ws/api/v4/futures/usdt/contracts")
    found = {t: {"sym": s, "fr": _f(r.get("funding_rate")), "next": _ms(r.get("funding_next_apply")),
                 "period_h": (_f(r.get("funding_interval")) or 0) / 3600 or None,
                 "index": _f(r.get("index_price")), "mark": _f(r.get("mark_price")), "_mult": _f(r.get("quanto_multiplier")) or 1}
             for t, (s, r) in resolve(rows, "name", lambda n: n + "_USDT").items()}
    def fetch(s, d):
        b = get("https://api.gateio.ws/api/v4/futures/usdt/order_book?contract=%s&limit=50" % s)
        return (_lv([(x["p"], x["s"]) for x in b["bids"]], d["_mult"]),
                _lv([(x["p"], x["s"]) for x in b["asks"]], d["_mult"]))
    return _depths(found, fetch)


HTX_HOSTS = ["api.hbdm.vn", "api.hbdm.com"]   # api.hbdm.com served a frozen snapshot on 26/11/2026 (07:11 UTC onwards)
MAX_AGE = 30                                   # seconds: a book older than this is not a live book


def htx():
    host = None
    for h in HTX_HOSTS:   # keep the first host whose BTC book is live
        tick = get("https://%s/linear-swap-ex/market/depth?contract_code=BTC-USDT&type=step0" % h)["tick"]
        if time.time() - tick["ts"] / 1000 <= MAX_AGE:
            host = h
            break
    if host is None:
        raise RuntimeError("HTX feed frozen on every host")
    info = get("https://%s/linear-swap-api/v1/swap_contract_info" % host)["data"]
    fr = {r["contract_code"]: r for r in get("https://%s/linear-swap-api/v1/swap_batch_funding_rate" % host)["data"]}
    found = {}
    for t, (s, r) in resolve(info, "contract_code", lambda n: n + "-USDT").items():
        k = fr.get(s, {})
        found[t] = {"sym": s, "fr": _f(k.get("funding_rate")), "next": _ms(k.get("funding_time")), "period_h": None,
                    "_mult": _f(r.get("contract_size")) or 1}
    def fetch(s, d):
        b = get("https://%s/linear-swap-ex/market/depth?contract_code=%s&type=step0" % (host, s))["tick"]
        if time.time() - b["ts"] / 1000 > 4 * MAX_AGE:   # quiet books tick less often than BTC
            raise RuntimeError("stale book")
        return _lv(b["bids"][:50], d["_mult"]), _lv(b["asks"][:50], d["_mult"])
    return _depths(found, fetch)


def whitebit():
    rows = get("https://whitebit.com/api/v4/public/futures")["result"]
    found = {t: {"sym": s, "fr": _f(r.get("funding_rate")), "next": _ms(r.get("next_funding_rate_timestamp")),
                 "period_h": None, "index": _f(r.get("index_price")), "mark": _f(r.get("mark_price"))}
             for t, (s, r) in resolve(rows, "ticker_id", lambda n: n + "_PERP").items()}
    def fetch(s, d):
        b = get("https://whitebit.com/api/v4/public/orderbook/%s?limit=50&level=0" % s)
        return _lv(b["bids"]), _lv(b["asks"])
    return _depths(found, fetch)


def phemex():
    rows = get("https://api.phemex.com/md/v3/ticker/24hr/all")["result"]
    found = {t: {"sym": s, "fr": _f(r.get("fundingRateRr")), "next": None, "period_h": None,
                 "index": _f(r.get("indexRp")), "mark": _f(r.get("markRp"))}
             for t, (s, r) in resolve(rows, "symbol", lambda n: n + "USDT").items()}
    def fetch(s, d):
        b = get("https://api.phemex.com/md/v2/orderbook?symbol=" + s)["result"]["orderbook_p"]
        return _lv(b["bids"][:50]), _lv(b["asks"][:50])
    return _depths(found, fetch)


EXCHANGES = {"binance": binance, "bybit": bybit, "okx": okx, "bitget": bitget, "kucoin": kucoin, "mexc": mexc,
             "gate": gate, "htx": htx, "whitebit": whitebit, "zoomex": zoomex, "phemex": phemex}


# ------------------------------------------------- deposits and withdrawals
# Only the exchanges that publish the status without an account.

def _coins():
    return [n for t in TOKENS for n in NAMES.get(t, [t])] + ["USDT"]


def w_bitget():
    out = {}
    for r in get("https://api.bitget.com/api/v2/spot/public/coins")["data"]:
        if r.get("coin") in _coins():
            ch = r.get("chains") or []
            out[r["coin"]] = {"deposit": any(c.get("rechargeable") == "true" for c in ch),
                              "withdraw": any(c.get("withdrawable") == "true" for c in ch), "chains": len(ch)}
    return out


def w_kucoin():
    out = {}
    for r in get("https://api.kucoin.com/api/v3/currencies")["data"]:
        if r.get("currency") in _coins():
            ch = r.get("chains") or []
            out[r["currency"]] = {"deposit": any(c.get("isDepositEnabled") for c in ch),
                                  "withdraw": any(c.get("isWithdrawEnabled") for c in ch), "chains": len(ch)}
    return out


def w_gate():
    out = {}
    for r in get("https://api.gateio.ws/api/v4/spot/currencies"):
        c = (r.get("currency") or "").split("_")[0]
        if c in _coins():
            cur = out.setdefault(c, {"deposit": False, "withdraw": False, "chains": 0})
            cur["deposit"] = cur["deposit"] or not r.get("deposit_disabled")
            cur["withdraw"] = cur["withdraw"] or not r.get("withdraw_disabled")
            cur["chains"] += 1
    return out


def w_htx():
    out = {}
    for r in get("https://api.huobi.pro/v2/reference/currencies")["data"]:
        c = (r.get("currency") or "").upper()
        if c in _coins():
            ch = r.get("chains") or []
            out[c] = {"deposit": any(x.get("depositStatus") == "allowed" for x in ch),
                      "withdraw": any(x.get("withdrawStatus") == "allowed" for x in ch), "chains": len(ch)}
    return out


def w_whitebit():
    out = {}
    for c, r in get("https://whitebit.com/api/v4/public/assets").items():
        if c in _coins():
            out[c] = {"deposit": bool(r.get("can_deposit")), "withdraw": bool(r.get("can_withdraw")),
                      "chains": len(((r.get("networks") or {}).get("deposits")) or [])}
    return out


WALLETS = {"bitget": w_bitget, "kucoin": w_kucoin, "gate": w_gate, "htx": w_htx, "whitebit": w_whitebit}


def _all(funcs):
    out, errors, took = {}, {}, {}
    def call(name):
        s = time.time()
        try:
            return name, funcs[name](), None, time.time() - s
        except Exception as e:
            return name, {}, str(e)[:150], time.time() - s
    with ThreadPoolExecutor(len(funcs)) as ex:
        for name, res, err, dt in ex.map(call, funcs):
            out[name], took[name] = res, round(dt, 1)
            if err:
                errors[name] = err
    return out, errors, took


def one_cycle(with_wallets):
    t0 = time.time()
    data, errors, took = _all(EXCHANGES)
    row = {"t": round(t0, 1), "took": took, "errors": errors, "ex": data}
    if with_wallets:
        row["wallets"], werr, _ = _all(WALLETS)
        if werr:
            row["wallet_errors"] = werr
    row["span_s"] = round(time.time() - t0, 1)
    return row


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycles", type=int, default=1)
    ap.add_argument("--every", type=int, default=300)
    ap.add_argument("--wallets-every", type=int, default=12, help="cycles between two deposit/withdrawal checks")
    ap.add_argument("--out", default="contexte.jsonl", help="file name inside runs/")
    a = ap.parse_args()
    path = os.path.join(ROOT, "runs", a.out)
    for i in range(a.cycles):
        t0 = time.time()
        try:
            r = one_cycle(i % a.wallets_every == 0)
        except Exception as e:
            print("[%d/%d] cycle failed: %s" % (i + 1, a.cycles, str(e)[:200]), flush=True)
            time.sleep(a.every)
            continue
        with open(path, "a") as f:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")
        n = {e: "%d/%d" % (sum(1 for d in v.values() if d.get("depth")), len(v)) for e, v in r["ex"].items()}
        print("[%d/%d] %s  %.0fs  carnets lus %s  erreurs: %s%s" % (
            i + 1, a.cycles, time.strftime("%H:%M:%S", time.gmtime(r["t"])), r["span_s"], n, r["errors"] or "aucune",
            ("  retraits: %s" % sorted(r["wallets"])) if "wallets" in r else ""), flush=True)
        if i < a.cycles - 1:
            time.sleep(max(0, a.every - (time.time() - t0)))
