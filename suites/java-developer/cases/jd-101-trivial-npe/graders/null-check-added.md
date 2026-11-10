---
type: regex
pattern: discount\s*==\s*null|null\s*==\s*discount|Objects\.isNull\(\s*discount|discount\s*!=\s*null|Optional\.ofNullable\(\s*discount
weight: 3
target:
  source: file
  path: src/main/java/com/demo/booking/rate/RateService.java
---
