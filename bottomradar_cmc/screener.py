"""Screener and replay built on engine + market."""
import json
import os
import time

from . import engine, rules
from .client import CMC, RUNS
from .market import BAR, DAY, Store, fetch, id_map, load_universe

SCAN_SPAN = max(340, (rules.MARKET_MA + 6) * 6 + 40) * BAR  # RSI warm-up + hourly market mean
DAILY_SPAN = (rules.TREND_MA + 35) * DAY                     # trend means with a margin


def _universe():
    ids = id_map()
    tokens = [s for s in load_universe("universe_75") if s in ids]
    market = [s for s in load_universe("market_33") if s in ids]
    need = sorted(set(tokens) | set(market) | {"BTC", "ETH"})
    return ids, tokens, market, need


def load(cmc, span10, now):
    ids, tokens, market, need = _universe()
    store = Store()
    c10 = fetch(cmc, store, [ids[s]["id"] for s in need], "10m", span10, now=now)
    cd = fetch(cmc, store, [ids[s]["id"] for s in need], "daily", DAILY_SPAN + span10, now=now)
    p10 = {s: store.series("10m", ids[s]["id"]) for s in need}
    pday = {s: store.series("daily", ids[s]["id"]) for s in need}
    regime = engine.Regime({s: p10[s] for s in market}, {s: p10[s] for s in market}, pday)
    return ids, tokens, p10, regime, {"credits_10m": c10, "credits_daily": cd}


def scan(cmc=None, now=None):
    cmc = cmc or CMC()
    now = int(now or time.time())
    ids, tokens, p10, regime, cost = load(cmc, SCAN_SPAN, now)
    k_now = now // BAR - 1
    rows, opens = [], {}
    for s in tokens:
        events, pos, last = engine.run_token(s, p10[s], regime, now=now)
        if not last or last["rsi"] is None:
            continue
        lad, name, reasons = regime.ladder_for(s, k_now)
        fresh = [e for e in events if e["t"] >= last["t"]]
        row = {
            "symbol": s, "cmc_id": ids[s]["id"], "price": last["price"], "rsi": round(last["rsi"], 2),
            "ladder_if_opened_now": name,
            "next_level": None, "rsi_to_next": None,
            "signal_now": fresh[-1]["type"] if fresh else None,
            "position": None,
        }
        if pos:
            opens[s] = pos
            nxt = pos.next_step()
            row["position"] = {
                "ladder": pos.ladder_name, "steps": pos.fired, "rebuys": pos.rebuys,
                "cost_usd": round(pos.cost, 2), "avg": pos.avg,
                "pnl_pct": round(100 * (last["price"] / pos.avg - 1), 2),
                "exit_at_rsi": rules.EXIT_RSI,
                "exit_min_price": pos.avg * (1 + rules.EXIT_MIN_GAIN_PCT / 100),
            }
            if nxt:
                row["next_level"], row["rsi_to_next"] = nxt[0], round(last["rsi"] - nxt[0], 2)
        else:
            row["next_level"] = lad[0][0]
            row["rsi_to_next"] = round(last["rsi"] - lad[0][0], 2)
        rows.append(row)
    rows.sort(key=lambda r: (r["signal_now"] is None, r["position"] is None, r["rsi_to_next"] if r["rsi_to_next"] is not None else 999))
    out = {
        "generated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(now)),
        "filters_now": {
            "eth_btc_above_trend_mean": regime.ethbtc_strong(k_now),
            "market_falling_together": regime.market_falling(k_now),
        },
        "tokens": rows,
        "rule": public_rule(),
        "api": {"calls": cmc.calls, "credits": cmc.credits, **cost, "keyless": not cmc.keyed},
    }
    _save("scan.json", out)
    return out


def replay(days=30, cmc=None, now=None):
    cmc = cmc or CMC()
    now = int(now or time.time())
    span = days * DAY
    warm = 60 * BAR  # RSI warm-up before the first bar that may trade
    ids, tokens, p10, regime, cost = load(cmc, span, now)
    k_from = (now - span + warm) // BAR
    events, opens, last_px = [], {}, {}
    for s in tokens:
        ev, pos, last = engine.run_token(s, p10[s], regime, k_from=k_from, now=now)
        events.extend(ev)
        if pos:
            opens[s] = pos
        if last:
            last_px[s] = last["price"]
    events.sort(key=lambda e: e["t"])
    summary = engine.summarize(events, opens, last_px)
    known = [k for k in range(k_from, now // BAR) if regime.market_falling(k) is not None]
    falling = sum(1 for k in known if regime.market_falling(k))
    out = {
        "generated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(now)),
        "window": {"from": time.strftime("%Y-%m-%d %H:%M", time.gmtime(k_from * BAR)),
                   "to": time.strftime("%Y-%m-%d %H:%M", time.gmtime(now)), "days": days},
        "rule": public_rule(),
        "summary": summary,
        "market_falling_share": round(falling / len(known), 3) if known else None,
        "opens_by_ladder": {n: sum(1 for e in events if e["type"] == "open" and e["ladder"] == n) for n in ("high", "low")},
        "events": events,
        "open_positions": {s: {"ladder": p.ladder_name, "steps": p.fired, "rebuys": p.rebuys,
                               "cost_usd": round(p.cost, 2), "avg": p.avg,
                               "pnl_pct": round(100 * (last_px[s] / p.avg - 1), 2)} for s, p in opens.items()},
        "api": {"calls": cmc.calls, "credits": cmc.credits, **cost},
    }
    _save("replay_%dd.json" % days, out)
    return out


def gaps_check(cmc=None):
    """CMC quotes of perpetuals against the exchanges' own order books, right now."""
    from . import gaps
    out = gaps.check(cmc or CMC())
    _save("gaps.json", out)
    return out


def public_rule():
    """The parameters, or only their source when they are private settings."""
    if rules.SOURCE != "example values":
        return {"source": rules.SOURCE, "values": "not shown"}
    return {"source": rules.SOURCE, **rules.EXAMPLE}


def context(cmc=None):
    """Market context shown next to the scan (not part of the rule). Works without a key."""
    cmc = cmc or CMC()
    fg = cmc.get("/v3/fear-and-greed/latest")["data"]
    idx = cmc.get("/v3/index/cmc100-latest")["data"]
    out = {"fear_greed": {"value": fg.get("value"), "label": fg.get("value_classification")},
           "cmc100": {"value": idx.get("value"), "change_24h_pct": idx.get("value_24h_percentage_change")}}
    _save("context.json", out)
    return out


def _save(name, obj):
    os.makedirs(RUNS, exist_ok=True)
    with open(os.path.join(RUNS, name), "w") as f:
        json.dump(obj, f, indent=1, default=str)
