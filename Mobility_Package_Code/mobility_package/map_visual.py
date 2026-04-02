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

    Steps:
        1. Load capacity CSV and find tracts with enough stations
        2. Load tract shapefile and filter to NYC boroughs
        3. Keep only tracts that exist in the capacity universe
        4. Apply gate column filter (drop tracts with zero capacity)

    Returns a GeoDataFrame in EPSG:3857 ready for mapping.
    """
    # load capacity and validate required columns
    cap_raw = pd.read_csv(capacity_csv)
    for col in [tract_col, station_count_col, gate_col]:
        if col not in cap_raw.columns:
            raise KeyError(
                f"capacity_csv is missing column '{col}'. "
                f"Available columns: {list(cap_raw.columns)}"
            )

    cap_raw[tract_col] = _to_geoid11(cap_raw[tract_col])
    cap = cap_raw.groupby(tract_col, as_index=False).agg(
        {station_count_col: "sum", gate_col: "mean"}
    )

    tract_universe = cap.loc[
        cap[station_count_col].fillna(0) >= min_stations, tract_col
    ].unique()

    if len(tract_universe) == 0:
        raise ValueError(
            f"No tracts found with {station_count_col} >= {min_stations}. "
            f"Check your capacity_csv or lower min_stations."
        )

    # load shapefile and filter to NYC boroughs and capacity universe
    tracts = gpd.read_file(tract_shp)
    if shp_geoid_col not in tracts.columns:
        raise KeyError(
            f"tract_shp is missing column '{shp_geoid_col}'. "
            f"Available columns: {list(tracts.columns)}"
        )

    tracts[shp_geoid_col] = _to_geoid11(tracts[shp_geoid_col])
    tracts_nyc = tracts[tracts[shp_geoid_col].str.startswith(_NYC_BOROUGH_PREFIXES)].copy()
    tracts_nyc = tracts_nyc[tracts_nyc[shp_geoid_col].isin(tract_universe)].copy()

    if tracts_nyc.empty:
        raise ValueError(
            "No tracts remain after NYC borough and capacity filtering. "
            "Check that GEOID formats match between the shapefile and capacity_csv."
        )

    # merge capacity data onto geometry and apply gate filter
    gdf = tracts_nyc.merge(cap, left_on=shp_geoid_col, right_on=tract_col, how="left")
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
) -> tuple[pd.DataFrame, str]:
    """
    Load a metric CSV and reduce it to one value per tract.

    Returns the aggregated DataFrame and the name of the aggregated column.
    """
    df = pd.read_csv(csv)

    for col in [tract_col, value_col]:
        if col not in df.columns:
            raise KeyError(
                f"CSV is missing column '{col}'. "
                f"Available columns: {list(df.columns)}"
            )

    valid_aggs = {"mean", "median", "sum", "max", "min"}
    if agg not in valid_aggs:
        raise ValueError(f"agg must be one of: {sorted(valid_aggs)}")

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