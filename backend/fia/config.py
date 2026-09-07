from dataclasses import dataclass
import os
from dotenv import load_dotenv
load_dotenv()

@dataclass(frozen=True)
class Config:
    horizon_hours: int = 8
    refresh_seconds: int = 30
    live_required: bool = True
    fred_key: str = os.getenv('FRED_API_KEY','')
    alpha_key: str = os.getenv('ALPHAVANTAGE_API_KEY','')
    finnhub_key: str = os.getenv('FINNHUB_API_KEY','')
    polygon_key: str = os.getenv('POLYGON_API_KEY','')
    news_key: str = os.getenv('NEWS_API_KEY','')

MEGA_CAP_WEIGHTS = {
    'NVDA': .14, 'MSFT': .10, 'AAPL': .09, 'AMZN': .08, 'META': .07,
    'AVGO': .06, 'GOOGL': .06, 'GOOG': .04, 'TSLA': .04, 'NFLX': .03,
}
SECTOR_WEIGHTS = {'semis': .24, 'mega_cap': .40, 'software': .18, 'other': .18}
