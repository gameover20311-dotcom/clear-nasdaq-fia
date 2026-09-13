# CLEAR NASDAQ — CANONICAL SIGNAL IDENTITY
#
# WHY THIS MODULE EXISTS
# ----------------------
# The equal-weighted participation signal was originally named "Breadth". That
# name was provably misleading: the value is the equal-weighted mean change of
# the 15 tracked large caps, NOT market breadth and NOT an advance/decline line.
# It was therefore renamed to "Equal-weight participation".
#
# PROVENANCE OF THAT RENAME:
#   ORIGIN_PRE_REPOSITORY / EXACT_DIVERGENCE_UNRECOVERABLE
# The rename is already present in the first commit of this repository
# (6b05d0b "Initial CLEAR NASDAQ cloud backup"). No commit in version control
# performs it, and no model-version note or seal record documents it. The exact
# divergence point happened before the repository existed and cannot be
# recovered. That fact is recorded, not invented around.
#
# THE DEFECT THIS MODULE REPAIRS
# ------------------------------
# The rename was applied to fia/engine.py (adapter label and EVIDENCE_QUALITY)
# and aliased in fia/premove_watch.py, but was NOT propagated to four other live
# consumers, which continued to look up the legacy key "Breadth":
#
#   fia/premove_engine.py     LEADING_SIGNAL_NAMES, CRITICAL_SIGNALS
#   fia/phase34_engine.py     state['breadth'] lookup
#   fia/premove_max_engine.py core_names analog vector
#   fia/phase33_analogs.py    CORE analog vector
#
# Measured consequences on a fully healthy fixture (data_coverage == 1.0):
#   - premove _data_guard reported critical_missing == ['Breadth'] permanently,
#     tripping the abstention guard one signal earlier than designed;
#   - usable leading weight was 0.72 instead of the intended 0.80;
#   - phase34 state['breadth'] was permanently None;
#   - phase33 analog vectors placed LIVE observations at 0.0 on the
#     participation axis while HISTORICAL rows carried their real value
#     (e.g. -0.5997), i.e. live queries and the analog database were in
#     different coordinate spaces.
#
# The author of premove_watch.py had already written down this exact risk:
#   "The internal signal NAME is a stable lookup key used by weights,
#    calibration, analogy and research modules; renaming it would silently
#    change weight lookups in ten modules."
#
# WHAT THIS MODULE DOES — AND DELIBERATELY DOES NOT DO
# ----------------------------------------------------
# DOES:  provide ONE canonical name per signal and translate legacy names at
#        every read boundary, so historical rows written as "Breadth" and live
#        rows written as "Equal-weight participation" land on the SAME
#        coordinate.
# DOES:  make double counting structurally impossible — canonicalisation
#        collapses both spellings into exactly one entry.
#
# DOES NOT: change any numeric weight, probability mathematics, source
#           eligibility, checkpoint timing or outcome semantics. The weight
#           vector is unchanged and still sums to exactly 1.0. Historical
#           datasets are never rewritten; translation happens only on read.
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

# The truthful canonical name. This is the name the live engine emits.
CANONICAL_EQUAL_WEIGHT_PARTICIPATION = "Equal-weight participation"

# Legacy spelling -> canonical spelling. Read boundaries translate through this.
# Historical files on disk keep whatever they were written with; nothing is
# rewritten.
LEGACY_SIGNAL_ALIASES: Dict[str, str] = {
    "Breadth": CANONICAL_EQUAL_WEIGHT_PARTICIPATION,
}

# Every spelling that must resolve to the same underlying 0.08 signal.
EQUAL_WEIGHT_PARTICIPATION_SPELLINGS: Tuple[str, ...] = (
    CANONICAL_EQUAL_WEIGHT_PARTICIPATION,
    "Breadth",
)


def canonical_signal_name(name: Any) -> str:
    """Translate one signal name to its canonical spelling.

    Unknown names pass through unchanged, so this is safe to apply blanketly at
    a read boundary without enumerating every signal.
    """
    text = str(name if name is not None else "").strip()
    return LEGACY_SIGNAL_ALIASES.get(text, text)


def canonical_name_list(names: Iterable[Any]) -> List[str]:
    """Canonicalise an ordered list of names and drop duplicates.

    Order of first appearance is preserved. If a caller's list contained both
    "Breadth" and "Equal-weight participation", the result contains the
    canonical name exactly ONCE, so a fixed-length feature vector built from
    this list can never allocate two axes to the same underlying signal.
    """
    seen = set()
    out: List[str] = []
    for raw in names:
        canon = canonical_signal_name(raw)
        if canon in seen:
            continue
        seen.add(canon)
        out.append(canon)
    return out


def canonicalize_signal_keys(mapping: Any) -> Dict[str, Any]:
    """Rekey a {signal_name: value} mapping onto canonical names.

    Collapsing is what makes double counting impossible: both spellings map to
    one key, so no consumer can sum, average or vector-encode the same signal
    twice.

    Collision policy is deterministic and never raises, because this sits on the
    live forecast path and must not convert a data quirk into an outage:
    a value already stored under the canonical name wins over a value stored
    under a legacy alias. Use `alias_collisions` to detect and report the case.
    """
    if not isinstance(mapping, dict):
        return {}
    out: Dict[str, Any] = {}
    # Pass 1: canonical-named entries take precedence.
    for key, value in mapping.items():
        if canonical_signal_name(key) == str(key).strip():
            out[str(key).strip()] = value
    # Pass 2: legacy aliases fill in only where the canonical key is absent.
    for key, value in mapping.items():
        canon = canonical_signal_name(key)
        if canon not in out:
            out[canon] = value
    return out


def alias_collisions(mapping: Any) -> List[str]:
    """Canonical names that were supplied under more than one spelling."""
    if not isinstance(mapping, dict):
        return []
    counts: Dict[str, int] = {}
    for key in mapping:
        canon = canonical_signal_name(key)
        counts[canon] = counts.get(canon, 0) + 1
    return sorted(name for name, n in counts.items() if n > 1)


def is_equal_weight_participation(name: Any) -> bool:
    """True for any spelling of the equal-weighted participation signal."""
    return canonical_signal_name(name) == CANONICAL_EQUAL_WEIGHT_PARTICIPATION
