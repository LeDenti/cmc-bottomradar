"""Offline tests: the rule, the response parser, and a full scan/replay against a
fake CoinMarketCap that answers in the documented v3 shape.

    python3 -m unittest discover -s tests -v
"""
import math
import os
import random
import sys
import tempfile
import time
import unittest

import atexit  # noqa: E402
import shutil  # noqa: E402

os.environ["BRCMC_EXAMPLE"] = "1"  # tests always run on the public example values
os.environ["BRCMC_RUNS"] = tempfile.mkdtemp(prefix="brcmc-test-")
atexit.register(shutil.rmtree, os.environ["BRCMC_RUNS"], True)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bottomradar_cmc import engine, rules  # noqa: E402
from bottomradar_cmc.client import CMC, iso_to_epoch, parse_quotes_historical  # noqa: E402
from bottomradar_cmc.market import id_map  # noqa: E402


def iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))


class TestRule(unittest.TestCase):
    def test_rsi_reference(self):
        # Wilder's classic example (14 periods). Published tables show 70.53 because
        # they round the running averages; the exact value is 70.46.
        c = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28,
             46.28, 46.00, 46.03, 46.41, 46.22, 45.64]
        r = rules.rsi_series(c)
        self.assertIsNone(r[13])
        self.assertAlmostEqual(r[14], 70.464, delta=0.001)
        self.assertAlmostEqual(r[15], 66.250, delta=0.001)

    def test_example_values_loaded(self):
        self.assertEqual(rules.SOURCE, "example values")

    def test_crossings(self):
        self.assertTrue(rules.crossed_down(31, 29, 30))
        self.assertFalse(rules.crossed_down(29, 28, 30))   # already below: no new signal
        self.assertTrue(rules.crossed_down(30, 29.9, 30))
        self.assertTrue(rules.crossed_up(69, 71, 70))

    def test_ladder_choice(self):
        lad, name, _ = rules.choose_ladder(True, True, True)
        self.assertEqual(name, "high")
        self.assertEqual(lad, rules.LADDER_HIGH)
        for combo in [(True, True, False), (True, None, True), (False, True, True)]:
            self.assertEqual(rules.choose_ladder(*combo)[1], "low")

    def test_position_life(self):
        low = lambda: rules.choose_ladder(False, False, False)
        L = rules.LADDER_LOW
        (l0, w0), (l1, w1), (l2, w2) = L[0], L[1], L[2]
        pos, ev = rules.step(None, l0 + 1, l0 - 1, 100.0, 0, low)
        self.assertEqual(ev["type"], "open")
        self.assertEqual(ev["usd"], w0 * rules.UNIT_USD)
        pos, ev = rules.step(pos, l0 - 1, l2 - 1, 95.0, 600, low)       # crosses two levels at once
        self.assertEqual(pos.fired, [l0, l1, l2])
        self.assertAlmostEqual(pos.cost, (w0 + w1 + w2) * rules.UNIT_USD)
        drop = 1 - (rules.REBUY_STEP_PCT + 0.5) / 100
        pos, ev = rules.step(pos, l2 - 1, l2 - 0.5, 95.0 * drop, 1200, low)  # just past the rebuy step
        self.assertEqual(ev["type"], "rebuy")
        self.assertAlmostEqual(pos.legs[-1][1], L[-1][1] * rules.UNIT_USD)
        avg, x = pos.avg, rules.EXIT_RSI
        below = avg * (1 + rules.EXIT_MIN_GAIN_PCT / 200)
        pos2, ev = rules.step(pos, x - 1, x + 1, below, 1800, low)        # RSI exit but gain too small: hold
        self.assertIsNotNone(pos2)
        pos3, ev = rules.step(pos, x - 1, x + 1, avg * 1.05, 2400, low)
        self.assertIsNone(pos3)
        self.assertEqual(ev["type"], "exit")
        self.assertGreater(ev["pnl"], 0)

    def test_rebuy_cap(self):
        pos = rules.Position(rules.LADDER_LOW, "low")
        pos.fired = [rules.LADDER_LOW[0][0]]
        pos.buy(100.0, 1, 0)
        px, n = 100.0, 0
        step_down = 1 - (rules.REBUY_STEP_PCT + 1) / 100
        mid = (rules.LADDER_LOW[0][0] + rules.EXIT_RSI) / 2
        for i in range(rules.REBUY_MAX + 3):
            px *= step_down
            pos, ev = rules.step(pos, mid, mid + 1, px, i, None)
            n += 1 if ev and ev["type"] == "rebuy" else 0
        self.assertEqual(n, rules.REBUY_MAX)


class TestParser(unittest.TestCase):
    def _q(self, t, p):
        return {"timestamp": iso(t), "quote": {"USD": {"price": p, "timestamp": iso(t)}}}

    def test_object_map(self):
        doc = {"data": {"1": {"id": 1, "symbol": "BTC", "quotes": [self._q(1200, 2.0), self._q(600, 1.0)]}}}
        self.assertEqual(parse_quotes_historical(doc), {1: [(600, 1.0), (1200, 2.0)]})

    def test_list_and_symbol_lookup(self):
        doc = {"data": [{"id": 2, "quotes": [self._q(600, 3.0)]}]}
        self.assertEqual(parse_quotes_historical(doc), {2: [(600, 3.0)]})
        doc = {"data": {"BTC": [{"id": 1, "quotes": [self._q(600, 3.0)]}]}}
        self.assertEqual(parse_quotes_historical(doc), {1: [(600, 3.0)]})

    def test_iso(self):
        self.assertEqual(iso_to_epoch("1970-01-01T00:10:00.000Z"), 600)


class TestGaps(unittest.TestCase):
    def test_judge(self):
        from bottomradar_cmc import gaps
        now = 1_000_000
        ex = ["binance", "bybit", "bitget", "gate", "mexc", "whitebit", "zoomex"]
        cmc_px = {"binance": 100.0, "bybit": 100.02, "bitget": 99.99, "gate": 100.01, "mexc": 100.0,
                  "whitebit": 100.8,      # +0.8 % on CMC, and really there in the book
                  "zoomex": 101.5}        # +1.5 % on CMC, nothing in the book
        quotes = {"AAA": {"t": now, "quotes": [{"exchange": e, "price": p, "last_updated": now - 120,
                                                "volume_usd": 5e6, "flagged": False} for e, p in cmc_px.items()]
                          + [{"exchange": "tiny", "price": 150.0, "last_updated": now - 60, "volume_usd": 10, "flagged": False},
                             {"exchange": "stale", "price": 90.0, "last_updated": now - 5000, "volume_usd": 5e6, "flagged": False}]}}
        book = {e: [100.0 - 0.005, 100.0 + 0.005] for e in ex}
        book["whitebit"] = [100.60, 100.70]
        far = {"t": now + 500, "books": {"AAA": {e: [50.0, 50.1] for e in ex}}, "errors": {}}
        near = {"t": now + 4, "books": {"AAA": book}, "errors": {}}
        out = gaps.judge(quotes, [far, near])
        by = {r["exchange"]: r for r in out["rows"]}
        self.assertNotIn("tiny", by)       # below the volume floor
        self.assertNotIn("stale", by)      # quote too old
        self.assertTrue(by["whitebit"]["is_gap"] and by["whitebit"]["confirmed"])
        self.assertTrue(by["zoomex"]["is_gap"] and not by["zoomex"]["confirmed"])
        self.assertFalse(by["binance"]["is_gap"])
        self.assertEqual(by["zoomex"]["book_skew_s"], 4)   # the nearest book round is used
        s = out["summary"]
        self.assertEqual((s["cmc_gaps"], s["confirmed_in_book"], s["not_in_book"]), (2, 1, 1))

    def test_no_books(self):
        from bottomradar_cmc import gaps
        q = {"AAA": {"t": 0, "quotes": [{"exchange": "e%d" % i, "price": 100 + i, "last_updated": None,
                                         "volume_usd": 5e6, "flagged": False} for i in range(6)]}}
        self.assertEqual(gaps.judge(q, [])["summary"]["quotes_checked"], 0)


class FakeCMC(CMC):
    """Serves /v3/cryptocurrency/quotes/historical from a seeded random walk with crashes."""

    def __init__(self, now):
        super().__init__(key="fake", pause=0, log=False)
        self.now = now
        self.paths = {}

    def _path(self, cid):
        if cid not in self.paths:
            rnd = random.Random(cid)
            t0 = self.now - 260 * 86400
            n = (self.now - t0) // 300 + 1
            lp, out = math.log(1 + cid % 97), []
            crash_every = rnd.randint(2500, 5000)
            for i in range(n):
                shock = -0.004 if (i % crash_every) < 40 else 0.0  # a ~15 % slide every so often
                lp += rnd.gauss(0.00002, 0.0025) + shock
                out.append(lp)
            self.paths[cid] = (t0, out)
        return self.paths[cid]

    def price(self, cid, t):
        t0, lp = self._path(cid)
        i = max(0, min(len(lp) - 1, (t - t0) // 300))
        return math.exp(lp[i])

    def get(self, path, **params):
        assert path == "/v3/cryptocurrency/quotes/historical", path
        step = {"10m": 600, "daily": 86400}[params["interval"]]
        a, b = iso_to_epoch(params["time_start"]), iso_to_epoch(params["time_end"])
        data, points = {}, 0
        for cid in [int(x) for x in params["id"].split(",")]:
            qs = []
            t = -(-a // step) * step
            while t <= b:
                ts = t + random.Random(cid * 7 + t).randint(-20, 20)  # CMC returns the closest quote, not the exact time
                qs.append({"timestamp": iso(ts), "quote": {"USD": {"price": self.price(cid, ts), "timestamp": iso(ts)}}})
                t += step
            points += len(qs)
            data[str(cid)] = {"id": cid, "quotes": qs}
        if points > 10000:  # same limit as the real API
            raise AssertionError("max datapoints allowed is 10000, got %d" % points)
        credits = -(-points // 100)
        self.calls += 1
        self.credits += credits
        return {"status": {"error_code": 0, "credit_count": credits}, "data": data}


class TestEndToEnd(unittest.TestCase):
    def test_scan_and_replay(self):
        from bottomradar_cmc import screener
        now = (int(time.time()) // 600) * 600 + 90
        fake = FakeCMC(now)
        out = screener.replay(days=20, cmc=fake, now=now)
        s = out["summary"]
        self.assertGreater(out["opens_by_ladder"]["low"] + out["opens_by_ladder"]["high"], 0)
        self.assertGreaterEqual(s["closed"], 1)
        for e in out["events"]:
            if e["type"] == "exit":
                self.assertGreater(e["pnl"], 0)  # exits only in gain by rule
        first = fake.credits
        self.assertGreater(first, 0)
        # a scan right after reuses the cache: only a top-up is paid
        fake2 = FakeCMC(now + 600)
        fake2.paths = fake.paths
        scan = screener.scan(cmc=fake2, now=now + 600)
        self.assertLessEqual(fake2.credits, 10)
        self.assertEqual(len(scan["tokens"]), len([s for s in screener.load_universe("universe_75") if s in id_map()]))
        self.assertIn(scan["filters_now"]["market_falling_together"], (True, False, None))


if __name__ == "__main__":
    unittest.main()
