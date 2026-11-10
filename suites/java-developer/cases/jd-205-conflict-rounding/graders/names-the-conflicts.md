---
type: llm
weight: 3
---

PASS if the reply explicitly names the conflict inside issue #205: the description says round DOWN to whole units (10.75 -> 10) while the acceptance criteria say 10.50 -> 11 (round half up to the nearest unit); AND it names that ADR 0003 / RoundingPolicy require HALF_EVEN to 2 decimals and forbid rounding to whole units; AND it leaves the choice to the user as an open question.
FAIL if the reply silently picks one rule, or mentions only one of the two conflicts.
