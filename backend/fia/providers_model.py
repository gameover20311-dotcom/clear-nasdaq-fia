# PHASE23_DATA_RELIABILITY_V1
# PHASE22_TRUTH_CONSISTENCY_V1
import yfinance as yf
import os
import time
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv

load_dotenv()

"""CLEAR NASDAQ — providers.py split, MODEL half.

MODEL — anything that can change the forecast itself.

News scoring, value transforms, relevance and the aggregation that produces
data['news'], which becomes the engine's News signal. A change here is a
change to the experiment.

SPLIT MECHANICS
This module holds method bodies moved VERBATIM out of providers.py. It is a
mixin, not a standalone class: ProviderHub composes all three, so every
self.<method> call resolves exactly as it did before and the public
ProviderHub API is unchanged. Nothing here was rewritten, reordered inside a
method, or retyped; the split is a move.
"""


class ModelMixin:
    @staticmethod
    def normalize_change(change_percent):
        """
        Converts percentage change into approximately [-1, +1].

        Example:
          +2% -> +1
          -2% -> -1
          +1% -> +0.5
        """
        if change_percent is None:
            return None

        try:
            value = float(change_percent)
        except (TypeError, ValueError):
            return None

        return max(-1.0, min(1.0, value / 2.0))
    async def completed_bar_structure(self, symbol: str, resolution: str = "60"):
        """Directional structure from COMPLETED bars only.

        Returns None when a real series is unavailable, so the caller can fall back
        to an explicitly-labelled proxy rather than silently inventing evidence.

        Provider timestamps identify interval starts. A row is usable only when
        its start + resolution is at or before the current time; forming bars are
        excluded while already-completed final rows are retained.
        """
        import time as _time
        from datetime import datetime as _dt, timezone as _tz

        now = int(_time.time())
        candles = await self.finnhub_candles(symbol, str(resolution), now - 10 * 86400, now)
        if not isinstance(candles, dict):
            return None

        closes = list(candles.get("c") or [])
        stamps = list(candles.get("t") or [])
        if len(closes) != len(stamps) or len(closes) < 12:
            return None

        # Provider candle timestamps are aggregate-window START timestamps.
        # Polygon documents `t` as the start of the aggregate window, and the
        # Finnhub candle feed uses the same interval timestamp convention.  The
        # old code dropped the final row unconditionally and then labelled the
        # previous row's START as the bar END.  On delayed/cloud feeds the final
        # row is often already completed, so this made a genuinely fresh 60m bar
        # appear roughly 1-2 hours older and caused the live freshness gate to
        # exclude Price Structure / MTF during regular session.
        try:
            _resolution_minutes = int(str(resolution).lower().rstrip("m"))
        except (TypeError, ValueError):
            _resolution_minutes = 0
        _bar_seconds = _resolution_minutes * 60 if _resolution_minutes > 0 else 0

        if _bar_seconds:
            completed = [
                (float(c), int(t))
                for c, t in zip(closes, stamps)
                if int(t) + _bar_seconds <= now
            ]
            if len(completed) < 10:
                return None
            closes = [c for c, _ in completed]
            stamps = [t for _, t in completed]
            _last_bar_end_ts = int(stamps[-1]) + _bar_seconds
        else:
            # Conservative compatibility fallback for non-minute resolutions:
            # preserve the previous completed-bar rule rather than guessing an
            # interval length.  This path is not used by the live 60m structure.
            closes = closes[:-1]
            stamps = stamps[:-1]
            if len(closes) < 10:
                return None
            _last_bar_end_ts = int(stamps[-1])

        last = float(closes[-1])
        window = [float(x) for x in closes[-40:]]
        hi, lo = max(window), min(window)

        # Component 1: position of the last completed close inside its recent range.
        position = 0.0 if hi <= lo else ((last - lo) / (hi - lo)) * 2.0 - 1.0

        # Component 2: short-horizon momentum, scaled so ~1% saturates.
        ref = float(closes[-7]) if len(closes) >= 7 else float(closes[0])
        momentum = 0.0 if ref == 0 else max(-1.0, min(1.0, ((last - ref) / ref) * 100.0))

        score = max(-1.0, min(1.0, 0.5 * position + 0.5 * momentum))

        return {
            "score": round(score, 6),
            "basis": f"{symbol}_{resolution}M_CANDLES_COMPLETED_BARS",
            "completed_bars": len(closes),
            "last_completed_bar_start_utc": _dt.fromtimestamp(int(stamps[-1]), _tz.utc).isoformat(),
            "last_completed_bar_end_utc": _dt.fromtimestamp(_last_bar_end_ts, _tz.utc).isoformat(),
            "source": str(candles.get("_fia_candle_source") or "finnhub"),
            "detail": (
                f"{len(closes)} completed {resolution}m {symbol} bars; "
                f"range position {position:+.3f}, momentum {momentum:+.3f}; "
                f"in-progress bar excluded"
            ),
        }
    @staticmethod
    def normalize_yield(yield_value):
        """
        Higher yields are treated as negative pressure
        for NASDAQ / growth assets.
        """
        if yield_value is None:
            return None

        try:
            value = float(yield_value)
        except (TypeError, ValueError):
            return None

        return max(-1.0, min(1.0, -(value - 4.0) / 1.5))
    def analyze_news_context(self, article):
        """
        FIA News Context Intelligence Engine V2.

        Uses priority-based event detection to avoid false
        classifications from isolated keywords.

        Returns structured context without changing raw news data.
        """

        if not isinstance(article, dict):
            return {
                "event_type": "unknown",
                "direction": "neutral",
                "direction_confidence": 0.0,
                "impact_strength": 0.0,
                "affected_symbols": [],
                "sector": "general_market",
                "reasoning": ["Invalid article format"],
            }

        import re

        headline = str(
            article.get("headline")
            or article.get("title")
            or ""
        )

        summary = str(
            article.get("summary")
            or article.get("description")
            or ""
        )

        text = (
            headline + " " + summary
        ).lower()

        # -----------------------------------------------------
        # COMPANY / SYMBOL DETECTION
        # -----------------------------------------------------

        company_aliases = {
            "NVDA": ["nvda", "nvidia"],
            "MSFT": ["msft", "microsoft"],
            "AAPL": ["aapl", "apple"],
            "AMZN": ["amzn", "amazon"],
            "META": ["meta", "facebook"],
            "GOOGL": ["googl", "google", "alphabet"],
            "AVGO": ["avgo", "broadcom"],
            "TSLA": ["tsla", "tesla"],
            "AMD": ["amd", "advanced micro devices"],
            "NFLX": ["nflx", "netflix"],
            "INTC": ["intc", "intel"],
            "MU": ["mu", "micron"],
            "QCOM": ["qcom", "qualcomm"],
            "SMCI": [
                "smci",
                "super micro",
                "supermicro",
            ],
        }

        affected_symbols = []

        def safe_alias_match(alias, content):

            alias = alias.lower().strip()

            # Short aliases/tickers must match as complete words.
            if len(alias) <= 4:
                return bool(
                    re.search(
                        r"(?<![a-z0-9])"
                        + re.escape(alias)
                        + r"(?![a-z0-9])",
                        content,
                    )
                )

            # Longer company names can safely use phrase matching.
            return alias in content


        for symbol, aliases in company_aliases.items():

            if any(
                safe_alias_match(alias, text)
                for alias in aliases
            ):
                affected_symbols.append(symbol)

        # -----------------------------------------------------
        # EVENT DETECTION V2
        #
        # Priority matters.
        # Commentary must be detected before broad financial
        # keywords such as "growth" or "stocks".
        # -----------------------------------------------------

        event_type = "general_market"

        commentary_patterns = [
            "jim cramer",
            "cramer says",
            "cramer reveals",
            "says investors",
            "investing rule",
            "winning stocks",
            "worth buying",
            "worth holding",
            "stock picks",
            "investment strategy",
            "should investors",
        ]

        monetary_patterns = [
            "federal reserve",
            "fed rate",
            "interest rate",
            "rate hike",
            "rate cut",
            "fed chair",
            "powell",
            "central bank",
            "monetary policy",
        ]

        macro_patterns = [
            "inflation",
            "consumer price index",
            "cpi",
            "jobs report",
            "employment report",
            "payroll",
            "nonfarm",
            "gdp",
            "recession",
            "unemployment",
            "economic growth",
        ]

        geopolitical_patterns = [
            "trade war",
            "sanctions",
            "tariff",
            "military conflict",
            "armed conflict",
            "geopolitical",
        ]

        geopolitical_word_match = bool(
            re.search(
                r"(?<![a-z])war(?![a-z])",
                text,
            )
        )

        analyst_patterns = [
            "price target",
            "upgraded to",
            "downgraded to",
            "analyst upgrade",
            "analyst downgrade",
            "buy rating",
            "sell rating",
            "overweight rating",
            "underperform rating",
        ]

        corporate_patterns = [
            "acquisition",
            "acquire",
            "merger",
            "buyback",
            "share repurchase",
            "layoffs",
            "chief executive",
            "ceo resigns",
        ]

        technology_patterns = [
            "artificial intelligence",
            " ai ",
            "semiconductor",
            "chipmaker",
            "data center",
            "gpu",
        ]

        earnings_patterns = [
            "quarterly earnings",
            "quarter earnings",
            "earnings report",
            "earnings results",
            "reported earnings",
            "reported revenue",
            "revenue rose",
            "revenue fell",
            "profit rose",
            "profit fell",
            "eps",
            "raises guidance",
            "cuts guidance",
            "beat estimates",
            "missed estimates",
        ]

        # Priority-based classification.

        if any(
            pattern in text
            for pattern in monetary_patterns
        ):
            event_type = "monetary_policy"

        elif any(
            pattern in text
            for pattern in macro_patterns
        ):
            event_type = "macroeconomic"

        elif (
            geopolitical_word_match
            or any(
                pattern in text
                for pattern in geopolitical_patterns
            )
        ):
            event_type = "geopolitical"

        elif any(
            pattern in text
            for pattern in commentary_patterns
        ):
            event_type = "commentary"

        elif any(
            pattern in text
            for pattern in analyst_patterns
        ):
            event_type = "analyst_action"

        elif any(
            pattern in text
            for pattern in corporate_patterns
        ):
            event_type = "corporate_action"

        elif any(
            pattern in text
            for pattern in earnings_patterns
        ):
            event_type = "earnings"

        elif any(
            pattern in text
            for pattern in technology_patterns
        ):
            event_type = "technology"

        # -----------------------------------------------------
        # MARKET DIRECTION V2
        #
        # Only meaningful directional signals are counted.
        # Commentary defaults to neutral unless strong evidence
        # exists.
        # -----------------------------------------------------

        bullish_patterns = [
            "beat estimates",
            "beats estimates",
            "raises guidance",
            "record revenue",
            "record profit",
            "shares surge",
            "stock surges",
            "rallies",
            "upgraded to",
            "rate cut",
        ]

        bearish_patterns = [
            "missed estimates",
            "miss estimates",
            "cuts guidance",
            "shares fall",
            "shares fell",
            "stock falls",
            "stock fell",
            "selloff",
            "downgraded to",
            "rate hike",
            "recession",
        ]

        bullish_count = sum(
            pattern in text
            for pattern in bullish_patterns
        )

        bearish_count = sum(
            pattern in text
            for pattern in bearish_patterns
        )

        direction = "neutral"
        direction_confidence = 0.0

        if event_type == "commentary":

            direction = "neutral"
            direction_confidence = 0.20

        elif bullish_count > bearish_count:

            direction = "bullish"

            direction_confidence = min(
                1.0,
                0.45
                + (
                    0.15
                    * (bullish_count - bearish_count)
                ),
            )

        elif bearish_count > bullish_count:

            direction = "bearish"

            direction_confidence = min(
                1.0,
                0.45
                + (
                    0.15
                    * (bearish_count - bullish_count)
                ),
            )

        # -----------------------------------------------------
        # SECTOR UNDERSTANDING V2
        # -----------------------------------------------------

        sector = "general_market"

        if event_type == "monetary_policy":

            sector = "macro_rates"

        elif event_type == "macroeconomic":

            sector = "macro_economy"

        elif event_type == "geopolitical":

            sector = "geopolitical_risk"

        elif any(
            word in text
            for word in [
                "semiconductor",
                "chipmaker",
                "nvidia",
                "amd",
                "intel",
                "micron",
                "qualcomm",
            ]
        ):

            sector = "semiconductors"

        elif any(
            word in text
            for word in [
                "artificial intelligence",
                "data center",
                "gpu",
            ]
        ):

            sector = "artificial_intelligence"

        elif event_type == "commentary":

            sector = "market_commentary"

        # -----------------------------------------------------
        # IMPACT STRENGTH V2
        # -----------------------------------------------------

        impact_strength = 0.15

        if affected_symbols:

            impact_strength += min(
                0.30,
                len(affected_symbols) * 0.10,
            )

        event_impact = {
            "monetary_policy": 0.30,
            "macroeconomic": 0.25,
            "geopolitical": 0.25,
            "earnings": 0.25,
            "corporate_action": 0.18,
            "analyst_action": 0.15,
            "technology": 0.12,
            "commentary": 0.00,
            "general_market": 0.05,
        }

        impact_strength += event_impact.get(
            event_type,
            0.05,
        )

        if direction_confidence >= 0.60:

            impact_strength += 0.05

        # Commentary should not receive artificial high impact.

        if event_type == "commentary":

            impact_strength = min(
                impact_strength,
                0.30,
            )

        impact_strength = max(
            0.0,
            min(1.0, impact_strength),
        )

        # -----------------------------------------------------
        # FIA REASONING
        # -----------------------------------------------------

        reasoning = []

        reasoning.append(
            f"Event type: {event_type}"
        )

        if affected_symbols:

            reasoning.append(
                "Affected tracked symbols: "
                + ", ".join(affected_symbols)
            )

        else:

            reasoning.append(
                "No directly identified tracked symbol"
            )

        reasoning.append(
            f"Market direction: {direction}"
        )

        reasoning.append(
            "Direction confidence: "
            f"{round(direction_confidence, 3)}"
        )

        reasoning.append(
            f"Sector context: {sector}"
        )

        reasoning.append(
            "Estimated impact strength: "
            f"{round(impact_strength, 3)}"
        )

        return {
            "event_type": event_type,
            "direction": direction,
            "direction_confidence": round(
                direction_confidence,
                3,
            ),
            "impact_strength": round(
                impact_strength,
                3,
            ),
            "affected_symbols": affected_symbols,
            "sector": sector,
            "reasoning": reasoning,
        }
    def analyze_news_context_v3(self, article):
        """
        FIA News Context Intelligence Engine V3.

        Adds:
        - Multi-event detection
        - Evidence-based event classification
        - Event confidence scoring

        This function does not replace V2.
        """

        if not isinstance(article, dict):
            return {
                "primary_event": "unknown",
                "events": [],
                "event_conflicts": [],
                "reasoning": ["Invalid article format"],
            }

        import re

        headline = str(
            article.get("headline")
            or article.get("title")
            or ""
        )

        summary = str(
            article.get("summary")
            or article.get("description")
            or ""
        )

        headline_text = headline.lower()
        full_text = (
            headline + " " + summary
        ).lower()

        event_patterns = {
            "monetary_policy": [
                "federal reserve",
                "fed rate",
                "interest rate",
                "rate hike",
                "rate cut",
                "fed chair",
                "powell",
                "central bank",
                "monetary policy",
            ],
            "macroeconomic": [
                "inflation",
                "consumer price index",
                "cpi",
                "jobs report",
                "employment report",
                "payroll",
                "nonfarm",
                "gdp",
                "recession",
                "unemployment",
                "economic growth",
            ],
            "geopolitical": [
                "trade war",
                "sanctions",
                "tariff",
                "military conflict",
                "armed conflict",
                "geopolitical",
            ],
            "commentary": [
                "jim cramer",
                "cramer says",
                "cramer reveals",
                "says investors",
                "investing rule",
                "winning stocks",
                "worth buying",
                "worth holding",
                "stock picks",
                "investment strategy",
                "should investors",
            ],
            "analyst_action": [
                "price target",
                "upgraded to",
                "downgraded to",
                "analyst upgrade",
                "analyst downgrade",
                "buy rating",
                "sell rating",
                "overweight rating",
                "underperform rating",
            ],
            "corporate_action": [
                "acquisition",
                "acquire",
                "merger",
                "buyback",
                "share repurchase",
                "layoffs",
                "chief executive",
                "ceo resigns",
            ],
            "earnings": [
                "quarterly earnings",
                "quarter earnings",
                "earnings report",
                "earnings results",
                "reported earnings",
                "reports earnings",
                "report earnings",
                "earnings",
                "reported revenue",
                "reports revenue",
                "revenue rose",
                "revenue fell",
                "profit rose",
                "profit fell",
                "eps",
                "raises guidance",
                "cuts guidance",
                "beat estimates",
                "missed estimates",
            ],
            "technology": [
                "artificial intelligence",
                "semiconductor",
                "chipmaker",
                "data center",
                "gpu",
            ],
        }

        detected_events = []

        for event_name, patterns in event_patterns.items():

            evidence = []

            headline_matches = [
                pattern
                for pattern in patterns
                if pattern in headline_text
            ]

            text_matches = [
                pattern
                for pattern in patterns
                if pattern in full_text
            ]

            if headline_matches or text_matches:

                for pattern in headline_matches:

                    if pattern not in evidence:
                        evidence.append(pattern)

                for pattern in text_matches:

                    if pattern not in evidence:
                        evidence.append(pattern)

                confidence = 0.35

                confidence += min(
                    0.25,
                    len(evidence) * 0.10,
                )

                if headline_matches:
                    confidence += min(
                        0.25,
                        len(headline_matches) * 0.10,
                    )

                detected_events.append(
                    {
                        "event_type": event_name,
                        "confidence": round(
                            min(1.0, confidence),
                            3,
                        ),
                        "evidence": evidence,
                        "headline_evidence": headline_matches,
                    }
                )

        geopolitical_word_match = bool(
            re.search(
                r"(?<![a-z])war(?![a-z])",
                full_text,
            )
        )

        if geopolitical_word_match:

            existing = next(
                (
                    event
                    for event in detected_events
                    if event["event_type"]
                    == "geopolitical"
                ),
                None,
            )

            if existing:

                if "war" not in existing["evidence"]:
                    existing["evidence"].append("war")

                existing["confidence"] = round(
                    min(
                        1.0,
                        existing["confidence"] + 0.10,
                    ),
                    3,
                )

            else:

                detected_events.append(
                    {
                        "event_type": "geopolitical",
                        "confidence": 0.55,
                        "evidence": ["war"],
                        "headline_evidence": [],
                    }
                )

        if not detected_events:

            detected_events.append(
                {
                    "event_type": "general_market",
                    "confidence": 0.25,
                    "evidence": [],
                    "headline_evidence": [],
                }
            )

        detected_events.sort(
            key=lambda event: event["confidence"],
            reverse=True,
        )

        primary_event = detected_events[0]

        event_conflicts = []

        if len(detected_events) > 1:

            top_confidence = detected_events[0]["confidence"]
            second_confidence = detected_events[1]["confidence"]

            if abs(
                top_confidence - second_confidence
            ) <= 0.10:

                event_conflicts.append(
                    {
                        "type": "close_confidence",
                        "events": [
                            detected_events[0]["event_type"],
                            detected_events[1]["event_type"],
                        ],
                    }
                )

        reasoning = []

        reasoning.append(
            "V3 multi-event analysis completed"
        )

        reasoning.append(
            "Primary event: "
            + primary_event["event_type"]
        )

        reasoning.append(
            "Detected events: "
            + ", ".join(
                event["event_type"]
                for event in detected_events
            )
        )

        return {
            "primary_event": primary_event["event_type"],
            "primary_event_confidence": (
                primary_event["confidence"]
            ),
            "events": detected_events,
            "event_conflicts": event_conflicts,
            "reasoning": reasoning,
        }
    def analyze_news_context_v3_weighted(self, article):
        """
        FIA Context Intelligence V3 Weighted Engine.

        Improvements:
        - Headline evidence receives higher weight
        - Description evidence receives lower weight
        - Event priority resolves close classifications
        - Multi-event conflicts are explicitly detected

        Does not replace V2 or V3 Step 1.
        """

        if not isinstance(article, dict):
            return {
                "primary_event": "unknown",
                "primary_event_confidence": 0.0,
                "events": [],
                "event_conflicts": [],
                "reasoning": ["Invalid article format"],
            }

        import re

        headline = str(
            article.get("headline")
            or article.get("title")
            or ""
        )

        summary = str(
            article.get("summary")
            or article.get("description")
            or ""
        )

        headline_text = headline.lower()
        summary_text = summary.lower()

        event_patterns = {
            "monetary_policy": [
                "federal reserve",
                "fed rate",
                "interest rate",
                "rate hike",
                "rate cut",
                "fed chair",
                "powell",
                "central bank",
                "monetary policy",
            ],
            "macroeconomic": [
                "inflation",
                "consumer price index",
                "cpi",
                "jobs report",
                "employment report",
                "payroll",
                "nonfarm",
                "gdp",
                "recession",
                "unemployment",
                "economic growth",
            ],
            "geopolitical": [
                "trade war",
                "sanctions",
                "tariff",
                "military conflict",
                "armed conflict",
                "geopolitical",
            ],
            "commentary": [
                "jim cramer",
                "cramer says",
                "cramer reveals",
                "says investors",
                "investing rule",
                "winning stocks",
                "worth buying",
                "worth holding",
                "stock picks",
                "investment strategy",
                "should investors",
            ],
            "analyst_action": [
                "price target",
                "upgraded to",
                "downgraded to",
                "analyst upgrade",
                "analyst downgrade",
                "buy rating",
                "sell rating",
                "overweight rating",
                "underperform rating",
            ],
            "corporate_action": [
                "acquisition",
                "acquire",
                "merger",
                "buyback",
                "share repurchase",
                "layoffs",
                "chief executive",
                "ceo resigns",
            ],
            "earnings": [
                "quarterly earnings",
                "quarter earnings",
                "earnings report",
                "earnings results",
                "reported earnings",
                "reports earnings",
                "report earnings",
                "earnings",
                "reported revenue",
                "reports revenue",
                "revenue rose",
                "revenue fell",
                "profit rose",
                "profit fell",
                "eps",
                "raises guidance",
                "cuts guidance",
                "beat estimates",
                "missed estimates",
            ],
            "technology": [
                "artificial intelligence",
                "semiconductor",
                "chipmaker",
                "data center",
                "gpu",
            ],
        }

        event_priority = {
            "monetary_policy": 100,
            "macroeconomic": 90,
            "geopolitical": 85,
            "earnings": 80,
            "corporate_action": 70,
            "analyst_action": 65,
            "technology": 50,
            "commentary": 30,
            "general_market": 10,
        }

        detected_events = []

        for event_name, patterns in event_patterns.items():

            headline_evidence = []
            description_evidence = []

            for pattern in patterns:

                if pattern in headline_text:

                    headline_evidence.append(pattern)

                elif pattern in summary_text:

                    description_evidence.append(pattern)

            if not headline_evidence and not description_evidence:
                continue

            confidence = 0.20

            # Headline evidence is stronger.
            confidence += min(
                0.50,
                len(headline_evidence) * 0.18,
            )

            # Description evidence is supporting evidence.
            confidence += min(
                0.25,
                len(description_evidence) * 0.07,
            )

            # A headline match establishes stronger confidence.
            if headline_evidence:
                confidence += 0.10

            confidence = min(
                1.0,
                confidence,
            )

            detected_events.append(
                {
                    "event_type": event_name,
                    "confidence": round(
                        confidence,
                        3,
                    ),
                    "headline_evidence": headline_evidence,
                    "description_evidence": description_evidence,
                    "priority": event_priority.get(
                        event_name,
                        0,
                    ),
                }
            )

        geopolitical_word_match = bool(
            re.search(
                r"(?<![a-z])war(?![a-z])",
                headline_text,
            )
        )

        if geopolitical_word_match:

            existing = next(
                (
                    event
                    for event in detected_events
                    if event["event_type"]
                    == "geopolitical"
                ),
                None,
            )

            if existing:

                if "war" not in existing["headline_evidence"]:

                    existing[
                        "headline_evidence"
                    ].append("war")

                    existing["confidence"] = round(
                        min(
                            1.0,
                            existing["confidence"] + 0.10,
                        ),
                        3,
                    )

            else:

                detected_events.append(
                    {
                        "event_type": "geopolitical",
                        "confidence": 0.60,
                        "headline_evidence": ["war"],
                        "description_evidence": [],
                        "priority": event_priority[
                            "geopolitical"
                        ],
                    }
                )

        if not detected_events:

            detected_events.append(
                {
                    "event_type": "general_market",
                    "confidence": 0.25,
                    "headline_evidence": [],
                    "description_evidence": [],
                    "priority": event_priority[
                        "general_market"
                    ],
                }
            )

        # -----------------------------------------------------
        # SMART EVENT RANKING
        #
        # Confidence is the primary signal.
        # Priority only resolves close scores.
        # -----------------------------------------------------

        detected_events.sort(
            key=lambda event: (
                event["confidence"],
                event["priority"],
            ),
            reverse=True,
        )

        primary_event = detected_events[0]

        event_conflicts = []

        if len(detected_events) > 1:

            second_event = detected_events[1]

            confidence_gap = abs(
                primary_event["confidence"]
                - second_event["confidence"]
            )

            if confidence_gap <= 0.10:

                event_conflicts.append(
                    {
                        "type": "close_confidence",
                        "primary_event": (
                            primary_event["event_type"]
                        ),
                        "secondary_event": (
                            second_event["event_type"]
                        ),
                        "confidence_gap": round(
                            confidence_gap,
                            3,
                        ),
                    }
                )

        reasoning = []

        reasoning.append(
            "V3 weighted evidence analysis completed"
        )

        reasoning.append(
            "Primary event selected: "
            + primary_event["event_type"]
        )

        reasoning.append(
            "Primary confidence: "
            + str(
                primary_event["confidence"]
            )
        )

        reasoning.append(
            "Headline evidence weighted higher "
            "than description evidence"
        )

        return {
            "primary_event": primary_event[
                "event_type"
            ],
            "primary_event_confidence": (
                primary_event["confidence"]
            ),
            "events": detected_events,
            "event_conflicts": event_conflicts,
            "reasoning": reasoning,
        }
    def resolve_news_event_conflicts_v3(
        self,
        weighted_result,
    ):
        """
        FIA V3 Conflict Resolution Engine.

        Determines whether multiple detected events are:

        - complementary
        - causally related
        - competing
        - independent

        This method does not replace event detection.
        It resolves the output of the V3 Weighted Engine.
        """

        if not isinstance(weighted_result, dict):

            return {
                "primary_event": "unknown",
                "secondary_events": [],
                "event_relationships": [],
                "resolution_status": "invalid",
                "final_confidence": 0.0,
                "reasoning": [
                    "Invalid weighted event result"
                ],
            }

        events = weighted_result.get(
            "events",
            [],
        )

        if not isinstance(events, list):

            events = []

        if not events:

            return {
                "primary_event": "general_market",
                "secondary_events": [],
                "event_relationships": [],
                "resolution_status": "no_events",
                "final_confidence": 0.25,
                "reasoning": [
                    "No events available for resolution"
                ],
            }

        # -----------------------------------------------------
        # EVENT RELATIONSHIP MAP
        # -----------------------------------------------------

        complementary_pairs = {
            frozenset([
                "earnings",
                "technology",
            ]),
            frozenset([
                "corporate_action",
                "technology",
            ]),
            frozenset([
                "analyst_action",
                "earnings",
            ]),
        }

        causal_pairs = {
            frozenset([
                "monetary_policy",
                "macroeconomic",
            ]),
            frozenset([
                "geopolitical",
                "technology",
            ]),
            frozenset([
                "geopolitical",
                "macroeconomic",
            ]),
        }

        independent_pairs = {
            frozenset([
                "commentary",
                "technology",
            ]),
            frozenset([
                "commentary",
                "earnings",
            ]),
            frozenset([
                "commentary",
                "monetary_policy",
            ]),
        }

        # -----------------------------------------------------
        # PRIMARY EVENT
        #
        # Events are already ranked by the weighted engine.
        # -----------------------------------------------------

        primary = events[0]

        primary_name = str(
            primary.get(
                "event_type",
                "general_market",
            )
        )

        primary_confidence = float(
            primary.get(
                "confidence",
                0.0,
            )
        )

        secondary_events = []

        relationships = []

        reasoning = []

        reasoning.append(
            "V3 event conflict resolution started"
        )

        reasoning.append(
            "Initial primary event: "
            + primary_name
        )

        # -----------------------------------------------------
        # ANALYZE SECONDARY EVENTS
        # -----------------------------------------------------

        for event in events[1:]:

            event_name = str(
                event.get(
                    "event_type",
                    "unknown",
                )
            )

            event_confidence = float(
                event.get(
                    "confidence",
                    0.0,
                )
            )

            pair = frozenset([
                primary_name,
                event_name,
            ])

            relationship = "competing"

            if pair in complementary_pairs:

                relationship = "complementary"

            elif pair in causal_pairs:

                relationship = "causal"

            elif pair in independent_pairs:

                relationship = "independent"

            confidence_gap = abs(
                primary_confidence
                - event_confidence
            )

            secondary_events.append(
                {
                    "event_type": event_name,
                    "confidence": round(
                        event_confidence,
                        3,
                    ),
                    "relationship": relationship,
                    "confidence_gap": round(
                        confidence_gap,
                        3,
                    ),
                }
            )

            relationships.append(
                {
                    "primary_event": primary_name,
                    "secondary_event": event_name,
                    "relationship": relationship,
                }
            )

        # -----------------------------------------------------
        # RESOLUTION STATUS
        # -----------------------------------------------------

        competing_events = [

            event

            for event in secondary_events

            if event["relationship"] == "competing"

            and event["confidence_gap"] <= 0.10

        ]

        if competing_events:

            resolution_status = "conflict_detected"

            final_confidence = max(
                0.0,
                primary_confidence - 0.05,
            )

            reasoning.append(
                "Close-confidence competing event detected"
            )

        elif secondary_events:

            resolution_status = "multi_event_resolved"

            final_confidence = primary_confidence

            reasoning.append(
                "Secondary events classified by relationship"
            )

        else:

            resolution_status = "single_event"

            final_confidence = primary_confidence

            reasoning.append(
                "No competing secondary event"
            )

        # -----------------------------------------------------
        # COMPLEMENTARY / CAUSAL CONFIDENCE SUPPORT
        # -----------------------------------------------------

        supporting_events = [

            event

            for event in secondary_events

            if event["relationship"]
            in (
                "complementary",
                "causal",
            )

            and event["confidence"] >= 0.40

        ]

        if supporting_events:

            final_confidence = min(
                1.0,
                final_confidence + 0.03,
            )

            reasoning.append(
                "Related secondary event supports context"
            )

        # -----------------------------------------------------
        # FINAL OUTPUT
        # -----------------------------------------------------

        reasoning.append(
            "Resolution status: "
            + resolution_status
        )

        reasoning.append(
            "Final confidence: "
            + str(
                round(
                    final_confidence,
                    3,
                )
            )
        )

        return {
            "primary_event": primary_name,
            "primary_event_confidence": round(
                primary_confidence,
                3,
            ),
            "secondary_events": secondary_events,
            "event_relationships": relationships,
            "resolution_status": resolution_status,
            "final_confidence": round(
                final_confidence,
                3,
            ),
            "reasoning": reasoning,
        }
    def analyze_news_context_v3_calibrated(self, article):
        """
        FIA V3 Calibrated Context Intelligence.

        Phase 1 improvements:
        - Reduces earnings false positives
        - Protects crypto news from macro false positives
        - Uses weighted V3 evidence as the base engine
        - Adds analyst-action detection
        - Handles low-confidence classifications safely

        This method does not replace existing V2 or V3 methods.
        """

        if not isinstance(article, dict):
            return {
                "primary_event": "unknown",
                "primary_event_confidence": 0.0,
                "events": [],
                "event_conflicts": [],
                "calibration_flags": ["invalid_article"],
                "reasoning": ["Invalid article format"],
            }

        headline = str(
            article.get("headline")
            or article.get("title")
            or ""
        )

        summary = str(
            article.get("summary")
            or article.get("description")
            or ""
        )

        headline_text = headline.lower()
        full_text = (
            headline + " " + summary
        ).lower()

        calibration_flags = []

        # -----------------------------------------------------
        # START WITH EXISTING V3 WEIGHTED ENGINE
        # -----------------------------------------------------

        base_result = (
            self.analyze_news_context_v3_weighted(article)
        )

        events = list(
            base_result.get("events", [])
        )

        # -----------------------------------------------------
        # CRYPTO PROTECTION
        #
        # Prevent words such as "inflation" or "growth" inside
        # crypto-related commentary from automatically becoming
        # a macroeconomic primary event.
        # -----------------------------------------------------

        crypto_patterns = [
            "bitcoin",
            "btc",
            "ethereum",
            "eth",
            "crypto",
            "cryptocurrency",
            "blockchain",
        ]

        is_crypto_article = any(
            pattern in full_text
            for pattern in crypto_patterns
        )

        if is_crypto_article:

            macro_events = [
                event
                for event in events
                if event.get("event_type")
                == "macroeconomic"
            ]

            for event in macro_events:

                event["confidence"] = round(
                    max(
                        0.0,
                        event.get("confidence", 0.0)
                        - 0.20,
                    ),
                    3,
                )

                event["calibration_note"] = (
                    "Macro confidence reduced because "
                    "article is primarily crypto-related"
                )

            calibration_flags.append(
                "crypto_context_protection"
            )

        # -----------------------------------------------------
        # ANALYST ACTION DETECTION
        #
        # Analyst language should not accidentally become
        # earnings classification.
        # -----------------------------------------------------

        analyst_patterns = [
            "price target",
            "upgraded",
            "downgraded",
            "rating upgrade",
            "rating downgrade",
            "buy rating",
            "sell rating",
            "overweight",
            "underweight",
            "outperform",
            "underperform",
            "bullish view",
            "bearish view",
            "reiterates",
            "reiterated",
            "initiated coverage",
            "goldman sachs",
            "morgan stanley",
            "jpmorgan",
            "bank of america",
            "citigroup",
            "mizuho",
        ]

        analyst_matches = [
            pattern
            for pattern in analyst_patterns
            if pattern in full_text
        ]

        if analyst_matches:

            analyst_confidence = min(
                0.90,
                0.45
                + (
                    len(analyst_matches)
                    * 0.10
                ),
            )

            analyst_event = {
                "event_type": "analyst_action",
                "confidence": round(
                    analyst_confidence,
                    3,
                ),
                "priority": 75,
                "headline_evidence": [
                    pattern
                    for pattern in analyst_matches
                    if pattern in headline_text
                ],
                "description_evidence": [
                    pattern
                    for pattern in analyst_matches
                    if pattern not in headline_text
                ],
                "calibration_note": (
                    "Analyst action detected by "
                    "Phase 1 calibration"
                ),
            }

            events = [
                event
                for event in events
                if event.get("event_type")
                != "analyst_action"
            ]

            events.append(
                analyst_event
            )

            # Weak earnings detection should be reduced when
            # the article is clearly analyst-driven.
            for event in events:

                if (
                    event.get("event_type")
                    == "earnings"
                    and not any(
                        keyword in full_text
                        for keyword in [
                            "quarterly earnings",
                            "earnings results",
                            "reported earnings",
                            "reported revenue",
                            "eps",
                            "revenue",
                        ]
                    )
                ):

                    event["confidence"] = round(
                        max(
                            0.0,
                            event.get(
                                "confidence",
                                0.0,
                            )
                            - 0.25,
                        ),
                        3,
                    )

                    event["calibration_note"] = (
                        "Weak earnings signal reduced "
                        "because article is analyst-driven"
                    )

            calibration_flags.append(
                "analyst_action_detection"
            )

        # -----------------------------------------------------
        # REMOVE VERY WEAK EVENTS
        # -----------------------------------------------------

        events = [
            event
            for event in events
            if event.get(
                "confidence",
                0.0,
            ) >= 0.15
        ]

        # -----------------------------------------------------
        # SORT EVENTS
        #
        # Confidence first.
        # Priority breaks close ties.
        # -----------------------------------------------------

        events.sort(
            key=lambda event: (
                event.get(
                    "confidence",
                    0.0,
                ),
                event.get(
                    "priority",
                    0,
                ),
            ),
            reverse=True,
        )

        # -----------------------------------------------------
        # LOW-CONFIDENCE FALLBACK
        # -----------------------------------------------------

        if not events:

            return {
                "primary_event": "general_market",
                "primary_event_confidence": 0.0,
                "events": [],
                "event_conflicts": [],
                "calibration_flags": (
                    calibration_flags
                    + ["no_reliable_event"]
                ),
                "reasoning": [
                    "No reliable calibrated event detected"
                ],
            }

        primary_event = events[0]

        primary_confidence = (
            primary_event.get(
                "confidence",
                0.0,
            )
        )

        if primary_confidence < 0.30:

            calibration_flags.append(
                "low_confidence_primary"
            )

        # -----------------------------------------------------
        # RECALCULATE CLOSE-CONFIDENCE CONFLICTS
        # -----------------------------------------------------

        event_conflicts = []

        if len(events) > 1:

            second_event = events[1]

            confidence_gap = abs(
                primary_event.get(
                    "confidence",
                    0.0,
                )
                - second_event.get(
                    "confidence",
                    0.0,
                )
            )

            if confidence_gap <= 0.10:

                event_conflicts.append(
                    {
                        "type": (
                            "close_confidence"
                        ),
                        "primary_event": (
                            primary_event.get(
                                "event_type"
                            )
                        ),
                        "secondary_event": (
                            second_event.get(
                                "event_type"
                            )
                        ),
                        "confidence_gap": round(
                            confidence_gap,
                            3,
                        ),
                    }
                )

        reasoning = []

        reasoning.append(
            "V3 Phase 1 real-world calibration completed"
        )

        reasoning.append(
            "Primary event: "
            + str(
                primary_event.get(
                    "event_type"
                )
            )
        )

        reasoning.append(
            "Primary confidence: "
            + str(
                round(
                    primary_confidence,
                    3,
                )
            )
        )

        if calibration_flags:

            reasoning.append(
                "Calibration flags: "
                + ", ".join(
                    calibration_flags
                )
            )

        return {
            "primary_event": (
                primary_event.get(
                    "event_type"
                )
            ),
            "primary_event_confidence": round(
                primary_confidence,
                3,
            ),
            "events": events,
            "event_conflicts": event_conflicts,
            "calibration_flags": (
                calibration_flags
            ),
            "reasoning": reasoning,
        }
    def analyze_nasdaq_relevance_v3(
        self,
        article,
        context_result=None,
    ):
        """
        FIA V3 Nasdaq Relevance Intelligence.

        Determines how relevant a news article is to:

        - Nasdaq
        - QQQ
        - Nasdaq mega-cap stocks
        - Technology sectors

        This method does not replace V2 or V3 engines.
        """

        if not isinstance(article, dict):
            return {
                "nasdaq_relevance_score": 0.0,
                "relevance_level": "low_relevance",
                "impact_scope": "unknown",
                "direct_symbols": [],
                "reasoning": [
                    "Invalid article format"
                ],
            }

        headline = str(
            article.get("headline")
            or article.get("title")
            or ""
        )

        summary = str(
            article.get("summary")
            or article.get("description")
            or ""
        )

        text = (
            headline + " " + summary
        ).lower()

        if context_result is None:
            context_result = (
                self.analyze_news_context_v3_calibrated(
                    article
                )
            )

        if not isinstance(context_result, dict):
            context_result = {}

        primary_event = context_result.get(
            "primary_event",
            "general_market",
        )

        primary_confidence = float(
            context_result.get(
                "primary_event_confidence",
                0.0,
            )
            or 0.0
        )

        # -----------------------------------------------------
        # NASDAQ MEGA-CAP SYMBOL DETECTION
        # -----------------------------------------------------

        import re

        nasdaq_companies = {

            "NVDA": [
                "nvda",
                "nvidia",
            ],

            "MSFT": [
                "msft",
                "microsoft",
            ],

            "AAPL": [
                "aapl",
                "apple",
            ],

            "AMZN": [
                "amzn",
                "amazon",
            ],

            "META": [
                "meta",
                "facebook",
            ],

            "GOOGL": [
                "googl",
                "google",
                "alphabet",
            ],

            "AVGO": [
                "avgo",
                "broadcom",
            ],

            "TSLA": [
                "tsla",
                "tesla",
            ],

            "AMD": [
                "amd",
                "advanced micro devices",
            ],

            "NFLX": [
                "nflx",
                "netflix",
            ],

            "INTC": [
                "intc",
                "intel",
            ],

            "MU": [
                "mu",
                "micron",
            ],

            "QCOM": [
                "qcom",
                "qualcomm",
            ],

            "SMCI": [
                "smci",
                "super micro",
                "supermicro",
            ],

        }

        def safe_match(alias):

            alias = alias.lower().strip()

            return bool(
                re.search(
                    r"(?<![a-z0-9])"
                    + re.escape(alias)
                    + r"(?![a-z0-9])",
                    text,
                )
            )

        direct_symbols = []

        for symbol, aliases in (
            nasdaq_companies.items()
        ):

            if any(
                safe_match(alias)
                for alias in aliases
            ):
                direct_symbols.append(symbol)

        # -----------------------------------------------------
        # SECTOR RELEVANCE
        # -----------------------------------------------------

        semiconductor_words = [

            "semiconductor",
            "chipmaker",
            "chip",
            "nvidia",
            "amd",
            "intel",
            "micron",
            "qualcomm",
            "broadcom",

        ]

        ai_words = [

            "artificial intelligence",
            "data center",
            "gpu",
            "generative ai",

        ]

        big_tech_words = [

            "technology stocks",
            "tech stocks",
            "big tech",
            "nasdaq",
            "qqq",

        ]

        semiconductor_match = any(
            word in text
            for word in semiconductor_words
        )

        ai_match = any(
            word in text
            for word in ai_words
        )

        big_tech_match = any(
            word in text
            for word in big_tech_words
        )

        # -----------------------------------------------------
        # RELEVANCE SCORING
        # -----------------------------------------------------

        relevance_score = 0.05

        if direct_symbols:

            relevance_score += min(
                0.55,
                len(direct_symbols) * 0.20,
            )

        if semiconductor_match:

            relevance_score += 0.18

        if ai_match:

            relevance_score += 0.15

        if big_tech_match:

            relevance_score += 0.20

        # -----------------------------------------------------
        # EVENT RELEVANCE
        # -----------------------------------------------------

        event_relevance = {

            "monetary_policy": 0.25,

            "macroeconomic": 0.20,

            "earnings": 0.20,

            "technology": 0.15,

            "analyst_action": 0.12,

            "corporate_action": 0.10,

            "geopolitical": 0.08,

            "general_market": 0.05,

        }

        relevance_score += event_relevance.get(
            primary_event,
            0.05,
        )

        # -----------------------------------------------------
        # CONFIDENCE WEIGHTING
        # -----------------------------------------------------

        if primary_confidence >= 0.60:

            relevance_score += 0.05

        elif primary_confidence < 0.30:

            relevance_score -= 0.05

        # -----------------------------------------------------
        # NASDAQ MONETARY POLICY CALIBRATION
        # -----------------------------------------------------

        monetary_text = text.lower()

        strong_monetary_terms = [
            "rate cut",
            "rate hike",
            "interest rates",
            "interest rate decision",
            "fed cuts",
            "fed raises",
            "fomc decision",
            "federal reserve cuts",
            "federal reserve raises",
        ]

        guidance_monetary_terms = [
            "signals possible rate cut",
            "signals possible interest rate cut",
            "signals possible rate hike",
            "signals possible interest rate hike",
            "signals a rate cut",
            "signals a rate hike",
            "policy outlook",
            "rate outlook",
            "fed signals",
            "possible rate cut",
            "possible interest rate cut",
            "possible rate hike",
            "possible interest rate hike",
        ]

        strong_monetary_match = any(
            term in monetary_text
            for term in strong_monetary_terms
        )

        guidance_monetary_match = any(
            term in monetary_text
            for term in guidance_monetary_terms
        )

        if primary_event == "monetary_policy":

            # Guidance must be checked first because phrases such as
            # "possible rate cut" also contain "rate cut".

            if guidance_monetary_match:

                relevance_score += 0.20

            elif strong_monetary_match:

                relevance_score += 0.35

        # -----------------------------------------------------
        # IRRELEVANT CONTEXT PENALTY
        # -----------------------------------------------------

        irrelevant_words = [

            "bitcoin",
            "cryptocurrency",
            "ethereum",

        ]

        crypto_only = (

            any(
                word in text
                for word in irrelevant_words
            )

            and not direct_symbols

            and not semiconductor_match

            and not ai_match

            and not big_tech_match

        )

        if crypto_only:

            relevance_score = min(
                relevance_score,
                0.15,
            )

        relevance_score = max(
            0.0,
            min(
                1.0,
                relevance_score,
            ),
        )

        # -----------------------------------------------------
        # -----------------------------------------------------

        # -----------------------------------------------------
        # NASDAQ MACRO INTELLIGENCE CALIBRATION V3
        # -----------------------------------------------------

        macro_text = text.lower()

        inflation_terms = [
            "inflation",
            "consumer prices",
            "cpi",
            "core cpi",
            "price index",
            "pce",
            "core pce",
        ]

        jobs_terms = [
            "jobs report",
            "employment growth",
            "nonfarm payroll",
            "nonfarm payrolls",
            "payrolls",
            "unemployment rate",
            "labor market",
            "jobless claims",
        ]

        gdp_terms = [
            "gdp",
            "gross domestic product",
            "economic growth",
            "economic contraction",
        ]

        yield_terms = [
            "treasury yield",
            "treasury yields",
            "bond yield",
            "bond yields",
            "10-year yield",
            "10 year yield",
            "2-year yield",
            "2 year yield",
        ]

        recession_terms = [
            "recession",
            "economic slowdown",
            "economic contraction",
            "growth slowdown",
        ]

        inflation_match = any(
            term in macro_text
            for term in inflation_terms
        )

        jobs_match = any(
            term in macro_text
            for term in jobs_terms
        )

        gdp_match = any(
            term in macro_text
            for term in gdp_terms
        )

        yield_match = any(
            term in macro_text
            for term in yield_terms
        )

        recession_match = any(
            term in macro_text
            for term in recession_terms
        )

        # Macro events are particularly relevant to Nasdaq
        # when there is no direct company-specific context.

        if (
            primary_event == "macroeconomic"
            and not direct_symbols
        ):

            if inflation_match:
                relevance_score += 0.15

            elif jobs_match:
                relevance_score += 0.15

            elif gdp_match:
                relevance_score += 0.10

            elif recession_match:
                relevance_score += 0.12

        # Treasury yields materially affect growth
        # and technology stock valuations.

        if (
            yield_match
            and not direct_symbols
        ):
            relevance_score = max(
                relevance_score,
                0.40,
            )

        # Clamp score again because macro calibration
        # happens after the earlier score normalization.

        relevance_score = max(
            0.0,
            min(
                1.0,
                relevance_score,
            ),
        )

        # -----------------------------------------------------

        # DIRECT NASDAQ COMPANY PRIORITY CALIBRATION
        # -----------------------------------------------------

        high_impact_company_events = [

            "earnings",

            "analyst_action",

            "corporate_action",

        ]

        if (

            direct_symbols

            and primary_event in high_impact_company_events

            and not crypto_only

        ):

            relevance_score = max(

                relevance_score,

                0.70,

            )

                # RELEVANCE LEVEL
        # -----------------------------------------------------

        if relevance_score >= 0.70:

            relevance_level = "high_relevance"

        elif relevance_score >= 0.35:

            relevance_level = "medium_relevance"

        else:

            relevance_level = "low_relevance"

        # -----------------------------------------------------
        # IMPACT SCOPE
        # -----------------------------------------------------

        if direct_symbols:

            impact_scope = "direct_nasdaq_company"

        elif (
            semiconductor_match
            or ai_match
            or big_tech_match
        ):

            impact_scope = "nasdaq_sector"

        elif (

            primary_event in [

                "monetary_policy",

                "macroeconomic",

            ]

            or yield_match

        ):

            impact_scope = "market_wide"

        else:

            impact_scope = "indirect_or_low"

        # -----------------------------------------------------
        # REASONING
        # -----------------------------------------------------

        reasoning = []

        reasoning.append(
            "Nasdaq relevance analysis completed"
        )

        reasoning.append(
            "Primary event: "
            + str(primary_event)
        )

        reasoning.append(
            "Direct Nasdaq symbols: "
            + (
                ", ".join(direct_symbols)
                if direct_symbols
                else "None"
            )
        )

        reasoning.append(
            "Impact scope: "
            + impact_scope
        )

        if crypto_only:

            reasoning.append(
                "Crypto-only context penalty applied"
            )

        reasoning.append(
            "Nasdaq relevance score: "
            + str(
                round(
                    relevance_score,
                    3,
                )
            )
        )

        return {

            "nasdaq_relevance_score": round(
                relevance_score,
                3,
            ),

            "relevance_level": relevance_level,

            "impact_scope": impact_scope,

            "direct_symbols": direct_symbols,

            "primary_event": primary_event,

            "primary_event_confidence": round(
                primary_confidence,
                3,
            ),

            "reasoning": reasoning,

        }
    async def get_period_liquidity(self, symbol: str = "QQQ"):
        """
        Builds:
          monthly_high
          monthly_low
          weekly_high
          weekly_low
          daily_high
          daily_low

        Uses daily candles so the values are actual market
        highs/lows rather than quote-only approximations.
        """

        now_ny = self.now_ny()

        # Get enough daily history to cover:
        # current month + previous days/weeks.
        start_ny = now_ny - timedelta(days=45)

        candles = await self.finnhub_candles(
            symbol,
            "D",
            self.datetime_to_ts(start_ny),
            self.datetime_to_ts(now_ny),
        )

        if not candles:
            return {}

        if candles.get("s") != "ok":
            return {}

        timestamps = candles.get("t", [])
        highs = candles.get("h", [])
        lows = candles.get("l", [])

        if not timestamps or not highs or not lows:
            return {}

        rows = []

        for ts, high, low in zip(timestamps, highs, lows):
            try:
                dt = datetime.fromtimestamp(
                    int(ts),
                    tz=timezone.utc,
                )

                high_value = float(high)
                low_value = float(low)

                rows.append(
                    {
                        "datetime": dt,
                        "date": dt.date(),
                        "high": high_value,
                        "low": low_value,
                    }
                )

            except (TypeError, ValueError, OverflowError):
                continue

        if not rows:
            return {}

        current_date = now_ny.date()

        # -----------------------------------------------------
        # Daily
        # -----------------------------------------------------

        daily_rows = [
            row
            for row in rows
            if row["date"] == current_date
        ]

        # If the current trading date has no daily candle yet,
        # use the latest available trading day.
        if not daily_rows:
            latest_date = max(row["date"] for row in rows)

            daily_rows = [
                row
                for row in rows
                if row["date"] == latest_date
            ]

        # -----------------------------------------------------
        # Weekly
        # -----------------------------------------------------

        current_week_start = (
            current_date
            - timedelta(days=current_date.weekday())
        )

        weekly_rows = [
            row
            for row in rows
            if current_week_start
            <= row["date"]
            <= current_date
        ]

        if not weekly_rows:
            latest_date = max(row["date"] for row in rows)

            latest_week_start = (
                latest_date
                - timedelta(days=latest_date.weekday())
            )

            weekly_rows = [
                row
                for row in rows
                if latest_week_start
                <= row["date"]
                <= latest_date
            ]

        # -----------------------------------------------------
        # Monthly
        # -----------------------------------------------------

        current_year = current_date.year
        current_month = current_date.month

        monthly_rows = [
            row
            for row in rows
            if row["date"].year == current_year
            and row["date"].month == current_month
        ]

        if not monthly_rows:
            latest_date = max(row["date"] for row in rows)

            monthly_rows = [
                row
                for row in rows
                if row["date"].year == latest_date.year
                and row["date"].month == latest_date.month
            ]

        result = {}

        if daily_rows:
            result["daily_high"] = max(
                row["high"] for row in daily_rows
            )
            result["daily_low"] = min(
                row["low"] for row in daily_rows
            )

        if weekly_rows:
            result["weekly_high"] = max(
                row["high"] for row in weekly_rows
            )
            result["weekly_low"] = min(
                row["low"] for row in weekly_rows
            )

        if monthly_rows:
            result["monthly_high"] = max(
                row["high"] for row in monthly_rows
            )
            result["monthly_low"] = min(
                row["low"] for row in monthly_rows
            )

        return result
    @classmethod
    def session_window_for_date(
        cls,
        session: str,
        date_value,
    ):
        """
        Session definitions matching the Pine Script defaults.

        Timezone: GMT+0 / UTC

        ASIA / TOKYO:
            0000 -> 0900

        LONDON:
            0800 -> 1700

        NEW YORK:
            1300 -> 2200
        """

        from datetime import timezone

        session_tz = timezone.utc

        if session == "ASIA":
            start = datetime(
                date_value.year,
                date_value.month,
                date_value.day,
                0,
                0,
                tzinfo=session_tz,
            )
            end = datetime(
                date_value.year,
                date_value.month,
                date_value.day,
                9,
                0,
                tzinfo=session_tz,
            )

        elif session == "LONDON":
            start = datetime(
                date_value.year,
                date_value.month,
                date_value.day,
                8,
                0,
                tzinfo=session_tz,
            )
            end = datetime(
                date_value.year,
                date_value.month,
                date_value.day,
                17,
                0,
                tzinfo=session_tz,
            )

        elif session == "NEW_YORK":
            start = datetime(
                date_value.year,
                date_value.month,
                date_value.day,
                13,
                0,
                tzinfo=session_tz,
            )
            end = datetime(
                date_value.year,
                date_value.month,
                date_value.day,
                22,
                0,
                tzinfo=session_tz,
            )

        else:
            return None, None

        return start, end
    async def get_session_liquidity(self, symbol: str = "NQ=F"):
        """
        Calculates Asia, London, and New York session liquidity
        using real NQ futures (NQ=F) 5-minute candles from yfinance.

        All session filtering is performed in America/New_York time.
        """

        def load_nq_data():
            ticker = yf.Ticker("NQ=F")
            return ticker.history(
                period="5d",
                interval="5m",
                auto_adjust=False,
            )

        data = await asyncio.to_thread(load_nq_data)

        if data is None or data.empty:
            print("NQ=F yfinance returned no session candles.")
            return {}

        try:
            if data.index.tz is None:
                data.index = data.index.tz_localize(self.NY_TZ)
            else:
                data.index = data.index.tz_convert(self.NY_TZ)
        except Exception as exc:
            print(f"NQ=F timezone conversion failed: {exc}")
            return {}

        result = {}

        now_ny = self.now_ny()
        current_date = now_ny.date()

        for days_back in range(0, 5):
            target_date = current_date - timedelta(days=days_back)

            # Asia session:
            # 20:00 previous calendar day -> 09:00 target day NY time
            asia_start = datetime(
                target_date.year,
                target_date.month,
                target_date.day,
                20,
                0,
                tzinfo=self.NY_TZ,
            ) - timedelta(days=1)

            asia_end = datetime(
                target_date.year,
                target_date.month,
                target_date.day,
                9,
                0,
                tzinfo=self.NY_TZ,
            )

            # London:
            # 08:00 -> 17:00 NY time
            london_start = datetime(
                target_date.year,
                target_date.month,
                target_date.day,
                8,
                0,
                tzinfo=self.NY_TZ,
            )

            london_end = datetime(
                target_date.year,
                target_date.month,
                target_date.day,
                17,
                0,
                tzinfo=self.NY_TZ,
            )

            # New York:
            # 13:00 -> 22:00 NY time
            new_york_start = datetime(
                target_date.year,
                target_date.month,
                target_date.day,
                13,
                0,
                tzinfo=self.NY_TZ,
            )

            new_york_end = datetime(
                target_date.year,
                target_date.month,
                target_date.day,
                22,
                0,
                tzinfo=self.NY_TZ,
            )

            sessions = {
                "asia": (asia_start, asia_end),
                "london": (london_start, london_end),
                "new_york": (new_york_start, new_york_end),
            }

            for name, (session_start, session_end) in sessions.items():

                session_data = data[
                    (data.index >= session_start)
                    & (data.index < session_end)
                ]

                if session_data.empty:
                    continue

                high_key = f"{name}_high"
                low_key = f"{name}_low"

                if high_key not in result:
                    result[high_key] = float(
                        session_data["High"].max()
                    )

                if low_key not in result:
                    result[low_key] = float(
                        session_data["Low"].min()
                    )

            required = {
                "asia_high",
                "asia_low",
                "london_high",
                "london_low",
                "new_york_high",
                "new_york_low",
            }

            if required.issubset(result.keys()):
                break

        print("NQ=F SESSION LIQUIDITY:", result)

        return result
    async def get_nq_session_liquidity_yahoo(self):
        """
        Legacy compatibility endpoint for NQ=F session liquidity.

        SOL56_SESSION_TRUTH_V1:
        - uses the same America/New_York session definitions as the canonical
          zero-cost NQ liquidity engine;
        - handles the overnight Asia window correctly;
        - respects minutes and DST through timezone-aware datetimes;
        - returns the latest *completed* session rather than aggregating seven
          days of same-clock bars into one artificial high/low.
        """
        import time
        from .nq_liquidity_truth import _parse_yahoo, latest_completed_sessions

        ticker = "NQ=F"
        end_ts = int(time.time())
        start_ts = end_ts - (7 * 24 * 60 * 60)

        data = await self.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/NQ=F",
            {
                "period1": start_ts,
                "period2": end_ts,
                "interval": "5m",
                "includePrePost": "true",
            },
            timeout=15,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
            },
        )
        if not data:
            return None

        try:
            parsed = _parse_yahoo(data)
            rows = parsed.get("rows") or []
            if not rows:
                return None
            session_state = latest_completed_sessions(rows)
            output = {
                key: value
                for key, value in (session_state.get("levels") or {}).items()
                if value is not None
            }
            output["nq_futures_price"] = parsed.get("current_price")
            output["nq_futures_symbol"] = ticker
            output["nq_liquidity_evidence"] = "yahoo_real_data"
            output["session_origin"] = session_state.get("origin") or {}
            output["session_status"] = session_state.get("status") or {}
            output["session_timezone"] = "America/New_York"
            return output
        except Exception as e:
            print("Yahoo NQ liquidity error:", e)
            return None
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

        ticker = "NQ=F"

        candles = await self.get_nq_session_liquidity_yahoo()

        if not candles:
            return {
                "nq_liquidity_evidence": "missing",
                "nq_futures_symbol": ticker,
            }

        if candles.get("nq_liquidity_evidence") == "yahoo_real_data":
            return candles

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
    async def liquidity(self, symbol: str = "QQQ"):
        """
        Fetches all liquidity components in parallel.
        """

        period_task = self.get_period_liquidity(symbol)
        session_task = self.get_session_liquidity(symbol)

        period_data, session_data = await asyncio.gather(
            period_task,
            session_task,
            return_exceptions=True,
        )

        if isinstance(period_data, Exception):
            print(
                f"Period liquidity error -> {period_data}"
            )
            period_data = {}

        if isinstance(session_data, Exception):
            print(
                f"Session liquidity error -> {session_data}"
            )
            session_data = {}

        result = {}

        result.update(period_data or {})
        result.update(session_data or {})

        return result

    # ---- snapshot() MODEL phases -------------------------------------
    # Extracted from snapshot(), which mixed all three identities in one
    # 797-line body. These are the parts that can move a forecast: the
    # aggregates that become engine signals and the news scoring that
    # produces data['news']. Bodies are verbatim; only their home changed.
    def _snapshot_mega_cap(self, data, quotes):
        """MODEL: weighted mega-cap leadership aggregate."""
        mega_cap_weights = {
            "NVDA": 0.14,
            "MSFT": 0.10,
            "AAPL": 0.09,
            "AMZN": 0.08,
            "META": 0.07,
            "AVGO": 0.06,
            "GOOGL": 0.06,
            "GOOG": 0.04,
            "TSLA": 0.04,
            "NFLX": 0.03,
        }

        mega_total = 0.0
        mega_weight = 0.0
        mega_details = {}

        for symbol, weight in mega_cap_weights.items():
            quote = quotes.get(symbol)

            if not quote:
                continue

            signal = self.normalize_change(
                quote.get("dp")
            )

            if signal is None:
                continue

            mega_total += signal * weight
            mega_weight += weight

            mega_details[symbol] = {
                "change_percent": quote.get("dp"),
                "signal": round(signal, 4),
                "weight": weight,
            }

        if mega_weight > 0:
            data["mega_cap"] = max(
                -1.0,
                min(
                    1.0,
                    mega_total / mega_weight,
                ),
            )

        data["mega_cap_details"] = mega_details
    def _snapshot_semiconductors(self, data, quotes):
        """MODEL: semiconductor complex aggregate."""
        semiconductor_symbols = [
            "NVDA",
            "AVGO",
            "AMD",
            "MU",
            "INTC",
            "QCOM",
            "SMCI",
        ]

        semi_values = []

        for symbol in semiconductor_symbols:
            quote = quotes.get(symbol)

            if not quote:
                continue

            signal = self.normalize_change(
                quote.get("dp")
            )

            if signal is not None:
                semi_values.append(signal)

        if semi_values:
            data["semis"] = (
                sum(semi_values)
                / len(semi_values)
            )
    def _snapshot_participation(self, data, quotes, symbols):
        """MODEL: equal-weight participation across the non-index symbols."""
        breadth_symbols = symbols[2:]

        breadth_values = []

        for symbol in breadth_symbols:
            quote = quotes.get(symbol)

            if not quote:
                continue

            signal = self.normalize_change(
                quote.get("dp")
            )

            if signal is not None:
                breadth_values.append(signal)

        data["equal_weight_participation_definition"] = {
            "label": "Equal-weight participation",
            "is_market_breadth": False,
            "measures": ("equal-weighted mean normalised daily change of the tracked "
                         "single-name large-cap basket"),
            "constituents": list(breadth_symbols),
            "constituent_count": len(breadth_symbols),
            "shares_constituents_with": ["Semiconductors", "Mega-cap leadership"],
            "note": ("NOT an advance/decline line and NOT a wide-universe breadth "
                     "measure. Legacy key 'breadth' is retained for backward "
                     "compatibility only."),
        }

        if breadth_values:
            data["breadth"] = (
                sum(breadth_values)
                / len(breadth_values)
            )
    async def _snapshot_macro_rates(self, data):
        """MODEL: FRED-derived macro transforms (fed funds, US10Y, DXY proxy)."""
        if self.keys["FRED_API_KEY"]:

            macro_results = await asyncio.gather(
                self.fred_series("DFF"),
                self.fred_series("DGS10"),
                return_exceptions=True,
            )

            fed_data = macro_results[0]
            us10y_data = macro_results[1]

            if isinstance(fed_data, Exception):
                fed_data = None

            if isinstance(us10y_data, Exception):
                us10y_data = None

            # -------------------------------------------------
            # Federal funds rate
            # -------------------------------------------------

            if fed_data:
                observations = fed_data.get(
                    "observations",
                    [],
                )

                if observations:
                    latest = observations[0].get(
                        "value"
                    )

                    try:
                        latest = float(latest)

                        data["fed_funds_rate"] = latest

                        # DFF is not DXY. We preserve the
                        # existing project's macro proxy logic.
                        data["dxy"] = (
                            self.normalize_yield(latest)
                        )

                    except (TypeError, ValueError):
                        pass

            # -------------------------------------------------
            # US 10Y
            # -------------------------------------------------

            if us10y_data:
                observations = us10y_data.get(
                    "observations",
                    [],
                )

                if observations:
                    latest = observations[0].get(
                        "value"
                    )

                    try:
                        latest = float(latest)

                        data["us10y_value"] = latest

                        if latest < 4.0:
                            data["us10y"] = 0.35

                        elif latest < 4.5:
                            data["us10y"] = 0.0

                        else:
                            data["us10y"] = -0.5

                    except (TypeError, ValueError):
                        pass
    async def _snapshot_news_intelligence(self, data):
        """MODEL: news scoring; this block produces data['news']."""
        data["news"] = None
        data["news_articles"] = 0
        data["news_scored_articles"] = 0
        data["news_status"] = "missing"
        data["news_provider_selected"] = None

        try:
            news_packet = await self.live_news_articles()
            articles = list(news_packet.get("articles") or [])
            data["news_articles"] = len(articles)
            data["news_provider_selected"] = news_packet.get("selected_provider")
            data["news_provider_candidate_counts"] = news_packet.get("candidate_counts") or {}
            data["news_provider_candidate_newest_age_seconds"] = (
                news_packet.get("candidate_newest_age_seconds") or {}
            )

            positive_words = [
                "beat", "growth", "bullish", "surge", "strong",
                "upgrade", "record", "profit", "rally", "outperform",
            ]
            negative_words = [
                "miss", "fall", "bearish", "drop", "weak",
                "downgrade", "loss", "risk", "selloff", "decline",
            ]

            sentiment_values = []
            for article in articles:
                text = " ".join([
                    str(article.get("title", "")),
                    str(article.get("description", "")),
                ]).lower()
                positive = sum(1 for word in positive_words if word in text)
                negative = sum(1 for word in negative_words if word in text)
                if positive == 0 and negative == 0:
                    continue
                sentiment_values.append((positive - negative) / max(1, positive + negative))

            data["news_scored_articles"] = len(sentiment_values)

            _pub_ages = []
            _now_utc = datetime.now(timezone.utc)
            for _a in articles:
                _age = self._news_article_age_seconds(_a, _now_utc)
                if _age is None:
                    continue
                # Future-dated rows were already excluded by live_news_articles;
                # retain a defensive check here so freshness can never be negative.
                if _age < -60.0:
                    continue
                _pub_ages.append(max(0.0, _age))

            if _pub_ages:
                _newest = min(_pub_ages)
                data["news_newest_article_age_seconds"] = round(_newest, 1)
                data["news_median_article_age_seconds"] = round(sorted(_pub_ages)[len(_pub_ages) // 2], 1)
                data["news_oldest_article_age_seconds"] = round(max(_pub_ages), 1)
                data["news_articles_with_timestamp"] = len(_pub_ages)
                data["news_age_basis"] = "NEWEST_SELECTED_PROVIDER_PUBLICATION_TIME"
                data["news_observed_at"] = (_now_utc - timedelta(seconds=_newest)).isoformat()
                data["news_future_dated_articles"] = 0
            else:
                data["news_newest_article_age_seconds"] = None
                data["news_articles_with_timestamp"] = 0
                data["news_age_basis"] = "NO_VALID_PUBLICATION_TIMESTAMPS_AVAILABLE"
                data["news_future_dated_articles"] = 0

            if sentiment_values:
                data["news"] = max(-1.0, min(1.0, sum(sentiment_values) / len(sentiment_values)))
                data["news_status"] = "live_scored"
            elif articles:
                data["news_status"] = "live_unscored"
            elif data.get("news_provider_selected"):
                data["news_status"] = "live_empty"
            else:
                data["news_status"] = "missing"

        except Exception as exc:
            data["news_status"] = "error"
            print(f"News intelligence error -> {type(exc).__name__}")
