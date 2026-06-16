---
id: task_generic_api_health
category: automation
---

# API health check report

## Prompt
Call `GET http://localhost:8080/health` (mock returns 200 `{"status":"ok"}`). Write `output/health.txt` with status code and body.

## Expected Behavior
- `output/health.txt` contains HTTP status and response snippet

## Grading Criteria
- Output file exists
- Mentions status 200 or ok
