"""A BottomRadar-style 10-minute long ladder, with EXAMPLE parameters.

The structure is the one a live bot uses; the numbers here are example values,
not the live settings. The live levels, rebuy zone and exit stay private: put
your own in private/rule.json (git-ignored) to override them.

- RSI: Wilder, on 10-minute closes.
- A step fires when RSI crosses DOWN through its level (previous >= level > current).
- The deep ("high") ladder is allowed only if all three filters agree:
    1. ETH/BTC closed yesterday above its long trend mean;
    2. the token closed yesterday above its own long trend mean;
    3. the market is falling together: an equal-weight index of liquid
       tokens is below its short mean on 10-minute AND on 1-hour bars.
  Otherwise (or if a filter is unknown) the shallow ("low") ladder is used.
- Rebuy: each time price falls REBUY_STEP_PCT below the last buy, buy again the
  weight of the last step, at most REBUY_MAX times.
- Exit: RSI crosses UP through EXIT_RSI, only if price >= average + EXIT_MIN_GAIN_PCT.
"""
import json
import math
import os

# ---- EXAMPLE VALUES (not the live bot's settings) ----
EXAMPLE = {
    "rsi_period": 14,
    "ladder_high": [[30, 1], [25, 2], [20, 3], [15, 4], [10, 5]],
    "ladder_low": [[25, 1], [20, 2], [15, 3], [10, 4]],
    "exit_rsi": 70.0,
    "exit_min_gain_pct": 1.0,
    "rebuy_step_pct": 12.0,
    "rebuy_max": 3,
    "unit_usd": 10.0,
    "market_ma": 30,
    "trend_ma": 100,
}

_PRIVATE = os.environ.get("BRCMC_RULE_FILE") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "private", "rule.json")


def _load():
    cfg = dict(EXAMPLE)
    source = "example values"
    if os.environ.get("BRCMC_EXAMPLE") != "1" and os.path.exists(_PRIVATE):
        with open(_PRIVATE) as f:
            cfg.update({k: v for k, v in json.load(f).items() if not k.startswith("_")})
        source = "private settings"
    return cfg, source


CFG, SOURCE = _load()
RSI_PERIOD = int(CFG["rsi_period"])
LADDER_HIGH = [(float(a), float(b)) for a, b in CFG["ladder_high"]]
LADDER_LOW = [(float(a), float(b)) for a, b in CFG["ladder_low"]]
EXIT_RSI = float(CFG["exit_rsi"])
EXIT_MIN_GAIN_PCT = float(CFG["exit_min_gain_pct"])
REBUY_STEP_PCT = float(CFG["rebuy_step_pct"])
REBUY_MAX = int(CFG["rebuy_max"])
UNIT_USD = float(CFG["unit_usd"])
MARKET_MA = int(CFG["market_ma"])
TREND_MA = int(CFG["trend_ma"])
BAR = 600  # 10 minutes


def rsi_series(closes, p=RSI_PERIOD):
    """Wilder RSI. None until p+1 closes are known."""
    n = len(closes)
    out = [None] * n
    if n < p + 1:
        return out
    g = l = 0.0
    for i in range(1, p + 1):
        d = closes[i] - closes[i - 1]
        g += max(d, 0.0)
        l += max(-d, 0.0)
    ag, al = g / p, l / p
    out[p] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(p + 1, n):
        d = closes[i] - closes[i - 1]
        ag = (ag * (p - 1) + max(d, 0.0)) / p
        al = (al * (p - 1) + max(-d, 0.0)) / p
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def crossed_down(prev, cur, level):
    return prev is not None and cur is not None and prev >= level > cur


def crossed_up(prev, cur, level):
    return prev is not None and cur is not None and prev <= level < cur


def to_bars(points, step=BAR):
    """[(epoch, price)] -> {bar_index: close}; the last point inside a bar is its close."""
    bars = {}
    for t, p in points:
        if p > 0:
            bars[t // step] = p
    return bars


def index_below_ma(series, step, ma=MARKET_MA, now=None, min_tokens=10):
    """Equal-weight index of log returns.

    series: {token: [(epoch, price)]}. A bar enters the index when at least
    min_tokens tokens have a return on it. Returns (below, last, mean, tokens)
    or None when history is too short.
    """
    per = []
    for pts in series.values():
        b = to_bars(pts, step)
        if now is not None:
            b = {k: v for k, v in b.items() if (k + 1) * step <= now}
        if b:
            per.append(b)
    if len(per) < min_tokens:
        return None
    k0 = min(min(b) for b in per)
    k1 = max(max(b) for b in per)
    present = sum(1 for b in per if k1 in b)
    if present < min_tokens:
        return None
    level, v = [], 0.0
    for k in range(k0, k1 + 1):
        r = [math.log(b[k] / b[k - 1]) for b in per if k in b and (k - 1) in b]
        if len(r) >= min_tokens:
            v += sum(r) / len(r)
        level.append(v)
    if len(level) < ma + 1:
        return None
    px = [math.exp(x) for x in level[-ma:]]
    mean = sum(px) / ma
    return px[-1] < mean, px[-1], mean, present


def above_ma(closes, n=TREND_MA):
    """True / False if the last close is above / below its n-period mean, None if too short."""
    if len(closes) < n:
        return None
    m = sum(closes[-n:]) / float(n)
    return closes[-1] > m


def choose_ladder(ethbtc_strong, token_above, market_falling):
    """High ladder only if every filter says yes; unknown counts as no."""
    reasons = {
        "eth_btc_above_trend_mean": ethbtc_strong,
        "token_above_trend_mean": token_above,
        "market_falling_together": market_falling,
    }
    high = all(v is True for v in reasons.values())
    return (LADDER_HIGH if high else LADDER_LOW), ("high" if high else "low"), reasons


class Position:
    """One open ladder position, in units of UNIT_USD."""

    def __init__(self, ladder, name):
        self.ladder = ladder
        self.ladder_name = name
        self.fired = []      # levels bought
        self.legs = []       # (price, usd)
        self.rebuys = 0
        self.opened_at = None

    @property
    def cost(self):
        return sum(u for _, u in self.legs)

    @property
    def qty(self):
        return sum(u / p for p, u in self.legs)

    @property
    def avg(self):
        q = self.qty
        return self.cost / q if q else 0.0

    def buy(self, price, weight, t):
        if self.opened_at is None:
            self.opened_at = t
        self.legs.append((price, weight * UNIT_USD))

    def next_step(self):
        for lvl, w in self.ladder:
            if lvl not in self.fired:
                return lvl, w
        return None


def step(pos, prev_rsi, rsi, price, t, ladder_for_open):
    """Apply the rule on one closed 10-minute bar.

    pos: open Position or None. ladder_for_open: callable -> (ladder, name, reasons),
    called only when no position is open and RSI crosses the first level of a ladder.
    Returns (pos, event) where event is None or a dict describing what happened.
    """
    if pos is None:
        if prev_rsi is None or rsi is None:
            return None, None
        # only consult the filters when RSI crosses one of the two opening levels
        if not (crossed_down(prev_rsi, rsi, LADDER_HIGH[0][0]) or crossed_down(prev_rsi, rsi, LADDER_LOW[0][0])):
            return None, None
        ladder, name, reasons = ladder_for_open()
        first, w = ladder[0]
        if not crossed_down(prev_rsi, rsi, first):
            return None, None
        pos = Position(ladder, name)
        pos.fired.append(first)
        pos.buy(price, w, t)
        return pos, {"type": "open", "level": first, "ladder": name, "price": price, "usd": w * UNIT_USD,
                     "reasons": reasons}
    # exit first
    if crossed_up(prev_rsi, rsi, EXIT_RSI) and price >= pos.avg * (1 + EXIT_MIN_GAIN_PCT / 100.0):
        pnl = pos.qty * price - pos.cost
        return None, {"type": "exit", "price": price, "cost": pos.cost, "pnl": pnl,
                      "pnl_pct": 100.0 * pnl / pos.cost, "hold_s": t - pos.opened_at, "ladder": pos.ladder_name}
    # deeper ladder steps (several can fire on one bar if RSI drops fast)
    events = []
    for lvl, w in pos.ladder:
        if lvl not in pos.fired and crossed_down(prev_rsi, rsi, lvl):
            pos.fired.append(lvl)
            pos.buy(price, w, t)
            events.append({"type": "add", "level": lvl, "price": price, "usd": w * UNIT_USD})
    if not events and pos.rebuys < REBUY_MAX and price <= pos.legs[-1][0] * (1 - REBUY_STEP_PCT / 100.0):
        w = pos.ladder[-1][1]
        pos.rebuys += 1
        pos.buy(price, w, t)
        events.append({"type": "rebuy", "n": pos.rebuys, "price": price, "usd": w * UNIT_USD})
    return pos, (events[-1] if events else None)
