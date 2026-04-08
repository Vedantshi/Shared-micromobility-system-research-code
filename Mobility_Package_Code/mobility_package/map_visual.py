"""
=============================================================================
FAIRNESS TREND MAP VISUALIZATION
=============================================================================

OVERVIEW
--------
This module provides simple map visualization functions for docked and
dockless bike share utility metrics. Each call to plot_map() produces
one map from one input file.

AVAILABLE METRICS
-----------------
    "availability"  - vehicle availability rank by census tract
    "usage"         - usage (trips starting) rank by census tract
    "idle_time"     - idle time rank by census tract
    "safety"        - bike lane safety rank by census tract

HOW TO USE
----------
    Single metric:
        plot_map(
            metric="availability",
            csv=r"path/to/availability_norm_tract.csv",
            capacity_csv=r"path/to/capacity_tract_norm.csv",
            tract_shp=r"path/to/tract.shp",
            output_dir="maps_out",
        )

    All metrics at once:
        plot_all(
            availability_csv=r"path/to/availability_norm_tract.csv",
            usage_csv=r"path/to/usage_norm_hourly_tract.csv",
            idle_time_csv=r"path/to/idle_time_norm_tract.csv",
            safety_csv=r"path/to/safety_bike_lane_norm_tract.csv",
            capacity_csv=r"path/to/capacity_tract_norm.csv",
            tract_shp=r"path/to/tract.shp",
            output_dir="maps_out",
        )

NOTES
-----
    - capacity_csv and tract_shp are always required — they define which
      census tracts appear in every map.
    - All styling (colormap, basemap, compass, scalebar) is fixed and
      consistent across every map so outputs are always comparable.
    - Maps are saved as high-resolution PNG files in output_dir.
    - The value column is auto-detected per metric. Override with value_col
      if your CSV uses a different column name.
=============================================================================
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Union

import contextily as ctx
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Circle, FancyArrow, Rectangle


# ===========================================================================
# FIXED STYLING
# Never changes between maps — all outputs are visually consistent
# and directly comparable without the user needing to set anything.
# ===========================================================================

_STYLE = {
    "figsize":              (10, 10),
    "cmap":                 "RdYlBu",
    "edgecolor":            "black",
    "linewidth":            0.30,
    "alpha":                0.90,
    "legend_loc":           "upper left",
    "add_basemap":          True,
    "add_compass":          True,
    "add_scalebar":         True,
    "scalebar_segments_km": (0, 2, 5),
    "dpi":                  300,
}

# NYC borough GEOID prefixes — tracts outside these are excluded
_NYC_BOROUGH_PREFIXES = ("36061", "36047", "36081", "36005")

# ===========================================================================
# COLUMN INFERENCE
# Resolves capacity column names automatically for both docked and dockless.
# Docked:   station_count → num_station   |  gate → total_capacity_norm
# Dockless: station_count → vehicle_capacity | gate → vehicle_capacity_norm
# Any future system whose columns are semantically named will also work.
# ===========================================================================

# Keywords used to identify station/vehicle count columns (not normalised)
_COUNT_KEYWORDS    = ["num_station", "station", "vehicle_capacity", "total_capacity"]
_COUNT_EXCLUDES    = ["norm", "dock", "occupancy", "pressure", "rate"]

# Keywords used to identify the gate (normalised capacity) column
_GATE_KEYWORDS     = ["capacity_norm", "vehicle_capacity_norm", "total_capacity_norm"]
_GATE_EXCLUDES     = ["dock", "occupancy", "pressure", "rate", "num_station"]


def _resolve_capacity_cols(
    cap_df: pd.DataFrame,
    requested_count_col: str,
    requested_gate_col: str,
) -> tuple[str, str]:
    """
    Return the best (station_count_col, gate_col) pair for this capacity CSV.

    If the originally requested columns exist, they are returned unchanged.
    Otherwise the function scans all columns and picks the best semantic
    match using keyword scoring — so it works automatically for both
    docked (num_station / total_capacity_norm) and dockless
    (vehicle_capacity / vehicle_capacity_norm) CSVs, and for any future
    system whose columns are descriptively named.
    """
    cols = list(cap_df.columns)

    def _best(keywords, excludes, fallback):
        # Return requested col if present, otherwise score all columns.
        if fallback in cols:
            return fallback
        scored = []
        for c in cols:
            cl = c.lower()
            if any(ex in cl for ex in excludes):
                continue
            score = sum(1 for kw in keywords if kw in cl)
            if score > 0:
                scored.append((score, c))
        if scored:
            return max(scored)[1]
        return None

    count_col = _best(_COUNT_KEYWORDS, _COUNT_EXCLUDES, requested_count_col)
    gate_col  = _best(_GATE_KEYWORDS,  _GATE_EXCLUDES,  requested_gate_col)

    return count_col, gate_col


def _resolve_value_col(
    df: pd.DataFrame,
    metric: str,
    requested_col: str,
) -> str:
    """
    Return the best normalised value column for a given metric.

    If the requested column exists it is returned unchanged. Otherwise
    the function scans all columns using metric-specific keywords so it
    works automatically for both docked and dockless CSVs.

    Docked vs dockless differences resolved here:
        availability: total_vehicle_available_norm → total_available_norm
        usage:        trips_starting_norm          → trips_starting_norm / starts_norm
        idle_time:    avg_idle_time_norm            → avg_idle_time_minutes_norm
        safety:       bike_lane_ratio_norm          (same in both)
    """
    cols = list(df.columns)

    if requested_col in cols:
        return requested_col

    # Metric-specific keyword profiles: (must_contain, must_not_contain)
    profiles = {
        "availability": (["available", "norm"],      ["dock", "bike", "ebike", "station"]),
        "usage":        (["start", "norm"],           ["end", "time", "station"]),
        "idle_time":    (["idle", "norm"],            ["segment", "count", "ping"]),
        "safety":       (["bike", "lane", "norm"],    ["protect"]),
    }

    must, must_not = profiles.get(metric, (["norm"], []))
    scored = []
    for c in cols:
        cl = c.lower()
        if any(ex in cl for ex in must_not):
            continue
        score = sum(1 for kw in must if kw in cl)
        if score > 0:
            scored.append((score, c))

    if scored:
        chosen = max(scored)[1]
        print(f"   -> value_col '{requested_col}' not found. "
              f"Auto-selected '{chosen}' for {metric}.")
        return chosen

    raise KeyError(
        f"Could not find a suitable value column for metric '{metric}'. "
        f"Requested '{requested_col}'. Available columns: {cols}"
    )

# Per-metric defaults: (default value column, map title, output filename stem)
_METRIC_CONFIG = {
    "availability": (
        "total_vehicle_available_norm",
        "Vehicle Availability Rank by Census Tract",
        "availability_rank",
    ),
    "usage": (
        "trips_starting_norm",
        "Usage (Trips Starting) Rank by Census Tract",
        "usage_rank",
    ),
    "idle_time": (
        "avg_idle_time_norm",
        "Idle Time Rank by Census Tract",
        "idle_time_rank",
    ),
    "safety": (
        "bike_lane_ratio_norm",
        "Bike Lane Safety Rank by Census Tract",
        "safety_rank",
    ),
}


# ===========================================================================
# INTERNAL HELPERS
# All shared logic lives here. Not meant to be called by the user directly.
# ===========================================================================

def _to_geoid11(s: pd.Series) -> pd.Series:
    """Normalize census tract IDs to 11-character zero-padded strings."""
    return (
        s.astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.replace(r"\s+", "", regex=True)
        .str.zfill(11)
    )


def _build_tract_universe(
    capacity_csv: Union[str, Path],
    tract_shp: Union[str, Path],
    tract_col: str,
    shp_geoid_col: str,
    station_count_col: str,
    min_stations: int,
    gate_col: str,
    drop_zeros: bool,
) -> gpd.GeoDataFrame:
    """
    Build the filtered GeoDataFrame that every map uses as its base.
    Works for both docked and dockless capacity CSVs — column names
    are resolved automatically if the defaults are not present.
    """
    cap_raw = pd.read_csv(capacity_csv)

    if tract_col not in cap_raw.columns:
        raise KeyError(
            f"capacity_csv is missing tract column '{tract_col}'. "
            f"Available columns: {list(cap_raw.columns)}"
        )

    # Auto-resolve station count and gate columns for this CSV
    count_col, gate_col = _resolve_capacity_cols(cap_raw, station_count_col, gate_col)

    cap_raw[tract_col] = _to_geoid11(cap_raw[tract_col])

    # Build tract universe — for dockless (no station count) include all tracts
    if count_col:
        cap = cap_raw.groupby(tract_col, as_index=False).agg(
            {count_col: "sum", **({gate_col: "mean"} if gate_col else {})}
        )
        tract_universe = cap.loc[
            cap[count_col].fillna(0) >= min_stations, tract_col
        ].unique()
    else:
        cap = cap_raw.groupby(tract_col, as_index=False).mean(numeric_only=True)
        tract_universe = cap[tract_col].unique()

    if len(tract_universe) == 0:
        raise ValueError(
            f"No tracts found after capacity filtering. "
            f"Check your capacity_csv or lower min_stations."
        )

    # Load shapefile and apply city-aware borough filter
    tracts = gpd.read_file(tract_shp)
    if shp_geoid_col not in tracts.columns:
        raise KeyError(
            f"tract_shp is missing column '{shp_geoid_col}'. "
            f"Available columns: {list(tracts.columns)}"
        )

    tracts[shp_geoid_col] = _to_geoid11(tracts[shp_geoid_col])

    # Only apply NYC borough filter when the shapefile contains NYC tracts
    has_nyc = tracts[shp_geoid_col].str.startswith(_NYC_BOROUGH_PREFIXES).any()
    if has_nyc:
        tracts = tracts[tracts[shp_geoid_col].str.startswith(_NYC_BOROUGH_PREFIXES)].copy()

    tracts = tracts[tracts[shp_geoid_col].isin(tract_universe)].copy()

    if tracts.empty:
        raise ValueError(
            "No tracts remain after capacity filtering. "
            "Check that GEOID formats match between the shapefile and capacity_csv."
        )

    # Merge capacity onto geometry
    agg_cols = {c: ("sum" if c == count_col else "mean")
                for c in [count_col, gate_col] if c}
    cap_agg = cap_raw.groupby(tract_col, as_index=False).agg(agg_cols) if agg_cols else cap_raw

    gdf = tracts.merge(cap_agg, left_on=shp_geoid_col, right_on=tract_col, how="left")

    # Apply gate filter only if we have a gate column
    if gate_col and gate_col in gdf.columns:
        gdf = gdf.dropna(subset=[gate_col]).copy()
        if drop_zeros:
            gdf = gdf[gdf[gate_col] > 0].copy()

    if gdf.empty:
        raise ValueError(
            "No tracts remain after gate filtering. Try drop_zeros=False to debug."
        )

    return gdf.to_crs(epsg=3857)


def _aggregate_metric(
    csv: Union[str, Path],
    value_col: str,
    tract_col: str,
    time_col: str,
    agg: str,
    metric: str = "",
) -> tuple[pd.DataFrame, str]:
    """
    Load a metric CSV and reduce it to one value per tract.
    Value column is auto-resolved if the default is not present in the CSV.
    """
    df = pd.read_csv(csv)

    if tract_col not in df.columns:
        raise KeyError(
            f"CSV is missing tract column '{tract_col}'. "
            f"Available columns: {list(df.columns)}"
        )

    valid_aggs = {"mean", "median", "sum", "max", "min"}
    if agg not in valid_aggs:
        raise ValueError(f"agg must be one of: {sorted(valid_aggs)}")

    # Auto-resolve the value column for this metric and CSV
    value_col = _resolve_value_col(df, metric, value_col)

    if time_col in df.columns:
        df[time_col] = pd.to_datetime(df[time_col], errors="coerce")

    df[tract_col] = _to_geoid11(df[tract_col])

    aggregated = getattr(df.groupby(tract_col)[value_col], agg)()
    agg_col    = f"{value_col}__{agg}"

    return aggregated.reset_index().rename(columns={value_col: agg_col}), agg_col


def _add_decile_labels(gdf: gpd.GeoDataFrame, value_col: str) -> str:
    """
    Assign each tract to a percentile decile bucket based on its rank.
    Returns the name of the new decile column.
    """
    decile_col = f"{value_col}__decile"
    pct        = gdf[value_col].rank(pct=True, method="average")
    bins       = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    labels     = [
        "1-10%",  "11-20%", "21-30%", "31-40%", "41-50%",
        "51-60%", "61-70%", "71-80%", "81-90%", "91-100%",
    ]
    gdf[decile_col] = pd.cut(pct, bins=bins, labels=labels, include_lowest=True)
    return decile_col


def _add_compass(ax: plt.Axes, xlim: tuple, ylim: tuple) -> None:
    """Draw a compass rose in the upper-right corner of the map."""
    width  = xlim[1] - xlim[0]
    height = ylim[1] - ylim[0]
    cx     = xlim[0] + 0.88 * width
    cy     = ylim[0] + 0.88 * height
    R      = 0.075 * min(width, height)

    ax.add_patch(Circle((cx, cy), R,        facecolor="white", edgecolor="black", linewidth=1.2, zorder=10))
    ax.add_patch(Circle((cx, cy), R * 0.88, facecolor="white", edgecolor="black", linewidth=0.8, zorder=11))

    ax.text(cx, cy + R + 0.012 * height, "N", ha="center", va="bottom", fontsize=12, fontweight="bold", zorder=12)
    ax.text(cx, cy - R - 0.012 * height, "S", ha="center", va="top",    fontsize=10, zorder=12)
    ax.text(cx - R - 0.006 * width, cy,  "W", ha="right",  va="center", fontsize=10, zorder=12)
    ax.text(cx + R + 0.006 * width, cy,  "E", ha="left",   va="center", fontsize=10, zorder=12)

    ax.add_patch(FancyArrow(
        cx, cy - 0.18 * R, 0, 0.72 * R,
        width=0.0, head_width=0.22 * R, head_length=0.28 * R,
        length_includes_head=True, facecolor="black", edgecolor="black", zorder=13,
    ))


def _add_scalebar(ax: plt.Axes, xlim: tuple, ylim: tuple) -> None:
    """Draw a scale bar in the lower-right area of the map."""
    segments_km = _STYLE["scalebar_segments_km"]
    width       = xlim[1] - xlim[0]
    height      = ylim[1] - ylim[0]
    x0          = xlim[0] + 0.72 * width
    y0          = ylim[0] + 0.06 * height
    bar_h       = 0.012 * height
    total_m     = segments_km[-1] * 1000.0
    seg1_m      = (segments_km[1] - segments_km[0]) * 1000.0
    seg2_m      = (segments_km[2] - segments_km[1]) * 1000.0

    ax.add_patch(Rectangle((x0,          y0), seg1_m, bar_h, facecolor="black", edgecolor="black", linewidth=0.8, zorder=10))
    ax.add_patch(Rectangle((x0 + seg1_m, y0), seg2_m, bar_h, facecolor="white", edgecolor="black", linewidth=0.8, zorder=10))

    for x in [x0, x0 + seg1_m, x0 + total_m]:
        ax.plot([x, x], [y0, y0 + bar_h], color="black", linewidth=1.0, zorder=11)

    ax.text(x0,              y0 - 0.012 * height, f"{segments_km[0]}",    ha="center", va="top",    fontsize=10, zorder=12)
    ax.text(x0 + seg1_m,     y0 - 0.012 * height, f"{segments_km[1]} km", ha="center", va="top",    fontsize=10, zorder=12)
    ax.text(x0 + total_m,    y0 - 0.012 * height, f"{segments_km[2]} km", ha="center", va="top",    fontsize=10, zorder=12)
    ax.text(x0 + total_m/2,  y0 + bar_h + 0.008 * height, "Scale",        ha="center", va="bottom", fontsize=10, zorder=12)


def _render_map(
    gdf_web: gpd.GeoDataFrame,
    value_col: str,
    title: str,
    out_path: Path,
) -> Path:
    """
    Render a decile rank choropleth map and save it to disk.

    Parameters
    ----------
    gdf_web   : GeoDataFrame in EPSG:3857 with the metric column attached
    value_col : column containing the aggregated metric values
    title     : map title shown at the top
    out_path  : full path where the PNG will be saved
    """
    tmp = gdf_web.dropna(subset=[value_col]).copy()
    if tmp.empty:
        raise ValueError(
            f"No non-null values to plot for '{value_col}'. "
            f"Check that CSV tract IDs match the shapefile."
        )

    decile_col          = _add_decile_labels(tmp, value_col)
    xmin, ymin, xmax, ymax = tmp.total_bounds
    xlim, ylim          = (xmin, xmax), (ymin, ymax)

    fig, ax = plt.subplots(figsize=_STYLE["figsize"])

    tmp.plot(
        ax=ax,
        column=decile_col,
        categorical=True,
        legend=True,
        cmap=_STYLE["cmap"],
        edgecolor=_STYLE["edgecolor"],
        linewidth=_STYLE["linewidth"],
        alpha=_STYLE["alpha"],
        legend_kwds={"loc": _STYLE["legend_loc"]},
    )

    ax.set_xlim(xlim)
    ax.set_ylim(ylim)

    if _STYLE["add_basemap"]:
        ctx.add_basemap(ax, source=ctx.providers.OpenStreetMap.Mapnik)
        ax.set_xlim(xlim)
        ax.set_ylim(ylim)

    if _STYLE["add_compass"]:
        _add_compass(ax, xlim, ylim)

    if _STYLE["add_scalebar"]:
        _add_scalebar(ax, xlim, ylim)

    ax.set_title(title, fontsize=15, fontweight="bold")
    ax.axis("off")

    plt.savefig(out_path, dpi=_STYLE["dpi"], bbox_inches="tight")
    plt.close(fig)
    print(f"   -> Saved: {out_path}")
    return out_path


# ===========================================================================
# PUBLIC FUNCTIONS
# ===========================================================================

def plot_map(
    *,
    metric: str,
    csv: Union[str, Path],
    capacity_csv: Union[str, Path],
    tract_shp: Union[str, Path],
    output_dir: Union[str, Path],
    value_col: Optional[str] = None,
    agg: str = "mean",
    tract_col: str = "census_tract",
    shp_geoid_col: str = "GEOID",
    time_col: str = "time_slot",
    station_count_col: str = "num_station",
    min_stations: int = 1,
    gate_col: str = "total_capacity_norm",
    drop_zeros: bool = True,
) -> Path:
    """
    Create a rank map for a single metric.

    Parameters
    ----------
    metric        : which metric to map —
                    "availability", "usage", "idle_time", or "safety"
    csv           : path to the metric norm tract CSV for that metric
    capacity_csv  : path to the capacity tract norm CSV
                    (defines which tracts are included in the map)
    tract_shp     : path to the census tract shapefile
    output_dir    : folder where the PNG will be saved
    value_col     : column to visualize — if not provided the default
                    for the chosen metric is used automatically
    agg           : how to summarize across time slots —
                    "mean", "median", "sum", "max", or "min"

    Returns
    -------
    Path to the saved PNG file
    """
    if metric not in _METRIC_CONFIG:
        raise ValueError(
            f"Unknown metric '{metric}'. "
            f"Valid options: {list(_METRIC_CONFIG.keys())}"
        )

    default_col, title, filename_stem = _METRIC_CONFIG[metric]
    value_col = value_col or default_col

    print(f"Plotting {metric} map...")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # build the filtered tract geometry using capacity as the universe
    base_gdf = _build_tract_universe(
        capacity_csv=capacity_csv,
        tract_shp=tract_shp,
        tract_col=tract_col,
        shp_geoid_col=shp_geoid_col,
        station_count_col=station_count_col,
        min_stations=min_stations,
        gate_col=gate_col,
        drop_zeros=drop_zeros,
    )

    # aggregate the metric CSV to one value per tract
    metric_agg, agg_col = _aggregate_metric(
        csv=csv,
        value_col=value_col,
        tract_col=tract_col,
        time_col=time_col,
        agg=agg,
        metric=metric,
    )

    # merge metric onto geometry and reproject for basemap
    gdf     = base_gdf.merge(metric_agg, left_on=shp_geoid_col, right_on=tract_col, how="left")
    gdf_web = gdf if gdf.crs.to_epsg() == 3857 else gdf.to_crs(epsg=3857)

    out_path = out_dir / f"{filename_stem}__{agg}.png"

    return _render_map(gdf_web, agg_col, title, out_path)


def plot_all(
    *,
    availability_csv: Union[str, Path],
    usage_csv: Union[str, Path],
    idle_time_csv: Union[str, Path],
    safety_csv: Union[str, Path],
    capacity_csv: Union[str, Path],
    tract_shp: Union[str, Path],
    output_dir: Union[str, Path],
    availability_value_col: Optional[str] = None,
    usage_value_col: Optional[str] = None,
    idle_time_value_col: Optional[str] = None,
    safety_value_col: Optional[str] = None,
    agg: str = "mean",
    tract_col: str = "census_tract",
    shp_geoid_col: str = "GEOID",
    time_col: str = "time_slot",
    station_count_col: str = "num_station",
    min_stations: int = 1,
    gate_col: str = "total_capacity_norm",
    drop_zeros: bool = True,
) -> Dict[str, Path]:
    """
    Produce all four maps in one call.

    Parameters
    ----------
    availability_csv  : path to the availability norm tract CSV
    usage_csv         : path to the usage norm hourly tract CSV
    idle_time_csv     : path to the idle time norm tract CSV
    safety_csv        : path to the safety bike lane norm tract CSV
    capacity_csv      : path to the capacity tract norm CSV
                        (defines which tracts are included in every map)
    tract_shp         : path to the census tract shapefile
    output_dir        : folder where all four PNGs will be saved
    agg               : how to summarize across time slots for all maps —
                        "mean", "median", "sum", "max", or "min"

    Returns
    -------
    dict with keys "availability", "usage", "idle_time", "safety"
    each containing the Path to the saved PNG
    """
    # shared arguments passed to every plot_map call
    shared = dict(
        capacity_csv=capacity_csv,
        tract_shp=tract_shp,
        output_dir=output_dir,
        agg=agg,
        tract_col=tract_col,
        shp_geoid_col=shp_geoid_col,
        time_col=time_col,
        station_count_col=station_count_col,
        min_stations=min_stations,
        gate_col=gate_col,
        drop_zeros=drop_zeros,
    )

    return {
        "availability": plot_map(metric="availability", csv=availability_csv, value_col=availability_value_col, **shared),
        "usage":        plot_map(metric="usage",        csv=usage_csv,        value_col=usage_value_col,        **shared),
        "idle_time":    plot_map(metric="idle_time",    csv=idle_time_csv,    value_col=idle_time_value_col,     **shared),
        "safety":       plot_map(metric="safety",       csv=safety_csv,       value_col=safety_value_col,        **shared),
    }


if __name__ == "__main__":
    print("map_visual module loaded successfully")