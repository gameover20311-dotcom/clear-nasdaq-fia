from pathlib import Path

providers = Path('backend/fia/providers.py')
s = providers.read_text()

old = '''        except Exception as e:\n            print(f"Provider error: {url} -> {e}")\n            return None\n'''
new = '''        except Exception as e:\n            # SECURITY: never stringify provider exceptions here. httpx embeds the\n            # fully-expanded request URL in HTTPStatusError, including query-string\n            # credentials such as Finnhub token=... and Polygon apiKey=....\n            # Log only scheme/host/path plus status/type; never query parameters.\n            try:\n                from urllib.parse import urlsplit\n                parts = urlsplit(str(url))\n                safe_url = f"{parts.scheme}://{parts.netloc}{parts.path}"\n            except Exception:\n                safe_url = "<provider-url-redacted>"\n\n            status = None\n            if isinstance(e, httpx.HTTPStatusError) and getattr(e, "response", None) is not None:\n                status = getattr(e.response, "status_code", None)\n            if status is not None:\n                print(f"Provider error: {safe_url} -> HTTP {status} ({type(e).__name__})")\n            else:\n                print(f"Provider error: {safe_url} -> {type(e).__name__}")\n            return None\n'''
if old not in s:
    raise SystemExit('generic HTTP error block not found exactly')
s = s.replace(old, new, 1)

start = s.index('    async def finnhub_candles(')
end_marker = '    # =========================================================\n    # FRED\n'
end = s.index(end_marker, start)

replacement = r'''    async def _yahoo_chart_candles(
        self,
        symbol: str,
        resolution: str,
        start_ts: int,
        end_ts: int,
    ):
        """Keyless Yahoo chart fallback, normalized to Finnhub candle shape.

        This is a live fallback only. Timestamps remain provider aggregate-window
        START timestamps; completed_bar_structure() remains the single authority
        that rejects a still-forming final bar before any structure score is used.
        """
        from urllib.parse import quote

        interval_map = {
            "D": "1d",
            "5": "5m", "5m": "5m",
            "15": "15m", "15m": "15m",
            "30": "30m", "30m": "30m",
            "60": "60m", "60m": "60m",
        }
        interval = interval_map.get(str(resolution))
        if not interval:
            return None

        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(str(symbol), safe='')}"
        payload = await self.get(
            url,
            {
                "period1": int(start_ts),
                "period2": int(end_ts) + 60,
                "interval": interval,
                "includePrePost": "true",
                "events": "div,splits",
            },
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if not isinstance(payload, dict):
            return None

        chart = payload.get("chart") or {}
        if chart.get("error"):
            return None
        results = chart.get("result") or []
        if not results or not isinstance(results[0], dict):
            return None
        result = results[0]
        stamps = list(result.get("timestamp") or [])
        indicators = result.get("indicators") or {}
        quotes = indicators.get("quote") or []
        if not stamps or not quotes or not isinstance(quotes[0], dict):
            return None
        q = quotes[0]
        closes_raw = list(q.get("close") or [])
        highs_raw = list(q.get("high") or [])
        lows_raw = list(q.get("low") or [])
        opens_raw = list(q.get("open") or [])
        volumes_raw = list(q.get("volume") or [])

        timestamps, highs, lows, closes, opens, volumes = [], [], [], [], [], []
        for i, ts in enumerate(stamps):
            try:
                close = closes_raw[i] if i < len(closes_raw) else None
                if ts is None or close is None:
                    continue
                close_f = float(close)
                high = highs_raw[i] if i < len(highs_raw) else None
                low = lows_raw[i] if i < len(lows_raw) else None
                open_ = opens_raw[i] if i < len(opens_raw) else None
                volume = volumes_raw[i] if i < len(volumes_raw) else None
                timestamps.append(int(ts))
                highs.append(float(high) if high is not None else close_f)
                lows.append(float(low) if low is not None else close_f)
                closes.append(close_f)
                opens.append(float(open_) if open_ is not None else close_f)
                volumes.append(float(volume) if volume is not None else 0.0)
            except (TypeError, ValueError, OverflowError, IndexError):
                continue

        if not timestamps:
            return None
        return {
            "s": "ok",
            "t": timestamps,
            "h": highs,
            "l": lows,
            "c": closes,
            "o": opens,
            "v": volumes,
            "_fia_candle_source": "yahoo_chart_fallback",
        }

    @staticmethod
    def _latest_candle_start(payload):
        if not isinstance(payload, dict):
            return None
        vals = []
        for x in payload.get("t") or []:
            try:
                vals.append(int(x))
            except (TypeError, ValueError, OverflowError):
                pass
        return max(vals) if vals else None

    async def finnhub_candles(
        self,
        symbol: str,
        resolution: str,
        start_ts: int,
        end_ts: int,
    ):
        """Return the freshest real candle series from the configured live paths.

        Finnhub remains primary when it succeeds. If it fails, Polygon and
        keyless Yahoo Chart are both evaluated and the series with the newest
        provider bar-start timestamp wins. Downstream completed-bar logic still
        rejects any forming row, so freshness cannot create future-bar leakage.
        """
        key = self.keys["FINNHUB_API_KEY"]

        if key:
            candles = await self.get(
                "https://" + "finnhub.io/api/v1/stock/candle",
                {
                    "symbol": symbol,
                    "resolution": resolution,
                    "from": start_ts,
                    "to": end_ts,
                    "token": key,
                },
                timeout=15,
            )
            if isinstance(candles, dict) and candles.get("s") == "ok":
                candles.setdefault("_fia_candle_source", "finnhub")
                self._candle_failure = None
                return candles
            print(f"Finnhub candles unavailable for {symbol} ({resolution}); trying fallbacks.")
            self._candle_failure = {
                "stage": "finnhub", "symbol": symbol, "resolution": str(resolution),
                "reason": "FINNHUB_CANDLES_UNAVAILABLE",
            }

        polygon_payload = None
        polygon_key = self.keys["POLYGON_API_KEY"]
        if polygon_key:
            resolution_map = {
                "D": ("1", "day"),
                "5": ("5", "minute"), "5m": ("5", "minute"),
                "15": ("15", "minute"), "15m": ("15", "minute"),
                "30": ("30", "minute"), "30m": ("30", "minute"),
                "60": ("60", "minute"), "60m": ("60", "minute"),
            }
            multiplier, timespan = resolution_map.get(str(resolution), ("1", "day"))
            start_date = datetime.utcfromtimestamp(int(start_ts)).strftime("%Y-%m-%d")
            end_date = datetime.utcfromtimestamp(int(end_ts)).strftime("%Y-%m-%d")
            polygon_url = (
                f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/"
                f"{multiplier}/{timespan}/{start_date}/{end_date}"
            )
            polygon = await self.get(
                polygon_url,
                {"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": polygon_key},
                timeout=15,
            )
            results = (polygon.get("results") or []) if isinstance(polygon, dict) else []
            if results:
                timestamps, highs, lows, closes, opens, volumes = [], [], [], [], [], []
                for row in results:
                    try:
                        ts_ms = row.get("t")
                        high = row.get("h")
                        low = row.get("l")
                        close = row.get("c")
                        open_ = row.get("o")
                        if ts_ms is None or high is None or low is None or close is None:
                            continue
                        timestamps.append(int(ts_ms) // 1000)
                        highs.append(float(high))
                        lows.append(float(low))
                        closes.append(float(close))
                        opens.append(float(open_) if open_ is not None else float(close))
                        try:
                            volumes.append(float(row.get("v") or 0.0))
                        except (TypeError, ValueError):
                            volumes.append(0.0)
                    except (TypeError, ValueError, OverflowError, AttributeError):
                        continue
                if timestamps:
                    polygon_payload = {
                        "s": "ok", "t": timestamps, "h": highs, "l": lows,
                        "c": closes, "o": opens, "v": volumes,
                        "_fia_candle_source": "polygon_fallback",
                    }
                    print(f"Polygon fallback available for {symbol} ({resolution}): {len(timestamps)} candles.")
            if polygon_payload is None:
                print(f"Polygon fallback returned no usable candles for {symbol} ({resolution}).")
        else:
            print("Polygon fallback unavailable: POLYGON_API_KEY is missing.")

        yahoo_payload = await self._yahoo_chart_candles(symbol, resolution, start_ts, end_ts)
        if isinstance(yahoo_payload, dict):
            print(f"Yahoo chart fallback available for {symbol} ({resolution}): {len(yahoo_payload.get('t') or [])} candles.")

        p_latest = self._latest_candle_start(polygon_payload)
        y_latest = self._latest_candle_start(yahoo_payload)
        chosen = None
        if y_latest is not None and (p_latest is None or y_latest > p_latest):
            chosen = yahoo_payload
        elif p_latest is not None:
            chosen = polygon_payload
        elif y_latest is not None:
            chosen = yahoo_payload

        if isinstance(chosen, dict):
            self._candle_failure = None
            print(
                f"Candle fallback selected for {symbol} ({resolution}): "
                f"{chosen.get('_fia_candle_source')} latest_start={self._latest_candle_start(chosen)}"
            )
            return chosen

        self._candle_failure = {
            "stage": "fallbacks", "symbol": symbol, "resolution": str(resolution),
            "reason": "NO_USABLE_CANDLE_PROVIDER",
            "remediation": "Finnhub, Polygon and Yahoo Chart returned no usable candle series.",
        }
        return None

'''
s = s[:start] + replacement + s[end:]
providers.write_text(s)

reliability = Path('backend/fia/provider_reliability.py')
r = reliability.read_text()
old_label = 'source="Finnhub candles + Polygon fallback"'
new_label = 'source="Finnhub candles + Polygon/Yahoo fallback"'
if old_label not in r:
    raise SystemExit('provider health candle source label not found')
reliability.write_text(r.replace(old_label, new_label, 1))

print('PATCH_APPLIED')
