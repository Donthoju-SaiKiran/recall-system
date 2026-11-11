# AI usage record

Tool used so far: Claude (chat session, then Claude Code). Sessions continue in Claude Code inside Antigravity IDE.

Columns marked **YOU FILL** must be completed honestly by the candidate. They are left blank on purpose, AI cannot know what you personally reviewed.

| # | Date | Tool | Purpose | AI generated or suggested | Reviewed by me | Modified by me | How validated |
|---|---|---|---|---|---|---|---|
| 1 | 2026-11-11 | Claude (chat) | Read problem, requirements, stack, architecture, phases, 48h plan | Requirement table, stack choice (Python, SQLite, pytest), 12-table design, phase plan | YOU FILL | YOU FILL | Discussed and approved in chat |
| 2 | 2026-11-11 | Claude (chat) | Phase 0: schema, DDL generator, data dictionary generator, schema tests | `recallsim/schema.py`, `ddl.py`, `dictionary.py`, `__main__.py`, `tests/test_schema.py` | YOU FILL | YOU FILL | `pytest`: 10 passed (executed in the AI session) |
| 3 | 2026-11-12 | Claude (chat) | Phase 1: seed, RNG, ID factory, DB helper, master data generators, tests | `config.py`, `rng.py`, `ids.py`, `db.py`, `generate/master.py`, `tests/test_master.py` | YOU FILL | YOU FILL | `pytest`: 24 passed total (executed in the AI session), distribution preview printed |
| 4 | 2026-11-12 | Claude (chat) | Handoff notes for continuing in Claude Code | `CLAUDE.md`, this file, prompt history file | YOU FILL | YOU FILL | n/a |
| 5 | 2026-11-12 | Claude (chat) | Phase 2: raw lots, work orders, FEFO consumption, finished lots, tests | `generate/production.py`, `tests/test_production.py`, `AS_OF` in `config.py` | YOU FILL | YOU FILL | `pytest`: 43 passed total (executed in the AI session), output statistics printed |

## Where AI accelerated work
Design, boilerplate, code generation, test writing, documentation drafting.

## What I personally reviewed, changed, validated
YOU FILL. Re-run the tests yourself on your machine and note it here with the date.

## Limitations of this record
Prompts are recorded in `AI_PROMPT_HISTORY.md`. The chat tool cannot export prompts automatically, they were copied by hand.
