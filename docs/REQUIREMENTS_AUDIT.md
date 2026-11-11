# Requirements audit

Every requirement from the problem statement (`docs/problem_statement.txt`) and from the YottaFlex
submission guidelines and FAQ, with where it is met and how to check it. Status is MET, PARTIAL or NOT MET.
Nothing is marked MET without a command or file you can run or open.

Run everything: `python -m pytest -q` (124 tests) and `python -m recallsim verify --scale full`.

## A. YottaFlex submission guidelines and FAQ

| Requirement | Where / evidence | Status |
|---|---|---|
| 01 Working executable code, steps to install, configure, run, verify | `README.md` quick start; fresh clone run, see section D | MET once pushed |
| 02 Public GitHub repo, evolution visible, meaningful commits | 8 commits, one per phase, `git log`; remote currently holds Phases 0 and 1 only | NOT MET until the candidate pushes all commits |
| 03 Prompt history with all prompts to every AI tool | `docs/AI_PROMPT_HISTORY.md` (P1 to the latest). P1 is only summarised until the master prompt is pasted into `docs/prompts/00_master_instruction.md` | PARTIAL, candidate action |
| 03 Where AI accelerated, relied heavily, what I reviewed, changed, validated | `docs/AI_USAGE.md` has the AI side filled; the "Reviewed by me", "Modified by me" cells are blank on purpose | PARTIAL, candidate action |
| 04 Problem, assumptions, decisions, trade-offs, testing approach, limitations, how I know it works | `CLAUDE.md` fixed facts and decisions, `docs/DATA_DICTIONARY.md`, `README.md` limitations, this file, 124 tests | MET (a short `docs/DECISIONS.md` would help the interview, optional) |
| FAQ 1 deadline: 72 h from the time YottaFlex sent the project | Send time not recorded in the repo. Commit timestamps: 2026-11-11 18:50 to 19:30 UTC, `git log --date=iso` | UNKNOWN, candidate must check against the email time |
| FAQ 3 new dedicated public repo, link sent from recruitment email | `Donthoju-SaiKiran/recall-system` | Candidate action |
| FAQ 4 code, prompt history, supporting artifacts in an identifiable directory | `docs/`, `docs/prompts/`, `data/` | MET |
| FAQ 7 individual work, understand core logic | Interview drill (Phase 8) | Candidate action |
| FAQ 9 setup/run instructions, show how core behaviour was verified | `README.md`, tests, `verify`, `validation/` and `metrics/` outputs | MET |
| FAQ 10 no imported solution, standard dependencies only | stdlib only, pytest for tests, no copied code | MET |
| FAQ 11 assumptions and limitations stated | `README.md` "Known limitations", section C below | MET |
| FAQ 12 no secrets, credentials, personal data | History and tree scanned, section E | MET |

## B. Problem statement requirements

| Requirement | Where / evidence | Status |
|---|---|---|
| Trace through suppliers, production, warehouses, customers | `recall.py` `trace_scope`; raw lot, work order, finished lot, delivery, customer, shipment (warehouse is a code on the shipment) | PARTIAL: no warehouse table |
| Simulate recall scope and completion | `generate_recalls`, `metrics.py`; `tests/test_recall.py` | MET |
| Expose key decisions and exceptions | `ground_truth/`, `validation/`, `metrics/`, `CLAUDE.md` decisions | MET |
| At least one exception path | FAILED deliveries, CANCELLED work orders and shipments, recall non-responders (3%), unused raw lot recall; `test_status_rules` | MET |
| Meaningful evaluation metrics | scope precision/recall, completion, time to notify; `tests/test_validate.py` metric tests | MET |
| Workflow 1: master data first | `schema.py` `TABLES` parent-first order, `test_foreign_keys_point_to_real_columns_and_parents_come_first` | MET |
| Workflow 2: dependents use valid parent IDs | `test_all_tables_load_and_fk_clean`, `test_loads_into_sqlite_and_fk_clean`, validator FK check | MET |
| Workflow 3: lots, consumption, finished lots, shipments, deliveries, triggers, traversal, notifications, quarantine, recovered qty | `generate/*.py`, `recall.py`; `test_mass_balance_per_job_and_material`, `test_delivered_never_exceeds_produced_per_lot`, `tests/test_recall.py` | MET |
| Workflow 4: state changes as explicit events, history not overwritten | `recall_action` append-only, status derived (`test_case_status_matches_derivation`); BOM versions by effective date (`test_bom_versions_do_not_overlap`) | MET |
| Workflow 5: outcomes and labels from documented rules | `inject.py` RULES, answer key from engine trace on clean data; `test_only_intended_rows_changed` | MET |
| 12 entities, PK on each, FK for relationships, cardinality, optional relationships, effective dates, lifecycle | `schema.py`, `docs/DATA_DICTIONARY.md` (cardinality and lifecycle per table); `tests/test_schema.py` | MET |
| Bridge tables for N:M, validate joins | `wo_input_lot`, `delivery`; validator FK and polymorphic checks | MET |
| Anomalies labelled, not silent corruption | `ground_truth/ground_truth.csv`, `test_only_intended_rows_changed` | MET |
| ID formats, zero-padded, immutable, consistent | `test_id_format_examples`, `test_raw_lot_id_embeds_its_supplier`, validator ID_FORMAT | MET |
| Step 1 data dictionary: type, required, allowed, units, uniqueness, rule | `docs/DATA_DICTIONARY.md`, `test_dictionary_mentions_every_column` | MET |
| Step 4 volumes 500 / 10,000 / 5,000 / 8,000 / 20,000 | `test_exact_counts_full` in master, production, distribution tests; `data/full_manifest.json` | MET |
| Step 4 hidden labels on contaminated lots, fixed seed, parameterised scale | `ground_truth/recall_answer_key.json`, `config.py` SEED and `--scale` | MET |
| Step 5 four anomalies | A1 to A4 in `inject.py`; `test_a1_orphans`, `test_a2_over_delivery`, `test_a3_missed_customer`, `test_a4_recalled_still_available` | MET |
| Step 6 derived values from source | `test_status_rules`, sale_status from scope, case status from actions, on-hand from ledger | MET |
| Step 7 separate ground_truth.csv/json, never leaked | `write_ground_truth`; `test_nothing_reads_ground_truth_or_injector`, `test_ground_truth_kept_apart` | MET |
| Step 8 validation: PK, FK, enums, dates, arithmetic, lifecycle, duplicates | `validate.py` 18 checks, one test each (`test_every_check_has_a_test`) | MET |
| Step 9 CSV, JSON, SQL, README, dictionary, command, seed, manifest, validation summary | `export.py`; `test_exact_file_set`, `test_manifest_checksums_match_files` | MET |
| Step 10 regenerate twice, compare counts and checksums | `python -m recallsim verify`; `test_reproducible_across_processes_full` | MET |
| Acceptance: genealogy complete | `test_bfs_equals_sql_cte_for_every_case`, `test_scope_matches_independent_manual_join` | MET |
| Acceptance: quantities reconcile | production and distribution reconciliation tests, validator ARITH checks | MET |
| Acceptance: recall scope matches planted lots | `answer_key` vs engine, `scope_metrics` is 1.0 on clean data | MET |
| Acceptance: actions track affected quantity and disposition | `test_quarantine_qty_equals_on_hand`, `test_recovered_never_exceeds_delivered` | MET |
| Evaluation (a) realistic distributions | `test_distribution_shapes`, `test_distribution_near_targets`, `test_materials_and_lot_sizes_are_varied`. Shapes are chosen by me, not fitted to real data | PARTIAL by nature |
| Evaluation (e) normal, boundary, failure, exception coverage | FAILED deliveries, non-responders, unused-lot recall, 4 anomalies. Only 5 IN_TRANSIT deliveries | PARTIAL |
| Evaluation (g) lawful provenance | `manifest.json` provenance: no external data, no personal data | MET |

## C. Known limitations and deviations (stated, not hidden)

- No warehouse table, only `shipment.warehouse_code`.
- Supplier country is not linked to material origin.
- Only 5 deliveries are IN_TRANSIT because every finished lot is older than a week at the as-of date.
- Recall blast radii are small (largest: 30 deliveries) and 13 of 15 cases close, so completion looks tidy.
  Recovered units are 54.7% of notified units.
- Added `finished_lot.sale_status` and the `wo_input_lot` bridge, which are not in the brief's entity list.
- The planted anomalies are fixed in number (5 per type at full scale) by a rule, not drawn at random.
- `data/starter/` is committed, the full dataset is not (42 MB); the full manifest is committed and checked by a test.

## D. Fresh-clone test

Clone, install, run only the README commands, compare with the committed manifest. Result recorded at the end
of Phase 8 in the commit message and in the reply.

## E. Hygiene scans (tree and history)

- Secrets and key patterns: none found.
- Email addresses: only the candidate's public commit email (in `CLAUDE.md` and the prompt history).
- Phone numbers: none. Commit authors: one identity, `Donthoju SaiKiran`, on all commits.
- Junk files (`__pycache__`, `.db`, `.sqlite`) tracked: none.
- Em dashes: none in repo text, apart from the original `docs/problem_statement.txt`, kept verbatim.
