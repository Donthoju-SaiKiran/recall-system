# recallsim: synthetic recall traceability data and recall simulator

Built for the YottaFlex AI Technologies Round 3 challenge. A seeded generator for a food manufacturer's
supply chain (suppliers, raw lots, production, finished lots, shipments, deliveries) plus a recall
engine that traces contaminated lots downstream, simulates the recall actions, plants four labelled
anomalies, and validates the result.

## Quick start

Python 3.11 or newer. The generator uses only the standard library. pytest is needed for the tests.

```
pip install -r requirements-dev.txt
python -m pytest -q                                   # run the tests
python -m recallsim generate --scale full --out out   # full dataset, seed 20261022
python -m recallsim generate --scale starter --out out_small
python -m recallsim verify --scale full               # two separate processes, compare SHA-256 of every file
python -m recallsim docs                              # regenerate sql/schema.sql and the data dictionary
```

`generate` writes CSV, JSON and a SQLite seed file, the schema and data dictionary, a manifest with a
SHA-256 for every file, the validation summaries, recall metrics, and the separate ground truth. The
README written next to the data lists the exact row counts.

## What is committed

- `data/starter/`: the 5% dataset, so you can open real files without running anything.
- `data/full_manifest.json`: the manifest of the full run (seed 20261022). Regenerate the full dataset
  and compare the checksums to prove reproducibility.

## How it is built

| Phase | Module | Purpose |
|---|---|---|
| 0 | `schema.py`, `ddl.py`, `dictionary.py` | One schema file drives the SQL DDL, the data dictionary and the validator |
| 1 | `generate/master.py` | Suppliers, customers, products, versioned BOMs |
| 2 | `generate/production.py` | Raw lots, work orders, first-expiry-first-out consumption, finished lots |
| 3 | `generate/distribution.py` | Deliveries and shipments, including a FAILED delivery path |
| 4 | `recall.py` | Downstream trace (BFS plus a SQL recursive query as a cross-check), recall case and action simulation |
| 5 | `inject.py` | Four rule-based anomalies and the separate ground truth |
| 6 | `validate.py`, `metrics.py`, `score.py` | 18 validation checks, three recall metrics, detection scoring |
| 7 | `export.py`, `pipeline.py`, `__main__.py` | Export, manifest, README, reproducibility check, CLI |

Design rules: each stage has its own seeded random stream, so one stage can change without shifting
the others. Quantities reconcile by construction (mass balance, delivered never above produced).
Status and totals are derived from source records. Ground truth is computed before anomalies are
planted and is never read by the generator, engine or validator (a test enforces this).

## Documentation

- `docs/DATA_DICTIONARY.md`: every table and column, with rules and cardinality
- `docs/AI_USAGE.md`: how AI was used, what was reviewed and verified
- `docs/AI_PROMPT_HISTORY.md`: the prompts sent
- `docs/problem_statement.txt`: the challenge brief

## Known limitations

- Supplier country is not linked to the origin of the materials.
- Very few deliveries are IN_TRANSIT, because every finished lot is older than a week at the as-of date.
- Recall blast radii are small and most cases close; recovered units are well below 100%.
- No warehouse table, only a warehouse code on each shipment.
- A recall on a finished lot traces downstream only: sibling lots from the same work order are not included.
- This is a test set for a validator with documented rules, not a blind benchmark: the action ID gaps left by anomaly A3 are visible, and `csv_clean/` ships next to `csv/`.
- Checksums were verified on Python 3.13 only; other Python versions may change the random stream.
