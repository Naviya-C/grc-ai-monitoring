# scripts/clean_data.py
import os
import pandas as pd

RAW, CLEAN, DOCS = "data/raw", "data/clean", "docs"
REF_DATE = pd.Timestamp("2026-10-30")  # "today" for overdue calculations
os.makedirs(CLEAN, exist_ok=True)
os.makedirs(DOCS, exist_ok=True)

log = ["# Data Quality Report", ""]

def note(msg=""):
    print(msg)
    log.append(msg)

def section(title):
    note(f"\n## {title}")

def clean_ids(df, cols):
    for c in cols:
        df[c] = df[c].astype(str).str.strip().str.upper()
    return df

# ---------------- transactions ----------------
section("transactions")
tx = pd.read_csv(f"{RAW}/transactions.csv")
note(f"- Rows loaded: {len(tx)}")
note(f"- Null counts (non-zero only): {tx.isna().sum()[tx.isna().sum() > 0].to_dict()}")

tx = clean_ids(tx, ["transaction_id", "vendor_id", "requester_id", "approver_id", "invoice_no"])
tx["payment_date"] = pd.to_datetime(tx["payment_date"], errors="coerce")
tx["amount"] = pd.to_numeric(tx["amount"], errors="coerce")

bad_dates = tx["payment_date"].isna().sum()
bad_amounts = (tx["amount"].isna() | (tx["amount"] <= 0)).sum()
dup_ids = tx["transaction_id"].duplicated().sum()
note(f"- Unparseable dates: {bad_dates}")
note(f"- Missing or non-positive amounts: {bad_amounts}")
note(f"- Duplicate transaction_id: {dup_ids}")

key_cols = ["transaction_id", "vendor_id", "payment_date", "amount", "requester_id", "approver_id"]
before = len(tx)
tx = tx.dropna(subset=key_cols)
tx = tx[tx["amount"] > 0]
tx = tx.drop_duplicates(subset="transaction_id", keep="first")
note(f"- Rows removed: {before - len(tx)} | Rows after cleaning: {len(tx)}")

# Derived features
tx["payment_day"] = tx["payment_date"].dt.date
tx["hour"] = tx["payment_date"].dt.hour
tx["weekday"] = tx["payment_date"].dt.weekday
tx["is_weekend"] = (tx["weekday"] >= 5).astype(int)
tx["is_off_hours"] = ((tx["hour"] < 7) | (tx["hour"] >= 19)).astype(int)
tx["is_self_approved"] = (tx["requester_id"] == tx["approver_id"]).astype(int)

# Duplicate-payment candidates: flagged, NOT deleted
tx["dup_candidate"] = tx.duplicated(subset=["vendor_id", "invoice_no", "amount"], keep=False).astype(int)
note(f"- Duplicate payment candidates flagged: {tx['dup_candidate'].sum()}")
note(f"- Amount range: {tx['amount'].min():,.2f} to {tx['amount'].max():,.2f}")
note(f"- Date range: {tx['payment_date'].min()} to {tx['payment_date'].max()}")
tx["planted_type"] = tx["planted_type"].fillna("")
tx.drop(columns=["payment_day"]).to_csv(f"{CLEAN}/transactions.csv", index=False)

# ---------------- risk_register ----------------
section("risk_register")
risk = pd.read_csv(f"{RAW}/risk_register.csv")
risk = clean_ids(risk, ["risk_id"])
note(f"- Rows: {len(risk)} | Duplicate risk_id: {risk['risk_id'].duplicated().sum()}")
bad_scale = risk[(~risk["likelihood"].between(1, 5)) | (~risk["impact"].between(1, 5))]
note(f"- Likelihood/impact outside 1-5: {len(bad_scale)}")
mismatch = risk[risk["inherent_score"] != risk["likelihood"] * risk["impact"]]
note(f"- Inherent score != likelihood x impact: {len(mismatch)}")
risk["rating"] = pd.cut(risk["residual_score"], bins=[0, 5, 12, 25], labels=["Low", "Medium", "High"])
risk.to_csv(f"{CLEAN}/risk_register.csv", index=False)

# ---------------- control_register ----------------
section("control_register")
ctl = pd.read_csv(f"{RAW}/control_register.csv")
ctl = clean_ids(ctl, ["control_id", "risk_id"])
orphan = ~ctl["risk_id"].isin(risk["risk_id"])
note(f"- Rows: {len(ctl)} | Duplicate control_id: {ctl['control_id'].duplicated().sum()}")
note(f"- Controls with unknown risk_id: {orphan.sum()}")
ctl = ctl[~orphan]
ctl.to_csv(f"{CLEAN}/control_register.csv", index=False)

# ---------------- control_tests ----------------
section("control_tests")
ct = pd.read_csv(f"{RAW}/control_tests.csv")
ct = clean_ids(ct, ["control_id"])
ct["test_date"] = pd.to_datetime(ct["test_date"], errors="coerce")
note(f"- Rows: {len(ct)} | Unparseable dates: {ct['test_date'].isna().sum()}")
note(f"- Unknown control_id: {(~ct['control_id'].isin(ctl['control_id'])).sum()}")
note(f"- Unexpected result values: {sorted(set(ct['result']) - {'Pass', 'Fail', 'Partial'})}")
ct = ct.dropna(subset=["test_date"])
ct = ct[ct["control_id"].isin(ctl["control_id"])]
ct["is_pass"] = (ct["result"] == "Pass").astype(int)
ct["is_fail"] = (ct["result"] == "Fail").astype(int)
ct.to_csv(f"{CLEAN}/control_tests.csv", index=False)

# ---------------- audit_findings ----------------
section("audit_findings")
af = pd.read_csv(f"{RAW}/audit_findings.csv")
af = clean_ids(af, ["finding_id", "control_id"])
for c in ["raised_date", "due_date", "closed_date"]:
    af[c] = pd.to_datetime(af[c], errors="coerce")
note(f"- Rows: {len(af)} | Duplicate finding_id: {af['finding_id'].duplicated().sum()}")
note(f"- due_date before raised_date: {(af['due_date'] < af['raised_date']).sum()}")
note(f"- Closed with no closed_date: {((af['status'] == 'Closed') & af['closed_date'].isna()).sum()}")
note(f"- Not closed but has closed_date: {((af['status'] != 'Closed') & af['closed_date'].notna()).sum()}")
note(f"- Unknown control_id: {(~af['control_id'].isin(ctl['control_id'])).sum()}")
af = af[af["control_id"].isin(ctl["control_id"])]
af["is_overdue"] = ((af["status"] != "Closed") & (af["due_date"] < REF_DATE)).astype(int)
af["days_overdue"] = ((REF_DATE - af["due_date"]).dt.days.clip(lower=0) * af["is_overdue"]).astype(int)
af["closed_late"] = ((af["status"] == "Closed") & (af["closed_date"] > af["due_date"])).astype(int)
note(f"- Overdue open findings (as of {REF_DATE.date()}): {af['is_overdue'].sum()}")
af.to_csv(f"{CLEAN}/audit_findings.csv", index=False)

# ---------------- kri_monthly ----------------
section("kri_monthly")
kri = pd.read_csv(f"{RAW}/kri_monthly.csv")
kri["month"] = pd.to_datetime(kri["month"], errors="coerce")
note(f"- Rows: {len(kri)} | Unparseable months: {kri['month'].isna().sum()}")
note(f"- Null values: {kri['value'].isna().sum()}")
kri = kri.dropna(subset=["month", "value"])
kri["status"] = "Green"
kri.loc[kri["value"] >= kri["amber_threshold"], "status"] = "Amber"
kri.loc[kri["value"] >= kri["red_threshold"], "status"] = "Red"
note(f"- Status counts: {kri['status'].value_counts().to_dict()}")
kri.to_csv(f"{CLEAN}/kri_monthly.csv", index=False)

# ---------------- write report ----------------
with open(f"{DOCS}/data_quality_report.md", "w") as f:
    f.write("\n".join(log))
print(f"\nDone. Clean files in {CLEAN}/, report in {DOCS}/data_quality_report.md")