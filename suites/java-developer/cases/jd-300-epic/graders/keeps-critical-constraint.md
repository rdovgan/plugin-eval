---
type: llm
weight: 3
---

PASS if the reply mentions all five sub-issues (#301-#305) and the constraint from #304 that group bookings never get promotional discounts (RateService must not apply a Discount to a group booking).
FAIL if the #304 constraint is missing or any sub-issue is not mentioned.
