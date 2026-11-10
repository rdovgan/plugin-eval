---
type: llm
weight: 3
focus:
  source: file
  path: .claude/analysis/gh-205/01-research.md
---

PASS if the "Conflicts between sources" part of the research document records both conflicts: description (round down to whole units) vs acceptance criteria (10.50 -> 11), and the issue vs ADR 0003 / RoundingPolicy (HALF_EVEN to 2 decimals, never whole units), and the open questions ask which rule wins.
FAIL if the conflicts section says "none" or records only one conflict.
