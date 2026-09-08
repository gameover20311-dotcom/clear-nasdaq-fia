from pathlib import Path

p = Path('backend/fia/providers.py')
s = p.read_text()

old = '''        polygon_payload = None\n        polygon_key = self.keys["POLYGON_API_KEY"]\n        if polygon_key:\n'''
new = '''        polygon_payload = None\n        polygon_failure = None\n        polygon_key = self.keys["POLYGON_API_KEY"]\n        if polygon_key:\n'''
if old not in s:
    raise SystemExit('polygon preamble not found')
s = s.replace(old, new, 1)

old = '''            results = (polygon.get("results") or []) if isinstance(polygon, dict) else []\n            if results:\n'''
new = '''            if not isinstance(polygon, dict):\n                polygon_failure = {\n                    "stage": "polygon", "symbol": symbol, "resolution": str(resolution),\n                    "reason": "POLYGON_REQUEST_FAILED",\n                    "remediation": "Polygon returned no usable response (auth, rate limit or network).",\n                }\n            results = (polygon.get("results") or []) if isinstance(polygon, dict) else []\n            if results:\n'''
if old not in s:
    raise SystemExit('polygon results block not found')
s = s.replace(old, new, 1)

old = '''            if polygon_payload is None:\n                print(f"Polygon fallback returned no usable candles for {symbol} ({resolution}).")\n        else:\n            print("Polygon fallback unavailable: POLYGON_API_KEY is missing.")\n\n        yahoo_payload = await self._yahoo_chart_candles(symbol, resolution, start_ts, end_ts)\n'''
new = '''            if polygon_payload is None:\n                if polygon_failure is None:\n                    polygon_failure = {\n                        "stage": "polygon", "symbol": symbol, "resolution": str(resolution),\n                        "reason": "POLYGON_EMPTY_RESULTS",\n                        "remediation": "Polygon returned no aggregate rows usable as candles.",\n                    }\n                print(f"Polygon fallback returned no usable candles for {symbol} ({resolution}).")\n        else:\n            polygon_failure = {\n                "stage": "polygon", "symbol": symbol, "resolution": str(resolution),\n                "reason": "POLYGON_API_KEY_NOT_CONFIGURED",\n                "remediation": "Set POLYGON_API_KEY in the deployment environment.",\n            }\n            print("Polygon fallback unavailable: POLYGON_API_KEY is missing.")\n\n        yahoo_payload = await self._yahoo_chart_candles(symbol, resolution, start_ts, end_ts)\n'''
if old not in s:
    raise SystemExit('polygon failure tail not found')
s = s.replace(old, new, 1)

old = '''        self._candle_failure = {\n            "stage": "fallbacks", "symbol": symbol, "resolution": str(resolution),\n            "reason": "NO_USABLE_CANDLE_PROVIDER",\n            "remediation": "Finnhub, Polygon and Yahoo Chart returned no usable candle series.",\n        }\n        return None\n'''
new = '''        # Preserve the most actionable provider-specific diagnostic. Yahoo is a\n        # keyless rescue path; its failure must not erase whether Polygon was\n        # unconfigured, rejected/rate-limited, or simply returned no rows.\n        self._candle_failure = polygon_failure or {\n            "stage": "fallbacks", "symbol": symbol, "resolution": str(resolution),\n            "reason": "NO_USABLE_CANDLE_PROVIDER",\n            "remediation": "Finnhub, Polygon and Yahoo Chart returned no usable candle series.",\n        }\n        if isinstance(self._candle_failure, dict):\n            self._candle_failure["yahoo_fallback_attempted"] = True\n        return None\n'''
if old not in s:
    raise SystemExit('final failure block not found')
s = s.replace(old, new, 1)

p.write_text(s)

rpath = Path('backend/fia/provider_reliability.py')
r = rpath.read_text()
r = r.replace('Finnhub candles + Polygon/Yahoo fallback', 'Finnhub candles + Polygon fallback + Yahoo fallback')
rpath.write_text(r)
print('COMPAT_PATCH_APPLIED')
