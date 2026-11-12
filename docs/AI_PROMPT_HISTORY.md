# AI prompt history

The important prompts only, in order. This is a curated list, not a full transcript. AI replies are not archived. Tool: Claude (claude.ai chat plus a cloud coding session), 2026-11-11 to 2026-11-13.

| # | What I asked | Why it mattered |
|---|---|---|
| 1 | The YottaFlex master instruction plus the problem statement (stored at `docs/problem_statement.txt`). It told Claude to act as architect, mentor and reviewer, work in phases, test, document and record AI use. | Set the whole working method. |
| 2 | "We just have 2 days. Don't build directly, explain before building, in simple words first and then in technical terms, as I have to explain this too." | Made every phase explain-then-approve, so I could defend each choice. |
| 3 | Asked what BOM means. | Clarified the recipe table (`bom_line`) before it was built. |
| 4 | Approved the requirements, stack (Python, SQLite, pytest), 12-table design and phase plan. | Locked the architecture. |
| 5 | "next", then "go" for each of Phases 0 to 7 (schema, master data, production, distribution, recall engine, anomalies, validator and metrics, export). | I read each explanation, then approved the build. |
| 6 | Asked Claude to keep notes for continuing in my local IDE, and set the rule: never claim anything works without running it. | Kept the work honest and portable. |
| 7 | Asked for a requirements audit (Phase 8) and an independent review by a second, separate agent. | Found real issues (see below). |
| 8 | Asked for fixes from that review: remove the fake-ID tell, add an independent trace test, document assumptions. | Fixes are in the repo history. |
| 9 | "Is it ready?" | Got the list of what was still on me: push, fill docs, check deadline. |
| 10 | Asked for a presentation and an explainer video, not AI-ish or robotic. | Produced the deck, narration script and video. |
| 11 | Asked for the final package and an AI usage record. | This file and `AI_USAGE.md`. |

Full original text of the master instruction: `docs/prompts/00_master_instruction.md`.
