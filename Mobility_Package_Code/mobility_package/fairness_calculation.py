from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

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
# 2) HELPERS
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
    if norm_col and norm_col in df.columns:
        return df[norm_col]
    guess = raw_col + "_norm"
    if guess in df.columns:
        return df[guess]
    return minmax_norm(df[raw_col])


def aggregate_to_tract(df, tract_col, time_col, aggregation):
    df = df.copy()
    df["tract_geoid11"] = clean_tract(df[tract_col])
    df = df.dropna(subset=["tract_geoid11"])

    if time_col and time_col in df.columns:
        grp = df.groupby("tract_geoid11", as_index=False)
        if aggregation == "mean":
            return grp.mean(numeric_only=True)
        if aggregation == "sum":
            return grp.sum(numeric_only=True)
    return df


def service_area_tracts(cap_df):
    cap_df = cap_df.copy()
    cap_df["tract_geoid11"] = clean_tract(cap_df["census_tract"])
    cap_df = cap_df.dropna(subset=["tract_geoid11"])

    tc = pd.to_numeric(cap_df["total_capacity"], errors="coerce").fillna(0)
    ns = pd.to_numeric(cap_df["num_station"], errors="coerce").fillna(0)

    service = cap_df[(tc > 0) | (ns > 0)]
    return set(service["tract_geoid11"].unique())


# ============================================================
# 3) MAIN FUNCTION
# ============================================================
def run_paper_style_fairness(
    *,
    city_key: str,
    save_directory: Union[str, Path],  # REQUIRED

    capacity_csv: Union[str, bool] = False,
    safety_csv: Union[str, bool] = False,
    accessibility_csv: Union[str, bool] = False, 
    availability_csv: Union[str, bool] = False,
    idle_time_csv: Union[str, bool] = False,
    usage_csv: Union[str, bool] = False,

    filter_to_capacity_service_area: bool = False,
):
    """
    Always saves results to user-specified save_directory.
    """
    save_directory = Path(save_directory)
    save_directory.mkdir(parents=True, exist_ok=True)

    rows = []
    inputs_summary = []

    service_tracts = None
    if filter_to_capacity_service_area and capacity_csv:
        cap_df = pd.read_csv(capacity_csv)
        service_tracts = service_area_tracts(cap_df)

    def process_file(name, path, tract_col, time_col, aggregation, metrics):
        df = pd.read_csv(path)
        df = aggregate_to_tract(df, tract_col, time_col, aggregation)

        if service_tracts is not None:
            df = df[df["tract_geoid11"].isin(service_tracts)]

        for label, raw_col in metrics:
            if raw_col not in df.columns:
                continue

            norm_series = infer_norm(df, raw_col, None)

            raw = pd.to_numeric(df[raw_col], errors="coerce").dropna()
            norm = pd.to_numeric(norm_series, errors="coerce").dropna()

            rows.append({
                "Utility": name,
                "Metric": label,
                "Min": raw.min(),
                "Max": raw.max(),
                "Mean": raw.mean(),
                "StDev": raw.std(),
                "Gini Coefficient": gini_coefficient(norm),
                "Alpha Fairness (α = 1, Normalized)": alpha_fairness_alpha1_normalized(norm),
            })

        inputs_summary.append({
            "Utility": name,
            "Source File": str(path),
            "Tracts Used": int(df["tract_geoid11"].nunique()),
        })

    # ---------------------------------------------------
    # Process each file if provided
    # ---------------------------------------------------
    if capacity_csv:
        process_file(
            "Capacity",
            capacity_csv,
            "census_tract",
            None,
            "mean",
            [
                ("Total capacity", "total_capacity"),
                ("Number of stations", "num_station"),
            ],
        )

    if safety_csv:
        process_file(
            "Safety",
            safety_csv,
            "census_tract",
            None,
            "mean",
            [
                ("Bike lane ratio", "bike_lane_ratio"),
                ("Protected bike lane ratio", "protected_bike_lane_ratio"),
            ],
        )

    
    if accessibility_csv:
        process_file(
            "Accessibility",
            accessibility_csv,
            "census_tract",
            None,
            "mean",
            [
           ("Total key destinations", "key_destinations"),
            ("Workplaces", "avg_Workplaces"),
            ("Education institutions", "avg_education_institutions"),
            ("Health services", "avg_health_services"),
            ("Public transit services", "avg_transit_access"),
            ("Leisure activities", "avg_leisure_activities"),
            ],
        )

    if availability_csv:
        process_file(
            "Availability",
            availability_csv,
            "census_tract",
            "time_slot",
            "mean",
            [
                ("Total vehicles available", "total_vehicle_available"),
            ],
        )

    if idle_time_csv:
        process_file(
            "Idle Time",
            idle_time_csv,
            "census_tract",
            "hour",
            "mean",
            [
                ("Average idle time", "avg_idle_time"),
            ],
        )

    if usage_csv:
        process_file(
            "Usage",
            usage_csv,
            "census_tract",
            "time_slot",
            "mean",
            [
                ("Trips starting", "trips_starting"),
                ("Trips ending", "trips_ending"),
            ],
        )

    fairness_table = pd.DataFrame(rows)
    summary_table = pd.DataFrame(inputs_summary)

    # ---------------------------------------------------
    # ALWAYS SAVE
    # ---------------------------------------------------
    fairness_path = save_directory / f"{city_key}_fairness_results.csv"
    summary_path = save_directory / f"{city_key}_fairness_input_summary.csv"

    fairness_table.to_csv(fairness_path, index=False)
    summary_table.to_csv(summary_path, index=False)

    return {
        "fairness_table": fairness_table,
        "saved_to": str(fairness_path),
        "summary_saved_to": str(summary_path),
    }