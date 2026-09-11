"""SIMONS Shadow Lab V1: isolated, read-only research tooling for CLEAR NASDAQ FIA."""

from .lab import (
    LAB_SCHEMA_VERSION,
    CandidateSpec,
    ShadowLab,
    canonical_bytes,
    sha256_file,
)

__all__ = [
    "LAB_SCHEMA_VERSION",
    "CandidateSpec",
    "ShadowLab",
    "canonical_bytes",
    "sha256_file",
]

__version__ = "1.0.0"
