"""Minimal CoinMarketCap Pro API client (standard library only).

Every call is logged to runs/calls.jsonl (endpoint, params, HTTP status,
credit_count, elapsed) and the first response of each endpoint is saved to
runs/evidence/ so a reviewer can see real calls and real responses.
The API key is read from the environment or from .env and is never logged.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://pro-api.coinmarketcap.com"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = os.environ.get("BRCMC_RUNS") or os.path.join(ROOT, "runs")

# Endpoints that also work without a key, under the /public-api prefix.
KEYLESS = {
    "/v1/cryptocurrency/map",
    "/v3/cryptocurrency/listings/latest",
    "/v3/cryptocurrency/quotes/latest",
    "/v3/fear-and-greed/latest",
    "/v3/fear-and-greed/historical",
    "/v3/index/cmc100-latest",
    "/v3/index/cmc100-historical",
    "/v1/altcoin-season-index/latest",
    "/v1/global-metrics/quotes/latest",
}


class CMCError(RuntimeError):
    pass


def _load_key():
    key = os.environ.get("CMC_API_KEY", "").strip()
    if key:
        return key
    path = os.path.join(ROOT, ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line.startswith("CMC_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


class CMC:
    def __init__(self, key=None, pause=1.3, log=True):
        self.key = _load_key() if key is None else key
        self.pause = pause  # Basic plan: 50 requests per minute
        self.log = log
        self.credits = 0
        self.calls = 0
        self._last = 0.0
        self._seen = set()

    @property
    def keyed(self):
        return bool(self.key)

    def get(self, path, **params):
        params = {k: v for k, v in params.items() if v is not None}
        if self.keyed:
            url = BASE + path
            headers = {"Accept": "application/json", "X-CMC_PRO_API_KEY": self.key}
        elif path in KEYLESS:
            url = BASE + "/public-api" + path
            headers = {"Accept": "application/json"}
        else:
            raise CMCError("%s needs an API key: put CMC_API_KEY in .env" % path)
        if params:
            url += "?" + urllib.parse.urlencode(params)
        for attempt in range(6):
            wait = self.pause - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            t0 = time.time()
            self._last = t0
            status, body = None, None
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
                    status, body = r.status, r.read()
            except urllib.error.HTTPError as e:
                status, body = e.code, e.read()
            except urllib.error.URLError as e:
                status, body = 0, json.dumps({"status": {"error_message": str(e)}}).encode()
            elapsed = round(time.time() - t0, 3)
            try:
                doc = json.loads(body or b"{}")
            except ValueError:
                doc = {"status": {"error_message": (body or b"")[:200].decode("utf-8", "replace")}}
            st = doc.get("status") or {}
            credits = int(st.get("credit_count") or 0)
            self.calls += 1
            self.credits += credits
            self._record(path, params, status, st, credits, elapsed, doc)
            if status == 429 and attempt < 5:
                time.sleep(2 ** attempt)
                continue
            if status != 200 or st.get("error_code") not in (0, "0", None):
                raise CMCError("%s -> HTTP %s, %s" % (path, status, st.get("error_message")))
            return doc
        raise CMCError("%s -> too many retries" % path)

    def _record(self, path, params, status, st, credits, elapsed, doc):
        if not self.log:
            return
        os.makedirs(os.path.join(RUNS, "evidence"), exist_ok=True)
        line = {
            "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "endpoint": path,
            "keyless": not self.keyed,
            "params": params,
            "http": status,
            "error_code": st.get("error_code"),
            "credit_count": credits,
            "elapsed_s": elapsed,
        }
        with open(os.path.join(RUNS, "calls.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
        if status == 200 and path not in self._seen:
            self._seen.add(path)
            name = path.strip("/").replace("/", "_") + ".json"
            with open(os.path.join(RUNS, "evidence", name), "w", encoding="utf-8") as f:
                json.dump({"request": {"endpoint": path, "params": params}, "response": _trim(doc)}, f, indent=1)


def _trim(doc, n=3):
    """Keep the evidence files short: at most n items per list, recursively."""
    if isinstance(doc, list):
        return [_trim(x, n) for x in doc[:n]] + (["... %d more" % (len(doc) - n)] if len(doc) > n else [])
    if isinstance(doc, dict):
        items = list(doc.items())
        out = {k: _trim(v, n) for k, v in items[:12]}
        if len(items) > 12:
            out["..."] = "%d more keys" % (len(items) - 12)
        return out
    return doc


def iso_to_epoch(s):
    """'2026-11-23T09:40:00.000Z' -> epoch seconds (UTC)."""
    import calendar
    s = s.rstrip("Z").split(".")[0]
    return calendar.timegm(time.strptime(s, "%Y-%m-%dT%H:%M:%S"))


def parse_quotes_historical(doc):
    """{cmc_id: [(epoch, price_usd), ...] oldest first} from /v3/cryptocurrency/quotes/historical.

    v3 returns an object map keyed by the ids sent; the guide example shows a
    list. Both shapes, and symbol lookups (lists of objects), are accepted.
    """
    data = doc.get("data")
    objs = []
    if isinstance(data, dict):
        if "quotes" in data:
            objs = [data]
        else:
            for v in data.values():
                objs.extend(v if isinstance(v, list) else [v])
    elif isinstance(data, list):
        objs = data
    out = {}
    for o in objs:
        if not isinstance(o, dict) or "quotes" not in o:
            continue
        pts = []
        for q in o.get("quotes") or []:
            usd = (q.get("quote") or {}).get("USD") or {}
            p = usd.get("price")
            ts = q.get("timestamp") or usd.get("timestamp")
            if p and ts:
                pts.append((iso_to_epoch(ts), float(p)))
        pts.sort()
        out[int(o["id"])] = pts
    return out
