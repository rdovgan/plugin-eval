---
description: '/qa-docs:ask without a ticket: Jira is not touched, there is no night limit in the code'
tags:
- ask
- control
max_turns: 30
timeout_seconds: 600
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

/qa-docs:ask What is the maximum number of nights that can be booked?
