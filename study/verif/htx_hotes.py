"""Evidence for one case: the two public hosts of HTX futures, read once a minute.

On 26/11/2026 api.hbdm.com served a snapshot frozen at 07:11:38 UTC while
api.hbdm.vn was live. Row: {t, hosts: {host: {tick_ts, BTC: [bid, ask, last], ETH: [...]}}}
"""
import argparse, json, os, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOSTS = ["api.hbdm.com", "api.hbdm.vn"]


def read(host):
    req = urllib.request.Request("https://%s/linear-swap-ex/market/detail/batch_merged" % host,
                                 headers={"User-Agent": "spread-scanner/0.1", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as r:
        ticks = {x.get("contract_code"): x for x in json.loads(r.read())["ticks"]}
    out = {"tick_ts": round(max(x.get("ts") or 0 for x in ticks.values()) / 1000, 1)}
    for tok in ("BTC", "ETH"):
        x = ticks.get(tok + "-USDT") or {}
        out[tok] = [(x.get("bid") or [None])[0], (x.get("ask") or [None])[0], x.get("close")]
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--every", type=int, default=60)
    ap.add_argument("--out", default="htx_hotes.jsonl")
    a = ap.parse_args()
    for i in range(a.rounds):
        t0 = time.time()
        row = {"t": round(t0, 1), "hosts": {}}
        for h in HOSTS:
            try:
                row["hosts"][h] = read(h)
            except Exception as e:
                row["hosts"][h] = {"error": str(e)[:100]}
        with open(os.path.join(ROOT, "runs", a.out), "a") as f:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
        if i < a.rounds - 1:
            time.sleep(max(0, a.every - (time.time() - t0)))
