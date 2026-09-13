# DPCSE V2.3 — SHADOW/BETA kernel

Status: **STARTED, NOT ARMED, N=0**.

This package implements the frozen V2.3 protocol/gating kernel without touching BASE_FIA production logic. It is intentionally outside `backend/fia/`, so the candidate cannot silently enter the BASE scientific identity.

Implemented: frozen constants/spec fingerprint; exact 30-row environment arm and integer alarm; `WARMUP / VALID / SHIFT_DETECTED / STALE`; binary 8H contract and three hard gates; zero-alpha bookkeeping; all-row paired Brier diagnostics including NO_EDGE rows; N=0 preregistration seal builder; fail-closed candidate slot.

Not implemented by design: no invented predictive-state features or Direct-8H coefficients; no V6 mutation/reseal/backfill; no BASE promotion; no 4H promotion; no sequential e-process, transition generator, first-passage or committor.

Next scientific step: audit/select and freeze the actual minimal predictive-state schema plus Direct-8H candidate model artifact. Only then may the shadow campaign be armed before its first prospective checkpoint.
