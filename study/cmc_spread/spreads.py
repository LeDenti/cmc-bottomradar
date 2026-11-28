"""Turn one snapshot into a list of price gaps, gross and net of estimated costs.

Every gap has a stable `key` so the report can follow it from one snapshot to
the next (how often it shows up, how long it lives).

Four kinds:
- perp      same token, perpetual USDT pairs on two CEX
- dex       same token, two DEX pools on the same network
- triangle  three swaps on one network that end with more of the first token
- linked    two tokens that should be worth the same (WBTC/BTC, USDC/USDT...)

All percentages are in percent. Costs are estimates (config.json).
"""
import statistics
from collections import defaultdict


def _slip_pct(size, liquidity):
    """Constant-product price impact of a swap of `size` USD: about 2*size/L."""
    if not liquidity:
        return 100.0
    return 200.0 * size / liquidity


def perp_gaps(snap, cfg, size):
    """Two tiers: every CEX that passes the filters, and the large ones only.

    A market more than `aberrant_pct` away from the token's median price is a
    data error (seen: one exchange at +42 % on ETH), not a gap: it is counted
    apart and never alerted.
    """
    by_token = defaultdict(list)
    for m in snap["perp"]:
        if m["outlier"] or m["exclusions"] or not m["price"] or not m["t"]:
            continue
        if (m["volume_usd"] or 0) < cfg["min_volume_usd"] or snap["t"] - m["t"] > cfg["max_age_s"]:
            continue
        by_token[m["token"]].append(m)
    cost = cfg["taker_fee_pct"] * cfg["orders_per_trade"]
    major = set(cfg["major_exchanges"])
    out = []
    for tok, ms in by_token.items():
        newest = max(m["t"] for m in ms)
        ms = [m for m in ms if newest - m["t"] <= cfg["max_skew_s"]]
        if len(ms) < 2:
            continue
        med = statistics.median(m["price"] for m in ms)
        bad = [m for m in ms if abs(m["price"] / med - 1) * 100 > cfg["aberrant_pct"]]
        for m in bad:
            out.append({"kind": "perp", "tier": "aberrant", "key": "perp|aberrant|%s|%s" % (tok, m["exchange"]),
                        "token": tok, "buy": m["exchange"], "sell": "median",
                        "gross_pct": abs(m["price"] / med - 1) * 100, "cost_pct": cost,
                        "net_pct": abs(m["price"] / med - 1) * 100 - cost, "net_opt_pct": 0.0, "aberrant": True})
        ms = [m for m in ms if m not in bad]
        for tier, pool in (("all", ms), ("major", [m for m in ms if m["exchange"] in major])):
            if len(pool) < 2:
                continue
            lo = min(pool, key=lambda m: m["price"])
            hi = max(pool, key=lambda m: m["price"])
            gross = (hi["price"] / lo["price"] - 1) * 100
            out.append({
                "kind": "perp", "tier": tier, "key": "perp|%s|%s|%s>%s" % (tier, tok, lo["exchange"], hi["exchange"]),
                "token": tok, "buy": lo["exchange"], "sell": hi["exchange"],
                "buy_price": lo["price"], "sell_price": hi["price"], "n_markets": len(pool),
                "gross_pct": gross, "cost_pct": cost, "net_pct": gross - cost, "net_opt_pct": gross - cost,
                "min_volume_usd": min(lo["volume_usd"], hi["volume_usd"]),
                "funding_gap": (hi["funding"] or 0) - (lo["funding"] or 0),
                "skew_s": abs(hi["t"] - lo["t"]),
            })
    return out


def suspect_pools(snap, cfg):
    """Pools whose USD price is more than `pool_outlier_pct` away from the median
    of the same token on the same network (groups of 3 pools or more).
    Seen on 26/11: one large WBTC/WETH pool on Arbitrum at 40 WETH for one
    snapshot while every other pool said 35.85 -- a data error, not a gap."""
    groups = defaultdict(list)
    for p in snap["dex"]:
        if p["price_usd"] and p["base"]:
            groups[(p["network"], p["base"])].append(p)
    bad = set()
    for ps in groups.values():
        ps = list({p["pool"]: p for p in ps}.values())
        if len(ps) < 3:
            continue
        med = statistics.median(p["price_usd"] for p in ps)
        for p in ps:
            if abs(p["price_usd"] / med - 1) * 100 > cfg["pool_outlier_pct"]:
                bad.add(p["pool"])
    return bad


def _dex_ok(p, snap, cfg):
    if p["pool"] in snap.get("_suspect", ()):
        return False
    return (p["price_usd"] and p["price_in_quote"] and p["t"] and p["base"] and p["quote"]
            and (p["liquidity_usd"] or 0) >= cfg["min_liquidity_usd"]
            and (p["volume_usd"] or 0) >= cfg["min_volume_usd"])


def dex_gaps(snap, cfg, size):
    out = []
    for p in snap["dex"]:
        if p["pool"] in snap.get("_suspect", ()):
            out.append({"kind": "dex", "key": "dex|aberrant|%s|%s" % (p["network"], p["pool"][:10]),
                        "token": p["base_sym"], "network": p["network"], "buy": p["dex"], "sell": "median",
                        "gross_pct": 0.0, "cost_pct": 0.0, "net_pct": 0.0, "net_opt_pct": 0.0, "aberrant": True})
    groups = defaultdict(list)
    for p in snap["dex"]:
        if _dex_ok(p, snap, cfg):
            groups[(p["network"], p["base"])].append(p)
    for (net, base), ps in groups.items():
        # one entry per pool (the listing may repeat a pool across pages)
        ps = list({p["pool"]: p for p in ps}.values())
        if len(ps) < 2:
            continue
        newest = max(p["t"] for p in ps)
        ps = [p for p in ps if newest - p["t"] <= cfg["max_skew_s"]]
        if len(ps) < 2:
            continue
        lo = min(ps, key=lambda p: p["price_usd"])
        hi = max(ps, key=lambda p: p["price_usd"])
        gross = (hi["price_usd"] / lo["price_usd"] - 1) * 100
        gas = 2 * cfg["networks"][net]["gas_usd"] / size * 100
        slip = _slip_pct(size, lo["liquidity_usd"]) + _slip_pct(size, hi["liquidity_usd"])
        cost = 2 * cfg["fee_pct_prudent"] + slip + gas
        cost_opt = 2 * cfg["fee_pct_optimistic"] + slip + gas
        out.append({
            "kind": "dex", "key": "dex|%s|%s|%s>%s" % (net, lo["base_sym"], lo["pool"][:10], hi["pool"][:10]),
            "token": lo["base_sym"], "network": net,
            "buy": "%s %s/%s" % (lo["dex"], lo["base_sym"], lo["quote_sym"]),
            "sell": "%s %s/%s" % (hi["dex"], hi["base_sym"], hi["quote_sym"]),
            "buy_pool": lo["pool"], "sell_pool": hi["pool"],
            "buy_price": lo["price_usd"], "sell_price": hi["price_usd"], "n_markets": len(ps),
            "gross_pct": gross, "cost_pct": cost, "net_pct": gross - cost, "net_opt_pct": gross - cost_opt,
            "min_volume_usd": min(lo["volume_usd"], hi["volume_usd"]),
            "min_liquidity_usd": min(lo["liquidity_usd"], hi["liquidity_usd"]),
            "aberrant": gross >= cfg["aberrant_pct"],
            "skew_s": abs(hi["t"] - lo["t"]),
        })
    return out


def triangle_gaps(snap, cfg, size):
    """Best directed edge per token pair on each network, then all 3-cycles."""
    by_net = defaultdict(list)
    for p in snap["dex"]:
        if _dex_ok(p, snap, cfg):
            by_net[p["network"]].append(p)
    out = []
    for net, ps in by_net.items():
        newest = max(p["t"] for p in ps)
        ps = [p for p in ps if newest - p["t"] <= cfg["max_skew_s"]]
        sym = {}
        edges = {}  # (u, v) -> (rate_mid, cost_pct, pool, dex)

        def add(u, v, rate, p):
            slip = _slip_pct(size, p["liquidity_usd"])
            old = edges.get((u, v))
            if old is None or rate > old[0]:
                edges[(u, v)] = (rate, slip, p["pool"], p["dex"], p["liquidity_usd"])

        for p in ps:
            sym[p["base"]], sym[p["quote"]] = p["base_sym"], p["quote_sym"]
            r = p["price_in_quote"]
            add(p["base"], p["quote"], r, p)
            add(p["quote"], p["base"], 1.0 / r, p)
        nxt = defaultdict(list)
        for (u, v) in edges:
            nxt[u].append(v)
        gas = 3 * cfg["networks"][net]["gas_usd"] / size * 100
        seen = set()
        for (a, b), e1 in edges.items():
            for c in nxt[b]:
                if c in (a, b) or (c, a) not in edges:
                    continue
                e2, e3 = edges[(b, c)], edges[(c, a)]
                # one entry per cycle and direction, whatever the start token
                cyc = (a, b, c)
                rot = min(cyc[i:] + cyc[:i] for i in range(3))
                if rot in seen:
                    continue
                seen.add(rot)
                gross = (e1[0] * e2[0] * e3[0] - 1) * 100
                if gross <= 0:
                    continue
                slip = e1[1] + e2[1] + e3[1]
                cost = 3 * cfg["fee_pct_prudent"] + slip + gas
                cost_opt = 3 * cfg["fee_pct_optimistic"] + slip + gas
                path = "%s>%s>%s>%s" % (sym[rot[0]], sym[rot[1]], sym[rot[2]], sym[rot[0]])
                out.append({
                    "kind": "triangle", "key": "tri|%s|%s|%s" % (net, path, "/".join(x[2][:8] for x in (e1, e2, e3))),
                    "token": path, "network": net, "buy": path, "sell": "",
                    "gross_pct": gross, "cost_pct": cost, "net_pct": gross - cost, "net_opt_pct": gross - cost_opt,
                    "min_liquidity_usd": min(e1[4], e2[4], e3[4]),
                    "aberrant": gross >= cfg["aberrant_pct"],
                })
    return out


def linked_gaps(snap, lcfg, dcfg, size):
    out = []
    agg = {int(k): v for k, v in snap["linked"].items()}
    cost = lcfg["cex_taker_fee_pct"] * lcfg["orders_per_trade"]
    for a, ia, b, ib in lcfg["pairs"]:
        pa, pb = agg.get(ia), agg.get(ib)
        if not pa or not pb or not pa["price"] or not pb["price"]:
            continue
        gross = abs(pa["price"] / pb["price"] - 1) * 100
        rich, cheap = (a, b) if pa["price"] > pb["price"] else (b, a)
        out.append({
            "kind": "linked", "key": "linked|cmc|%s/%s" % (a, b), "token": "%s/%s" % (a, b),
            "buy": cheap, "sell": rich, "source": "CMC aggregate",
            "ratio": pa["price"] / pb["price"], "check_symbols": "%s/%s" % (pa["symbol"], pb["symbol"]),
            "gross_pct": gross, "cost_pct": cost, "net_pct": gross - cost, "net_opt_pct": gross - cost,
        })
    # direct DEX pools between the two tokens of a linked pair
    pairs = {}
    for a, ia, b, ib in lcfg["pairs"]:
        pairs[(str(ia), str(ib))] = (a, b, False)
        pairs[(str(ib), str(ia))] = (a, b, True)
    for p in snap["dex"]:
        if not _dex_ok(p, snap, dcfg):
            continue
        hit = pairs.get((str(p["base_ucid"]), str(p["quote_ucid"])))
        if not hit:
            continue
        a, b, flipped = hit
        ratio = (1.0 / p["price_in_quote"]) if flipped else p["price_in_quote"]
        gross = abs(ratio - 1) * 100
        gas = 2 * dcfg["networks"][p["network"]]["gas_usd"] / size * 100
        slip = 2 * _slip_pct(size, p["liquidity_usd"])
        out.append({
            "kind": "linked", "key": "linked|%s|%s/%s|%s" % (p["network"], a, b, p["pool"][:10]),
            "token": "%s/%s" % (a, b), "network": p["network"], "buy": p["dex"], "sell": "",
            "source": "DEX pool", "ratio": ratio,
            "gross_pct": gross,
            "cost_pct": 2 * dcfg["fee_pct_prudent"] + slip + gas, "net_pct": gross - (2 * dcfg["fee_pct_prudent"] + slip + gas),
            "net_opt_pct": gross - (2 * dcfg["fee_pct_optimistic"] + slip + gas),
            "min_liquidity_usd": p["liquidity_usd"],
        })
    return out


def all_gaps(snap, config):
    size = config["trade_size_usd"]
    snap["_suspect"] = suspect_pools(snap, config["dex"])
    gaps = (perp_gaps(snap, config["perp"], size) + dex_gaps(snap, config["dex"], size)
            + triangle_gaps(snap, config["dex"], size)
            + linked_gaps(snap, config["linked"], config["dex"], size))
    snap.pop("_suspect", None)
    for g in gaps:
        g["t"] = snap["t"]
        for k in ("gross_pct", "cost_pct", "net_pct", "net_opt_pct"):
            g[k] = round(g[k], 4)
    return gaps
