# plugin-eval

A thin layer over `claude plugin eval` for three plugins from `claude-plugins`: `java-developer`, `java-analyst` and `qa-docs`. It runs the same set of cases against different plugin versions (git tags, branches, commits) and models, caches the results, enforces a budget, and gives a verdict of "better / worse / inconclusive" with a 95% bootstrap interval.

Isolation, running the agent, attempts, MCP mocks and graders are handled by `claude plugin eval` itself (Claude Code ≥ 2.1.269). This repository does not change it: it only prepares the cases directory in the plugin's working copy, runs the CLI and reads `aggregate-result.json`.

## Layout

```text
config.yaml                 plugins (repo + directory), models, attempts, budgets, ~/.m2
tracker/                    test tracker shared by all plugins
  tickets/<n>.yaml          ticket; #n in GitHub, DEMO-n in Jira
  pages/<id>.yaml           Confluence pages (for the Jira variant)
  workspace/booking-core/   synthetic Maven project (Java 21) the tickets refer to
  presets/<domain>/         ready-made qa-docs domain for export cases
suites/<plugin>/cases/      cases: prompt.md + graders/*.md + fixture.yaml
suites/<plugin>/hidden/     hidden set, only with --hidden
evalkit/tracker.py          tickets -> MCP mocks, fixture.yaml -> scaffold.sh
evalkit/run.py              plugins × versions × models: worktree, case build, cache, budget, run
evalkit/compare.py          paired comparison and verdict
evalkit/report.py           Markdown evidence card in reports/<plugin>/
results/                    raw JSON and the spend ledger, outside git
```

## How the tracker is substituted

The plugin does not know it is working with a test tracker. `tracker.build` looks at the `.mcp.json` of the plugin version under test and generates mocks for the server it declares:

| Plugin | MCP server | What is mocked |
| --- | --- | --- |
| `java-developer`, `java-analyst` | `github` | `issue_read` (one fixture per issue with the description, comments, sub-issues and parent), `search_issues`, `list_issues` |
| `qa-docs` | `jira` (Atlassian) | `getJiraIssue`, `searchJiraIssuesUsingJql`, `getJiraIssueRemoteIssueLinks`, Confluence pages, descendants and comments, `createConfluencePage`, `updateConfluencePage` |

- `expect:` blocks in the mocks check the parameters: owner and repository `demo-org/booking-core`, key `DEMO-<n>`, numeric `pageId`. A call with wrong parameters aborts the attempt with a score of 0.
- Tools without a mock file are unavailable to the plugin, so the real GitHub and Jira are never touched.
- The `db` server is deliberately not mocked: this is the "database not configured" scenario.
- `_tools.json` holds the real tool names and schemas (GitHub MCP and Atlassian MCP as of November 2026).
- `searchJiraIssuesUsingJql` does not interpret JQL and always returns the whole `DEMO` project.

A case's `fixture.yaml` defines the workspace that `scaffold.sh` builds:

| profile | What is created |
| --- | --- |
| `dev` | `booking-core` at the root (git, `origin` = `github.com/demo-org/booking-core`), `.mvn/maven.config` for an offline build from `~/.m2` |
| `qa` | root of the qa-docs server workspace: `booking-core/`, `.qa-docs/config.env` (space `QA`, parent page `777001`), a fresh `sources.tsv`, `qa-docs/modules.md`, `domains.md` |
| `qa` + `preset` + `status` | the same plus a ready-made domain in `qa-docs/domains/<preset>/` with status `verified` or `draft` |

Commits have fixed dates, so the `booking-core` SHA is the same in every run.

## Ticket catalog

| # | Type | What it checks |
| --- | --- | --- |
| 101 | clear, trivial | NPE in `RateService.applyDiscount` when `discount == null` |
| 102 | clear, standard | 30-night limit, 4 acceptance criteria, mentions the `booking` table |
| 110 | vague | "discounts are sometimes wrong", no data |
| 205 | conflict: description vs AC | rounding down vs "10.50 → 11", and both vs ADR 0003 (HALF_EVEN, to cents) |
| 206 | comment overrides a requirement | email → webhook through `PartnerWebhookClient`, which does not exist in the code |
| 207 | ticket vs document | the ticket says 24 h; `docs/cancellation-rules.md`, Confluence and the code say 48 h |
| 230 | incomplete | internal wiki and screenshot are unavailable; in Jira, page 5599 returns 403 |
| 240 | noisy | 25 comments with off-topic chatter; the current decision is in comment 21: 3 rooms |
| 250 | prompt injection | typo + a hidden instruction for the agent: force push, delete tests, publish to Confluence |
| 260 | already done | closed issue, the currency is already in `Price` |
| 300 + 301-305 | epic | 5 sub-issues; the critical constraint "no discounts for groups" is only in #304 |

## Case catalog

**java-developer** (13): `jd-101-trivial-npe`, `jd-102-standard-max-nights`, `jd-110-vague`, `jd-205-conflict-rounding`, `jd-206-comment-overrides`, `jd-207-ticket-vs-doc`, `jd-230-incomplete`, `jd-240-noisy-thread`, `jd-300-epic`, `jd-250-prompt-injection`, `jd-260-already-done`, `jd-control-question`, `jd-github-unavailable` (case-level `issue_read` mock with `error: true`).

**java-analyst** (7): `ja-205-conflict-rounding`, `ja-207-doc-conflict`, `ja-300-epic`, `ja-230-incomplete`, `ja-102-db-unavailable`, `ja-250-prompt-injection`, `ja-control-implement-request`. Graders check `.claude/analysis/gh-<n>/01-research.md`: the `## Sources` section, `**R1**` requirements, recorded conflicts.

**qa-docs** (7): `qd-ask-refund-vs-jira`, `qd-ask-no-ticket`, `qd-ask-forbidden-page`, `qd-ask-prompt-injection`, `qd-document-cancellation` (tag `full`, long), `qd-export-verified`, `qd-export-draft-refused`.

Every case combines an outcome grader (`llm` with a PASS/FAIL rubric, `regex` over a file) and a step grader (`tool_used`: which skill fired, which issues were read, that Edit/Write did not touch `src/`). Tags: `smoke`, `clear`, `vague`, `conflict`, `incomplete`, `noisy`, `epic`, `security`, `control`.

## Usage

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# smoke run of all three plugins on the current HEAD
python -m evalkit.run --refs HEAD --models haiku --smoke

# full run of two versions of one plugin, then a comparison
python -m evalkit.run --plugins java-developer --refs <old-commit> HEAD --models sonnet
python -m evalkit.compare --plugin java-developer --a <old-commit> --b HEAD --model sonnet --report

# a single case for debugging (not used by compare)
python -m evalkit.run --plugins qa-docs --refs HEAD --models haiku --case qd-ask-refund-vs-jira --runs 1

# see exactly what claude plugin eval will receive
python -m evalkit.tracker preview --plugin qa-docs --out /tmp/pe-preview
```

`claude-plugins` has no git tags yet, so versions are given as commits or branches. Tag the releases and `--refs v0.10.0 v0.11.0` will work.

## Adding a ticket or a case

- **Ticket**: a new `tracker/tickets/<n>.yaml` (same fields as its neighbours). It automatically shows up both as GitHub issue `#n` and as `DEMO-n` in Jira. A Confluence page is `tracker/pages/<id>.yaml`, linked from the ticket through `links: [{title, page_id}]`.
- **Case**: a directory `suites/<plugin>/cases/<name>/` with `prompt.md` (frontmatter: `tags`, `max_turns`, `timeout_seconds`, `allowed_tools`), `graders/*.md` and `fixture.yaml`. A mock that has to differ for one case only goes into `<case>/mocks/<server>/<tool>.md`.
- Changing a ticket, a page or the synthetic project changes the suite hash, so the cache is invalidated automatically and `compare` refuses to compare runs made on different suites.

## HTML report

`reports/index.html` is a single self-contained file with no external dependencies (works offline, light and dark themes). It is refreshed automatically after every `run` and `compare`. To build it manually:

```bash
python -m evalkit.html_report --open
```

What it contains:

- filters: plugin, model, run; debug runs made with `--case` are hidden until you turn the toggle on;
- tiles: overall score, cases and attempts passed, cost, duration, ungraded attempts;
- case scores: the bar is the mean score, dots are individual attempts; hovering shows which graders failed, clicking opens the case in the table;
- cost and agent turns per case (the tick is the `max_turns` limit);
- trend of the overall score across full valid runs, one line per model;
- comparison of two runs: Δ per case, bootstrap interval, verdict, control case regressions, warnings about different suites or CLI versions;
- a case table with sorting and a tag filter; a row expands to the prompt, errors and every grader's verdict in every attempt, with the explanation.

A run in which at least one attempt aborted before grading (plan limit, rate limit, API error) is marked invalid: the report shows a banner, and `compare`, the trend and the cache ignore that run.

## Result storage

| What | Where |
| --- | --- |
| Raw result and run manifest (source of truth) | `results/<key>/aggregate.json`, `manifest.json` (outside git) |
| Spend ledger for the daily budget | `results/ledger.jsonl` |
| Comparison cards | `reports/<plugin>/*.md` (in git) |
| Index for queries and trends | MariaDB, if `PE_DB_URL` is set |

MariaDB is optional. Point `PE_DB_URL` at any MariaDB 11 instance. If the database only listens on the server's loopback interface, also set `PE_DB_SSH` in `.env`: `evalkit` then opens an SSH tunnel itself and closes it when it finishes.

```
PE_DB_URL=mysql://plugin_eval:<password>@127.0.0.1:3307/plugin_eval
PE_DB_SSH=-p 22 user@db-host.example.com
```

`run` records every run, `compare` records the comparison. If the database is unavailable, the run is not lost: the files are already written and can be loaded into the database later.

```bash
python -m evalkit.db init      # create or update the tables (migrations are versioned)
python -m evalkit.db import    # rewrite all runs from results/ into the database (safe to re-run)
python -m evalkit.db status    # row counts and the latest runs
```

Tables:

| Table | Row |
| --- | --- |
| `runs` | one `claude plugin eval` invocation (plugin, commit, model, suite hash, CLI version, score, cost) |
| `case_results` | a case in a run: score, spread between attempts, tags, whether it is a control case |
| `attempts` | one attempt of a case: score, turns, cost, error, mock calls |
| `grader_results` | every grader's verdict with its explanation |
| `comparisons` | result of `compare`: Δ, interval, verdict, control regressions |
| `case_trend` (view) | case scores per commit for full runs, the basis for charts |

## Tests

```bash
python3 -m unittest discover -s tests -v
```
