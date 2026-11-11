# Validation summary

Result: **FAIL**, total issues: 8

| Check | Status | Issues |
|---|---|---|
| PK_UNIQUE | PASS | 0 |
| REQUIRED | PASS | 0 |
| TYPE | PASS | 0 |
| ENUM | PASS | 0 |
| ID_FORMAT | PASS | 0 |
| RANGE | PASS | 0 |
| DATE_VALID | PASS | 0 |
| FK | FAIL | 2 |
| POLY_TARGET | PASS | 0 |
| DATE_ORDER | PASS | 0 |
| ARITH_DELIVERED | FAIL | 2 |
| ARITH_CONSUMED | PASS | 0 |
| ARITH_RECOVERED | PASS | 0 |
| LIFECYCLE_ORDER | PASS | 0 |
| CASE_STATUS | PASS | 0 |
| SALE_STATUS | FAIL | 2 |
| DUPLICATE | PASS | 0 |
| SCOPE_COVERAGE | FAIL | 2 |

## Row counts

| Table | Rows |
|---|---|
| supplier | 25 |
| customer | 75 |
| product | 10 |
| bom_line | 54 |
| material_lot | 500 |
| production_order | 250 |
| wo_input_lot | 1173 |
| finished_lot | 400 |
| shipment | 600 |
| delivery | 1000 |
| recall_case | 3 |
| recall_action | 413 |
