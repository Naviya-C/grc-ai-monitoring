import os
import pandas as pd

os.makedirs("powerbi", exist_ok=True)
files = {  # sheet name -> csv in data/clean
    "transactions": "transactions_flagged",
    "exceptions": "exceptions",
    "risk_register": "risk_register",
    "control_register": "control_register",
    "control_tests": "control_tests",
    "audit_findings": "audit_findings",
    "kri_monthly": "kri_monthly",
}

with pd.ExcelWriter("powerbi/grc_model.xlsx", engine="xlsxwriter",
                    datetime_format="yyyy-mm-dd hh:mm") as w:
    for sheet, f in files.items():
        df = pd.read_csv(f"data/clean/{f}.csv")
        for c in df.columns:
            if c.endswith("_date") or c == "month":
                df[c] = pd.to_datetime(df[c], errors="coerce")
        df.to_excel(w, sheet_name=sheet, index=False)
        ws = w.sheets[sheet]
        ws.add_table(0, 0, len(df), len(df.columns) - 1,
                     {"name": f"t_{sheet}", "columns": [{"header": c} for c in df.columns]})
print("Created powerbi/grc_model.xlsx")