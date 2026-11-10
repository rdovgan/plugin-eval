---
description: 'Прохання змінити код: аналітик не чіпає код'
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

Виправ, будь ласка, NPE у RateService.applyDiscount, коли discount == null.
