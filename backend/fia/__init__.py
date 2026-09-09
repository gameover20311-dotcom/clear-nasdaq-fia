# CLEAR NASDAQ FIA package bootstrap.
# Installs the staged live market-truth enrichment without performing network I/O.
from .live_market_truth import install as _install_live_market_truth

_install_live_market_truth()
