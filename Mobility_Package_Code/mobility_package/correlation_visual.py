"""
=============================================================================
FAIRNESS CORRELATION MAP VISUALIZATION
=============================================================================

OVERVIEW
--------
This module produces four-category correlation maps that compare two bike
share utility metrics against each other at the census tract level.

Every tract is placed into one of four quadrants based on whether its
value for each metric is above or below a threshold:

    High X + High Y  —  both metrics are high
    High X + Low Y   —  first metric high, second low
    Low X  + High Y  —  first metric low, second high
    Low X  + Low Y   —  both metrics are low

AVAILABLE METRICS
-----------------
    "availability"  - vehicle availability per tract
    "usage"         - trips starting per tract
    "idle_time"     - average idle time per tract
    "safety"        - bike lane ratio per tract

HOW TO USE
----------
    plot_correlation(
        metric_x="availability",
        csv_x=r"path/to/availability_norm_tract.csv",
        metric_y="usage",
        csv_y=r"path/to/usage_norm_hourly_tract.csv",
        capacity_csv=r"path/to/capacity_tract_norm.csv",
        tract_shp=r"path/to/tract.shp",
        output_dir="CORRELATION_MAPS_OUT",
    )

    Any two metrics can be compared — just swap metric_x, csv_x,
    metric_y, csv_y. Everything else is handled automatically.

NOTES
-----
    - capacity_csv and tract_shp are always required — they define
      which census tracts appear in the map.
    - Thresholds default to the median (0.5 quantile) of each metric
      across all tracts. Override with threshold if needed.
    - All styling is fixed and consistent across every map.
    - Maps are saved as high-resolution PNG files in output_dir.
=============================================================================
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Union

import contextily as ctx
import geopandas as gpd
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Circle, FancyArrow, Rectangle


# ===========================================================================
# FIXED STYLING
# Never changes between maps — all outputs are visually consistent.
# ===========================================================================

_STYLE = {
    "figsize":              (10, 10),
    "edgecolor":            "black",
    "linewidth":            0.25,
    "alpha":                0.92,
    "add_basemap":          True,
    "add_compass":          True,
    "add_scalebar":         True,
    "scalebar_segments_km": (0, 2, 5),
    "dpi":                  300,
    "title_fontsize":       13,
    "legend_fontsize":      10,
}

# Four-category color palette — colorblind friendly blue-orange scheme
# Keys are category codes 1-4, consistent across every map
_CATEGORY_COLORS = {
    1: "#2166AC",   # High X + High Y  (dark blue)
    2: "#67A9CF",   # High X + Low Y   (light blue)
    3: "#FDAE61",   # Low X  + High Y  (light orange)
    4: "#D6604D",   # Low X  + Low Y   (dark orange/red)
}

# NYC borough GEOID prefixes — tracts outside these are excluded
_NYC_BOROUGH_PREFIXES = ("36061", "36047", "36081", "36005")

# Per-metric defaults: (default value column, short display label)
_METRIC_CONFIG = {
    "availability": ("total_vehicle_available_norm", "Availability"),
    "usage":        ("trips_starting_norm",          "Usage"),
    "idle_time":    ("avg_idle_time_norm",            "Idle Time"),
    "safety":       ("bike_lane_ratio_norm",          "Safety"),
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


def _compute_threshold(series: pd.Series, method: str, value: float) -> float:
    """
    Compute the threshold used to split tracts into high and low groups.

    Parameters
    ----------
    series : the metric values across all tracts
    method : "quantile" uses a percentile of the data e.g. 0.5 = median
             "absolute" uses the value directly
    value  : quantile (0-1) or absolute cutoff depending on method
    """
    if method == "quantile":
        return float(series.quantile(value))
    elif method == "absolute":
        return float(value)
    else:
        raise ValueError("threshold_method must be 'quantile' or 'absolute'")


def _assign_categories(
    gdf: gpd.GeoDataFrame,
    x_col: str,
    y_col: str,
    x_thr: float,
    y_thr: float,
    x_label: str,
    y_label: str,
) -> gpd.GeoDataFrame:
    """
    Assign each tract to one of four categories based on whether its
    x and y metric values are above or below their respective thresholds.

    Category codes:
        1 = High X + High Y
        2 = High X + Low Y
        3 = Low X  + High Y
        4 = Low X  + Low Y
    """
    x_high = gdf[x_col] >= x_thr
    y_high = gdf[y_col] >= y_thr

    gdf["category_code"] = np.select(
        [x_high & y_high, x_high & ~y_high, ~x_high & y_high, ~x_high & ~y_high],
        [1, 2, 3, 4],
        default=0,
    ).astype(int)

    # build category labels dynamically from the metric names
    gdf["category_label"] = gdf["category_code"].map({
        1: f"High {x_label} + High {y_label}",
        2: f"High {x_label} + Low {y_label}",
        3: f"Low {x_label} + High {y_label}",
        4: f"Low {x_label} + Low {y_label}",
    })

    # drop any rows that didn't fall into a valid category
    return gdf[gdf["category_code"].isin([1, 2, 3, 4])].copy()


def _add_compass(ax: plt.Axes, xlim: tuple, ylim: tuple) -> None:
    """Draw a compass rose in the upper-right corner of the map."""
    width  = xlim[1] - xlim[0]
    height = ylim[1] - ylim[0]
    cx     = xlim[0] + 0.88 * width
    cy     = ylim[0] + 0.88 * height
    R      = 0.075 * min(width, height)

    ax.add_patch(Circle((cx, cy), R,        facecolor="white", edgecolor="black", linewidth=1.1, zorder=10))
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

    ax.text(x0,             y0 - 0.012 * height, f"{segments_km[0]}",    ha="center", va="top",    fontsize=10, zorder=12)
    ax.text(x0 + seg1_m,    y0 - 0.012 * height, f"{segments_km[1]} km", ha="center", va="top",    fontsize=10, zorder=12)
    ax.text(x0 + total_m,   y0 - 0.012 * height, f"{segments_km[2]} km", ha="center", va="top",    fontsize=10, zorder=12)
    ax.text(x0 + total_m/2, y0 + bar_h + 0.008 * height, "Scale",        ha="center", va="bottom", fontsize=10, zorder=12)


def _render_correlation_map(
    gdf_web: gpd.GeoDataFrame,
    x_label: str,
    y_label: str,
    x_thr: float,
    y_thr: float,
    threshold_method: str,
    threshold: float,
    out_path: Path,
) -> Path:
    """
    Render the four-category correlation map and save it to disk.

    Parameters
    ----------
    gdf_web          : GeoDataFrame in EPSG:3857 with category_code and
                       category_label columns already assigned
    x_label          : display name of the x metric e.g. "Availability"
    y_label          : display name of the y metric e.g. "Usage"
    x_thr            : computed threshold value for the x metric
    y_thr            : computed threshold value for the y metric
    threshold_method : "quantile" or "absolute"
    threshold        : the threshold parameter the user passed
    out_path         : full path where the PNG will be saved
    """
    xmin, ymin, xmax, ymax = gdf_web.total_bounds
    xlim, ylim = (xmin, xmax), (ymin, ymax)

    fig, ax = plt.subplots(figsize=_STYLE["figsize"])

    gdf_web.plot(
        ax=ax,
        color=gdf_web["category_code"].map(_CATEGORY_COLORS),
        edgecolor=_STYLE["edgecolor"],
        linewidth=_STYLE["linewidth"],
        alpha=_STYLE["alpha"],
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

    # title shows metric names and the threshold values that were used
    ax.set_title(
        f"{x_label} × {y_label} Correlation Map\n"
        f"{x_label} threshold={x_thr:.4f}  |  "
        f"{y_label} threshold={y_thr:.4f}  "
        f"({threshold_method}={threshold})",
        fontsize=_STYLE["title_fontsize"],
        fontweight="bold",
    )
    ax.axis("off")

    # build legend from the category labels present in the data
    category_labels = gdf_web.set_index("category_code")["category_label"].to_dict()
    handles = [
        mpatches.Patch(color=_CATEGORY_COLORS[k], label=category_labels[k])
        for k in sorted(category_labels)
    ]
    ax.legend(
        handles=handles,
        loc="upper left",
        frameon=True,
        fontsize=_STYLE["legend_fontsize"],
        title="Categories",
    )

    plt.savefig(out_path, dpi=_STYLE["dpi"], bbox_inches="tight")
    plt.close(fig)
    print(f"   -> Saved: {out_path}")
    return out_path


# ===========================================================================
# PUBLIC FUNCTION
# One function that handles any metric pair combination.
# ===========================================================================

def plot_correlation(
    *,
    metric_x: str,
    csv_x: Union[str, Path],
    metric_y: str,
    csv_y: Union[str, Path],
    capacity_csv: Union[str, Path],
    tract_shp: Union[str, Path],
    output_dir: Union[str, Path],
    value_col_x: Optional[str] = None,
    value_col_y: Optional[str] = None,
    agg: str = "mean",
    threshold_method: str = "quantile",
    threshold: float = 0.5,
    tract_col: str = "census_tract",
    shp_geoid_col: str = "GEOID",
    time_col: str = "time_slot",
    station_count_col: str = "num_station",
    min_stations: int = 1,
    gate_col: str = "total_capacity_norm",
    drop_zeros: bool = True,
) -> Dict[str, object]:
    """
    Create a four-category correlation map comparing two metrics.

    Every census tract is colored based on whether its value for each
    metric is above or below the threshold — producing four quadrants:
    High/High, High/Low, Low/High, Low/Low.

    Parameters
    ----------
    metric_x          : first metric to compare —
                        "availability", "usage", "idle_time", or "safety"
    csv_x             : path to the norm tract CSV for metric_x
    metric_y          : second metric to compare —
                        "availability", "usage", "idle_time", or "safety"
    csv_y             : path to the norm tract CSV for metric_y
    capacity_csv      : path to the capacity tract norm CSV
                        (defines which tracts are included in the map)
    tract_shp         : path to the census tract shapefile
    output_dir        : folder where the PNG will be saved
    value_col_x       : column to use from csv_x — if not provided the
                        default for metric_x is used automatically
    value_col_y       : column to use from csv_y — if not provided the
                        default for metric_y is used automatically
    agg               : how to summarize each metric across time slots —
                        "mean", "median", "sum", "max", or "min"
    threshold_method  : how to compute the high/low split —
                        "quantile" splits at a percentile of the data
                        "absolute" uses the threshold value directly
    threshold         : quantile (0-1) or absolute value for the split
                        applied to both metrics
                        default is 0.5 which splits at the median

    Returns
    -------
    dict with keys:
        png_path               : Path to the saved PNG file
        x_threshold_value      : computed threshold value for metric_x
        y_threshold_value      : computed threshold value for metric_y
        metric_x               : name of the x metric
        metric_y               : name of the y metric
    """
    # validate metric names
    for m, name in [(metric_x, "metric_x"), (metric_y, "metric_y")]:
        if m not in _METRIC_CONFIG:
            raise ValueError(
                f"Unknown {name} '{m}'. "
                f"Valid options: {list(_METRIC_CONFIG.keys())}"
            )

    if metric_x == metric_y:
        raise ValueError(
            f"metric_x and metric_y must be different. Both are '{metric_x}'."
        )

    # resolve value columns and display labels from config
    default_col_x, x_label = _METRIC_CONFIG[metric_x]
    default_col_y, y_label = _METRIC_CONFIG[metric_y]
    value_col_x = value_col_x or default_col_x
    value_col_y = value_col_y or default_col_y

    print(f"Plotting {x_label} × {y_label} correlation map...")

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

    # aggregate each metric CSV to one value per tract
    x_agg, x_col = _aggregate_metric(csv_x, value_col_x, tract_col, time_col, agg)
    y_agg, y_col = _aggregate_metric(csv_y, value_col_y, tract_col, time_col, agg)

    # merge both metrics onto the geometry
    gdf = base_gdf.merge(x_agg, left_on=shp_geoid_col, right_on=tract_col, how="left")
    gdf = gdf.merge(y_agg, left_on=shp_geoid_col, right_on=tract_col, how="left")
    gdf = gdf.dropna(subset=[x_col, y_col]).copy()

    if gdf.empty:
        raise ValueError(
            f"No tracts have non-null values for both '{x_col}' and '{y_col}'. "
            f"Check that CSV tract IDs match the shapefile."
        )

    # compute thresholds and assign the four categories
    x_thr = _compute_threshold(gdf[x_col], threshold_method, threshold)
    y_thr = _compute_threshold(gdf[y_col], threshold_method, threshold)

    gdf = _assign_categories(gdf, x_col, y_col, x_thr, y_thr, x_label, y_label)

    gdf_web  = gdf if gdf.crs.to_epsg() == 3857 else gdf.to_crs(epsg=3857)
    out_path = out_dir / f"correlation_{metric_x}_vs_{metric_y}__{agg}__{threshold_method}.png"

    _render_correlation_map(
        gdf_web=gdf_web,
        x_label=x_label,
        y_label=y_label,
        x_thr=x_thr,
        y_thr=y_thr,
        threshold_method=threshold_method,
        threshold=threshold,
        out_path=out_path,
    )

    return {
        "png_path":          out_path,
        "x_threshold_value": x_thr,
        "y_threshold_value": y_thr,
        "metric_x":          metric_x,
        "metric_y":          metric_y,
    }


if __name__ == "__main__":
    print("correlation_visual module loaded successfully")