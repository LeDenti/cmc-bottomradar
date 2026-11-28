"""CMC quotes of the 15 perpetuals, sampled next to the order-book samplers.

Only CoinMarketCap is called (15 credits per snapshot, one call per token).
Each token row keeps the time of its own call, so a CMC quote can be compared
with the order-book round taken at the same instant.

    python3 verif/cotes_cmc.py --snapshots 520 --every 150 --max-credits 8200 --out cmc_24h.jsonl

Row: {t, run, credits, tokens: {TOKEN: {t: call time, m: [[exchange, price,
index, funding, last_updated, flag, volume_usd], ...]}}}
flag: 0 clean, 1 outlier_detected, 2 has exclusions, 3 both.
"""
import argparse, json, os, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from cmc_spread.client import CMC, CMCError, BudgetExceeded, RUNS   # noqa: E402
from cmc_spread.scan import load_config                             # noqa: E402
from cmc_spread.sources import fetch_perps                          # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshots", type=int, default=1)
    ap.add_argument("--every", type=int, default=150)
    ap.add_argument("--max-credits", type=int, default=20)
    ap.add_argument("--reserve", type=int, default=100000, help="credits to leave on the key")
    ap.add_argument("--out", default="cmc_quotes.jsonl")
    a = ap.parse_args()
    cfg = load_config()["perp"]
    cmc = CMC(max_credits=a.max_credits, pause=0.4)
    use = cmc.key_info()["usage"]["current_month"]
    print("key: %d credits used this month, %d left" % (use["credits_used"], use["credits_left"]), flush=True)
    if use["credits_left"] - a.max_credits < a.reserve:
        sys.exit("stop: this run could leave fewer than %d credits on the key" % a.reserve)
    run = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = os.path.join(RUNS, a.out)
    for i in range(a.snapshots):
        t0, c0, toks, err = time.time(), cmc.credits, {}, None
        try:
            for sym, cid in cfg["tokens"].items():
                tc = time.time()
                rows = fetch_perps(cmc, dict(cfg, tokens={sym: cid}))
                toks[sym] = {"t": round(tc, 1), "m": [
                    [m["exchange"], m["price"], m["index"], m["funding"], m["t"],
                     (1 if m["outlier"] else 0) + (2 if m["exclusions"] else 0), m["volume_usd"]]
                    for m in rows if m["price"]]}
        except BudgetExceeded as e:
            print(e, flush=True)
            break
        except CMCError as e:
            err = str(e)
        except Exception as e:      # nothing may stop a 24-hour run: note it and go on
            err = "%s: %s" % (type(e).__name__, e)
        if toks:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"t": round(t0, 1), "run": run, "credits": cmc.credits - c0,
                                    "error": err, "tokens": toks}, separators=(",", ":")) + "\n")
        print("[%d/%d] %s  %d tokens, %d quotes, %d credits (total %d)  %.0fs%s" % (
            i + 1, a.snapshots, time.strftime("%H:%M:%S", time.gmtime(t0)), len(toks),
            sum(len(v["m"]) for v in toks.values()), cmc.credits - c0, cmc.credits, time.time() - t0,
            ("  ERROR " + err) if err else ""), flush=True)
        if i < a.snapshots - 1:
            time.sleep(max(0, a.every - (time.time() - t0)))
    print("run %s: %d calls, %d credits" % (run, cmc.calls, cmc.credits), flush=True)


if __name__ == "__main__":
    main()
