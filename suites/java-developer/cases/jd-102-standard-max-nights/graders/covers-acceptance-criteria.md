---
type: llm
weight: 2
---

PASS if the reply covers all four acceptance criteria of issue #102: (1) reject more than 30 nights with HTTP 400 and the message "Booking cannot exceed 30 nights"; (2) configurable property booking.max-nights with default 30; (3) WARN log with the partner id and no guest personal data; (4) unit tests for 30 and 31 nights. It must name BookingService.create (or BookingService) as the place of the change.
FAIL if any criterion is missing or changed, or the reply claims the code was already changed.
