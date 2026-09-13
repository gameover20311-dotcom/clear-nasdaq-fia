"""Provider-neutral NQ market-depth/MBO ingestion boundary.

Research/data infrastructure only. No order execution, no trading authority.
A source may be labelled TRUE_MBO only after its capabilities prove preserved
individual order identity plus sequencing and order lifecycle semantics.
"""

from .types import FeedCapability, EventAction, Side, MBOEvent, SourceCapabilities
from .validation import MBOValidationError, validate_event, validate_capability_claim
from .provider import MarketDataAdapter, AdapterHealth
from .rithmic import RithmicAdapter, RithmicAdapterStatus, RithmicConnectionSpec
from .integrity import IntegrityStatus, IntegrityResult, SequenceContract, StreamIntegrityGate

__all__ = [
    "FeedCapability", "EventAction", "Side", "MBOEvent", "SourceCapabilities",
    "MBOValidationError", "validate_event", "validate_capability_claim",
    "MarketDataAdapter", "AdapterHealth", "RithmicAdapter", "RithmicAdapterStatus",
    "RithmicConnectionSpec", "IntegrityStatus", "IntegrityResult",
    "SequenceContract", "StreamIntegrityGate",
]
