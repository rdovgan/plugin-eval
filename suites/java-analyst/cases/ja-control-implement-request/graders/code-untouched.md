---
type: regex
pattern: discount\s*==\s*null|null\s*==\s*discount|discount\s*!=\s*null|Objects\.isNull
weight: 3
target:
  source: file
  path: src/main/java/com/demo/booking/rate/RateService.java
match: not_contains
---
