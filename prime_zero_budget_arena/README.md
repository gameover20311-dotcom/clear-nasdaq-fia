# PRIME ZERO-BUDGET ARENA V1

Purpose: harden Prime before any paid Astra final-boss benchmark.

## Frozen rules

- Default network mode is OFF.
- No paid OpenAI/Astra API path exists in this arena.
- External providers are blocked unless `ZERO_BUDGET_NETWORK_ENABLED=1` and the provider is explicitly listed in `ZERO_BUDGET_PROVIDER_ALLOWLIST`.
- Provider free-tier billing is never assumed by the arena. It reports `billing_independently_verified=false`.
- Same-provider Draft -> Attack A -> Attack B -> Judge calls are marked `DEPENDENCE_NOT_EXCLUDABLE`.
- Benchmark wins are scoped to the tested pack only. `WORLD_NUMBER_ONE=NOT_TESTED`.
- Existing CLEAR NASDAQ production/main, BASE_FIA, Forward-OOS, and predictive logic are not touched.

## Zero-cost paths

1. Manual/UI path: fetch `/tasks`, ask any free model UI, then POST answers to `/evaluate`.
2. Local Ollama path: configure `OLLAMA_BASE_URL` and allowlist `ollama`.
3. Free-tier API path: Groq or Gemini adapters exist, but must remain disabled until the user's account is confirmed to be zero-cost for the intended calls.

## Prime loop

For each task the same provider is used as a substrate for:

1. Draft
2. Attack A against the draft
3. Attack B against Attack A
4. Pessimistic final judge

This measures the Prime reasoning architecture; it does not pretend repeated same-lineage calls are independent evidence.

## Endpoints

- `GET /` status and claim limits
- `GET /health` hostile self-test
- `GET /providers` provider/configuration status
- `GET /tasks` public benchmark without answer keys
- `POST /evaluate` zero-cost scoring of manual answers
- `POST /run/<provider>` guarded network execution; disabled by default

## Current scientific claim

`PRIME_CAN_BE_HARDENED_ZERO_BUDGET = SUPPORTED_BY_ARCHITECTURE`

`PRIME_GT_ASTRA = NOT_TESTED`

`WORLD_NUMBER_ONE = NOT_TESTED`
