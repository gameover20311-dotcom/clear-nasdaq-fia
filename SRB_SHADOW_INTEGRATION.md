# SRB V1.1 Shadow Integration

## Status

This branch stages the project-side integration boundary for the exact internally verified `SRB_V1_1_FINAL` artifact.

The verified SRB implementation itself is **not reconstructed from reports, hashes, or the manifest**. The exact final ZIP/source bytes must be supplied and must match the pinned hashes before shadow execution can become ready.

Current mode: `SHADOW_RESEARCH_ONLY`.

## Hard boundaries

- no BASE_FIA modification
- no Forward-OOS modification
- no forecast probability/direction/confidence influence
- no production deployment authority
- no predictive-edge claim
- no superintelligence claim
- SRB code stays outside `backend/` scientific fingerprint scope
- payload mismatch or absence fails closed

## Pinned identity

- Source generator SHA256: `e1303368e18c8b408c01866ff361fbecafb2fc83b480b496d949652684f2e61e`
- Final manifest SHA256: `d95420913c5a3401c40abf1c5da6e59451baab3f36727735ea5ada4263c00982`
- Final ZIP SHA256: `08045c3a630f50656d47f42021b27036e4250e77488e2e0df2a4d2129371474d`
- Independent-audit handoff ZIP SHA256: `5f3317efc40782959d6c8cf0d38960454c46cbc99c4776ee278de85833d6546f`

## Admission sequence

1. Exact verified final payload is placed under `research/srb_shadow/vendor/`.
2. `adapter.verify_payload()` must return `shadow_ready=true` only after exact SHA-256 equality.
3. SRB's own extracted hostile regression/mutation/repro checks are rerun from the vendored payload.
4. Existing CLEAR NASDAQ protected-artifact and scientific-identity checks are rerun.
5. Only then may SRB be exposed to the existing Shadow/Research lab as a non-authoritative reasoning candidate.
6. Production use remains separately prohibited until independent audit and an explicit later promotion decision.

## Current integration truth

This staging branch is **not allowed to claim `SRB_SHADOW_READY=true` until exact package bytes are present and verified**.
