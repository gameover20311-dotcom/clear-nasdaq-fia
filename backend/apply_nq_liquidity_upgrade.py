from pathlib import Path
import re

p = Path("fia/providers.py")
text = p.read_text()

if "async def polygon_futures_candles" in text:
    print("NQ liquidity upgrade already present.")
    raise SystemExit(0)

anchor = "    # =========================================================\n    # Complete liquidity data\n    # =========================================================\n"

if anchor not in text:
    raise SystemExit("ERROR: insertion point not found")

block = r'''    # =========================================================
    # NQ Futures liquidity intelligence
    # =========================================================

    def current_nq_futures_symbol(self):
        """
        Returns the active quarterly E-mini Nasdaq-100 futures
        contract using the standard CME quarterly cycle:
        H=Mar, M=Jun, U=Sep, Z=Dec.

        This intentionally uses a real futures symbol rather than
        pretending QQQ is NQ.
        """
        now = self.now_ny()

        contracts = [
            (3, "H"),
            (6, "M"),
            (9, "U"),
            (12, "Z"),
        ]

        for month, code in contracts:
            if now.month <= month:
                return f"NQ{code}{str(now.year)[-1]}"

        return f"NQH{str(now.year + 1)[-1]}"

    async def polygon_futures_candles(
        self,
        ticker: str,
        multiplier: int = 5,
        timespan: str = "minute",
        start_ts: int = None,
        end_ts: int = None,
    ):
        """
        Polygon Futures minute aggregates.

        Returns a normalized candle structure compatible with the
        existing session-liquidity calculation.
        """
        polygon_key = self.keys.get("POLYGON_API_KEY")

        if not polygon_key:
            print("NQ futures unavailable: POLYGON_API_KEY is missing.")
            return None

        if start_ts is None:
            start_ts = self.datetime_to_ts(
                self.now_ny() - timedelta(days=8)
            )

        if end_ts is None:
            end_ts = self.datetime_to_ts(self.now_ny())

        start_date = datetime.fromtimestamp(
            int(start_ts),
            tz=self.NY_TZ,
        ).strftime("%Y-%m-%d")

        end_date = datetime.fromtimestamp(
            int(end_ts),
            tz=self.NY_TZ,
        ).strftime("%Y-%m-%d")

        url = (
            f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/"
            f"{multiplier}/{timespan}/{start_date}/{end_date}"
        )

        response = await self.get(
            url,
            {
                "sort": "asc",
                "limit": 50000,
                "apiKey": polygon_key,
            },
            timeout=15,
        )

        if not response:
            print(f"Polygon NQ futures returned no response for {ticker}.")
            return None

        results = response.get("results") or []

        if not results:
            print(f"Polygon NQ futures returned no candles for {ticker}.")
            return None

        timestamps = []
        highs = []
        lows = []
        closes = []
        volumes = []

        for row in results:
            try:
                ts_ms = row.get("t")
                high = row.get("h")
                low = row.get("l")
                close = row.get("c")
                volume = row.get("v", 0)

                if (
                    ts_ms is None
                    or high is None
                    or low is None
                    or close is None
                ):
                    continue

                timestamps.append(int(ts_ms / 1000))
                highs.append(float(high))
                lows.append(float(low))
                closes.append(float(close))
                volumes.append(float(volume or 0))

            except (TypeError, ValueError, OverflowError):
                continue

        if not timestamps:
            return None

        return {
            "s": "ok",
            "t": timestamps,
            "h": highs,
            "l": lows,
            "c": closes,
            "v": volumes,
            "ticker": ticker,
        }

    async def get_nq_liquidity_intelligence(self):
        """
        Builds NQ-specific liquidity intelligence from real
        futures candles.

        Includes:
          - Asia / London / NY highs and lows
          - current NQ price
          - liquidity distances
          - sweep detection
          - target ranking
          - liquidity conflict
          - relative-volume context
        """
        now_ny = self.now_ny()
        start_ny = now_ny - timedelta(days=8)

        ticker = self.current_nq_futures_symbol()

        candles = await self.polygon_futures_candles(
            ticker,
            5,
            "minute",
            self.datetime_to_ts(start_ny),
            self.datetime_to_ts(now_ny),
        )

        if not candles:
            return {
                "nq_liquidity_evidence": "missing",
                "nq_futures_symbol": ticker,
            }

        timestamps = candles.get("t", [])
        highs = candles.get("h", [])
        lows = candles.get("l", [])
        closes = candles.get("c", [])
        volumes = candles.get("v", [])

        rows = []

        for i, (ts, high, low) in enumerate(
            zip(timestamps, highs, lows)
        ):
            try:
                dt = datetime.fromtimestamp(
                    int(ts),
                    tz=self.NY_TZ,
                )

                close = (
                    float(closes[i])
                    if i < len(closes)
                    else float(high + low) / 2.0
                )

                volume = (
                    float(volumes[i])
                    if i < len(volumes)
                    else 0.0
                )

                rows.append(
                    {
                        "datetime": dt,
                        "high": float(high),
                        "low": float(low),
                        "close": close,
                        "volume": volume,
                    }
                )

            except (TypeError, ValueError, OverflowError):
                continue

        if not rows:
            return {
                "nq_liquidity_evidence": "missing",
                "nq_futures_symbol": ticker,
            }

        latest_price = rows[-1]["close"]

        levels = {}

        for days_back in range(0, 8):
            target_date = (
                now_ny.date() - timedelta(days=days_back)
            )

            for session in (
                "ASIA",
                "LONDON",
                "NEW_YORK",
            ):
                start, end = self.session_window_for_date(
                    session,
                    target_date,
                )

                if start is None or end is None:
                    continue

                session_rows = [
                    row
                    for row in rows
                    if start <= row["datetime"] < end
                ]

                if not session_rows:
                    continue

                high_key = session.lower() + "_high"
                low_key = session.lower() + "_low"

                if high_key not in levels:
                    levels[high_key] = max(
                        row["high"] for row in session_rows
                    )

                if low_key not in levels:
                    levels[low_key] = min(
                        row["low"] for row in session_rows
                    )

            required = {
                "asia_high",
                "asia_low",
                "london_high",
                "london_low",
                "new_york_high",
                "new_york_low",
            }

            if required.issubset(levels.keys()):
                break

        result = {
            "nq_liquidity_evidence": "available",
            "nq_futures_symbol": ticker,
            "nq_price": latest_price,
        }

        result.update(levels)

        # -----------------------------------------------------
        # Liquidity proximity / distance
        # -----------------------------------------------------

        targets = []

        for name, level in levels.items():
            try:
                distance = float(level) - latest_price
                distance_abs = abs(distance)

                result[f"{name}_distance"] = distance
                result[f"{name}_distance_abs"] = distance_abs

                targets.append(
                    {
                        "level": name,
                        "price": float(level),
                        "distance": distance,
                        "distance_abs": distance_abs,
                    }
                )
            except (TypeError, ValueError):
                continue

        targets.sort(key=lambda x: x["distance_abs"])

        result["nearest_liquidity"] = (
            targets[0]["level"] if targets else None
        )

        result["nearest_liquidity_distance"] = (
            targets[0]["distance"] if targets else None
        )

        # -----------------------------------------------------
        # Sweep detection
        #
        # A sweep means price traded beyond a session extreme
        # while the latest price is back inside that range.
        # -----------------------------------------------------

        for session in ("asia", "london", "new_york"):
            high = levels.get(f"{session}_high")
            low = levels.get(f"{session}_low")

            if high is None or low is None:
                continue

            recent_rows = rows[-12:]

            swept_high = any(
                row["high"] > high
                for row in recent_rows
            )

            swept_low = any(
                row["low"] < low
                for row in recent_rows
            )

            reclaimed_high = (
                swept_high and latest_price < high
            )

            reclaimed_low = (
                swept_low and latest_price > low
            )

            result[f"{session}_high_sweep"] = swept_high
            result[f"{session}_low_sweep"] = swept_low
            result[f"{session}_high_reclaim"] = reclaimed_high
            result[f"{session}_low_reclaim"] = reclaimed_low

        # -----------------------------------------------------
        # Target ranking
        # -----------------------------------------------------

        ranked_targets = []

        for item in targets:
            score = 1.0 / (
                1.0 + item["distance_abs"]
            )

            if item["level"].endswith("_high"):
                direction = "UP"
            else:
                direction = "DOWN"

            ranked_targets.append(
                {
                    "level": item["level"],
                    "price": item["price"],
                    "direction": direction,
                    "distance": item["distance"],
                    "rank_score": round(score, 6),
                }
            )

        result["liquidity_targets"] = ranked_targets[:6]

        # -----------------------------------------------------
        # Conflict detection
        # -----------------------------------------------------

        bullish_liquidity = any(
            result.get(f"{session}_low_sweep")
            and result.get(f"{session}_low_reclaim")
            for session in ("asia", "london", "new_york")
        )

        bearish_liquidity = any(
            result.get(f"{session}_high_sweep")
            and result.get(f"{session}_high_reclaim")
            for session in ("asia", "london", "new_york")
        )

        if bullish_liquidity and bearish_liquidity:
            conflict = "HIGH"
        elif bullish_liquidity or bearish_liquidity:
            conflict = "LOW"
        else:
            conflict = "NONE"

        result["liquidity_conflict"] = conflict

        if bullish_liquidity and not bearish_liquidity:
            result["liquidity_direction"] = "BULLISH"
        elif bearish_liquidity and not bullish_liquidity:
            result["liquidity_direction"] = "BEARISH"
        else:
            result["liquidity_direction"] = "NEUTRAL"

        # -----------------------------------------------------
        # Relative volume
        # -----------------------------------------------------

        positive_volumes = [
            row["volume"]
            for row in rows[-60:]
            if row["volume"] > 0
        ]

        if positive_volumes:
            avg_volume = (
                sum(positive_volumes)
                / len(positive_volumes)
            )

            current_volume = rows[-1]["volume"]

            result["nq_relative_volume"] = (
                current_volume / avg_volume
                if avg_volume
                else None
            )
        else:
            result["nq_relative_volume"] = None

        return result

'''

text = text.replace(anchor, block + anchor, 1)

p.write_text(text)
print("NQ liquidity intelligence block added.")
