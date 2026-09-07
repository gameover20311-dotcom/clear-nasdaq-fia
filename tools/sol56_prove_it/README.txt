CLEAR NASDAQ — SOL 5.6 PROVE IT
================================

INSTALL:
Run installer from project root:
    python3 SOL56_INSTALL_CLEAR_NASDAQ.py

RUN AFTER INSTALL:
    python3 run_sol56_prove_it.py

WHAT IT DOES:
- Audits final A-to-Z report if present
- Auto-discovers historical prediction CSVs
- Uses chronological development / untouched holdout split
- Searches candidate policy on development only
- Evaluates holdout only after candidate is locked
- Refuses fake WORLD #1 / 90-95% claims
- Writes SOL56_PROVE_IT_RESULT.json in project root

SAFE BY DESIGN:
- no .env edits
- no broker execution
- no production weight changes
- no fabricated paid/licensed data
- no hidden losing rows
