# Project context for Claude Code (read this first)

## Who and what
Candidate is doing the YottaFlex AI Technologies Round 3 recruitment challenge. Hard limit: **48 hours** (candidate's own plan, official window is 72h from the time YottaFlex sent the project, candidate must confirm exact deadline). Output must be a **public GitHub repo** with working code, meaningful commits, honest AI usage docs, prompt history, tests or verification evidence, setup instructions.
Problem statement: `docs/problem_statement.txt` (recall traceability synthetic data generator and simulator).

## Working agreement (follow strictly)
- You are mentor + builder. **Explain before building**, every phase: first in simple words (analogy), then the same thing in technical terms so the candidate can say it in an interview.
- Wait for the candidate to say go before building each phase. Phase flow: explain, candidate confirms, build, run tests, show real results, interview questions, next.
- Never claim anything works without running it. Distinguish tests written, executed, passed. Do not fabricate results.
- Replies terse. No em dashes in any content or drafted text. No filler.
- Challenge poor decisions. No fake praise.
- Keep `docs/AI_USAGE.md` and `docs/AI_PROMPT_HISTORY.md` current. Never invent history or claim the candidate did something they did not.
- Commits: one per logical milestone, authored as Donthoju Sai Kiran <donthojusaikiran@gmail.com> (set in repo git config). No fake or backdated history. Do not add secrets. Public repo, safe sample data only.

## Stack (approved)
Python 3.11+, stdlib only for the generator (csv, json, sqlite3, hashlib, random), pytest for tests. SQLite for FK enforcement and recursive-CTE trace cross-check. No pandas, no numpy.

## Fixed facts
- Seed `20261022`. Scales: FULL = 500 suppliers, 1500 customers, 40 products, 10000 raw lots, 5000 work orders, 8000 finished lots, 12000 shipments, 20000 deliveries. STARTER = 5% (products min 10).
- 12 tables: supplier, customer, product, bom_line, material_lot, production_order, wo_input_lot (bridge, added), finished_lot, shipment, delivery, recall_case, recall_action. Generation order = order in `recallsim/schema.py` `TABLES`.
- IDs: S0001, RAWLOT-S0001-2026-000001, P001, BOM-000001, WO-2026-000001, FINLOT-2026-000001, SHP-2026-000001, C00001, DEL-2026-000001, REC-2026-000001, ACT-2026-000001. Global counters.
- Units: raw kg, finished packs. Dates ISO text.
- Delivery is the bridge finished_lot x shipment x customer (no separate shipment_line). No Warehouse table (`warehouse_code` field on shipment).
- Recall status is derived from `recall_action` rows (append-only). `trigger_lot_id` and `target_id` are polymorphic, checked by validator, not DB FKs.
- "Recalled stock still for sale" = finished lot in recall scope with on-hand (qty_produced minus delivered) greater than 0 and no QUARANTINE action.
- Each stage uses its own RNG: `stage_rng(seed, "stage.name")`.

## Done so far (all tests executed and passing: 43 passed)
- Phase 0: `recallsim/schema.py`, `ddl.py`, `dictionary.py`, `sql/schema.sql`, `docs/DATA_DICTIONARY.md`, `tests/test_schema.py`. Regenerate docs: `python -m recallsim docs`.
- Phase 1: `config.py`, `rng.py`, `ids.py`, `db.py`, `generate/master.py`, `tests/test_master.py`. Full scale output: 500 / 1500 / 40 / 217 BOM lines, 9 products with two recipe versions.
- Phase 2: `generate/production.py`, `tests/test_production.py`, `AS_OF = 2026-11-01` in config. Full scale output: 10000 raw lots, 5000 WOs (4500 completed, 200 cancelled, 200 in progress, 100 planned), 28048 wo_input_lot rows, 8000 finished lots, 1977 unused raw lots (19.8%), zero shortages, runs in about 2 s. Design: demand-driven supply (factor 1.25), FEFO with running balance in integer grams, loss 1 to 4 percent, only COMPLETED jobs consume or produce.
- Known gap (honest): supplier country is weighted but not linked to material origin. Optional P3.
- Git: repo initialised, 2 commits (Phase 0, Phase 1), authored as Donthoju Sai Kiran. Remote: https://github.com/Donthoju-SaiKiran/recall-system.git (push done by the candidate, Claude had no push access). Not done: README, all later phases.

## Next phases
2. DONE (see above). Original draft design kept for reference:
   - Raw lots: dates across 2026, supplier weighted by tier, received_date >= supplier onboarded_date, 1 to 3 materials per supplier (derived, no table), qty about 500 to 5000 kg, expiry by material.
   - Work orders: product weighted to ACTIVE, status mostly COMPLETED, few IN_PROGRESS and CANCELLED (cancelled consume nothing). Use BOM version effective on start_date.
   - Consume from raw lots of the right material received before start date, track remaining balance per lot, split across lots when needed (this creates the N:M rows). Decide produced packs, then consume required kg with a small loss factor. Never exceed lot balance.
   - Completed WOs yield 1 to 3 finished lots, tune so total is about 8000 at full scale.
3. Shipments and deliveries (delivered never exceeds produced, delivery_date >= ship_date >= produced_date).
4. Recall engine: BFS downstream plus SQL recursive CTE cross-check, RecallCase and RecallAction events, notify, quarantine, recover, completion simulation.
5. Anomaly injection (4 required) plus separate `ground_truth` files, never read by generator or recall engine.
6. Validator (PK, FK, enum, dates, arithmetic, lifecycle, duplicates) plus 3 metrics (scope precision and recall, completion %, time to notify).
7. Export CSV/JSON/SQL, manifest with SHA-256, README, reproducibility check (run twice same seed same checksums), validation summary.
8. Final audit, fresh-clone test, interview drill (ask questions one at a time, honest evaluation).

## Commands
```
python -m pytest -q
python -m recallsim docs
```
