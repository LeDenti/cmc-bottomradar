"""Small CoinMarketCap Pro API client, standard library only.

- The key comes from the CMC_API_KEY variable, or from a .env file
  (the path in CMC_ENV_FILE, then ./.env, which is in .gitignore).
  The key is never printed and never written to the logs.
- Every call is written to runs/calls.jsonl: endpoint, params, HTTP code and
  credit_count, so the credits spent can be counted exactly.
- A credit guard stops the run before it spends more than `max_credits`.
"""
import http.client
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://pro-api.coinmarketcap.com"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = os.environ.get("CMCSPREAD_RUNS") or os.path.join(ROOT, "runs")


class CMCError(RuntimeError):
    pass


class BudgetExceeded(CMCError):
    pass


def _key_from_file(path):
    if not path or not os.path.exists(path):
        return ""
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line.startswith("CMC_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def load_key():
    key = os.environ.get("CMC_API_KEY", "").strip()
    if key:
        return key
    for path in (os.environ.get("CMC_ENV_FILE"), os.path.join(ROOT, ".env")):
        key = _key_from_file(path)
        if key:
            return key
    return ""


class CMC:
    def __init__(self, max_credits=1000, pause=1.3):
        self.key = load_key()
        if not self.key:
            raise CMCError("no CMC_API_KEY found (environment or .env)")
        self.max_credits = max_credits
        self.pause = pause  # Basic plan: 50 requests per minute
        self.credits = 0
        self.calls = 0
        self._last = 0.0
        os.makedirs(RUNS, exist_ok=True)

    def key_info(self):
        """/v1/key/info costs 0 credits; returns the monthly usage."""
        return self.get("/v1/key/info")["data"]

    def get(self, path, **params):
        params = {k: v for k, v in params.items() if v is not None}
        if self.credits >= self.max_credits:
            raise BudgetExceeded("credit guard: %d credits spent, limit %d" % (self.credits, self.max_credits))
        url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
        headers = {"Accept": "application/json", "X-CMC_PRO_API_KEY": self.key}
        for attempt in range(6):
            wait = self.pause - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            t0 = self._last = time.time()
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
                    status, body = r.status, r.read()
            except urllib.error.HTTPError as e:
                status, body = e.code, e.read()
            except (urllib.error.URLError, http.client.HTTPException, OSError) as e:
                # a dropped connection (RemoteDisconnected, reset, timeout) must not stop a long run
                status, body = 0, json.dumps({"status": {"error_message": "%s: %s" % (type(e).__name__, e)}}).encode()
            try:
                doc = json.loads(body or b"{}")
            except ValueError:
                doc = {"status": {"error_message": (body or b"")[:200].decode("utf-8", "replace")}}
            st = doc.get("status") or {}
            credits = int(st.get("credit_count") or 0)
            self.calls += 1
            self.credits += credits
            self._log(path, params, status, st, credits, round(time.time() - t0, 3))
            busy = "busy" in str(st.get("error_message") or "").lower()
            if status == 0 and attempt < 2:      # network error: two more tries
                time.sleep(2)
                continue
            if (status == 429 or busy) and attempt < 5:
                time.sleep(2 ** attempt)
                continue
            if status != 200 or str(st.get("error_code")) not in ("0", "None"):
                raise CMCError("%s -> HTTP %s, %s" % (path, status, st.get("error_message")))
            return doc
        raise CMCError("%s -> too many retries" % path)

    def _log(self, path, params, status, st, credits, elapsed):
        line = {
            "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "endpoint": path, "params": params, "http": status,
            "error_code": st.get("error_code"), "error": st.get("error_message") or None,
            "credit_count": credits, "elapsed_s": elapsed,
        }
        with open(os.path.join(RUNS, "calls.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
