"""Paper scanner: take N snapshots, log every gap, alert on net gaps.

No order is ever sent. The only network calls go to CoinMarketCap.

    python3 -m cmc_spread.scan --snapshots 25 --every 150 --max-credits 800
    python3 -m cmc_spread.scan --once          # one snapshot, prints the gaps

Files written in runs/:
  calls.jsonl      every API call with its credit_count
  snapshots.jsonl  raw normalised prices of each snapshot
  gaps.jsonl       every gap of every snapshot, gross and net
  alerts.jsonl     gaps still positive after estimated costs (paper alerts)
"""
import argparse
import json
import os
import sys
import time

from .client import CMC, CMCError, BudgetExceeded, RUNS, ROOT
from .sources import snapshot
from .spreads import all_gaps


def load_config(path=None):
    with open(path or os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def _append(name, rows):
    with open(os.path.join(RUNS, name), "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")


def run(n, every, max_credits, reserve, config_path=None, quiet=False):
    config = load_config(config_path)
    cmc = CMC(max_credits=max_credits)
    info = cmc.key_info()
    left = info["usage"]["current_month"]["credits_left"]
    used = info["usage"]["current_month"]["credits_used"]
    print("key: %d credits used this month, %d left, reset %s" % (
        used, left, info["plan"].get("credit_limit_monthly_reset_timestamp")))
    if left - max_credits < reserve:
        sys.exit("stop: this run could leave fewer than %d credits for the other CMC project" % reserve)
    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    for i in range(n):
        t0 = time.time()
        try:
            snap = snapshot(cmc, config)
        except BudgetExceeded as e:
            print(e)
            break
        except CMCError as e:
            print("snapshot %d failed: %s" % (i + 1, e))
            _append("errors.jsonl", [{"t": int(t0), "run": run_id, "error": str(e)}])
            time.sleep(every)
            continue
        snap["run"] = run_id
        gaps = all_gaps(snap, config)
        for g in gaps:
            g["run"] = run_id
        alerts = [g for g in gaps if g["net_pct"] > 0 and not g.get("aberrant")]
        _append("snapshots.jsonl", [snap])
        _append("gaps.jsonl", gaps)
        _append("alerts.jsonl", alerts)
        print("[%d/%d] %s  %d perp, %d pools, %d gaps, %d net>0 (paper)  %d credits (total %d)  %.0fs" % (
            i + 1, n, time.strftime("%H:%M:%S", time.gmtime(snap["t"])), len(snap["perp"]), len(snap["dex"]),
            len(gaps), len(alerts), snap["credits"], cmc.credits, snap["fetch_s"]))
        if not quiet:
            for g in sorted(alerts, key=lambda g: -g["net_pct"])[:8]:
                print("   ALERTE papier  %-8s %-28s net %+.3f %%  (brut %.3f %%, frais %.3f %%)  %s -> %s" % (
                    g["kind"], g["token"][:28], g["net_pct"], g["gross_pct"], g["cost_pct"], g["buy"], g["sell"]))
        if i < n - 1:
            time.sleep(max(0, every - (time.time() - t0)))
    print("run %s: %d calls, %d credits" % (run_id, cmc.calls, cmc.credits))
    return run_id


def main(argv=None):
    ap = argparse.ArgumentParser(description="CMC price-gap scanner (paper only)")
    ap.add_argument("--snapshots", type=int, default=25)
    ap.add_argument("--every", type=int, default=150, help="seconds between snapshots")
    ap.add_argument("--max-credits", type=int, default=800)
    ap.add_argument("--reserve", type=int, default=6000, help="credits to leave for other projects")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--config")
    a = ap.parse_args(argv)
    if a.once:
        a.snapshots = 1
    run(a.snapshots, a.every, a.max_credits, a.reserve, a.config)


if __name__ == "__main__":
    main()
