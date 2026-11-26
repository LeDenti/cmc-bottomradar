"""Price data from CoinMarketCap, cached on disk so that each scan only pays for new points.

Endpoints used:
- GET /v1/cryptocurrency/map              (symbol -> CMC id, once)
- GET /v3/cryptocurrency/quotes/historical (interval=10m: RSI and market index;
                                            interval=daily: trend filters)
Cost: 1 credit per 100 points returned. The first 10-minute load is ~3 credits
per token; afterwards one request for all tokens costs ~2 credits.
"""
import json
import os
import time

from .client import CMC, RUNS, parse_quotes_historical

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
CACHE = os.path.join(RUNS, "cache")

BAR = 600
DAY = 86400
MAX_POINTS = 9500  # CMC limit: 10 000 data points per request (all ids together)


def kraken_to_symbol(sym):
    """'PF_XBTUSD' -> 'BTC', 'PF_SOLUSD' -> 'SOL'."""
    s = sym[3:-3] if sym.startswith("PF_") and sym.endswith("USD") else sym
    return {"XBT": "BTC"}.get(s, s)


# CMC symbols are case-sensitive for a few tokens.
CMC_CASE = {"XAUT": "XAUt"}


def load_universe(name="universe_75"):
    return [kraken_to_symbol(s) for s in json.load(open(os.path.join(DATA, name + ".json")))]


def build_id_map(cmc, symbols):
    """Resolve symbols with /v1/cryptocurrency/map; ties broken by best CMC rank."""
    query = sorted({CMC_CASE.get(s, s) for s in symbols})
    doc = cmc.get("/v1/cryptocurrency/map", symbol=",".join(query))
    best = {}
    for d in doc["data"]:
        if not d.get("is_active"):
            continue
        s = d["symbol"].upper()
        r = d.get("rank") or 10 ** 9
        if s not in best or r < best[s][0]:
            best[s] = (r, {"id": d["id"], "slug": d["slug"], "name": d["name"], "rank": d.get("rank")})
    return {s: v for s, (_, v) in sorted(best.items())}


def id_map():
    return json.load(open(os.path.join(DATA, "cmc_ids.json")))


def snap(points, step=BAR):
    """CMC returns the quote closest to each requested time. A quote near the
    boundary t is taken as the close of the bar that ENDS at t.
    Returns {bar_index: close} where bar k covers [k*step, (k+1)*step)."""
    out = {}
    for t, p in points:
        k = int((t + step // 2) // step) - 1
        out[k] = p
    return out


class Store:
    """Disk cache {interval: {cmc_id: [[epoch, price], ...]}}."""

    def __init__(self, path=os.path.join(CACHE, "quotes.json")):
        self.path = path
        self.d = {}
        if os.path.exists(path):
            with open(path) as f:
                self.d = json.load(f)

    def series(self, interval, cid):
        return [tuple(x) for x in self.d.get(interval, {}).get(str(cid), [])]

    def merge(self, interval, new):
        bucket = self.d.setdefault(interval, {})
        for cid, pts in new.items():
            old = {int(t): p for t, p in bucket.get(str(cid), [])}
            for t, p in pts:
                old[int(t)] = p
            bucket[str(cid)] = sorted([t, p] for t, p in old.items())

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.d, f)
        os.replace(tmp, self.path)


def fetch(cmc, store, ids, interval, span_s, batch=10, now=None):
    """Make sure store holds `span_s` seconds of `interval` quotes for every id.

    Ids already cached are topped up from their last point (cheap); new ids get
    the whole span. Returns the number of credits spent.
    """
    now = int(now or time.time())
    spent0 = cmc.credits
    fresh, topup = [], {}
    for cid in ids:
        s = store.series(interval, cid)
        if s and s[0][0] <= now - span_s + 2 * _step(interval):
            topup[cid] = s[-1][0]
        else:
            fresh.append(cid)
    # CMC caps a request at 10 000 data points across all ids sent.
    per_id = span_s // _step(interval) + 2
    batch = max(1, min(batch, MAX_POINTS // per_id))
    for i in range(0, len(fresh), batch):
        part = fresh[i:i + batch]
        doc = cmc.get("/v3/cryptocurrency/quotes/historical", id=",".join(map(str, part)),
                      interval=interval, time_start=_iso(now - span_s), time_end=_iso(now),
                      aux="price", skip_invalid="true")
        store.merge(interval, parse_quotes_historical(doc))
    if topup:
        start = min(topup.values()) + 1
        if now - start >= _step(interval):
            ids_t = sorted(topup)
            n = max(1, min(80, MAX_POINTS // ((now - start) // _step(interval) + 2)))
            for i in range(0, len(ids_t), n):
                doc = cmc.get("/v3/cryptocurrency/quotes/historical", id=",".join(map(str, ids_t[i:i + n])),
                              interval=interval, time_start=_iso(start), time_end=_iso(now),
                              aux="price", skip_invalid="true")
                store.merge(interval, parse_quotes_historical(doc))
    _trim(store, interval, now - span_s - 2 * _step(interval))
    store.save()
    return cmc.credits - spent0


def _trim(store, interval, oldest):
    for cid, pts in store.d.get(interval, {}).items():
        store.d[interval][cid] = [x for x in pts if x[0] >= oldest]


def _step(interval):
    return {"10m": BAR, "5m": 300, "1h": 3600, "daily": DAY}.get(interval, BAR)


def _iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(t)))
