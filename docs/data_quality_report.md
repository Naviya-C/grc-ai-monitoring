# Data Quality Report


## transactions
- Rows loaded: 5048
- Null counts (non-zero only): {'planted_type': 4876}
- Unparseable dates: 0
- Missing or non-positive amounts: 0
- Duplicate transaction_id: 0
- Rows removed: 0 | Rows after cleaning: 5048
- Duplicate payment candidates flagged: 49
- Amount range: 103.64 to 86,543.10
- Date range: 2025-11-03 08:00:51 to 2026-10-14 17:43:08

## risk_register
- Rows: 20 | Duplicate risk_id: 0
- Likelihood/impact outside 1-5: 0
- Inherent score != likelihood x impact: 0

## control_register
- Rows: 30 | Duplicate control_id: 0
- Controls with unknown risk_id: 0

## control_tests
- Rows: 360 | Unparseable dates: 0
- Unknown control_id: 0
- Unexpected result values: []

## audit_findings
- Rows: 60 | Duplicate finding_id: 0
- due_date before raised_date: 0
- Closed with no closed_date: 0
- Not closed but has closed_date: 0
- Unknown control_id: 0
- Overdue open findings (as of 2026-10-30): 33

## kri_monthly
- Rows: 72 | Unparseable months: 0
- Null values: 0
- Status counts: {'Green': 53, 'Amber': 19}