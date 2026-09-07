# Benchmark data

`cases.jsonl`
- locked FIA evidence cases
- do not edit a captured case after creating teacher/local outputs
- `outcome_direction` stays null until a genuine future horizon resolves

`sol_reference.jsonl`
- manually paste GPT-5.6 Sol reference JSON
- each row must include `case_id`

`local_outputs.jsonl`
- gpt-oss FIA Brain outputs
- each row must include `case_id`

IMPORTANT:
Teacher similarity answers "does local behavior resemble the reference?"
Market outcome Brier answers "which forecast was better on genuinely future-resolved cases?"
Never merge those two questions.
