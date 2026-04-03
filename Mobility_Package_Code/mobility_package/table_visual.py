"""
=============================================================================
TABLE VISUALIZATION — PAPER-STYLE FAIRNESS SUMMARY TABLE
=============================================================================

OVERVIEW
--------
This module takes a fairness-results CSV (produced by fairness_calculation)
and returns a publication-ready grouped summary table formatted to match
the professor's paper style:

    - Grouped by Utility (Capacity, Availability, Usage, Idle Time, Safety)
    - Bold group-header rows with a top border rule
    - Numeric columns right-aligned, label column left-aligned
    - Three-line table border (top, header-bottom, bottom)
    - Times New Roman font, 12pt

The table can be returned as a pandas Styler (renders inline in Jupyter)
or as a plain DataFrame (for further processing or CSV export).

INPUT CSV COLUMNS REQUIRED
--------------------------
    Utility
    Metric
    Min
    Max
    Mean
    StDev
    Gini Coefficient
    Alpha Fairness (α = 1, Normalized)

HOW TO USE
----------
    from mobility_package import table_visual

    # In Jupyter — renders the styled table inline
    table_visual.make_table(
        csv_path = r"path/to/NYC_DOCKED_fairness_results.csv"
    )

    # As a plain DataFrame (e.g. to export or inspect)
    df = table_visual.make_table(
        csv_path = r"path/to/NYC_DOCKED_fairness_results.csv",
        render   = "dataframe",
    )

=============================================================================
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Union

import numpy as np
import pandas as pd


# ===========================================================================
# REQUIRED COLUMNS
# The CSV must contain exactly these columns (names must match).
# ===========================================================================

_REQUIRED_COLS = [
    "Utility",
    "Metric",
    "Min",
    "Max",
    "Mean",
    "StDev",
    "Gini Coefficient",
    "Alpha Fairness (α = 1, Normalized)",
]

# Final display column order (matches the paper screenshot exactly)
_DISPLAY_COLS = [
    "Utility Metric",
    "Min",
    "Max",
    "Mean",
    "StDev",
    "Gini Coefficient",
    "Alpha Fairness\n(α = 1, Normalized)",
]


# ===========================================================================
# INTERNAL HELPERS
# ===========================================================================

def _build_paper_df(df: pd.DataFrame) -> tuple[pd.DataFrame, list[bool]]:
    """
    Convert the flat fairness CSV into a paper-style grouped DataFrame.

    Inserts a bold group-header row above each Utility group, then
    lists each metric below it with a two-space indent on the label.

    Returns
    -------
    paper_df          : the grouped DataFrame ready for styling
    section_row_flags : parallel list of booleans — True for header rows,
                        False for metric rows (used by the row styler)
    """
    numeric_cols = _REQUIRED_COLS[2:]   # Min, Max, Mean, StDev, Gini, Alpha

    rows: list[dict] = []
    flags: list[bool] = []

    for utility, group in df.groupby("Utility", sort=False):
        # ---- Group header row (bold, NaN for all numeric cells) ----
        rows.append({
            "Utility Metric": str(utility),
            **{c: np.nan for c in numeric_cols},
        })
        flags.append(True)

        # ---- One row per metric (indented label) ----
        for _, row in group.iterrows():
            rows.append({
                "Utility Metric":                   f"  {row['Metric']}",
                "Min":                              row["Min"],
                "Max":                              row["Max"],
                "Mean":                             row["Mean"],
                "StDev":                            row["StDev"],
                "Gini Coefficient":                 row["Gini Coefficient"],
                "Alpha Fairness\n(α = 1, Normalized)": row["Alpha Fairness (α = 1, Normalized)"],
            })
            flags.append(False)

    paper_df = pd.DataFrame(rows)[_DISPLAY_COLS]
    return paper_df, flags


def _apply_paper_style(
    paper_df: pd.DataFrame,
    section_row_flags: list[bool],
    decimals: int,
    font_family: str,
) -> "pd.io.formats.style.Styler":
    """
    Apply CSS styling to the paper DataFrame to produce a publication-
    quality table.

    Styling rules:
        - Three-line borders (top of table, below header row, bottom of table)
        - Bold + top border on each group-header row
        - Numbers right-aligned; label column left-aligned
        - NaN values shown as empty strings in header rows
    """
    styler = paper_df.style.hide(axis="index")

    # Format numbers — header rows have NaN which renders as blank
    numeric_display_cols = _DISPLAY_COLS[1:]
    fmt = {
        c: (lambda x, d=decimals: "" if pd.isna(x) else f"{x:.{d}f}")
        for c in numeric_display_cols
    }
    styler = styler.format(fmt)

    # CSS table structure
    table_styles = [
        {
            "selector": "table",
            "props": [
                ("border-collapse", "collapse"),
                ("font-family", font_family),
                ("font-size", "12pt"),
            ],
        },
        {
            # Top and bottom rule on the header row
            "selector": "thead th",
            "props": [
                ("border-top",    "2px solid black"),
                ("border-bottom", "1.5px solid black"),
                ("font-weight",   "normal"),
                ("text-align",    "center"),
                ("padding",       "6px 10px"),
            ],
        },
        {
            "selector": "tbody td",
            "props": [("padding", "6px 10px")],
        },
        {
            # Bottom border on the last row
            "selector": "tbody tr:last-child td",
            "props": [("border-bottom", "2px solid black")],
        },
        {
            # Label column left-aligned
            "selector": "tbody td:first-child",
            "props": [("text-align", "left")],
        },
        {
            # All numeric columns right-aligned
            "selector": "tbody td:not(:first-child)",
            "props": [("text-align", "right")],
        },
    ]
    styler = styler.set_table_styles(table_styles)

    # Bold group-header rows with a top border rule above each group
    def _row_style(row):
        is_header = section_row_flags[row.name]
        if not is_header:
            return [""] * len(row)
        return [
            "font-weight: bold; border-top: 1.5px solid black;"
            if i == 0
            else "border-top: 1.5px solid black;"
            for i in range(len(row))
        ]

    styler = styler.apply(_row_style, axis=1)
    return styler


# ===========================================================================
# PUBLIC FUNCTION
# ===========================================================================

def make_table(
    csv_path: Union[str, Path],
    *,
    decimals:    int = 3,
    font_family: str = "Times New Roman",
    render:      Literal["styler", "dataframe"] = "styler",
) -> Union["pd.io.formats.style.Styler", pd.DataFrame]:
    """
    Build a paper-style grouped fairness summary table from the results CSV.

    Parameters
    ----------
    csv_path    : path to the fairness-results CSV produced by
                  fairness_calculation (must contain the 8 required columns)
    decimals    : number of decimal places for numeric columns (default 3)
    font_family : CSS font family for the styled table (default Times New Roman)
    render      : "styler"    → returns a pandas Styler (renders in Jupyter)
                  "dataframe" → returns the plain grouped DataFrame

    Returns
    -------
    pandas Styler (default) or pd.DataFrame depending on render parameter.

    Usage in Jupyter
    ----------------
        from mobility_package import table_visual
        table_visual.make_table(r"path/to/fairness_results.csv")

    Usage for export
    ----------------
        df = table_visual.make_table(r"path/...", render="dataframe")
        df.to_csv("table_out.csv", index=False)
    """
    df = pd.read_csv(Path(csv_path))

    # Validate required columns early with a clear error message
    missing = [c for c in _REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(
            f"The following required columns are missing from the CSV: {missing}\n"
            f"Available columns: {list(df.columns)}"
        )

    # Sort by Utility then Metric so groups are always in consistent order
    df = (
        df[_REQUIRED_COLS]
        .sort_values(["Utility", "Metric"])
        .reset_index(drop=True)
    )

    # Build the paper-style grouped DataFrame
    paper_df, section_row_flags = _build_paper_df(df)

    if render == "dataframe":
        return paper_df

    # Apply styling and return Styler
    return _apply_paper_style(paper_df, section_row_flags, decimals, font_family)


if __name__ == "__main__":
    print("table_visual module loaded successfully.")