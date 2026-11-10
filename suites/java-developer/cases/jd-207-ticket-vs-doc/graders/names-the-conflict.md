---
type: llm
weight: 3
---

PASS if the reply says that the issue asks for a full refund from 24 hours, while docs/cancellation-rules.md and CancellationPolicy (FULL_REFUND_HOURS = 48) say 48 hours, that 30 hours is therefore correctly refunded 50% under the current rules, and that the rule change must be confirmed before coding.
FAIL if the reply treats the issue as a plain bug and plans to change the threshold to 24 without flagging the conflict.
