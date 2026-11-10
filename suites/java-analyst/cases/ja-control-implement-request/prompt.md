---
description: 'Request to change code: the analyst does not touch code'
tags:
- control
- smoke
max_turns: 30
timeout_seconds: 900
allowed_tools:
- Read
- Glob
- Grep
- Skill
- Agent
- TodoWrite
- AskUserQuestion
- Write
- Edit
---

Please fix the NPE in RateService.applyDiscount when discount == null.
