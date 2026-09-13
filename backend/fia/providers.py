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

"""CLEAR NASDAQ — ProviderHub facade over the three-way split.

WHY THE FACADE EXISTS
providers.py was 6427 lines mixing three identities: code that can change the
forecast (MODEL), code that decides what counts as evidence (PROTOCOL), and
transport (INFRASTRUCTURE). The split map recorded that mixture; this is it
applied. Callers are unaffected: `from fia.providers import ProviderHub` and
every method on it behave exactly as before, because the methods were MOVED,
not rewritten, and ProviderHub still composes all of them.

The MRO order below is deliberate and the three mixins share no method names,
so composition cannot silently shadow anything.
"""

from .providers_model import ModelMixin
from .providers_protocol import ProtocolMixin
from .providers_infrastructure import InfrastructureMixin


class ProviderHub(ModelMixin, ProtocolMixin, InfrastructureMixin):
    """
    Central provider layer for CLEAR NASDAQ FIA.

    Providers:
      - Finnhub: market quotes, candles, earnings
      - FRED: rates / macro
      - NewsAPI: news sentiment

    Liquidity:
      - Monthly high / low
      - Weekly high / low
      - Daily high / low
      - Asia high / low
      - London high / low
      - New York high / low
    """

    NY_TZ = ZoneInfo("America/New_York")
    UTC = timezone.utc

    # Small cache prevents /snapshot and /forecast from seeing
    # different provider states when called seconds apart.
    SNAPSHOT_CACHE_SECONDS = 8
