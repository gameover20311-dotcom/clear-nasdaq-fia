"""SRB V1.1 shadow integration boundary.

This package does not vendor or recreate SRB. It only admits the exact verified
SRB_V1_1_FINAL payload after hash verification.
"""

from .adapter import verify_payload, assert_shadow_ready

__all__ = ["verify_payload", "assert_shadow_ready"]
