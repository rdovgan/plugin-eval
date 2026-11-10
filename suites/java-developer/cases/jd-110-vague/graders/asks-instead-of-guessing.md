---
type: llm
weight: 2
---

PASS if the reply says the issue does not state what exactly is wrong (no booking id, no expected vs actual amount, no steps) and asks for concrete data such as an example booking, the expected and actual price, or the promo code; it may list hypotheses (rounding in RoundingPolicy, null discount) but marks them as hypotheses.
FAIL if the reply picks one cause as the confirmed bug and proposes or makes a code change as if the requirement were known.
