---
id: task_generic_csv_aggregate
category: data_processing
---

# Aggregate CSV metrics

## Prompt
Read `data/sales.csv` (columns: region, product, amount). Write `output/summary.json` with total amount per region and overall row count.

## Expected Behavior
- `output/summary.json` exists and is valid JSON
- Keys include per-region totals and `row_count`

## Grading Criteria
- File exists (40%)
- JSON parses (20%)
- Totals match reference within 0.01 (40%)
