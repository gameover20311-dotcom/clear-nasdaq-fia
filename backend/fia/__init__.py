# CLEAR NASDAQ FIA package bootstrap.
# Install transport/data-truth hardening without performing network I/O.
from .provider_guard import install as _install_provider_guard
from .live_market_truth import install as _install_live_market_truth
from .official_macro_fallback import install as _install_official_macro_fallback

_install_provider_guard()
_install_live_market_truth()
_install_official_macro_fallback()
