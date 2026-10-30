"""Detect exceptions on the CLEANED transactions file (rules + Isolation Forest).
Usage: python scripts/detect_exceptions.py data/clean/transactions.csv data/clean
Writes exceptions.csv, transactions_flagged.csv, detection_metrics.csv into the output dir.
is_planted_anomaly / planted_type are used ONLY for evaluation, never as features.
"""
import sys
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

SRC = sys.argv[1] if len(sys.argv) > 1 else "data/clean/transactions.csv"
OUT = sys.argv[2] if len(sys.argv) > 2 else "data/clean"
APPROVAL_LIMIT = 10000

tx = pd.read_csv(SRC, parse_dates=["payment_date"])
tx["planted_type"] = tx["planted_type"].fillna("")
tx["pay_day"] = tx["payment_date"].dt.date

exceptions = []

def add(mask, rule, severity, reason_fn):
    for _, r in tx[mask].iterrows():
        exceptions.append({"transaction_id": r.transaction_id, "detection_method": "Rule",
                           "rule": rule, "score": 1.0, "severity": severity, "reason": reason_fn(r)})

# --- Rules ---
add(tx.dup_candidate == 1, "Duplicate payment", "High",
    lambda r: f"Invoice {r.invoice_no} paid more than once to {r.vendor_id} for {r.amount:,.2f}")

near = tx[(tx.amount >= 0.9 * APPROVAL_LIMIT) & (tx.amount < APPROVAL_LIMIT)]
cnt = near.groupby(["vendor_id", "pay_day"]).transaction_id.transform("count")
split_ids = set(near[cnt >= 2].transaction_id)
add(tx.transaction_id.isin(split_ids), "Split invoice", "High",
    lambda r: f"{r.amount:,.2f} just under the {APPROVAL_LIMIT:,} limit, repeated same day for {r.vendor_id}")

add((tx.is_weekend == 1) | (tx.is_off_hours == 1), "Off-hours approval", "Medium",
    lambda r: f"Approved on {'weekend' if r.is_weekend else 'off-hours'} at {r.payment_date:%a %H:%M}")

add(tx.is_self_approved == 1, "Self-approval", "Critical",
    lambda r: f"Requester and approver are the same person ({r.requester_id})")

add((tx.vendor_age_days < 30) & (tx.amount > 20000), "New vendor large payment", "High",
    lambda r: f"Vendor only {r.vendor_age_days} days old paid {r.amount:,.2f}")

# --- Isolation Forest (unsupervised, no labels) ---
X = pd.DataFrame({
    "log_amount": np.log1p(tx.amount), "hour": tx.hour, "weekday": tx.weekday,
    "vendor_age_days": tx.vendor_age_days, "self_approved": tx.is_self_approved,
    "vendor_freq": tx.groupby("vendor_id").transaction_id.transform("count"),
})
iso = IsolationForest(n_estimators=200, contamination=0.035, random_state=42).fit(X)
tx["iso_score"] = -iso.score_samples(X)
tx["iso_flag"] = (iso.predict(X) == -1).astype(int)
hi = tx.iso_score.quantile(0.995)
for _, r in tx[tx.iso_flag == 1].iterrows():
    exceptions.append({"transaction_id": r.transaction_id, "detection_method": "Isolation Forest",
                       "rule": "Statistical outlier", "score": round(float(r.iso_score), 4),
                       "severity": "High" if r.iso_score > hi else "Medium",
                       "reason": f"Unusual mix of amount ({r.amount:,.2f}), timing and vendor profile"})

# --- Outputs ---
exc = pd.DataFrame(exceptions).merge(
    tx[["transaction_id", "vendor_id", "vendor_name", "department", "amount", "payment_date",
        "requester_id", "approver_id"]], on="transaction_id", how="left")
exc.insert(0, "exception_id", [f"EX{i:05d}" for i in range(1, len(exc) + 1)])
exc["status"] = np.random.RandomState(7).choice(["New", "Under review", "Resolved"], len(exc), p=[0.5, 0.3, 0.2])
exc.to_csv(f"{OUT}/exceptions.csv", index=False)

counts = exc.groupby("transaction_id").size().rename("exception_count")
tx = tx.merge(counts, on="transaction_id", how="left")
tx["exception_count"] = tx["exception_count"].fillna(0).astype(int)
tx["is_flagged"] = (tx.exception_count > 0).astype(int)
tx["rule_flag"] = tx.transaction_id.isin(exc[exc.detection_method == "Rule"].transaction_id).astype(int)
tx.drop(columns=["pay_day"]).to_csv(f"{OUT}/transactions_flagged.csv", index=False)

# --- Evaluation vs planted labels ---
def prf(pred, name):
    y = tx.is_planted_anomaly
    tp = int(((pred == 1) & (y == 1)).sum()); fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    p = tp / (tp + fp) if tp + fp else 0; r = tp / (tp + fn) if tp + fn else 0
    return {"method": name, "flagged": tp + fp, "true_positives": tp, "false_positives": fp,
            "false_negatives": fn, "precision": round(p, 3), "recall": round(r, 3),
            "f1": round(2 * p * r / (p + r), 3) if p + r else 0}

m = pd.DataFrame([prf(tx.rule_flag, "Rules"), prf(tx.iso_flag, "Isolation Forest"),
                  prf(tx.is_flagged, "Combined")])
m.to_csv(f"{OUT}/detection_metrics.csv", index=False)
print(m.to_string(index=False))
print("\nExceptions by rule:\n" + exc.groupby(["detection_method", "rule"]).size().to_string())
print("\nBy severity:\n" + exc.severity.value_counts().to_string())
print("\nRule catch rate by planted type:")
print(tx[tx.is_planted_anomaly == 1].groupby("planted_type").rule_flag.agg(["count", "sum"])
      .rename(columns={"count": "planted", "sum": "caught"}).to_string())
print("\nTotal exceptions:", len(exc))