from dataclasses import dataclass
from typing import Optional, Dict


@dataclass
class LiquidityLevel:
    name: str
    timeframe: str
    price: Optional[float]
    status: str
    side: str
    distance_pct: Optional[float] = None
    detail: str = ""


def _distance_pct(current_price: Optional[float], level: Optional[float]):
    if current_price is None or level is None or current_price == 0:
        return None
    return round(abs(level - current_price) / current_price * 100, 3)


def build_liquidity_map(data: dict) -> Dict[str, LiquidityLevel]:
    current = data.get("current_price")

    levels = {
        "monthly_high": LiquidityLevel(
            "Monthly High",
            "MONTHLY",
            data.get("monthly_high"),
            "UNTAPPED",
            "HIGH",
            _distance_pct(current, data.get("monthly_high")),
        ),
        "monthly_low": LiquidityLevel(
            "Monthly Low",
            "MONTHLY",
            data.get("monthly_low"),
            "UNTAPPED",
            "LOW",
            _distance_pct(current, data.get("monthly_low")),
        ),
        "weekly_high": LiquidityLevel(
            "Weekly High",
            "WEEKLY",
            data.get("weekly_high"),
            "UNTAPPED",
            "HIGH",
            _distance_pct(current, data.get("weekly_high")),
        ),
        "weekly_low": LiquidityLevel(
            "Weekly Low",
            "WEEKLY",
            data.get("weekly_low"),
            "UNTAPPED",
            "LOW",
            _distance_pct(current, data.get("weekly_low")),
        ),
        "daily_high": LiquidityLevel(
            "Daily High",
            "DAILY",
            data.get("daily_high"),
            "UNTAPPED",
            "HIGH",
            _distance_pct(current, data.get("daily_high")),
        ),
        "daily_low": LiquidityLevel(
            "Daily Low",
            "DAILY",
            data.get("daily_low"),
            "UNTAPPED",
            "LOW",
            _distance_pct(current, data.get("daily_low")),
        ),
        "asia_high": LiquidityLevel(
            "Asia High",
            "ASIA",
            data.get("asia_high"),
            "UNTAPPED",
            "HIGH",
            _distance_pct(current, data.get("asia_high")),
        ),
        "asia_low": LiquidityLevel(
            "Asia Low",
            "ASIA",
            data.get("asia_low"),
            "UNTAPPED",
            "LOW",
            _distance_pct(current, data.get("asia_low")),
        ),
        "london_high": LiquidityLevel(
            "London High",
            "LONDON",
            data.get("london_high"),
            "UNTAPPED",
            "HIGH",
            _distance_pct(current, data.get("london_high")),
        ),
        "london_low": LiquidityLevel(
            "London Low",
            "LONDON",
            data.get("london_low"),
            "UNTAPPED",
            "LOW",
            _distance_pct(current, data.get("london_low")),
        ),
        "new_york_high": LiquidityLevel(
            "New York High",
            "NEW_YORK",
            data.get("new_york_high"),
            "UNTAPPED",
            "HIGH",
            _distance_pct(current, data.get("new_york_high")),
        ),
        "new_york_low": LiquidityLevel(
            "New York Low",
            "NEW_YORK",
            data.get("new_york_low"),
            "UNTAPPED",
            "LOW",
            _distance_pct(current, data.get("new_york_low")),
        ),
    }

    return levels
