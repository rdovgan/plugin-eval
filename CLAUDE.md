# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

A thin Python layer over `claude plugin eval` that runs one set of cases against several plugin versions (git refs) and models, caches results, enforces a budget and gives a paired-comparison verdict. `claude plugin eval` does the isolation, agent runs, MCP mocking and grading; this repo only builds the cases directory, invokes the CLI and reads `aggregate-result.json`. See `README.md` for the ticket and case catalogs.

The plugins under test live in a separate repository (`repo:` in `config.yaml`). Do not edit that repository from here; `run` checks each ref out into a temporary git worktree.

## Commands

```bash
source .venv/bin/activate                      # deps: PyYAML, PyMySQL (requirements.txt)

python3 -m unittest discover -s tests -v       # all tests, offline, under a second
python3 -m unittest tests.test_evalkit.BootstrapTest.test_deterministic   # one test

python -m evalkit.tracker preview --plugin qa-docs --out <dir>   # build cases + mocks, no agent run, free
python -m evalkit.html_report                  # rebuild reports/index.html from results/
python -m evalkit.db status                    # only if PE_DB_URL is set
```

`python -m evalkit.run ...` starts real agent runs and **spends money** (budget in `config.yaml`, ledger in `results/ledger.jsonl`). Never run it without being asked. To check a change to cases, mocks or scaffolding, use the tests and `tracker preview` instead.

## Architecture

- `evalkit/config.py` loads `config.yaml`, substituting `${VAR}` from the environment and `.env`. Model variables are expanded only for the selected model, so a missing key for one model does not break another.
- `evalkit/tracker.py` is the test tracker. `tracker/tickets/<n>.yaml` is the single source for both GitHub issue `#n` and Jira `DEMO-n`; `build()` reads the plugin's `.mcp.json` and renders mocks only for the servers it declares (`github` or `jira`). It also turns each case's `fixture.yaml` into a `scaffold.sh` that creates the workspace (`profile: dev | qa`, optional `preset` + `status`).
- `evalkit/run.py` loops plugins × refs × models: resolve commit, check the cache, add a worktree, build cases, call `claude plugin eval`, write `results/<key>/{aggregate,manifest}.json`.
- `evalkit/store.py` owns the cache key, suite hash, manifests and the spend ledger.
- `evalkit/aggregate.py` is the only place that knows the `aggregate-result.json` schema.
- `evalkit/compare.py` does the percentile bootstrap over per-case differences and produces the verdict; `report.py` writes the Markdown card.
- `evalkit/html_report.py` generates one self-contained `reports/index.html`; the page (HTML, CSS, JS) is the `TEMPLATE` string in that file. It recomputes the comparison in JS, so the verdict rule exists in both `compare.py` and the template: change them together.
- `evalkit/db.py` is an optional MariaDB index. Files in `results/` are the source of truth; a database failure must never fail a run.

## Invariants

- **English only.** No other languages in code, comments, messages, prompts, tickets or docs.
- **Suite hash.** It covers every file under the selected case directories plus all of `tracker/`. Any edit to a prompt, grader, fixture, ticket, page or the synthetic project invalidates the cache and makes `compare` refuse old-vs-new runs. Say so when making such a change.
- **Verdict strings** are `better`, `worse`, `inconclusive`. They are stored in the database and mapped to the exit code in `compare.py`; `better` requires the CI lower bound > 0 and no regressed `control`-tagged case.
- **Partial runs.** A run with any attempt that aborted before grading is `partial`: it is not cached, not compared and not shown in the trend. Keep that when touching `aggregate.summary`, `store.cached` or the report.
- **Determinism.** Bootstrap uses a fixed seed (`SEED`, `ITERATIONS`), and scaffolded commits use a fixed date (`GIT_DATE`) so the `booking-core` SHA is stable. Do not introduce randomness or wall-clock time into either.
- **Mocks are the safety boundary.** A tool without a mock file is unavailable to the plugin, which is what keeps real GitHub and Jira untouched. The `db` MCP server is deliberately left unmocked.
- **Secrets.** Manifests and cache keys take `ModelProfile.public_fingerprint()` only; never write tokens or `.env` values into `results/`, reports or logs.
- `results/`, `.env` and `reports/index.html` are gitignored; `reports/<plugin>/*.md` cards are committed.

## Adding things

- **Ticket:** `tracker/tickets/<n>.yaml`, same fields as its neighbours; link a Confluence page with `links: [{title, page_id}]` and `tracker/pages/<id>.yaml`.
- **Case:** `suites/<plugin>/cases/<name>/` with `prompt.md` (frontmatter `description`, `tags`, `max_turns`, `timeout_seconds`, `allowed_tools`), `graders/*.md` (`type: llm | regex | tool_used`) and `fixture.yaml`. A per-case mock override goes in `<case>/mocks/<server>/<tool>.md`. `tests/test_tracker.py` checks that every case is well formed.
- Pair an outcome grader with a step grader, and tag control cases with `control`.

## Commits

Commit only when asked. Messages describe the change only, with no AI attribution or co-author trailers.
