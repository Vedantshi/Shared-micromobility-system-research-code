"""
=============================================================================
TREND VISUALIZATION — WEEKLY FAIRNESS TIME-SERIES
=============================================================================

OVERVIEW
--------
This module computes fairness metrics (Gini coefficient, Alpha fairness)
for each utility metric over time and plots them as weekly time-series
charts.  It is designed to show how equity in bike-share access evolves
hour by hour across a full week.

Each metric produces three plots:
    1. Mean ± SD over time        — how the average value and spread changes
    2. Gini Coefficient over time — higher = more unequal across tracts
    3. Alpha Fairness over time   — higher = more total log-utility

FAIRNESS METRICS
----------------
    Gini Coefficient:
        Measures inequality in the distribution of a metric across tracts.
        0 = perfectly equal, 1 = perfectly unequal.
        Formula: (n + 1 - 2 * Σ(cumulative values) / total) / n

    Alpha Fairness (α = 1):
        Proportional fairness — sum of log(x + 1) across all tracts.
        Higher = more total utility delivered fairly.
        Matches the professor's notebook definition exactly.

INPUT FLEXIBILITY
-----------------
Each metric input accepts three formats:
    - A single CSV path (a pre-merged weekly file)
    - A folder path   (all CSVs in the folder are auto-concatenated)
    - False / None    (skip this metric entirely)

HOW TO USE
----------
    from mobility_package import trend_visual

    # One metric at a time
    trend_visual.plot_availability_trend(
        city_key           = "NYC_DOCKED",
        output_dir         = "FAIRNESS_TREND_OUT",
        availability_input = r"path/to/availability__norm__tract/",
        capacity_input     = r"path/to/capacity.csv",
    )

    trend_visual.plot_usage_trend(...)
    trend_visual.plot_idle_time_trend(...)

    # Or all at once
    trend_visual.plot_all(
        city_key           = "NYC_DOCKED",
        output_dir         = "FAIRNESS_TREND_OUT",
        capacity_input     = r"path/to/capacity.csv",
        availability_input = r"path/to/availability__norm__tract/",
        usage_input        = r"path/to/usage_norm_hourly_tract/",
        idle_time_input    = r"path/to/idle_time_norm_tract/",
    )

OUTPUTS
-------
Per metric column, three PNGs are saved:
    MeanSD_Overall_<metric>.png
    Gini_Overall_<metric>.png
    AlphaFairness_Overall_<metric>.png

A combined CSV of all fairness numbers is also saved:
    <city_key>__results_ordered_df_week.csv

PLOT FEATURES
-------------
    - Red shaded bands for weekday peak hours (7:30–9am, 3:30–6pm)
    - Vertical red dashed lines at day boundaries
    - Day-of-week labels inside the plot
    - X-axis ticks every 6 hours
    - Midnight-bleed trimming (drops the final 00:00 point if it bleeds
      into the next week)

SUPPORTED CITY KEYS
-------------------
    "NYC_DOCKED"           New York City — docked system
    "NJ_DOCKED"            New Jersey    — docked system
    "PITT_DOCKED"          Pittsburgh    — docked system
    "SF_LIME_DOCKLESS"     San Francisco — Lime dockless
    "SF_SPIN_DOCKLESS"     San Francisco — Spin dockless
    "SEATTLE_BIRD_DOCKLESS" Seattle      — Bird dockless
    "SEATTLE_LIME_DOCKLESS" Seattle      — Lime dockless
=============================================================================
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch


# ===========================================================================
# FIXED DEFAULTS
# Column names tried in order when auto-detecting tract ID, time, and group.
# ===========================================================================

_ID_CANDIDATES = (
    "census_tract", "tract", "GEOID", "geoid", "tract_geoid", "tract_geoid11"
)
_TIME_CANDIDATES = (
    "Time Slot", "time_slot", "timestamp", "datetime", "hour", "time"
)
_GROUP_CANDIDATES = (
    "boro", "Boro", "borough", "Borough", "region", "Region"
)

# Default value columns to look for in each metric CSV.
# Only columns that actually exist in the file are processed.
_DEFAULT_AVAILABILITY_COLS = [
    "total_vehicle_available_norm",   # docked
    "num_docks_available_norm",       # docked
    "num_bikes_available_norm",       # docked
    "num_ebikes_available_norm",      # docked
    "total_available_norm",           # dockless
]
_DEFAULT_USAGE_COLS    = ["trips_starting_norm", "trips_ending_norm"]
_DEFAULT_IDLE_COLS     = ["avg_idle_time_norm"]

# Capacity columns tried in order when filtering to the service area
_CAPACITY_COLS_PRIORITY = (
    "total_capacity", "vehicle_capacity", "dock_capacity", "num_station"
)

# NYC borough lookup — derived from the first 5 digits of GEOID11
_NYC_COUNTY_MAP = {
    "36005": "The Bronx",
    "36047": "Brooklyn",
    "36061": "Manhattan",
    "36081": "Queens",
    "36085": "Staten Island",
}
_NYC_ALLOWED_GROUPS = list(_NYC_COUNTY_MAP.values())


# ===========================================================================
# INTERNAL HELPERS — IO
# ===========================================================================

def _read_csv_or_folder(
    source: Union[str, Path, pd.DataFrame, bool, None]
) -> Optional[pd.DataFrame]:
    """
    Load a metric dataset from:
        - a single CSV file path
        - a folder path (all CSVs are sorted and concatenated)
        - a DataFrame already in memory
        - False / None → returns None (metric is skipped)
    """
    if source is False or source is None:
        return None
    if isinstance(source, pd.DataFrame):
        return source.copy()

    p = Path(source)
    if p.is_file() and p.suffix.lower() == ".csv":
        return pd.read_csv(p)

    if p.is_dir():
        files = sorted(f for f in p.glob("*.csv") if f.is_file())
        if not files:
            raise ValueError(f"No CSV files found in folder: {p}")
        return pd.concat([pd.read_csv(f) for f in files], ignore_index=True)

    raise ValueError(
        f"Input must be a CSV path, folder path, DataFrame, or False/None. Got: {source}"
    )


def _detect_cols(
    df: pd.DataFrame,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Auto-detect the tract ID column, time column, and group column
    by scanning for known candidate names.

    Returns (id_col, time_col, group_col) — any may be None if not found.
    """
    id_col    = next((c for c in _ID_CANDIDATES    if c in df.columns), None)
    time_col  = next((c for c in _TIME_CANDIDATES  if c in df.columns), None)
    group_col = next((c for c in _GROUP_CANDIDATES if c in df.columns), None)
    return id_col, time_col, group_col


def _valid_tract_mask(s: pd.Series) -> pd.Series:
    """Return a boolean mask: True where the value is an 11-digit tract GEOID."""
    return s.astype(str).str.fullmatch(r"\d{11}")


# ===========================================================================
# INTERNAL HELPERS — SERVICE AREA
# ===========================================================================

def _service_area_tracts(
    cap_df: Optional[pd.DataFrame],
    filter_enabled: bool,
) -> Optional[set]:
    """
    Derive the set of tract IDs that have positive capacity.

    If filter_enabled=False, returns all tracts in the capacity file
    (no filtering, but still uses the file to define the universe).
    If cap_df is None, returns None (no filtering at all).
    """
    if cap_df is None or cap_df.empty:
        return None

    id_col, _, _ = _detect_cols(cap_df)
    if id_col is None:
        return None

    cap = cap_df[_valid_tract_mask(cap_df[id_col])].copy()
    if cap.empty:
        return None

    if not filter_enabled:
        # Return all tracts in the file without checking capacity values
        return set(cap[id_col].astype(str).unique())

    # Filter to tracts where the capacity value is > 0
    svc_col = next((c for c in _CAPACITY_COLS_PRIORITY if c in cap.columns), None)
    if svc_col is None:
        return set(cap[id_col].astype(str).unique())

    vals = pd.to_numeric(cap[svc_col], errors="coerce").fillna(0)
    return set(cap.loc[vals > 0, id_col].astype(str).unique())


def _filter_to_service_area(
    df: Optional[pd.DataFrame],
    service_tracts: Optional[set],
) -> Optional[pd.DataFrame]:
    """
    Keep only rows whose tract ID is in service_tracts.
    If service_tracts is None, returns df unchanged.
    """
    if df is None:
        return None

    id_col, _, _ = _detect_cols(df)
    if id_col is None:
        return df

    d = df[_valid_tract_mask(df[id_col])].copy()
    if service_tracts is not None:
        d = d[d[id_col].astype(str).isin(service_tracts)]
    return d


# ===========================================================================
# INTERNAL HELPERS — GROUPING
# ===========================================================================

def _nyc_boro(geoid11: str) -> str:
    """Infer NYC borough from the first 5 digits of an 11-digit GEOID."""
    if not isinstance(geoid11, str):
        return "Unknown"
    digits = "".join(ch for ch in geoid11 if ch.isdigit())
    return _NYC_COUNTY_MAP.get(digits[:5], "Unknown") if len(digits) >= 5 else "Unknown"


def _ensure_group_column(
    df: Optional[pd.DataFrame],
    city_key: str,
    group_col_name: str,
    group_infer_fn: Optional[Callable[[str], str]],
    allowed_groups: Optional[Sequence[str]],
) -> Optional[pd.DataFrame]:
    """
    Ensure the DataFrame has a group column (e.g. borough for NYC).

    Priority:
        1. Column already exists under a recognised group name → rename/use it
        2. group_infer_fn supplied → apply it to the tract ID column
        3. City key contains "NYC" → use the NYC borough lookup
        4. Everything else → set group = "Unknown"

    After adding the column, rows not in allowed_groups are dropped
    (if allowed_groups is not None).
    """
    if df is None or df.empty:
        return df

    d = df.copy()
    id_col, _, existing_group = _detect_cols(d)

    # If a recognised group column already exists, use or rename it
    if existing_group is not None:
        if existing_group != group_col_name:
            d[group_col_name] = d[existing_group]
        if allowed_groups is not None:
            d = d[d[group_col_name].isin(list(allowed_groups))]
        return d

    # Derive group from the tract ID column
    if id_col is None:
        d[group_col_name] = "Unknown"
    else:
        if group_infer_fn is None:
            group_infer_fn = (
                _nyc_boro if "NYC" in city_key.upper()
                else lambda _: "Unknown"
            )
        d[group_col_name] = d[id_col].astype(str).map(group_infer_fn)

    if allowed_groups is not None:
        d = d[d[group_col_name].isin(list(allowed_groups))]

    return d


# ===========================================================================
# INTERNAL HELPERS — COLORS
# ===========================================================================

# Default color per metric name — derived from city_key (docked vs dockless)
_DOCKED_COLORS = {
    "Availability (total_vehicle_available_norm)": "blue",
    "Availability (num_docks_available_norm)":     "orange",
    "Availability (num_bikes_available_norm)":     "orange",
    "Availability (num_ebikes_available_norm)":    "blue",
    "Usage (trips_starting_norm)":                 "orange",
    "Usage (trips_ending_norm)":                   "blue",
    "Idle Time (avg_idle_time_norm)":              "green",
}
_DOCKLESS_COLORS = {
    "Availability (total_available_norm)":          "blue",
    "Availability (total_vehicle_available_norm)":  "blue",
    "Usage (trips_starting_norm)":                  "orange",
    "Usage (trips_ending_norm)":                    "blue",
    "Idle Time (avg_idle_time_norm)":               "green",
}


def _build_color_map(city_key: str) -> Dict[str, str]:
    """Return the appropriate metric → color map for the given city/system."""
    ck = city_key.upper()
    if "DOCKED" in ck:
        return dict(_DOCKED_COLORS)
    if "DOCKLESS" in ck:
        return dict(_DOCKLESS_COLORS)
    return {"Idle Time (avg_idle_time_norm)": "green"}


def _metric_color(metric_name: str, color_map: Dict[str, str]) -> str:
    """
    Look up a metric's color from the map.
    Falls back to keyword matching if the exact name is not found.
    """
    if metric_name in color_map:
        return color_map[metric_name]
    m = metric_name.lower()
    if "idle time" in m:
        return "green"
    if "usage" in m:
        return "orange"
    if "availability" in m:
        return "blue"
    return "green"


# ===========================================================================
# INTERNAL HELPERS — FAIRNESS COMPUTATION
# ===========================================================================

def _clean(x: np.ndarray) -> np.ndarray:
    """Drop NaN, infinity, and negative values before computing fairness."""
    x = np.asarray(x, dtype=float)
    return x[np.isfinite(x) & (x >= 0)]


def _gini(x) -> float:
    """
    Gini coefficient — measures inequality across tracts.
    0 = perfectly equal, 1 = completely concentrated in one tract.
    """
    x = _clean(x)
    if x.size == 0:
        return np.nan
    if np.all(x == 0):
        return 0.0
    x = np.sort(x)
    n = x.size
    cumx = np.cumsum(x)
    return float((n + 1 - 2 * np.sum(cumx) / cumx[-1]) / n)


def _alpha_fairness(x) -> float:
    """
    Alpha fairness at α=1 (proportional fairness).
    Formula: Σ log(x + 1) across all tracts.
    Higher = more total log-utility delivered across the system.
    """
    x = _clean(x)
    if x.size == 0:
        return np.nan
    return float(np.sum(np.log(x + 1)))


def _compute_fairness_timeseries(
    df: pd.DataFrame,
    utility_name: str,
    value_cols: List[str],
    time_col: str,
    group_col: str,
    group_col_name: str,
    allowed_groups: Optional[Sequence[str]],
    invalid_time_slots: Optional[List[str]],
) -> List[pd.DataFrame]:
    """
    For each value column present in df, compute per-time-slot fairness metrics
    (mean, SD, Gini, Alpha) across all tracts and return one DataFrame per column.

    This is the core computation shared by all three public plot functions.
    Each returned DataFrame has one row per time slot with columns:
        Time Slot, Boro, Metric, Mean, SD, Gini Coefficient, Alpha Fairness (α=1)
    """
    d = df.copy()
    d[time_col] = pd.to_datetime(d[time_col], errors="coerce")
    d = d.dropna(subset=[time_col])

    # Drop any time slots explicitly marked as invalid (e.g. data gaps)
    if invalid_time_slots:
        bad = set(pd.to_datetime(invalid_time_slots, errors="coerce"))
        d = d[~d[time_col].isin(bad)]

    # Keep only the specified borough groups if provided
    if allowed_groups is not None:
        d = d[d[group_col].isin(list(allowed_groups))]

    parts = []
    for col in value_cols:
        if col not in d.columns:
            continue   # silently skip columns that don't exist in this CSV

        metric_name = f"{utility_name} ({col})"
        grp = d.groupby(time_col)[col]

        # Compute all four statistics in one groupby pass
        mean_s  = grp.mean()
        sd_s    = grp.std()
        gini_s  = grp.apply(lambda s: _gini(s.to_numpy()))
        alpha_s = grp.apply(lambda s: _alpha_fairness(s.to_numpy()))

        parts.append(pd.DataFrame({
            "Time Slot":           mean_s.index,
            group_col_name:        "Overall",
            "Metric":              metric_name,
            "Mean":                mean_s.values,
            "SD":                  sd_s.values,
            "Gini Coefficient":    gini_s.values,
            "Alpha Fairness (α=1)": alpha_s.values,
        }))

    return parts


# ===========================================================================
# INTERNAL HELPERS — PLOTTING
# ===========================================================================

def _render_trend_plot(
    *,
    df_plot: pd.DataFrame,
    time_col: str,
    y_col: str,
    sd_col: Optional[str],
    title: str,
    ylabel: str,
    line_label: str,
    line_color: str,
    save_path: str,
    invalid_time_slots: Optional[List[str]],
    add_band: bool,
    band_alpha: float = 0.20,
) -> Optional[str]:
    """
    Render and save one trend-line plot.

    Features:
        - Red shaded bands for weekday peak hours (7:30-9am, 3:30-6pm)
        - Vertical red dashed lines at day boundaries
        - Day-of-week labels inside the plot body
        - Optional shaded ±SD band around the mean line
        - Midnight-bleed trimming (drops final 00:00 point if it
          would extend the x-axis into the next day)

    Parameters
    ----------
    df_plot    : DataFrame with at least time_col and y_col columns
    time_col   : name of the timestamp column
    y_col      : name of the y-axis value column (Mean, Gini, or Alpha)
    sd_col     : name of the SD column (used only when add_band=True)
    title      : plot title
    ylabel     : y-axis label
    line_label : legend label for the main line
    line_color : matplotlib color string
    save_path  : full file path where the PNG is saved
    invalid_time_slots : list of ISO timestamp strings to exclude
    add_band   : draw a ±SD shaded band around the mean line
    band_alpha : transparency of the SD band

    Returns the save_path on success, None if the data is empty.
    """
    d = df_plot.copy()
    d[time_col] = pd.to_datetime(d[time_col], errors="coerce")
    d = d.dropna(subset=[time_col]).sort_values(time_col)

    if invalid_time_slots:
        bad = set(pd.to_datetime(invalid_time_slots, errors="coerce"))
        d = d[~d[time_col].isin(bad)]

    d[y_col] = pd.to_numeric(d[y_col], errors="coerce")

    # Aggregate to ensure one point per time slot (handles any duplicates)
    agg = {y_col: "mean"}
    if add_band and sd_col and sd_col in d.columns:
        d[sd_col] = pd.to_numeric(d[sd_col], errors="coerce")
        agg[sd_col] = "mean"
    d = d.groupby(time_col, as_index=False).agg(agg).sort_values(time_col)

    if d.empty:
        return None

    # ------------------------------------------------------------------
    # Trim midnight bleed: if the last point is exactly 00:00:00 on a
    # new day it bleeds into the next day on the x-axis — drop it.
    # ------------------------------------------------------------------
    last = d[time_col].iloc[-1]
    if last.hour == 0 and last.minute == 0 and last.second == 0 and len(d) > 1:
        d = d.iloc[:-1].copy()

    x = d[time_col]
    y = d[y_col].to_numpy(dtype=float)
    x_start, x_end = x.min(), x.max()

    # Day boundaries within the plot window (for dividers and labels)
    days = pd.date_range(
        start=pd.Timestamp(x_start).normalize(),
        end=pd.Timestamp(x_end).normalize(),
        freq="D",
    )

    # Compute y-axis limits including the SD band if present
    if add_band and sd_col and sd_col in d.columns:
        s      = d[sd_col].to_numpy(dtype=float)
        lower  = y - s
        upper  = y + s
        ok     = np.isfinite(lower) & np.isfinite(upper) & np.isfinite(y)
        ymin   = float(np.nanmin(lower[ok])) * 0.95
        ymax   = float(np.nanmax(upper[ok])) * 1.10
    else:
        ymin = float(np.nanmin(y)) * 0.95
        ymax = float(np.nanmax(y)) * 1.10

    # ------------------------------------------------------------------
    # Build figure
    # ------------------------------------------------------------------
    fig = plt.figure(figsize=(22, 10))
    ax  = plt.gca()
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.set_title(title, fontsize=25, pad=22)
    fig.subplots_adjust(top=0.88)

    # Peak-hour shading (weekday morning + evening rush) drawn first (zorder=0)
    for day in days:
        if day.strftime("%A") not in ("Saturday", "Sunday"):
            for t1h, t2h in [(7.5, 9.0), (15.5, 18.0)]:
                t1 = day + pd.Timedelta(hours=t1h)
                t2 = day + pd.Timedelta(hours=t2h)
                if t2 >= x_start and t1 <= x_end:
                    ax.axvspan(
                        max(t1, x_start), min(t2, x_end),
                        color="red", alpha=0.08, zorder=0,
                    )

    # Optional SD band (zorder=1 — behind the line)
    if add_band and sd_col and sd_col in d.columns:
        s     = d[sd_col].to_numpy(dtype=float)
        lower = y - s
        upper = y + s
        ok    = np.isfinite(lower) & np.isfinite(upper) & np.isfinite(y)
        ax.fill_between(
            x[ok], lower[ok], upper[ok],
            color=line_color, alpha=band_alpha, zorder=1, interpolate=True,
        )

    # Main trend line (zorder=2)
    line_plot, = ax.plot(
        x, y, label=line_label, color=line_color, linewidth=2, zorder=2
    )

    # Day labels and dividers (zorder=3 — on top)
    y_label_pos = ymax - (ymax - ymin) * 0.06
    for i, day in enumerate(days):
        # Weekday name at noon of each day
        noon = day + pd.Timedelta(hours=12)
        if x_start <= noon <= x_end:
            ax.text(
                noon, y_label_pos, day.strftime("%A"),
                color="black", fontsize=14, fontweight="semibold",
                ha="center", va="center", zorder=3,
            )
        # Vertical divider and date label at day boundaries (skip first day)
        if i > 0 and x_start < day < x_end:
            ax.axvline(day, color="red", linestyle="--", linewidth=1, zorder=3)
            ax.text(
                day, ymax - (ymax - ymin) * 0.12,
                day.strftime("%Y-%m-%d"),
                color="red", fontsize=11, ha="center", zorder=3,
            )

    # Axes formatting
    ax.set_xlabel("Time Slot", fontsize=20)
    ax.set_ylabel(ylabel, fontsize=20)
    ax.set_ylim(ymin, ymax)
    ax.set_xlim(x_start, x_end)
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=6))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M"))
    plt.xticks(rotation=45, fontsize=12)
    plt.yticks(fontsize=16)
    ax.grid(True, linestyle="--", linewidth=0.5)

    peak_patch = Patch(facecolor="red", alpha=0.08, label="Peak Hours")
    ax.legend(handles=[line_plot, peak_patch], fontsize=16, loc="lower right")

    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=300)
    plt.show()
    plt.close()
    return save_path


# ===========================================================================
# INTERNAL — SHARED ENGINE
# Loads, filters, computes fairness, renders plots.
# All public functions call this with different value-column lists.
# ===========================================================================

def _run_trend(
    *,
    city_key: str,
    output_dir: Union[str, Path],
    metric_input: Union[str, Path, pd.DataFrame, bool, None],
    capacity_input: Union[str, Path, pd.DataFrame, bool, None],
    utility_name: str,
    value_cols: List[str],
    filter_to_capacity_service_area: bool,
    invalid_time_slots: Optional[List[str]],
    group_col_name: str,
    group_infer_fn: Optional[Callable[[str], str]],
    allowed_groups: Optional[Sequence[str]],
    band_alpha: float,
    color_map: Dict[str, str],
) -> Dict:
    """
    Shared engine that every public plot_*_trend() function calls.

    Steps:
        1. Load the metric CSV / folder
        2. Load capacity CSV and derive the service-area tract set
        3. Filter metric data to service-area tracts
        4. Infer / ensure the group column (borough for NYC, Unknown otherwise)
        5. Compute Gini + Alpha per time slot for each value column found
        6. Save the combined fairness CSV
        7. For each metric column: render Mean±SD, Gini, and Alpha plots
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---- Load data ----
    metric_df = _read_csv_or_folder(metric_input)
    cap_df    = _read_csv_or_folder(capacity_input)

    if metric_df is None or metric_df.empty:
        print(f"  [{utility_name}] No data provided — skipping.")
        return {"plot_paths": {}, "results_df": pd.DataFrame()}

    # ---- Service area filter ----
    service_tracts = _service_area_tracts(cap_df, filter_to_capacity_service_area)
    metric_df = _filter_to_service_area(metric_df, service_tracts)

    if metric_df is None or metric_df.empty:
        print(f"  [{utility_name}] No data after service-area filter — skipping.")
        return {"plot_paths": {}, "results_df": pd.DataFrame()}

    # ---- Default allowed_groups for NYC ----
    if allowed_groups is None and "NYC" in city_key.upper():
        allowed_groups = _NYC_ALLOWED_GROUPS

    # ---- Ensure group column ----
    metric_df = _ensure_group_column(
        metric_df, city_key, group_col_name, group_infer_fn, allowed_groups
    )

    # ---- Detect time and group columns ----
    _, time_col, group_col = _detect_cols(metric_df)
    if time_col is None:
        raise ValueError(
            f"[{utility_name}] Could not find a time column. "
            f"Expected one of: {_TIME_CANDIDATES}"
        )
    if group_col is None:
        # After _ensure_group_column the group column has the user-supplied name
        group_col = group_col_name

    # ---- Compute fairness metrics ----
    parts = _compute_fairness_timeseries(
        df=metric_df,
        utility_name=utility_name,
        value_cols=value_cols,
        time_col=time_col,
        group_col=group_col,
        group_col_name=group_col_name,
        allowed_groups=allowed_groups,
        invalid_time_slots=invalid_time_slots,
    )

    if not parts:
        print(f"  [{utility_name}] None of the expected columns found — skipping.")
        return {"plot_paths": {}, "results_df": pd.DataFrame()}

    results_df = pd.concat(parts, ignore_index=True)
    results_df["Time Slot"] = pd.to_datetime(results_df["Time Slot"], errors="coerce")
    results_df = results_df.dropna(subset=["Time Slot"]).sort_values("Time Slot")

    # Save fairness numbers CSV
    csv_path = out_dir / f"{city_key}__{utility_name.lower().replace(' ', '_')}_trend.csv"
    results_df.to_csv(csv_path, index=False)
    print(f"  [{utility_name}] Fairness CSV saved: {csv_path}")

    system_label = "Docked System" if "DOCKED" in city_key.upper() else "Dockless System"
    plot_paths: Dict[str, Optional[str]] = {}

    # ---- Render one set of three plots per metric column ----
    for metric_name in sorted(results_df["Metric"].dropna().unique()):
        dm    = results_df[results_df["Metric"] == metric_name].copy()
        color = _metric_color(metric_name, color_map)

        # Build a filesystem-safe filename stem from the metric name
        safe  = (
            metric_name
            .replace(" ", "_")
            .replace("(", "")
            .replace(")", "")
            .replace("/", "_")
        )

        # Plot 1 — Mean ± SD
        p1 = str(out_dir / f"MeanSD_Overall_{safe}.png")
        plot_paths[f"{metric_name}::MeanSD"] = _render_trend_plot(
            df_plot=dm,
            time_col="Time Slot",
            y_col="Mean",
            sd_col="SD",
            title=f"Mean ± SD — {metric_name} ({system_label})",
            ylabel="Mean ± SD",
            line_label=f"Mean ± SD — {metric_name}",
            line_color=color,
            save_path=p1,
            invalid_time_slots=invalid_time_slots,
            add_band=True,
            band_alpha=band_alpha,
        )

        # Plot 2 — Gini Coefficient
        p2 = str(out_dir / f"Gini_Overall_{safe}.png")
        plot_paths[f"{metric_name}::Gini"] = _render_trend_plot(
            df_plot=dm,
            time_col="Time Slot",
            y_col="Gini Coefficient",
            sd_col=None,
            title=f"Gini — {metric_name} ({system_label})",
            ylabel="Gini Coefficient",
            line_label=f"Gini — {metric_name}",
            line_color=color,
            save_path=p2,
            invalid_time_slots=invalid_time_slots,
            add_band=False,
        )

        # Plot 3 — Alpha Fairness
        p3 = str(out_dir / f"AlphaFairness_Overall_{safe}.png")
        plot_paths[f"{metric_name}::Alpha"] = _render_trend_plot(
            df_plot=dm,
            time_col="Time Slot",
            y_col="Alpha Fairness (α=1)",
            sd_col=None,
            title=f"Alpha Fairness — {metric_name} ({system_label})",
            ylabel="Alpha Fairness (α=1)",
            line_label=f"Alpha Fairness — {metric_name}",
            line_color=color,
            save_path=p3,
            invalid_time_slots=invalid_time_slots,
            add_band=False,
        )

        print(f"  [{utility_name}] Plots saved for: {metric_name}")

    return {"plot_paths": plot_paths, "results_df": results_df}


# ===========================================================================
# PUBLIC FUNCTIONS
# ===========================================================================

def plot_availability_trend(
    *,
    city_key:           str,
    output_dir:         Union[str, Path],
    availability_input: Union[str, Path, pd.DataFrame, bool, None],
    capacity_input:     Union[str, Path, pd.DataFrame, bool, None] = False,
    filter_to_capacity_service_area: bool = True,
    invalid_time_slots: Optional[List[str]] = None,
    group_col_name:     str = "Boro",
    group_infer_fn:     Optional[Callable[[str], str]] = None,
    allowed_groups:     Optional[Sequence[str]] = None,
    value_cols:         Optional[List[str]] = None,
    band_alpha:         float = 0.20,
) -> Dict:
    """
    Plot Mean±SD, Gini, and Alpha Fairness trends for availability.

    Parameters
    ----------
    city_key           : city/system identifier (e.g. "NYC_DOCKED")
    output_dir         : folder where PNGs and CSV are saved
    availability_input : CSV path, folder path, DataFrame, or False to skip
    capacity_input     : capacity CSV used to define the service area
    filter_to_capacity_service_area : if True, only tracts with capacity > 0
                         are included in the fairness computation
    invalid_time_slots : list of ISO timestamps to exclude (e.g. data gaps)
    group_col_name     : column name for the grouping variable (default "Boro")
    group_infer_fn     : custom function to infer group from tract GEOID;
                         defaults to NYC borough lookup for NYC city keys
    allowed_groups     : only keep these group values; defaults to all 5 NYC
                         boroughs for NYC city keys
    value_cols         : override which columns to process; defaults to all
                         recognised availability column names
    band_alpha         : transparency of the ±SD shaded band

    Returns
    -------
    dict with keys:
        plot_paths  — {metric::MeanSD: path, metric::Gini: path, ...}
        results_df  — fairness numbers DataFrame
    """
    color_map = _build_color_map(city_key)
    return _run_trend(
        city_key=city_key,
        output_dir=output_dir,
        metric_input=availability_input,
        capacity_input=capacity_input,
        utility_name="Availability",
        value_cols=value_cols or _DEFAULT_AVAILABILITY_COLS,
        filter_to_capacity_service_area=filter_to_capacity_service_area,
        invalid_time_slots=invalid_time_slots,
        group_col_name=group_col_name,
        group_infer_fn=group_infer_fn,
        allowed_groups=allowed_groups,
        band_alpha=band_alpha,
        color_map=color_map,
    )


def plot_usage_trend(
    *,
    city_key:       str,
    output_dir:     Union[str, Path],
    usage_input:    Union[str, Path, pd.DataFrame, bool, None],
    capacity_input: Union[str, Path, pd.DataFrame, bool, None] = False,
    filter_to_capacity_service_area: bool = True,
    invalid_time_slots: Optional[List[str]] = None,
    group_col_name: str = "Boro",
    group_infer_fn: Optional[Callable[[str], str]] = None,
    allowed_groups: Optional[Sequence[str]] = None,
    value_cols:     Optional[List[str]] = None,
    band_alpha:     float = 0.20,
) -> Dict:
    """
    Plot Mean±SD, Gini, and Alpha Fairness trends for usage (trips).

    Parameters
    ----------
    city_key       : city/system identifier (e.g. "NYC_DOCKED")
    output_dir     : folder where PNGs and CSV are saved
    usage_input    : CSV path, folder path, DataFrame, or False to skip
    capacity_input : capacity CSV used to define the service area
    (all other parameters — see plot_availability_trend docstring)

    Returns
    -------
    dict with keys: plot_paths, results_df
    """
    color_map = _build_color_map(city_key)
    return _run_trend(
        city_key=city_key,
        output_dir=output_dir,
        metric_input=usage_input,
        capacity_input=capacity_input,
        utility_name="Usage",
        value_cols=value_cols or _DEFAULT_USAGE_COLS,
        filter_to_capacity_service_area=filter_to_capacity_service_area,
        invalid_time_slots=invalid_time_slots,
        group_col_name=group_col_name,
        group_infer_fn=group_infer_fn,
        allowed_groups=allowed_groups,
        band_alpha=band_alpha,
        color_map=color_map,
    )


def plot_idle_time_trend(
    *,
    city_key:         str,
    output_dir:       Union[str, Path],
    idle_time_input:  Union[str, Path, pd.DataFrame, bool, None],
    capacity_input:   Union[str, Path, pd.DataFrame, bool, None] = False,
    filter_to_capacity_service_area: bool = True,
    invalid_time_slots: Optional[List[str]] = None,
    group_col_name:   str = "Boro",
    group_infer_fn:   Optional[Callable[[str], str]] = None,
    allowed_groups:   Optional[Sequence[str]] = None,
    value_cols:       Optional[List[str]] = None,
    band_alpha:       float = 0.20,
) -> Dict:
    """
    Plot Mean±SD, Gini, and Alpha Fairness trends for idle time.

    Parameters
    ----------
    city_key        : city/system identifier (e.g. "NYC_DOCKED")
    output_dir      : folder where PNGs and CSV are saved
    idle_time_input : CSV path, folder path, DataFrame, or False to skip
    capacity_input  : capacity CSV used to define the service area
    (all other parameters — see plot_availability_trend docstring)

    Returns
    -------
    dict with keys: plot_paths, results_df
    """
    color_map = _build_color_map(city_key)
    return _run_trend(
        city_key=city_key,
        output_dir=output_dir,
        metric_input=idle_time_input,
        capacity_input=capacity_input,
        utility_name="Idle Time",
        value_cols=value_cols or _DEFAULT_IDLE_COLS,
        filter_to_capacity_service_area=filter_to_capacity_service_area,
        invalid_time_slots=invalid_time_slots,
        group_col_name=group_col_name,
        group_infer_fn=group_infer_fn,
        allowed_groups=allowed_groups,
        band_alpha=band_alpha,
        color_map=color_map,
    )


def plot_all(
    *,
    city_key:           str,
    output_dir:         Union[str, Path],
    capacity_input:     Union[str, Path, pd.DataFrame, bool, None] = False,
    availability_input: Union[str, Path, pd.DataFrame, bool, None] = False,
    usage_input:        Union[str, Path, pd.DataFrame, bool, None] = False,
    idle_time_input:    Union[str, Path, pd.DataFrame, bool, None] = False,
    filter_to_capacity_service_area: bool = True,
    invalid_time_slots: Optional[List[str]] = None,
    group_col_name:     str = "Boro",
    group_infer_fn:     Optional[Callable[[str], str]] = None,
    allowed_groups:     Optional[Sequence[str]] = None,
    band_alpha:         float = 0.20,
) -> Dict:
    """
    Run all three trend plots (availability, usage, idle time) in one call.

    This is a convenience wrapper — it calls plot_availability_trend(),
    plot_usage_trend(), and plot_idle_time_trend() in sequence, passing
    the same shared parameters to each.  Pass False for any metric you
    want to skip.

    Parameters
    ----------
    city_key           : city/system identifier (e.g. "NYC_DOCKED")
    output_dir         : folder where all PNGs and CSVs are saved
    capacity_input     : capacity CSV used to define the service area
    availability_input : availability CSV / folder / False
    usage_input        : usage CSV / folder / False
    idle_time_input    : idle-time CSV / folder / False
    filter_to_capacity_service_area : only include tracts with capacity > 0
    invalid_time_slots : ISO timestamps to exclude from all metrics
    group_col_name     : grouping column name (default "Boro")
    group_infer_fn     : custom group inference function
    allowed_groups     : filter to these group values
    band_alpha         : ±SD band transparency

    Returns
    -------
    dict with keys:
        availability — result dict from plot_availability_trend
        usage        — result dict from plot_usage_trend
        idle_time    — result dict from plot_idle_time_trend
    """
    print(f"\n[{city_key}] Running plot_all trend visualizations...")

    shared = dict(
        city_key=city_key,
        output_dir=output_dir,
        capacity_input=capacity_input,
        filter_to_capacity_service_area=filter_to_capacity_service_area,
        invalid_time_slots=invalid_time_slots,
        group_col_name=group_col_name,
        group_infer_fn=group_infer_fn,
        allowed_groups=allowed_groups,
        band_alpha=band_alpha,
    )

    avail_result = plot_availability_trend(
        availability_input=availability_input, **shared
    )
    usage_result = plot_usage_trend(
        usage_input=usage_input, **shared
    )
    idle_result  = plot_idle_time_trend(
        idle_time_input=idle_time_input, **shared
    )

    print(f"[{city_key}] All trend plots complete. Outputs in: {Path(output_dir)}")
    return {
        "availability": avail_result,
        "usage":        usage_result,
        "idle_time":    idle_result,
    }


if __name__ == "__main__":
    print("trend_visual module loaded successfully.")