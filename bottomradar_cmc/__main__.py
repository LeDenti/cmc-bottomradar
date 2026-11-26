"""bottomradar-cmc command line.

  python3 -m bottomradar_cmc map        resolve the token list to CMC ids (works without a key)
  python3 -m bottomradar_cmc context    Fear & Greed + CMC100 (works without a key)
  python3 -m bottomradar_cmc scan       live screener: signals now, paper positions, filters
  python3 -m bottomradar_cmc replay 30  what the rule did over the last N days (max ~30 on intraday plans)
  python3 -m bottomradar_cmc report     write runs/report.html from the last scan / replay
  python3 -m bottomradar_cmc calls      API calls and credits used so far
  python3 -m bottomradar_cmc watch 10   scan every N minutes
"""
import json
import os
import sys
import time

from .client import CMC, RUNS
from .market import DATA, build_id_map, load_universe


def _fmt_bool(v):
    return {True: "yes", False: "no", None: "unknown"}[v]


def cmd_map():
    syms = set(load_universe("universe_75")) | set(load_universe("market_33")) | {"BTC", "ETH"}
    m = build_id_map(CMC(), syms)
    json.dump(m, open(os.path.join(DATA, "cmc_ids.json"), "w"), indent=1)
    missing = sorted(syms - set(m))
    print("%d symbols mapped, missing: %s" % (len(m), missing or "none"))


def cmd_scan():
    from .screener import scan
    out = scan()
    f = out["filters_now"]
    print("BottomRadar on CoinMarketCap, %s" % out["generated"])
    print("Settings: %s" % out["rule"]["source"])
    print("ETH/BTC above its trend mean: %s | market falling together (10 min and 1 h): %s"
          % (_fmt_bool(f["eth_btc_above_trend_mean"]), _fmt_bool(f["market_falling_together"])))
    print("%-9s %12s %6s  %-6s %-6s %s" % ("token", "price", "RSI", "ladder", "next", "state"))
    for r in out["tokens"][:25]:
        state = r["signal_now"] or ""
        if r["position"]:
            p = r["position"]
            state = (state + " " if state else "") + "open %s steps %s, %+.2f %%, %.0f $" % (
                p["ladder"], p["steps"], p["pnl_pct"], p["cost_usd"])
        print("%-9s %12.6g %6.1f  %-6s %-6s %s" % (r["symbol"], r["price"], r["rsi"], r["ladder_if_opened_now"],
                                                  r["next_level"], state))
    a = out["api"]
    print("API: %d calls, %d credits this run" % (a["calls"], a["credits"]))


def cmd_replay(days):
    from .screener import replay
    out = replay(days)
    s = out["summary"]
    print("Replay %s -> %s (%d days), settings: %s" % (out["window"]["from"], out["window"]["to"], days,
                                                       out["rule"]["source"]))
    print("opened: high ladder %d, low ladder %d | market falling together %.0f %% of the time"
          % (out["opens_by_ladder"]["high"], out["opens_by_ladder"]["low"], 100 * (out["market_falling_share"] or 0)))
    print("closed %d (all exits are in gain by rule), realized %+.2f $, median %s %%, weighted %s %%"
          % (s["closed"], s["realized_usd"], s["median_pct"], s["weighted_pct"]))
    print("still open %d, cost %.2f $, latent %+.2f $ -> market value %+.2f $"
          % (s["open"], s["open_cost_usd"], s["open_latent_usd"], s["market_value_usd"]))
    a = out["api"]
    print("API: %d calls, %d credits this run" % (a["calls"], a["credits"]))


def cmd_context():
    from .screener import context
    print(json.dumps(context(), indent=1))


def cmd_calls():
    path = os.path.join(RUNS, "calls.jsonl")
    if not os.path.exists(path):
        print("no calls yet")
        return
    rows = [json.loads(l) for l in open(path)]
    by = {}
    for r in rows:
        b = by.setdefault(r["endpoint"], [0, 0, 0])
        b[0] += 1
        b[1] += r["credit_count"]
        b[2] += 1 if r["http"] != 200 else 0
    print("%-42s %6s %8s %6s" % ("endpoint", "calls", "credits", "errors"))
    for k, (n, c, e) in sorted(by.items()):
        print("%-42s %6d %8d %6d" % (k, n, c, e))
    print("total: %d calls, %d credits" % (len(rows), sum(r["credit_count"] for r in rows)))


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "scan"
    if cmd == "map":
        cmd_map()
    elif cmd == "scan":
        cmd_scan()
    elif cmd == "replay":
        cmd_replay(int(argv[2]) if len(argv) > 2 else 30)
    elif cmd == "context":
        cmd_context()
    elif cmd == "calls":
        cmd_calls()
    elif cmd == "report":
        from .report import write
        print(write())
    elif cmd == "watch":
        every = int(argv[2]) if len(argv) > 2 else 10
        while True:
            cmd_scan()
            from .report import write
            write()
            time.sleep(every * 60)
    elif cmd == "mcp":
        from .mcp_server import main as mcp_main
        mcp_main()
    else:
        print(__doc__)


if __name__ == "__main__":
    from .client import CMCError
    try:
        main(sys.argv)
    except CMCError as e:
        print("CoinMarketCap: %s" % e)
        sys.exit(2)
