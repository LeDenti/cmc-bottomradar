"""Self-contained HTML report from runs/scan.json, runs/replay_30d.json and runs/context.json."""
import html
import json
import os

from .client import RUNS

CSS = """
:root{--bg:#fafaf7;--fg:#1d1d1b;--mut:#6b6b66;--line:#e3e2dc;--card:#fff;--good:#1b7f4b;--bad:#b3261e;--acc:#2b59c3}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--fg:#ecebe6;--mut:#9c9b95;--line:#2c2c2a;--card:#1c1c1b;--good:#5fd08f;--bad:#ff8a80;--acc:#8fb0ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1000px;margin:0 auto;padding:24px 16px 48px}h1{font-size:24px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 8px}
.mut{color:var(--mut)}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin:14px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}.card b{display:block;font-size:20px}
.wrap{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--card)}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}th,td{padding:6px 10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left}th{font-weight:600;color:var(--mut);font-size:13px}tr:last-child td{border-bottom:0}
.good{color:var(--good)}.bad{color:var(--bad)}.tag{display:inline-block;padding:1px 7px;border-radius:99px;border:1px solid var(--line);font-size:12px}
code{font-size:13px}
"""


def _load(name):
    p = os.path.join(RUNS, name)
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return json.load(f)


def _yn(v):
    return {True: "yes", False: "no", None: "unknown"}[v]


def _num(v, fmt="%+.2f"):
    if v is None:
        return "–"
    cls = "good" if v > 0 else "bad" if v < 0 else ""
    return '<span class="%s">%s</span>' % (cls, fmt % v)


def write():
    scan, rep, ctx = _load("scan.json"), _load("replay_30d.json"), _load("context.json")
    e = html.escape
    out = ['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
           "<title>BottomRadar on CMC</title><style>%s</style></head><body><main>" % CSS,
           "<h1>BottomRadar on CoinMarketCap</h1>",
           '<p class="mut">A 10-minute RSI ladder fed by CoinMarketCap quotes. '
           "Paper positions only. Not financial advice.</p>"]
    if scan:
        f = scan["filters_now"]
        out.append('<div class="cards">')
        out.append('<div class="card"><span class="mut">Updated</span><b>%s</b></div>' % e(scan["generated"]))
        out.append('<div class="card"><span class="mut">Settings</span><b>%s</b></div>' % e(scan.get("rule", {}).get("source", "")))
        out.append('<div class="card"><span class="mut">ETH/BTC above trend mean</span><b>%s</b></div>' % _yn(f["eth_btc_above_trend_mean"]))
        out.append('<div class="card"><span class="mut">Market falling together</span><b>%s</b></div>' % _yn(f["market_falling_together"]))
        if ctx:
            out.append('<div class="card"><span class="mut">Fear &amp; Greed (context)</span><b>%s</b><span class="mut">%s</span></div>'
                       % (ctx["fear_greed"]["value"], e(str(ctx["fear_greed"]["label"]))))
        out.append("</div>")
        out.append("<h2>Signals and paper positions now</h2><div class=wrap><table><tr><th>Token</th><th>Price</th><th>RSI 10m</th>"
                   "<th>Ladder</th><th>Next step</th><th>RSI gap</th><th>Signal</th><th>Position</th><th>P&amp;L</th></tr>")
        for r in scan["tokens"]:
            p = r["position"]
            pos = "%s %s%s, %.0f $" % (p["ladder"], ",".join(map(str, p["steps"])),
                                       (" +%d rebuys" % p["rebuys"]) if p["rebuys"] else "", p["cost_usd"]) if p else ""
            out.append("<tr><td><b>%s</b></td><td>%.6g</td><td>%.1f</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                e(r["symbol"]), r["price"], r["rsi"], r["ladder_if_opened_now"], r["next_level"] or "–",
                "%.1f" % r["rsi_to_next"] if r["rsi_to_next"] is not None else "–",
                '<span class="tag">%s</span>' % r["signal_now"] if r["signal_now"] else "", e(pos),
                _num(p["pnl_pct"], "%+.2f %%") if p else ""))
        out.append("</table></div>")
    if rep:
        s = rep["summary"]
        out.append("<h2>What the rule did over the last %d days</h2>" % rep["window"]["days"])
        out.append('<p class="mut">%s → %s UTC. Exits only happen in gain, '
                   "so the honest figure is the market value, open positions included.</p>" % (e(rep["window"]["from"]), e(rep["window"]["to"])))
        out.append('<div class="cards">')
        for label, val in [("Positions opened", "%d high / %d low" % (rep["opens_by_ladder"]["high"], rep["opens_by_ladder"]["low"])),
                           ("Closed", str(s["closed"])),
                           ("Median / weighted return", "%s %% / %s %%" % (s["median_pct"], s["weighted_pct"])),
                           ("Realized", _num(s["realized_usd"], "%+.2f $")),
                           ("Still open (cost)", "%d (%.0f $)" % (s["open"], s["open_cost_usd"])),
                           ("Open latent", _num(s["open_latent_usd"], "%+.2f $")),
                           ("Market value", _num(s["market_value_usd"], "%+.2f $")),
                           ("Market falling together", "%.0f %% of bars" % (100 * (rep["market_falling_share"] or 0)))]:
            out.append('<div class="card"><span class="mut">%s</span><b>%s</b></div>' % (label, val))
        out.append("</div>")
    out.append("<h2>API usage</h2><p class=mut>Every call is logged in <code>runs/calls.jsonl</code> with its credit cost; "
               "one real response per endpoint is kept in <code>runs/evidence/</code>.</p>")
    rows = []
    p = os.path.join(RUNS, "calls.jsonl")
    if os.path.exists(p):
        by = {}
        with open(p) as f:
            for line in f:
                r = json.loads(line)
                b = by.setdefault(r["endpoint"], [0, 0])
                b[0] += 1
                b[1] += r["credit_count"]
        rows = sorted(by.items())
    out.append("<div class=wrap><table><tr><th>Endpoint</th><th>Calls</th><th>Credits</th></tr>")
    for k, (n, c) in rows:
        out.append("<tr><td><code>%s</code></td><td>%d</td><td>%d</td></tr>" % (e(k), n, c))
    out.append("</table></div></main></body></html>")
    path = os.path.join(RUNS, "report.html")
    os.makedirs(RUNS, exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(out))
    return path
