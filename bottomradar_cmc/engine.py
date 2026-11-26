"""Run the BottomRadar rule bar by bar on CoinMarketCap data.

Used both by the live screener (last ~2 days, to know which paper positions
are open right now) and by the replay (last 30 days, to show what the rule did).
"""
import bisect
import math

from . import rules
from .market import BAR, DAY, snap

HOUR = 3600


def index_levels(series_by_token, step, min_tokens=10):
    """Equal-weight cumulative log-return index: [(bar, level)]."""
    per = [snap(pts, step) for pts in series_by_token.values()]
    per = [b for b in per if b]
    if len(per) < min_tokens:
        return []
    k0 = min(min(b) for b in per)
    k1 = max(max(b) for b in per)
    out, v = [], 0.0
    for k in range(k0 + 1, k1 + 1):
        r = [math.log(b[k] / b[k - 1]) for b in per if k in b and (k - 1) in b and b[k - 1] > 0 and b[k] > 0]
        if len(r) >= min_tokens:
            v += sum(r) / len(r)
            out.append((k, v))
    return out


def below_ma_at(levels, k, ma=rules.MARKET_MA):
    """Is the index at bar k below the mean of its last `ma` values? None if unknown."""
    keys = [x[0] for x in levels]
    i = bisect.bisect_right(keys, k)
    if i < ma or keys[i - 1] < k - 2:  # need the bar itself (or very close) and ma bars of history
        return None
    px = [math.exp(x[1]) for x in levels[i - ma:i]]
    return px[-1] < sum(px) / ma


class Regime:
    """Answers the three filters at any 10-minute bar."""

    def __init__(self, market10, market1h, daily_by_symbol):
        self.l10 = index_levels(market10, BAR)
        self.l1h = index_levels(market1h, HOUR)
        self.daily = {s: snap(p, DAY) for s, p in daily_by_symbol.items()}
        self._trend_cache = {}

    def market_falling(self, k):
        m10 = below_ma_at(self.l10, k)
        t_end = (k + 1) * BAR
        h = t_end // HOUR - 1  # last fully closed hour
        h1 = below_ma_at(self.l1h, h)
        if m10 is None or h1 is None:
            return None
        return bool(m10 and h1)

    def _closes_until(self, sym, k):
        d = self.daily.get(sym) or {}
        last_day = (k + 1) * BAR // DAY - 1  # yesterday's close is known
        return [d[x] for x in sorted(d) if x <= last_day]

    def above_trend_mean(self, sym, k):
        key = (sym, (k + 1) * BAR // DAY)
        if key not in self._trend_cache:
            self._trend_cache[key] = rules.above_ma(self._closes_until(sym, k), rules.TREND_MA)
        return self._trend_cache[key]

    def ethbtc_strong(self, k):
        key = ("ETH/BTC", (k + 1) * BAR // DAY)
        if key not in self._trend_cache:
            e = self.daily.get("ETH") or {}
            b = self.daily.get("BTC") or {}
            last_day = (k + 1) * BAR // DAY - 1
            ratio = [e[x] / b[x] for x in sorted(e) if x in b and x <= last_day and b[x] > 0]
            self._trend_cache[key] = rules.above_ma(ratio, rules.TREND_MA)
        return self._trend_cache[key]

    def ladder_for(self, sym, k):
        return rules.choose_ladder(self.ethbtc_strong(k), self.above_trend_mean(sym, k), self.market_falling(k))


def run_token(sym, points10, regime, k_from=None, now=None):
    """Replay one token. Returns (events, open_position, last_bar_info)."""
    bars = snap(points10, BAR)
    if now is not None:
        bars = {k: v for k, v in bars.items() if (k + 1) * BAR <= now}
    ks = sorted(bars)
    closes = [bars[k] for k in ks]
    rsi = rules.rsi_series(closes)
    pos, events = None, []
    for i in range(1, len(ks)):
        k = ks[i]
        if k_from is not None and k < k_from:
            continue
        if ks[i - 1] != k - 1:  # gap in data: do not invent a crossing
            continue
        t = (k + 1) * BAR
        pos, ev = rules.step(pos, rsi[i - 1], rsi[i], closes[i], t, lambda: regime.ladder_for(sym, k))
        if ev:
            ev.update({"symbol": sym, "t": t, "rsi": round(rsi[i], 2)})
            events.append(ev)
    last = None
    if ks:
        last = {"t": (ks[-1] + 1) * BAR, "price": closes[-1], "rsi": rsi[-1], "rsi_prev": rsi[-2] if len(rsi) > 1 else None}
    return events, pos, last


def summarize(events, open_positions, last_prices):
    """The four numbers that matter (count, win rate, median and weighted return), realized and open."""
    exits = [e for e in events if e["type"] == "exit"]
    pnl = [e["pnl"] for e in exits]
    pct = sorted(e["pnl_pct"] for e in exits)
    cost = sum(e["cost"] for e in exits)
    latent = 0.0
    open_cost = 0.0
    for sym, p in open_positions.items():
        px = last_prices.get(sym)
        if px:
            latent += p.qty * px - p.cost
            open_cost += p.cost
    return {
        "closed": len(exits),
        "winners": sum(1 for x in pnl if x > 0),
        "realized_usd": round(sum(pnl), 2),
        "median_pct": round(pct[len(pct) // 2], 2) if pct else None,
        "weighted_pct": round(100 * sum(pnl) / cost, 2) if cost else None,
        "open": len(open_positions),
        "open_cost_usd": round(open_cost, 2),
        "open_latent_usd": round(latent, 2),
        "market_value_usd": round(sum(pnl) + latent, 2),
    }
