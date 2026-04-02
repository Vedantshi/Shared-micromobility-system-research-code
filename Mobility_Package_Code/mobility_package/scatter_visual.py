"""
=============================================================================
SCATTER PLOT VISUALIZATION — SUPPLY / DEMAND CLASSIFICATION
=============================================================================

OVERVIEW
--------
This module takes three tract-level CSVs (availability, usage, idle time),
aggregates them if they contain hourly/time-slot rows, classifies every
census tract into one of four supply-demand categories, and produces two
side-by-side scatter plots:

    Plot 1 — Availability (supply) vs Usage (demand)
    Plot 2 — Usage vs Idle Time

The classification uses percentile-based thresholds on availability and
usage to decide whether a tract has too many bikes, too few, or is well
balanced.

AVAILABLE CATEGORIES AND THEIR COLORS
--------------------------------------
    Undersupply             — red    — low supply  + high demand
    Oversupply              — orange — high supply + low demand
    High demand + high supply — green — both high (busy but well served)
    Balanced / Other        — blue   — everything that doesn't fit above

THRESHOLD METHODS
-----------------
Three modes are available, controlled by `threshold_method`:

    "median"   — simple 50/50 split on both axes.
                 One threshold line per axis.

    "quantile" — two cutoffs per axis expressed as fractions 0.0–1.0.
                 e.g. quantiles=(0.3, 0.7) means the bottom 30 % is "low"
                 and the top 30 % is "high"; the middle 40 % is "middle
                 band" and is classified as Balanced / Other.

    "percent"  — same as "quantile" but expressed in 0–100 for readability.
                 With use_symmetric_percentiles=True you only need to set
                 two values (availability_low_pct and usage_high_pct) and
                 the other two are derived automatically.

HOW TO USE
----------
    from mobility_package import scatter_visual

    scatter_visual.plot_scatter(
        availability_csv = r"path/to/availability_norm_tract.csv",
        usage_csv        = r"path/to/usage_norm_hourly_tract.csv",
        idle_csv         = r"path/to/idle_time_norm_tract.csv",
        output_dir       = "SCATTER_OUT",
        threshold_method = "percent",
        availability_low_pct = 30,
        usage_high_pct       = 70,
    )

OUTPUTS
-------
    scatter_supply_demand.png             — two side-by-side scatter plots
    tract_supply_demand_classification.csv — one row per tract with raw
                                             values, percentile ranks,
                                             pressure score, category, notes
    classification_summary_counts.csv     — tract count per category

RETURNS
-------
    (master_df, class_df, fig)
        master_df — merged tract-level DataFrame with every computed field
        class_df  — professor-facing subset with categories and notes
        fig       — matplotlib Figure object (None if make_plots=False)

NOTES
-----
    - Column-name defaults match the NYC docked-station tract files.
      Override them only if your CSVs use different names.
    - Census-tract IDs are normalised to 11-digit zero-padded strings so
      that IDs from different CSVs join correctly even when stored as
      floats or with trailing ".0".
=============================================================================
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple, Union

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


# ===========================================================================
# FIXED STYLING
# Colors and visual properties are constant across every run so that maps
# produced on different days or from different cities remain comparable.
# ===========================================================================

# Maps the simplified plot-group label to a hex/named color.
_GROUP_COLORS: Dict[str, str] = {
    "Undersupply":              "red",
    "Oversupply":               "orange",
    "High demand + high supply": "green",
    "Balanced / Other":         "blue",
}

# Detailed classification label → simplified plot-group label.
# Keeping this mapping explicit makes it easy to add new categories later.
_LABEL_TO_GROUP: Dict[str, str] = {
    "Access-constrained (Undersupply)": "Undersupply",
    "Low-demand (Oversupply)":          "Oversupply",
    "High-demand + High-supply":        "High demand + high supply",
    # everything else falls through to "Balanced / Other"
}

# Fixed plot order — Undersupply and Oversupply are drawn first so they
# sit on top of the larger Balanced cloud and remain clearly visible.
_GROUP_ORDER_BASE = ["Undersupply", "Oversupply", "High demand + high supply", "Balanced / Other"]


# ===========================================================================
# INTERNAL HELPERS
# These small utility functions are not part of the public API.
# ===========================================================================

def _to_geoid11(s: pd.Series) -> pd.Series:
    """
    Normalise a Series of census-tract IDs to 11-character zero-padded
    strings.

    Input values may be stored as ints, floats (with a trailing '.0'),
    or strings with leading/trailing whitespace — all are handled.
    """
    return (
        s.astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)   # drop trailing ".0" from floats
        .str.replace(r"\s+", "", regex=True)     # drop any embedded whitespace
        .str.zfill(11)                            # pad to 11 digits
    )


def _to_numeric(s: pd.Series) -> pd.Series:
    """
    Coerce a Series to float, replacing infinities with NaN so they don't
    corrupt downstream aggregations.
    """
    return pd.to_numeric(s, errors="coerce").replace([np.inf, -np.inf], np.nan)


def _agg_series(s: pd.Series, method: str) -> float:
    """
    Aggregate a numeric Series to a single float using mean / median / sum,
    ignoring NaNs.  Returns NaN for empty input.
    """
    arr = _to_numeric(s).to_numpy()
    if arr.size == 0:
        return np.nan
    if method == "mean":
        return float(np.nanmean(arr))
    if method == "median":
        return float(np.nanmedian(arr))
    return float(np.nansum(arr))   # "sum"


def _rank_pct(s: pd.Series) -> pd.Series:
    """
    Return the percentile rank of each value in a Series (0.0–1.0).
    Ties are broken by averaging ranks.
    """
    return _to_numeric(s).rank(pct=True, method="average")


def _pct_to_quantile(p: float) -> float:
    """
    Convert a user-supplied 0–100 percentile to a 0.0–1.0 quantile for
    numpy.  Validates the range and raises a clear error if out of bounds.
    """
    if not (0.0 <= p <= 100.0):
        raise ValueError(
            f"Percentile must be between 0 and 100, got {p}."
        )
    return p / 100.0


# ===========================================================================
# INTERNAL: THRESHOLD COMPUTATION
# ===========================================================================

def _compute_thresholds(
    x: pd.Series,
    y: pd.Series,
    threshold_method: str,
    quantiles: Tuple[float, float],
    use_symmetric_percentiles: bool,
    availability_low_pct: float,
    availability_high_pct: Optional[float],
    usage_low_pct: Optional[float],
    usage_high_pct: float,
    show_threshold_debug: bool,
) -> Tuple[float, float, float, float, str]:
    """
    Compute the four threshold values (x_low, x_high, y_low, y_high) and
    determine whether we are in "split" mode (one cut per axis) or "band"
    mode (two cuts per axis with a middle buffer zone).

    Returns
    -------
    (x_low, x_high, y_low, y_high, band_mode)
        band_mode is either "split" or "band".
    """
    th = threshold_method.lower().strip()

    if th not in {"median", "quantile", "percent"}:
        raise ValueError(
            f"threshold_method must be 'median', 'quantile', or 'percent'. Got '{th}'."
        )

    # Default — overwritten below for each method
    x_low = x_high = y_low = y_high = np.nan
    band_mode = "split"

    # ------------------------------------------------------------------
    # METHOD 1: median
    # A single threshold per axis at the 50th percentile.
    # A tract is "low" if it falls below the median and "high" if at or
    # above it — no middle buffer zone.
    # ------------------------------------------------------------------
    if th == "median":
        x_low = x_high = float(np.nanmedian(x))
        y_low = y_high = float(np.nanmedian(y))
        band_mode = "split"

        if show_threshold_debug:
            print("[THRESHOLD] method=median")
            print(f"  availability median (50%): {x_low:.6f}")
            print(f"  usage       median (50%): {y_low:.6f}")

    # ------------------------------------------------------------------
    # METHOD 2: quantile
    # Two thresholds per axis expressed as fractions (0.0–1.0).
    # Values below q_low  → "low"
    # Values above q_high → "high"
    # Values in between   → "middle band" (classified as Balanced / Other)
    # ------------------------------------------------------------------
    elif th == "quantile":
        ql, qh = quantiles
        if not (0 < ql < qh < 1):
            raise ValueError(
                "quantiles must satisfy 0 < q_low < q_high < 1, e.g. (0.3, 0.7)."
            )

        x_low  = float(np.nanquantile(x.dropna(), ql))
        x_high = float(np.nanquantile(x.dropna(), qh))
        y_low  = float(np.nanquantile(y.dropna(), ql))
        y_high = float(np.nanquantile(y.dropna(), qh))
        band_mode = "band"

        if show_threshold_debug:
            print("[THRESHOLD] method=quantile")
            print(f"  availability q_low ={ql:.2f}:  {x_low:.6f}")
            print(f"  availability q_high={qh:.2f}: {x_high:.6f}")
            print(f"  usage        q_low ={ql:.2f}:  {y_low:.6f}")
            print(f"  usage        q_high={qh:.2f}: {y_high:.6f}")

    # ------------------------------------------------------------------
    # METHOD 3: percent
    # Same logic as "quantile" but expressed in 0–100 for readability.
    # When use_symmetric_percentiles=True only two values are needed:
    #   availability_low_pct  — below this percentile → "low supply"
    #   usage_high_pct        — above this percentile → "high demand"
    # The other two are derived as their mirrors (100 - value).
    # ------------------------------------------------------------------
    else:  # th == "percent"
        if use_symmetric_percentiles:
            a_low  = availability_low_pct
            u_high = usage_high_pct
            a_high = 100.0 - a_low    # e.g. 30 → 70
            u_low  = 100.0 - u_high   # e.g. 70 → 30
        else:
            # All four values must be supplied explicitly
            if availability_high_pct is None or usage_low_pct is None:
                raise ValueError(
                    "When use_symmetric_percentiles=False you must also provide "
                    "availability_high_pct and usage_low_pct."
                )
            a_low  = availability_low_pct
            a_high = availability_high_pct
            u_low  = usage_low_pct
            u_high = usage_high_pct

        if not (0 <= a_low < a_high <= 100):
            raise ValueError(
                f"Availability percentiles must satisfy 0 <= low < high <= 100. "
                f"Got low={a_low}, high={a_high}."
            )
        if not (0 <= u_low < u_high <= 100):
            raise ValueError(
                f"Usage percentiles must satisfy 0 <= low < high <= 100. "
                f"Got low={u_low}, high={u_high}."
            )

        x_low  = float(np.nanquantile(x.dropna(), _pct_to_quantile(a_low)))
        x_high = float(np.nanquantile(x.dropna(), _pct_to_quantile(a_high)))
        y_low  = float(np.nanquantile(y.dropna(), _pct_to_quantile(u_low)))
        y_high = float(np.nanquantile(y.dropna(), _pct_to_quantile(u_high)))
        band_mode = "band"

        if show_threshold_debug:
            print("[THRESHOLD] method=percent")
            print(f"  availability low ={a_low:.1f}%  -> {x_low:.6f}")
            print(f"  availability high={a_high:.1f}% -> {x_high:.6f}")
            print(f"  usage        low ={u_low:.1f}%  -> {y_low:.6f}")
            print(f"  usage        high={u_high:.1f}% -> {y_high:.6f}")

    return x_low, x_high, y_low, y_high, band_mode


# ===========================================================================
# INTERNAL: TRACT CLASSIFICATION
# ===========================================================================

def _classify_tract(
    availability: float,
    usage: float,
    x_low: float,
    x_high: float,
    y_low: float,
    y_high: float,
    band_mode: str,
) -> str:
    """
    Assign a single tract to one of five classification labels based on
    where its (availability, usage) pair falls relative to the thresholds.

    "split" mode — one cut per axis (from the median method):
        availability < x_low  AND  usage >= y_low  → Undersupply
        availability >= x_low AND  usage <  y_low  → Oversupply
        availability >= x_low AND  usage >= y_low  → High-demand + High-supply
        availability <  x_low AND  usage <  y_low  → Balanced / Low-low

    "band" mode — two cuts per axis (quantile / percent methods):
        availability <= x_low  AND  usage >= y_high → Undersupply
        availability >= x_high AND  usage <= y_low  → Oversupply
        availability >= x_high AND  usage >= y_high → High-demand + High-supply
        availability <= x_low  AND  usage <= y_low  → Balanced / Low-low
        everything else (middle band)               → Balanced (Middle band)
    """
    if pd.isna(availability) or pd.isna(usage):
        return "Insufficient data"

    if band_mode == "split":
        # ---- split mode ----
        if availability < x_low and usage >= y_low:
            return "Access-constrained (Undersupply)"
        if availability >= x_low and usage < y_low:
            return "Low-demand (Oversupply)"
        if availability >= x_low and usage >= y_low:
            return "High-demand + High-supply"
        # remaining: availability < x_low AND usage < y_low
        return "Balanced / Low-low"

    # ---- band mode ----
    if availability <= x_low and usage >= y_high:
        return "Access-constrained (Undersupply)"
    if availability >= x_high and usage <= y_low:
        return "Low-demand (Oversupply)"
    if availability >= x_high and usage >= y_high:
        return "High-demand + High-supply"
    if availability <= x_low and usage <= y_low:
        return "Balanced / Low-low"
    # falls in the middle buffer on at least one axis
    return "Balanced (Middle band)"


# ===========================================================================
# INTERNAL: SCATTER PLOT RENDERING
# ===========================================================================

def _render_scatter_plots(
    class_df: pd.DataFrame,
    group_order: list,
    group_colors: Dict[str, str],
    band_mode: str,
    x_low: float,
    x_high: float,
    y_low: float,
    y_high: float,
    figsize: Tuple[int, int],
    point_size: int,
    alpha: float,
    title: str,
    add_caption: bool,
    include_high_high_group: bool,
) -> plt.Figure:
    """
    Build and return the matplotlib Figure containing the two scatter plots.

    Plot 1 — Availability vs Usage
        Colored by supply-demand category.
        Dashed lines mark the threshold boundaries.

    Plot 2 — Usage vs Idle Time
        Same dot colors as Plot 1 (categories come from the availability /
        usage classification, so idle time is not used for classification —
        it is purely a secondary view of the same tracts).

    The legend is placed on Plot 2 so Plot 1's axes are not obscured.
    """
    fig, axes = plt.subplots(1, 2, figsize=figsize, constrained_layout=True)
    fig.suptitle(title, fontsize=16, fontweight="bold")

    # ------------------------------------------------------------------
    # Plot 1: Availability (supply) on X, Usage (demand) on Y
    # ------------------------------------------------------------------
    ax1 = axes[0]

    for grp in group_order:
        subset = class_df[class_df["plot_group"] == grp]
        if subset.empty:
            continue   # skip a category that has zero tracts
        ax1.scatter(
            subset["availability"],
            subset["usage"],
            s=point_size,
            alpha=alpha,
            label=grp,
            color=group_colors.get(grp, "gray"),
        )

    ax1.set_title("Availability vs Usage", fontweight="bold")
    ax1.set_xlabel("Availability (tract-level, normalised)")
    ax1.set_ylabel("Usage (tract-level, normalised)")
    ax1.grid(True, linestyle=":", linewidth=0.8)

    # Draw dashed threshold lines so the viewer can see exactly where the
    # category boundaries are.
    if band_mode == "split":
        # One vertical line (availability cut) + one horizontal line (usage cut)
        ax1.axvline(x_low, linestyle="--", linewidth=1, color="black", alpha=0.6)
        ax1.axhline(y_low, linestyle="--", linewidth=1, color="black", alpha=0.6)
    else:
        # Two vertical lines + two horizontal lines forming a cross-hatch grid
        ax1.axvline(x_low,  linestyle="--", linewidth=1, color="black", alpha=0.6)
        ax1.axvline(x_high, linestyle="--", linewidth=1, color="black", alpha=0.6)
        ax1.axhline(y_low,  linestyle="--", linewidth=1, color="black", alpha=0.6)
        ax1.axhline(y_high, linestyle="--", linewidth=1, color="black", alpha=0.6)

    # ------------------------------------------------------------------
    # Plot 2: Usage on X, Idle Time on Y
    # Colors are inherited from the same classification — idle time itself
    # does not affect the categories, but seeing it here shows whether
    # undersupplied or oversupplied tracts also have unusual idle patterns.
    # ------------------------------------------------------------------
    ax2 = axes[1]

    for grp in group_order:
        subset = class_df[class_df["plot_group"] == grp]
        if subset.empty:
            continue
        ax2.scatter(
            subset["usage"],
            subset["idle_time"],
            s=point_size,
            alpha=alpha,
            label=grp,
            color=group_colors.get(grp, "gray"),
        )

    ax2.set_title("Usage vs Idle Time", fontweight="bold")
    ax2.set_xlabel("Usage (tract-level, normalised)")
    ax2.set_ylabel("Idle Time (tract-level, normalised)")
    ax2.grid(True, linestyle=":", linewidth=0.8)

    # Legend goes on Plot 2 — it is less likely to overlap with the data
    # cluster in the bottom-left corner of the usage/idle-time plot.
    ax2.legend(loc="best", fontsize=9, frameon=True)

    # ------------------------------------------------------------------
    # Optional caption below both plots
    # ------------------------------------------------------------------
    if add_caption:
        caption_parts = [
            "Each dot is a census tract (hourly/time-slot values aggregated to tract-level). ",
            "Supply-demand classes use percentile thresholds on availability (supply) and usage (demand). ",
            "Colors: Undersupply=red, Oversupply=orange, Balanced=blue",
        ]
        if include_high_high_group:
            caption_parts.append(", High demand + high supply=green")
        caption_parts.append(".")
        fig.text(
            0.5, -0.02,
            "".join(caption_parts),
            ha="center", va="top", fontsize=10, wrap=True,
        )

    return fig


# ===========================================================================
# PUBLIC FUNCTION
# This is the only entry point users need to call.
# ===========================================================================

def plot_scatter(
    *,
    # ---- required CSVs ----
    availability_csv: Union[str, Path],
    usage_csv:        Union[str, Path],
    idle_csv:         Union[str, Path],

    # ---- column names (defaults match NYC docked tract files) ----
    tract_col:        str = "census_tract",
    availability_col: str = "total_vehicle_available_norm",
    usage_col:        str = "trips_starting_norm",   # alternatively "trips_ending_norm"
    idle_col:         str = "avg_idle_time_norm",

    # ---- aggregation (if CSVs have one row per time slot per tract) ----
    agg_method: str = "mean",   # "mean" | "median" | "sum"

    # ---- threshold method ----
    threshold_method: str = "percent",   # "median" | "quantile" | "percent"

    # For "quantile" method — fractions in 0.0–1.0
    quantiles: Tuple[float, float] = (0.3, 0.7),

    # For "percent" method — integers / floats in 0–100
    # With use_symmetric_percentiles=True only two values are needed:
    #   availability_low_pct  → tracts below this percentile are "low supply"
    #   usage_high_pct        → tracts above this percentile are "high demand"
    # The other two cutoffs are derived: high = 100 - low, low = 100 - high.
    use_symmetric_percentiles: bool    = True,
    availability_low_pct:      float   = 30.0,
    availability_high_pct:     Optional[float] = None,
    usage_low_pct:             Optional[float] = None,
    usage_high_pct:            float   = 70.0,

    # ---- pressure score denominator protection ----
    # A tiny epsilon is added to availability before dividing so we never
    # divide by zero when computing the usage-over-supply pressure ratio.
    eps: float = 1e-9,

    # ---- plot settings ----
    make_plots: bool            = True,
    figsize:    Tuple[int, int] = (13, 6),
    point_size: int             = 18,
    alpha:      float           = 0.65,
    title:      str             = "Scatter Plots of Bike Sharing Metrics",
    add_caption: bool           = True,

    # When True, prints the numeric threshold values to the console so
    # you can verify the cuts make sense before interpreting the plot.
    show_threshold_debug: bool = True,

    # ---- category options ----
    # Set to False to merge "High demand + high supply" into "Balanced / Other"
    # if your research treats it as uninteresting.
    include_high_high_group: bool = True,

    # Individual color overrides (rarely needed — defaults match the
    # standard palette used across the whole project)
    color_undersupply: str = "red",
    color_oversupply:  str = "orange",
    color_balanced:    str = "blue",
    color_high_high:   str = "green",

    # ---- output paths ----
    output_dir:                 Optional[Union[str, Path]] = None,
    save_classification_csv:    bool = True,
    classification_csv_name:    str  = "tract_supply_demand_classification.csv",
    save_plot_png:              bool = True,
    plot_png_name:              str  = "scatter_supply_demand.png",
    dpi:                        int  = 300,
) -> Tuple[pd.DataFrame, pd.DataFrame, Optional[plt.Figure]]:
    """
    Classify every census tract into a supply-demand category and produce
    two side-by-side scatter plots.

    Parameters
    ----------
    availability_csv : path to the normalised availability tract CSV
    usage_csv        : path to the normalised usage tract CSV
    idle_csv         : path to the normalised idle-time tract CSV
    tract_col        : name of the census-tract ID column (all three CSVs)
    availability_col : value column in availability_csv
    usage_col        : value column in usage_csv
    idle_col         : value column in idle_csv
    agg_method       : how to collapse multiple rows per tract —
                       "mean" (default) | "median" | "sum"
    threshold_method : "median" | "quantile" | "percent"
                       controls how high/low thresholds are computed
    quantiles        : (q_low, q_high) used when threshold_method="quantile"
    use_symmetric_percentiles : derive the two missing percentile values
                                automatically (see module docstring)
    availability_low_pct  : 0–100 cutoff for "low supply"
    availability_high_pct : 0–100 cutoff for "high supply" (auto if symmetric)
    usage_low_pct         : 0–100 cutoff for "low demand"  (auto if symmetric)
    usage_high_pct        : 0–100 cutoff for "high demand"
    eps              : tiny offset to avoid division by zero in pressure ratio
    make_plots       : set False to skip plot generation (CSV outputs still work)
    figsize          : (width, height) in inches
    point_size       : scatter dot size in points²
    alpha            : dot transparency (0=invisible, 1=opaque)
    title            : figure suptitle
    add_caption      : add an explanatory caption below the plots
    show_threshold_debug : print numeric threshold values to console
    include_high_high_group : include the "High demand + high supply" category
    color_undersupply / color_oversupply / color_balanced / color_high_high :
                       matplotlib color strings for each category
    output_dir       : folder where outputs are saved (created if absent)
    save_classification_csv : write the per-tract CSV
    classification_csv_name : filename for the per-tract CSV
    save_plot_png    : write the scatter plot PNG
    plot_png_name    : filename for the PNG
    dpi              : image resolution

    Returns
    -------
    master_df : pd.DataFrame
        Full merged DataFrame with every computed column (availability,
        usage, idle_time, percentile ranks, pressure score, category).
    class_df : pd.DataFrame
        Researcher-facing subset — the same data but trimmed to the most
        useful columns plus readable category labels and notes.
    fig : plt.Figure or None
        The matplotlib Figure (None if make_plots=False).
    """

    # ------------------------------------------------------------------
    # Step 0 — Validate the aggregation method early so we fail fast
    # ------------------------------------------------------------------
    agg_method_l = agg_method.lower().strip()
    if agg_method_l not in {"mean", "median", "sum"}:
        raise ValueError(
            f"agg_method must be 'mean', 'median', or 'sum'. Got '{agg_method}'."
        )

    print(f"Loading CSVs and aggregating to tract level (agg_method='{agg_method_l}')...")

    # ------------------------------------------------------------------
    # Step 1 — Load CSVs and validate required columns
    # ------------------------------------------------------------------
    avail_df = pd.read_csv(availability_csv)
    usage_df  = pd.read_csv(usage_csv)
    idle_df   = pd.read_csv(idle_csv)

    # Check that the tract-ID column exists in every file
    for name, df in [("availability", avail_df), ("usage", usage_df), ("idle", idle_df)]:
        if tract_col not in df.columns:
            raise KeyError(
                f"The {name} CSV is missing the tract column '{tract_col}'. "
                f"Available columns: {list(df.columns)}"
            )

    # Check that the value columns exist
    if availability_col not in avail_df.columns:
        raise KeyError(
            f"availability_csv is missing column '{availability_col}'. "
            f"Available: {list(avail_df.columns)}"
        )
    if usage_col not in usage_df.columns:
        raise KeyError(
            f"usage_csv is missing column '{usage_col}'. "
            f"Available: {list(usage_df.columns)}"
        )
    if idle_col not in idle_df.columns:
        raise KeyError(
            f"idle_csv is missing column '{idle_col}'. "
            f"Available: {list(idle_df.columns)}"
        )

    # ------------------------------------------------------------------
    # Step 2 — Normalise tract IDs to consistent 11-digit strings
    # This ensures the three DataFrames join correctly even when IDs
    # are stored as floats in one file and strings in another.
    # ------------------------------------------------------------------
    avail_df[tract_col] = _to_geoid11(avail_df[tract_col])
    usage_df[tract_col]  = _to_geoid11(usage_df[tract_col])
    idle_df[tract_col]   = _to_geoid11(idle_df[tract_col])

    # ------------------------------------------------------------------
    # Step 3 — Aggregate each metric to one value per census tract
    # Each CSV may have many rows per tract (one per hour / time-slot).
    # We reduce them to a single representative value using the chosen
    # aggregation method.
    # ------------------------------------------------------------------
    avail_tract = (
        avail_df
        .groupby(tract_col, as_index=False)[availability_col]
        .apply(lambda s: _agg_series(s, agg_method_l))
        .rename(columns={availability_col: "availability"})
    )

    usage_tract = (
        usage_df
        .groupby(tract_col, as_index=False)[usage_col]
        .apply(lambda s: _agg_series(s, agg_method_l))
        .rename(columns={usage_col: "usage"})
    )

    idle_tract = (
        idle_df
        .groupby(tract_col, as_index=False)[idle_col]
        .apply(lambda s: _agg_series(s, agg_method_l))
        .rename(columns={idle_col: "idle_time"})
    )

    # Outer-join all three so tracts present in only some files still appear
    # (they will have NaN for the missing metric and be labelled
    # "Insufficient data" during classification)
    master = (
        avail_tract
        .merge(usage_tract, on=tract_col, how="outer")
        .merge(idle_tract,  on=tract_col, how="outer")
    )

    print(f"  Tracts after aggregation: {len(master)}")

    # ------------------------------------------------------------------
    # Step 4 — Compute thresholds
    # ------------------------------------------------------------------
    x_low, x_high, y_low, y_high, band_mode = _compute_thresholds(
        x=master["availability"],
        y=master["usage"],
        threshold_method=threshold_method,
        quantiles=quantiles,
        use_symmetric_percentiles=use_symmetric_percentiles,
        availability_low_pct=availability_low_pct,
        availability_high_pct=availability_high_pct,
        usage_low_pct=usage_low_pct,
        usage_high_pct=usage_high_pct,
        show_threshold_debug=show_threshold_debug,
    )

    # ------------------------------------------------------------------
    # Step 5 — Classify each tract
    # ------------------------------------------------------------------
    # Pressure ratio: usage / availability — high values flag tracts that
    # are heavily used relative to their bike stock.
    master["pressure_usage_over_supply"] = (
        master["usage"] / (master["availability"] + eps)
    )

    # Percentile ranks (0.0–1.0) for every metric so the CSV is easy to
    # interpret and sort without knowing the raw normalised scale.
    master["availability_pct"] = _rank_pct(master["availability"])
    master["usage_pct"]        = _rank_pct(master["usage"])
    master["idle_time_pct"]    = _rank_pct(master["idle_time"])
    master["pressure_pct"]     = _rank_pct(master["pressure_usage_over_supply"])

    # Apply the classify function row-by-row
    master["supply_demand_class"] = master.apply(
        lambda row: _classify_tract(
            row["availability"], row["usage"],
            x_low, x_high, y_low, y_high, band_mode,
        ),
        axis=1,
    )

    # Boolean convenience flags for quick filtering
    master["is_undersupply"] = master["supply_demand_class"].eq(
        "Access-constrained (Undersupply)"
    )
    master["is_oversupply"] = master["supply_demand_class"].eq(
        "Low-demand (Oversupply)"
    )

    # Human-readable explanation note attached to flagged tracts
    master["explain_note"] = np.where(
        master["is_undersupply"],
        "High usage with low availability suggests unmet demand due to limited access.",
        np.where(
            master["is_oversupply"],
            "Low usage despite high availability suggests low demand or oversupply.",
            "",   # Balanced / Other tracts get no note
        ),
    )

    # ------------------------------------------------------------------
    # Step 6 — Build the researcher-facing class_df
    # This is a trimmed, clearly-labelled subset of master intended to be
    # shared with your professor or included in a report.
    # ------------------------------------------------------------------
    class_df = master[[
        tract_col,
        "availability", "usage", "idle_time",
        "availability_pct", "usage_pct", "idle_time_pct",
        "pressure_usage_over_supply", "pressure_pct",
        "supply_demand_class",
        "is_undersupply", "is_oversupply",
        "explain_note",
    ]].copy()

    # Descending ranks so rank=1 means the highest value (most concerning)
    class_df["usage_rank_desc"]        = class_df["usage"].rank(ascending=False, method="min")
    class_df["availability_rank_desc"] = class_df["availability"].rank(ascending=False, method="min")
    class_df["pressure_rank_desc"]     = class_df["pressure_usage_over_supply"].rank(ascending=False, method="min")

    # Summary: how many tracts fall into each category
    summary = (
        class_df["supply_demand_class"]
        .value_counts(dropna=False)
        .rename_axis("supply_demand_class")
        .reset_index(name="tract_count")
    )

    # ------------------------------------------------------------------
    # Step 7 — Map detailed classification labels → simplified plot groups
    # The detailed labels ("Access-constrained (Undersupply)") are kept
    # in class_df for the CSV output.  The simpler labels ("Undersupply")
    # are used on the plot legend.
    # ------------------------------------------------------------------
    def _to_plot_group(label: str) -> str:
        return _LABEL_TO_GROUP.get(label, "Balanced / Other")

    class_df["plot_group"] = class_df["supply_demand_class"].map(_to_plot_group)

    # Build the ordered group list — include or exclude the High/High group
    # depending on the user's preference.
    group_order = ["Undersupply", "Oversupply"]
    if include_high_high_group:
        group_order.append("High demand + high supply")
    group_order.append("Balanced / Other")

    # Convert to an ordered Categorical so pandas respects the draw order
    class_df["plot_group"] = pd.Categorical(
        class_df["plot_group"],
        categories=group_order,
        ordered=True,
    )

    # Assemble the color map from the user's color arguments
    group_colors: Dict[str, str] = {
        "Undersupply":               color_undersupply,
        "Oversupply":                color_oversupply,
        "Balanced / Other":          color_balanced,
        "High demand + high supply": color_high_high,
    }

    print("\nClassification summary:")
    for _, row in summary.iterrows():
        print(f"  {row['supply_demand_class']}: {row['tract_count']} tracts")

    # ------------------------------------------------------------------
    # Step 8 — Render plots
    # ------------------------------------------------------------------
    fig = None
    if make_plots:
        print("\nRendering scatter plots...")
        fig = _render_scatter_plots(
            class_df=class_df,
            group_order=group_order,
            group_colors=group_colors,
            band_mode=band_mode,
            x_low=x_low,
            x_high=x_high,
            y_low=y_low,
            y_high=y_high,
            figsize=figsize,
            point_size=point_size,
            alpha=alpha,
            title=title,
            add_caption=add_caption,
            include_high_high_group=include_high_high_group,
        )

    # ------------------------------------------------------------------
    # Step 9 — Save outputs
    # ------------------------------------------------------------------
    if output_dir is not None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        if save_classification_csv:
            # Per-tract classification table
            csv_path = out / classification_csv_name
            class_df.to_csv(csv_path, index=False)
            print(f"   -> Saved classification CSV: {csv_path}")

            # Category count summary
            summary_path = out / "classification_summary_counts.csv"
            summary.to_csv(summary_path, index=False)
            print(f"   -> Saved summary CSV:        {summary_path}")

        if make_plots and save_plot_png and fig is not None:
            png_path = out / plot_png_name
            fig.savefig(png_path, dpi=dpi, bbox_inches="tight")
            print(f"   -> Saved scatter PNG:        {png_path}")

    return master, class_df, fig


if __name__ == "__main__":
    print("scatter_visual module loaded successfully.")