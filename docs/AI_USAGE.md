# AI usage record

## Tool
Claude (claude.ai chat plus a cloud coding session). One tool throughout. The cloud session could not push to GitHub, so I applied its patches with `git am` and pushed myself.

## Who did what
I did not write this code by hand. Claude generated the code, tests and documentation. My role was to direct the work, make the decisions, and approve each phase.

| Area | Claude | Me (Sai Kiran) |
|---|---|---|
| Requirements and scope | Read the brief, produced the requirement table | Chose to proceed, set the working rules (explain first, phased, never claim untested things) |
| Architecture | Proposed the 12-table schema, stack, stage-isolated seeding, validator design | Reviewed each explanation and approved it before any build |
| Code | Wrote all modules in `recallsim/` | Approved each phase; applied patches and pushed |
| Tests | Wrote and ran the 125 tests | Re-run on my machine: see note below |
| Evaluation | Ran an independent review by a second agent and fixed what it found | Requested the audit and the review, approved the fixes |
| Docs, deck, video | Drafted them | Directed tone and content |

I am not claiming a percentage split. Most of the implementation was AI generated.

## What I can explain and defend
Why SQLite, why whole-gram quantities, why two independent traces (BFS and a SQL recursive CTE), why the answer key is kept apart from the validator, and the known limits in `README.md` and the deck. The mentor-style workflow was set up so I could do this.

## What AI got wrong and was fixed
Real issues found by testing and by the independent review: a wrong test count, an in-transit date rule, a README that embedded a folder name and broke reproducibility, an SQL seed file that failed on foreign keys, and a fake-ID pattern that revealed the injected errors. All fixed and covered by tests.

## Validation
Executed in the AI session: 125 tests pass, `verify --scale full` passes (two separate processes, different hash seeds, identical hashes of all 50 files), validator finds 20 of 20 injected errors. Checked on Python 3.13 only.

## My own checks
Date I re-ran `pytest` and `python -m recallsim verify --scale full` on my machine: ____ (fill in after you run them).

## Prompts
Important prompts are in `AI_PROMPT_HISTORY.md`.
