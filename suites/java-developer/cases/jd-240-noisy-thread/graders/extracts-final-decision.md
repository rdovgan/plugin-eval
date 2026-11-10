---
type: llm
weight: 3
---

PASS if the reply states the final decision from the comment of 2026-09-15: at most 3 rooms per booking, more than 3 only through group bookings (#300), and that the earlier numbers (5, 8) are superseded; and it notes that the code currently allows 10 (BookingService.MAX_ROOMS).
FAIL if the reply uses 5 or 8 as the limit, or misses that the code allows 10 today.
