---
type: llm
weight: 3
---

PASS if the answer says the code has no upper limit on nights (BookingService.create only rejects nights <= 0), with a reference to BookingService.
FAIL if the answer states 30 nights (or any other number) as the current limit.
