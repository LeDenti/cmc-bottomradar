"""Fetch one snapshot of prices from CoinMarketCap and normalise it.

Three sources, all open on the free Basic plan (measured 26/11/2026):
- perpetual market pairs on centralised exchanges
  /v5/cryptocurrency/derivatives/market-pairs/list/latest (1 credit per 250 pairs)
- DEX spot pairs, per network and per DEX
  /v4/dex/spot-pairs/latest (1 credit per 100 pairs)
- aggregated CMC prices for linked tokens
  /v3/cryptocurrency/quotes/latest

Closed on Basic (HTTP 403): /v2/cryptocurrency/market-pairs/latest and
/v1/exchange/market-pairs/latest, so CEX *spot* pairs are not available.
"""
import calendar
import time


def epoch(s):
    if not s:
        return None
    s = s.rstrip("Z").split(".")[0]
    try:
        return calendar.timegm(time.strptime(s, "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        return None


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def fetch_perps(cmc, cfg):
    out = []
    for sym, cid in cfg["tokens"].items():
        doc = cmc.get("/v5/cryptocurrency/derivatives/market-pairs/list/latest",
                      crypto_id=cid, category="perpetual", matched_id=cfg["quote_id"],
                      center_type="cex", limit=250, sort="volume_24h_strict")
        data = doc.get("data") or {}
        for m in data.get("market_pairs") or []:
            rep = (m.get("exchange_reported_quotes") or [{}])[0]
            q = (m.get("quotes") or [{}])[0]
            out.append({
                "token": sym, "cmc_id": cid,
                "exchange": (m.get("exchange") or {}).get("exchange_slug"),
                "pair": m.get("market_pair_symbol"),
                "price": _f(rep.get("price")),          # in the quote asset (USDT)
                "volume_usd": _f(q.get("volume_24h")),
                "funding": _f(rep.get("funding_rate")),
                "index": _f(rep.get("index_price")),    # index price as CMC reports it
                "oi_usd": _f(q.get("open_interest")),
                "outlier": bool(m.get("outlier_detected")),
                "exclusions": m.get("exclusions") or [],
                "t": epoch(rep.get("last_updated") or q.get("last_updated")),
            })
    return out


def fetch_dex(cmc, cfg):
    out = []
    for net, ncfg in cfg["networks"].items():
        scroll = None
        for _ in range(cfg["pages"]):
            doc = cmc.get("/v4/dex/spot-pairs/latest", network_id=ncfg["network_id"],
                          dex_id=",".join(str(i) for i in ncfg["dex_ids"]),
                          sort="volume_24h", sort_dir="desc",
                          liquidity_min=cfg["min_liquidity_usd"], liquidity_max=cfg["max_liquidity_usd"],
                          volume_24h_min=cfg["min_volume_usd"], scroll_id=scroll)
            rows = doc.get("data") or []
            for p in rows:
                q = (p.get("quote") or [{}])[0]
                out.append({
                    "network": net, "dex": p.get("dex_slug"), "pool": p.get("contract_address"),
                    "base": (p.get("base_asset_contract_address") or "").lower(),
                    "base_sym": p.get("base_asset_symbol"), "base_ucid": p.get("base_asset_ucid"),
                    "quote": (p.get("quote_asset_contract_address") or "").lower(),
                    "quote_sym": p.get("quote_asset_symbol"), "quote_ucid": p.get("quote_asset_ucid"),
                    "price_usd": _f(q.get("price")),
                    "price_in_quote": _f(q.get("price_by_quote_asset")),
                    "volume_usd": _f(q.get("volume_24h")),
                    "liquidity_usd": _f(q.get("liquidity")),
                    "t": epoch(q.get("last_updated") or p.get("last_updated")),
                })
            if len(rows) < 100:
                break
            scroll = rows[-1].get("scroll_id")
            if not scroll:
                break
    return out


def fetch_linked(cmc, cfg):
    ids = sorted({x for a, ia, b, ib in cfg["pairs"] for x in (ia, ib)})
    doc = cmc.get("/v3/cryptocurrency/quotes/latest", id=",".join(map(str, ids)), skip_invalid="true")
    data = doc.get("data")
    objs = []
    if isinstance(data, dict):
        for v in data.values():
            objs.extend(v if isinstance(v, list) else [v])
    elif isinstance(data, list):
        objs = data
    out = {}
    for o in objs:
        quotes = o.get("quote")
        usd = {}
        if isinstance(quotes, list):
            usd = next((x for x in quotes if str(x.get("id")) == "2781" or x.get("symbol") == "USD"), quotes[0] if quotes else {})
        elif isinstance(quotes, dict):
            usd = quotes.get("USD") or {}
        out[int(o["id"])] = {"symbol": o.get("symbol"), "price": _f(usd.get("price")),
                             "volume_usd": _f(usd.get("volume_24h")),
                             "t": epoch(usd.get("last_updated") or o.get("last_updated"))}
    return out


def snapshot(cmc, config):
    t0 = time.time()
    c0 = cmc.credits
    snap = {"t": int(t0)}
    snap["perp"] = fetch_perps(cmc, config["perp"])
    snap["dex"] = fetch_dex(cmc, config["dex"])
    snap["linked"] = fetch_linked(cmc, config["linked"])
    snap["credits"] = cmc.credits - c0
    snap["fetch_s"] = round(time.time() - t0, 1)
    return snap
