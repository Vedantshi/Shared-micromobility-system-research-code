# ============================================================
# table_visual — paper-style fairness summary table
# ============================================================
from mobility_package import table_visual

# ---- In Jupyter (renders the styled table inline) ----
table_visual.make_table(
    # Fairness results CSV produced by fairness_calculation
    csv_path = r"D:\Research Fellowship\NYC_Docked_Output_v2\FAIRNESS_RESULTS\NYC_DOCKED_fairness_results.csv",

    # Decimal places for all numeric columns
    decimals = 3,

    # CSS font family for the styled table
    font_family = "Times New Roman",

    # "styler"    → pandas Styler — renders inline in Jupyter (default)
    # "dataframe" → plain DataFrame — use for export or inspection
    render = "styler",
)

# ---- As a plain DataFrame (e.g. to export) ----
df = table_visual.make_table(
    csv_path = r"D:\Research Fellowship\NYC_Docked_Output_v2\FAIRNESS_RESULTS\NYC_DOCKED_fairness_results.csv",
    render   = "dataframe",
)

df.to_csv("fairness_table_export.csv", index=False)