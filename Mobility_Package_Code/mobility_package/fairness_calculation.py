from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union

import numpy as np
import pandas as pd


# ============================================================
# 1) FAIRNESS METRICS
# ============================================================

def gini_coefficient(x):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    x = x[x >= 0]
    if x.size == 0:
        return np.nan
    if np.all(x == 0):
        return 0.0
    x_sorted = np.sort(x)
    n = x_sorted.size
    cumx = np.cumsum(x_sorted)
    return float((n + 1 - 2 * np.sum(cumx) / cumx[-1]) / n)


def alpha_fairness_alpha1_normalized(x_norm):
    x = np.asarray(x_norm, dtype=float)
    x = x[np.isfinite(x)]
    x = x[x >= 0]
    if x.size == 0:
        return np.nan
    return float(np.sum(np.log(x + 1)))


# ============================================================
# 2) COLUMN INFERENCE ENGINE
# Each metric defines semantic categories. For each category
# the engine scores every numeric column in the CSV and picks
# the best match automatically.
# ============================================================

# Keywords that identify the tract ID column
_TRACT_ID_KEYWORDS = [
    "census_tract", "tract_geoid", "geoid", "tract_id", "tractid",
]

# Keywords that identify time columns — used to decide whether to aggregate
_TIME_KEYWORDS = [
    "time_slot", "hour", "timestamp", "h_bucket", "slot", "date",
    "time", "period",
]

# Metric semantic profiles — each entry is:
#   utility_name: [
#       (metric_label, [must_contain_keywords], [must_not_contain_keywords])
#   ]
# The engine scores each numeric column against must_contain and
# must_not_contain, then picks the highest-scoring column per label.
_METRIC_PROFILES: Dict[str, List[Tuple[str, List[str], List[str]]]] = {
    "capacity": [
        ("Total capacity",     ["total", "capacity"],           ["vehicle", "norm", "dock"]),
        ("Vehicle capacity",   ["vehicle", "capacity"],         ["norm"]),
        ("Number of stations", ["station", "num"],              ["norm", "capacity"]),
        ("Dock capacity",      ["dock", "capacity"],            ["norm"]),
    ],
    "safety": [
        ("Bike lane ratio",           ["bike", "lane", "ratio"],       ["protect", "norm"]),
        ("Protected bike lane ratio", ["protect", "bike", "lane"],     ["norm"]),
    ],
    "accessibility": [
        ("Total key destinations",   ["key", "destination"],           ["norm"]),
        ("Workplaces",               ["workplace"],                    ["norm"]),
        ("Education institutions",   ["education", "institution"],     ["norm"]),
        ("Health services",          ["health", "service"],            ["norm"]),
        ("Public transit services",  ["transit", "access"],            ["norm"]),
        ("Leisure activities",       ["leisure", "activit"],           ["norm"]),
    ],
    "availability": [
        ("Total vehicles available", ["vehicle", "available"],         ["norm", "dock", "bike", "ebike"]),
        ("Bikes available",          ["bike", "available"],            ["norm", "ebike", "dock"]),
        ("E-bikes available",        ["ebike", "available"],           ["norm", "dock"]),
        ("Docks available",          ["dock", "available"],            ["norm"]),
        ("Total available",          ["total", "available"],           ["norm"]),
    ],
    "idle_time": [
        ("Average idle time",        ["idle", "time"],                 ["norm", "segment", "count", "ping"]),
        ("Average idle minutes",     ["idle", "minut"],                ["norm", "segment"]),
    ],
    "usage": [
        ("Trips starting",           ["trip", "start"],                ["norm", "end"]),
        ("Trips ending",             ["trip", "end"],                  ["norm", "start"]),
        ("Starts",                   ["start"],                        ["norm", "end", "time"]),
        ("Ends",                     ["end"],                          ["norm", "start", "time", "stamp"]),
    ],
}


def _score_column(col_name: str, must_contain: List[str], must_not: List[str]) -> int:
    """
    Score a column name against keyword lists.
    Returns the number of must_contain keywords found minus a large
    penalty for any must_not keyword found. A score <= 0 means no match.
    """
    col = col_name.lower()
    if any(kw in col for kw in must_not):
        return 0
    return sum(1 for kw in must_contain if kw in col)


def _infer_columns_for_utility(
    utility: str,
    df_cols: List[str],
) -> List[Tuple[str, str]]:
    """
    Given a utility name and the list of columns in a DataFrame,
    return a list of (metric_label, best_column) pairs by scoring
    every numeric-looking column against the utility's semantic profile.

    Only returns pairs where a column scores above zero, so it never
    forces a wrong match.
    """
    if utility not in _METRIC_PROFILES:
        return []

    profiles = _METRIC_PROFILES[utility]
    results  = []
    used_cols: Set[str] = set()

    for label, must_contain, must_not in profiles:
        best_col   = None
        best_score = 0

        for col in df_cols:
            if col in used_cols:
                continue
            score = _score_column(col, must_contain, must_not)
            if score > best_score:
                best_score = score
                best_col   = col

        if best_col is not None and best_score > 0:
            results.append((label, best_col))
            used_cols.add(best_col)

    return results


def _detect_tract_col(df: pd.DataFrame) -> Optional[str]:
    """Return the first column that looks like a census tract ID."""
    for col in df.columns:
        if any(kw in col.lower() for kw in _TRACT_ID_KEYWORDS):
            return col
    return None


def _detect_time_col(df: pd.DataFrame) -> Optional[str]:
    """Return the first column that looks like a time/slot column."""
    for col in df.columns:
        if any(kw in col.lower() for kw in _TIME_KEYWORDS):
            return col
    return None


# ============================================================
# 3) HELPERS
# ============================================================

def clean_tract(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.replace(r"\D", "", regex=True)
    s = s.where(s.str.len() == 11, np.nan)
    return s


def minmax_norm(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    mn, mx = s.min(skipna=True), s.max(skipna=True)
    if pd.isna(mn) or pd.isna(mx) or mx <= mn:
        return pd.Series(0.0, index=series.index)
    return (s - mn) / (mx - mn)


def infer_norm(df: pd.DataFrame, raw_col: str, norm_col: Optional[str]):
    """
    Find the normalised version of raw_col.
    Priority: explicit norm_col → auto-guessed _norm suffix → recompute.
    """
    if norm_col and norm_col in df.columns:
        return df[norm_col]
    guess = raw_col + "_norm"
    if guess in df.columns:
        return df[guess]
    return minmax_norm(df[raw_col])


def aggregate_to_tract(df: pd.DataFrame, tract_col: str, time_col: Optional[str]) -> pd.DataFrame:
    """
    Normalise tract IDs and collapse to one row per tract by taking
    the mean across all time slots. If no time column is present the
    DataFrame is returned as-is (already one row per tract).
    """
    df = df.copy()
    df["tract_geoid11"] = clean_tract(df[tract_col])
    df = df.dropna(subset=["tract_geoid11"])

    if time_col and time_col in df.columns:
        return df.groupby("tract_geoid11", as_index=False).mean(numeric_only=True)
    return df


def service_area_tracts(cap_df: pd.DataFrame) -> set:
    """
    Return the set of tract GEOIDs that have any capacity.
    Works for both docked (total_capacity / num_station) and
    dockless (vehicle_capacity) capacity CSVs by scoring columns
    automatically.
    """
    cap_df = cap_df.copy()
    tract_col = _detect_tract_col(cap_df) or "census_tract"
    cap_df["tract_geoid11"] = clean_tract(cap_df[tract_col])
    cap_df = cap_df.dropna(subset=["tract_geoid11"])

    # Find all columns that look like capacity counts
    cap_cols = [
        col for col in cap_df.columns
        if _score_column(col, ["capacity", "station", "vehicle"], ["norm"]) > 0
    ]

    if not cap_cols:
        return set(cap_df["tract_geoid11"].unique())

    mask = pd.Series(False, index=cap_df.index)
    for col in cap_cols:
        mask |= pd.to_numeric(cap_df[col], errors="coerce").fillna(0) > 0

    return set(cap_df.loc[mask, "tract_geoid11"].unique())


# ============================================================
# 4) MAIN FUNCTION
# ============================================================

def run_paper_style_fairness(
    *,
    city_key: str,
    save_directory: Union[str, Path],

    capacity_csv:      Union[str, bool] = False,
    safety_csv:        Union[str, bool] = False,
    accessibility_csv: Union[str, bool] = False,
    availability_csv:  Union[str, bool] = False,
    idle_time_csv:     Union[str, bool] = False,
    usage_csv:         Union[str, bool] = False,

    filter_to_capacity_service_area: bool = False,
):
    """
    Compute Gini coefficient and Alpha fairness (α=1) for every utility
    metric and save results to save_directory.

    Column names are inferred automatically from the CSV — no manual
    mapping is needed. Works with both docked and dockless output files,
    and will adapt to any future column naming changes as long as the
    column names remain semantically descriptive.

    Parameters
    ----------
    city_key                        : identifier used in output filenames
    save_directory                  : folder where results CSVs are saved
    capacity_csv                    : path to capacity tract CSV, or False
    safety_csv                      : path to safety tract CSV, or False
    accessibility_csv               : path to accessibility tract CSV, or False
    availability_csv                : path to availability tract CSV, or False
    idle_time_csv                   : path to idle time tract CSV, or False
    usage_csv                       : path to usage tract CSV, or False
    filter_to_capacity_service_area : restrict all metrics to tracts that
                                      have capacity > 0
    """
    save_directory = Path(save_directory)
    save_directory.mkdir(parents=True, exist_ok=True)

    rows           = []
    inputs_summary = []

    service_tracts = None
    if filter_to_capacity_service_area and capacity_csv:
        service_tracts = service_area_tracts(pd.read_csv(capacity_csv))

    def process_file(utility_name: str, display_name: str, path: Union[str, Path]):
        """
        Load a metric CSV, auto-detect tract and time columns, infer
        which columns correspond to which metrics, aggregate to one row
        per tract, and compute fairness for every matched column.
        """
        df = pd.read_csv(path)

        # Auto-detect the tract ID column
        tract_col = _detect_tract_col(df)
        if tract_col is None:
            print(f"  [fairness] WARNING: no tract column found in {path}. Skipping.")
            return

        # Auto-detect the time column
        time_col = _detect_time_col(df)

        # Collapse to one row per tract
        df = aggregate_to_tract(df, tract_col, time_col)

        # Filter to service area if requested
        if service_tracts is not None:
            df = df[df["tract_geoid11"].isin(service_tracts)]

        # Infer which columns match this utility's semantic profile
        matched = _infer_columns_for_utility(utility_name, list(df.columns))

        if not matched:
            print(f"  [fairness] WARNING: no matching columns found for "
                  f"'{display_name}' in {Path(path).name}. "
                  f"Available columns: {list(df.columns)}")
            return

        print(f"  [fairness] {display_name}: "
              + ", ".join(f"{lbl} → '{col}'" for lbl, col in matched))

        for label, raw_col in matched:
            norm_series = infer_norm(df, raw_col, None)
            raw  = pd.to_numeric(df[raw_col],  errors="coerce").dropna()
            norm = pd.to_numeric(norm_series,   errors="coerce").dropna()

            rows.append({
                "Utility": display_name,
                "Metric":  label,
                "Min":     raw.min(),
                "Max":     raw.max(),
                "Mean":    raw.mean(),
                "StDev":   raw.std(),
                "Gini Coefficient":                   gini_coefficient(norm),
                "Alpha Fairness (α = 1, Normalized)": alpha_fairness_alpha1_normalized(norm),
            })

        inputs_summary.append({
            "Utility":     display_name,
            "Source File": str(path),
            "Tracts Used": int(df["tract_geoid11"].nunique()),
        })

    # --------------------------------------------------------
    # Process each metric CSV if provided
    # --------------------------------------------------------
    if capacity_csv:
        process_file("capacity",      "Capacity",      capacity_csv)
    if safety_csv:
        process_file("safety",        "Safety",        safety_csv)
    if accessibility_csv:
        process_file("accessibility", "Accessibility", accessibility_csv)
    if availability_csv:
        process_file("availability",  "Availability",  availability_csv)
    if idle_time_csv:
        process_file("idle_time",     "Idle Time",     idle_time_csv)
    if usage_csv:
        process_file("usage",         "Usage",         usage_csv)

    fairness_table = pd.DataFrame(rows)
    summary_table  = pd.DataFrame(inputs_summary)

    fairness_path = save_directory / f"{city_key}_fairness_results.csv"
    summary_path  = save_directory / f"{city_key}_fairness_input_summary.csv"

    fairness_table.to_csv(fairness_path, index=False)
    summary_table.to_csv(summary_path,  index=False)

    return {
        "fairness_table":   fairness_table,
        "saved_to":         str(fairness_path),
        "summary_saved_to": str(summary_path),
    }