"""
=============================================================================
CAPACITY MAP VISUALIZATION
=============================================================================

OVERVIEW
--------
This module plots decile choropleth maps of capacity metrics for docked
and dockless bike-share systems at the census-tract level.

Each column requested produces one PNG saved to the output directory.

Every map includes:
    - OpenStreetMap basemap
    - RdYlBu decile choropleth (10 equal-percentile bins)
    - Compass rose (top-right)
    - Scale bar 0-2-5 km (bottom-right)

HOW TO USE
----------
    from mobility_package import capacity_map_visual

    capacity_map_visual.plot_capacity(
        capacity_csv = r"path/to/capacity_tract_norm.csv",
        tract_shp    = r"path/to/tl_2024_42_tract.shp",
        output_dir   = "CAPACITY_MAPS_OUT",
    )

=============================================================================
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Sequence, Union

import contextily as ctx
import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Circle, FancyArrow, Rectangle


# ===========================================================================
# FIXED STYLING — consistent across all capacity maps
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

# NYC borough GEOID prefixes — only applied when the shapefile contains NYC tracts
_NYC_BOROUGH_PREFIXES = ("36061", "36047", "36081", "36005")

# Default capacity columns to map if value_cols is not specified.
# Only columns that actually exist in the CSV are plotted.
# The engine also auto-discovers any extra normalised capacity columns.
_DEFAULT_VALUE_COLS = [
    "total_capacity_norm",
    "vehicle_capacity_norm",
    "dock_capacity_norm",
    "occupancy_rate",
    "return_pressure",
]

# Keywords for auto-resolving the station count column.
# Docked: num_station  |  Dockless: vehicle_capacity
_COUNT_KEYWORDS = ["num_station", "station", "vehicle_capacity", "total_capacity"]
_COUNT_EXCLUDES = ["norm", "dock", "occupancy", "pressure", "rate"]

# Keywords for auto-resolving the gate (normalised capacity) column.
# Docked: total_capacity_norm  |  Dockless: vehicle_capacity_norm
_GATE_KEYWORDS  = ["capacity_norm", "vehicle_capacity_norm", "total_capacity_norm"]
_GATE_EXCLUDES  = ["dock", "occupancy", "pressure", "rate", "num_station"]


# ===========================================================================
# INTERNAL HELPERS
# ===========================================================================

def _to_geoid11(s: pd.Series) -> pd.Series:
    """Normalise census-tract IDs to 11-character zero-padded strings."""
    return (
        s.astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.replace(r"\s+", "", regex=True)
        .str.zfill(11)
    )


def _resolve_capacity_cols(
    cap_df: pd.DataFrame,
    requested_count_col: str,
    requested_gate_col: str,
) -> tuple:
    """
    Return the best (station_count_col, gate_col) pair for this capacity CSV.

    If the requested columns exist they are returned unchanged.
    Otherwise every column is scored using keyword profiles so the
    function works automatically for both docked and dockless CSVs,
    and for any future system whose columns are descriptively named.

    Docked:   num_station / total_capacity_norm
    Dockless: vehicle_capacity / vehicle_capacity_norm
    """
    cols = list(cap_df.columns)

    def _best(keywords, excludes, requested):
        if requested in cols:
            return requested
        scored = [
            (sum(1 for kw in keywords if kw in c.lower()), c)
            for c in cols
            if not any(ex in c.lower() for ex in excludes)
            and sum(1 for kw in keywords if kw in c.lower()) > 0
        ]
        return max(scored)[1] if scored else None

    count_col = _best(_COUNT_KEYWORDS, _COUNT_EXCLUDES, requested_count_col)
    gate_col  = _best(_GATE_KEYWORDS,  _GATE_EXCLUDES,  requested_gate_col)

    return count_col, gate_col


def _discover_value_cols(cap_df: pd.DataFrame) -> list:
    """
    Return all columns in the capacity CSV that look like normalised
    capacity values suitable for mapping.

    Includes both the default list and any extra columns that contain
    'norm', 'rate', or 'pressure' — so new capacity columns added to
    either docked or dockless outputs are picked up automatically.
    """
    found = []
    for col in cap_df.columns:
        cl = col.lower()
        if col in _DEFAULT_VALUE_COLS:
            found.append(col)
            continue
        if ("norm" in cl or "rate" in cl or "pressure" in cl) and (
            "capacity" in cl or "vehicle" in cl or "station" in cl
            or "occupancy" in cl or "return" in cl
        ):
            if col not in found:
                found.append(col)
    return found


def _add_decile_labels(gdf: gpd.GeoDataFrame, value_col: str, label_col: str) -> None:
    """
    Bin tracts into deciles (1-10%, 11-20%, … 91-100%) based on their
    percentile rank for value_col. Adds the label string to label_col.
    """
    pct    = gdf[value_col].rank(pct=True, method="average")
    bins   = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    labels = [
        "1-10%",  "11-20%", "21-30%", "31-40%", "41-50%",
        "51-60%", "61-70%", "71-80%", "81-90%", "91-100%",
    ]
    gdf[label_col] = pd.cut(pct, bins=bins, labels=labels, include_lowest=True)


def _add_compass(ax, xlim: tuple, ylim: tuple) -> None:
    """Draw a compass rose in the top-right corner of the map."""
    w  = xlim[1] - xlim[0]
    h  = ylim[1] - ylim[0]
    cx = xlim[0] + 0.88 * w
    cy = ylim[0] + 0.88 * h
    R  = 0.075 * min(w, h)

    ax.add_patch(Circle((cx, cy), R,        facecolor="white", edgecolor="black", linewidth=1.2, zorder=10))
    ax.add_patch(Circle((cx, cy), R * 0.88, facecolor="white", edgecolor="black", linewidth=0.8, zorder=11))
    ax.text(cx, cy + R + 0.012 * h, "N", ha="center", va="bottom", fontsize=12, fontweight="bold", zorder=12)
    ax.text(cx, cy - R - 0.012 * h, "S", ha="center", va="top",    fontsize=10, zorder=12)
    ax.text(cx - R - 0.006 * w, cy, "W", ha="right",  va="center", fontsize=10, zorder=12)
    ax.text(cx + R + 0.006 * w, cy, "E", ha="left",   va="center", fontsize=10, zorder=12)
    ax.add_patch(FancyArrow(
        cx, cy - 0.18 * R, 0, 0.72 * R,
        width=0.0, head_width=0.22 * R, head_length=0.28 * R,
        length_includes_head=True, facecolor="black", edgecolor="black", zorder=13,
    ))


def _add_scalebar(ax, xlim: tuple, ylim: tuple, segments_km: tuple) -> None:
    """Draw a 0-2-5 km scale bar in the bottom-right area of the map."""
    w       = xlim[1] - xlim[0]
    h       = ylim[1] - ylim[0]
    x0      = xlim[0] + 0.72 * w
    y0      = ylim[0] + 0.06 * h
    bar_h   = 0.012 * h
    total_m = segments_km[-1] * 1_000.0
    seg1_m  = (segments_km[1] - segments_km[0]) * 1_000.0
    seg2_m  = (segments_km[2] - segments_km[1]) * 1_000.0

    ax.add_patch(Rectangle((x0,          y0), seg1_m, bar_h, facecolor="black", edgecolor="black", linewidth=0.8, zorder=10))
    ax.add_patch(Rectangle((x0 + seg1_m, y0), seg2_m, bar_h, facecolor="white", edgecolor="black", linewidth=0.8, zorder=10))
    for xp in [x0, x0 + seg1_m, x0 + total_m]:
        ax.plot([xp, xp], [y0, y0 + bar_h], color="black", linewidth=1.0, zorder=11)
    ax.text(x0,             y0 - 0.012 * h, f"{segments_km[0]}",    ha="center", va="top",    fontsize=10, zorder=12)
    ax.text(x0 + seg1_m,    y0 - 0.012 * h, f"{segments_km[1]} km", ha="center", va="top",    fontsize=10, zorder=12)
    ax.text(x0 + total_m,   y0 - 0.012 * h, f"{segments_km[2]} km", ha="center", va="top",    fontsize=10, zorder=12)
    ax.text(x0 + total_m/2, y0 + bar_h + 0.008 * h, "Scale",        ha="center", va="bottom", fontsize=10, zorder=12)


def _render_capacity_map(
    gdf_web: gpd.GeoDataFrame,
    col: str,
    gate_col: str,
    xlim: tuple,
    ylim: tuple,
    out_path: Path,
) -> Path:
    """
    Render one decile choropleth map for a single capacity column and save it.
    Skips silently if no data remains after dropping NaN.
    """
    tmp = gdf_web.dropna(subset=[col]).copy()
    if tmp.empty:
        print(f"   Skipping '{col}' — no data after dropping NaN.")
        return None

    decile_col = f"{col}_decile"
    _add_decile_labels(tmp, col, decile_col)

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

    # Lock extent before basemap so it does not auto-zoom out
    ax.set_xlim(xlim)
    ax.set_ylim(ylim)

    if _STYLE["add_basemap"]:
        ctx.add_basemap(ax, source=ctx.providers.OpenStreetMap.Mapnik)
        # Re-lock after basemap — it can shift the extent slightly
        ax.set_xlim(xlim)
        ax.set_ylim(ylim)

    if _STYLE["add_compass"]:
        _add_compass(ax, xlim, ylim)

    if _STYLE["add_scalebar"]:
        _add_scalebar(ax, xlim, ylim, _STYLE["scalebar_segments_km"])

    ax.set_title(
        f"Capacity Decile Map — {col}",
        fontsize=13,
        fontweight="bold",
    )
    ax.axis("off")

    plt.savefig(out_path, dpi=_STYLE["dpi"], bbox_inches="tight")
    plt.close(fig)
    print(f"   -> Saved: {out_path}")
    return out_path


# ===========================================================================
# PUBLIC FUNCTION
# ===========================================================================

def plot_capacity(
    *,
    capacity_csv:      Union[str, Path],
    tract_shp:         Union[str, Path],
    output_dir:        Union[str, Path],
    csv_tract_col:     str = "census_tract",
    shp_geoid_col:     str = "GEOID",
    capacity_norm_col: str = "total_capacity_norm",
    station_count_col: str = "num_station",
    min_stations:      int = 1,
    gate_col:          Optional[str] = None,
    drop_zeros:        bool = True,
    value_cols:        Optional[Sequence[str]] = None,
) -> Dict[str, Path]:
    """
    Plot decile choropleth maps for all capacity columns in the capacity CSV.

    Works automatically for both docked and dockless capacity CSVs —
    column names are resolved using keyword scoring so no manual column
    mapping is needed when switching between system types.

    Parameters
    ----------
    capacity_csv      : path to the normalised capacity tract CSV
    tract_shp         : path to the census-tract shapefile
    output_dir        : folder where PNGs are saved (created if absent)
    csv_tract_col     : tract ID column in the capacity CSV
    shp_geoid_col     : tract ID column in the shapefile
    capacity_norm_col : primary normalised capacity column — used as the
                        gate and in the output filename. Auto-resolved if
                        not found in the CSV.
    station_count_col : column holding station/vehicle count per tract —
                        used to define the service area. Auto-resolved if
                        not found in the CSV.
    min_stations      : minimum count for a tract to be included
    gate_col          : tracts where this is NaN/0 are excluded;
                        defaults to capacity_norm_col
    drop_zeros        : also exclude tracts where gate_col == 0
    value_cols        : columns to plot; auto-discovered if not specified

    Returns
    -------
    dict mapping column name → saved PNG path
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Step 1 — Load shapefile and apply city-aware borough filter
    # NYC shapefiles are filtered to the five boroughs. All other cities
    # pass through without any borough filtering.
    # ------------------------------------------------------------------
    tracts = gpd.read_file(str(tract_shp))
    if shp_geoid_col not in tracts.columns:
        raise KeyError(
            f"Shapefile missing column '{shp_geoid_col}'. "
            f"Available: {list(tracts.columns)}"
        )

    tracts[shp_geoid_col] = _to_geoid11(tracts[shp_geoid_col])

    has_nyc = tracts[shp_geoid_col].str.startswith(_NYC_BOROUGH_PREFIXES).any()
    if has_nyc:
        tracts = tracts[
            tracts[shp_geoid_col].str.startswith(_NYC_BOROUGH_PREFIXES)
        ].copy()

    if tracts.empty:
        raise ValueError("No tracts found in shapefile after city filter.")

    # ------------------------------------------------------------------
    # Step 2 — Load capacity CSV and auto-resolve column names
    # ------------------------------------------------------------------
    cap_raw = pd.read_csv(capacity_csv)

    if csv_tract_col not in cap_raw.columns:
        raise KeyError(
            f"capacity_csv missing tract column '{csv_tract_col}'. "
            f"Available: {list(cap_raw.columns)}"
        )

    # Auto-resolve station count and gate columns for this CSV
    count_col, resolved_gate = _resolve_capacity_cols(
        cap_raw, station_count_col, capacity_norm_col
    )
    gate_col = gate_col or resolved_gate or capacity_norm_col

    if count_col:
        print(f"  [capacity_map] Station count column : '{count_col}'")
    if gate_col and gate_col in cap_raw.columns:
        print(f"  [capacity_map] Gate column          : '{gate_col}'")
    else:
        gate_col = None

    cap_raw[csv_tract_col] = _to_geoid11(cap_raw[csv_tract_col])

    # Aggregate to one row per tract — sum counts, mean rates
    agg_rules: Dict = {}
    for c in cap_raw.select_dtypes(include="number").columns:
        cl = c.lower()
        if "capacity" in cl or "station" in cl or "vehicle" in cl:
            agg_rules[c] = "sum"
        else:
            agg_rules[c] = "mean"

    cap = cap_raw.groupby(csv_tract_col, as_index=False).agg(agg_rules)

    # ------------------------------------------------------------------
    # Step 3 — Define service area
    # Docked:   tracts with num_station >= min_stations
    # Dockless: tracts with vehicle_capacity >= min_stations
    # If no count column found: include all tracts
    # ------------------------------------------------------------------
    if count_col and count_col in cap.columns:
        service_tracts = set(
            cap.loc[cap[count_col].fillna(0) >= min_stations, csv_tract_col]
        )
    else:
        service_tracts = set(cap[csv_tract_col].unique())
        print("  [capacity_map] No station count column found — "
              "including all tracts in service area.")

    if not service_tracts:
        raise ValueError(
            "No tracts meet the minimum threshold. "
            "Check station_count_col or lower min_stations."
        )

    # ------------------------------------------------------------------
    # Step 4 — Filter shapefile tracts to service area and merge capacity
    # ------------------------------------------------------------------
    tracts = tracts[tracts[shp_geoid_col].isin(service_tracts)].copy()

    if tracts.empty:
        raise ValueError(
            "No tracts remain after service-area filter. "
            "GEOID formats likely differ between CSV and shapefile."
        )

    gdf = tracts.merge(cap, left_on=shp_geoid_col, right_on=csv_tract_col, how="left")

    if gate_col and gate_col in gdf.columns:
        gdf = gdf.dropna(subset=[gate_col]).copy()
        if drop_zeros:
            gdf = gdf[gdf[gate_col] > 0].copy()

    if gdf.empty:
        raise ValueError(
            f"No rows remain after gate filtering on '{gate_col}'. "
            f"Try drop_zeros=False to debug."
        )

    # ------------------------------------------------------------------
    # Step 5 — Resolve which columns to plot
    # ------------------------------------------------------------------
    if value_cols:
        cols_to_plot = [c for c in value_cols if c in gdf.columns]
    else:
        cols_to_plot = [c for c in _discover_value_cols(cap_raw) if c in gdf.columns]

    if not cols_to_plot:
        raise KeyError(
            f"No plottable capacity columns found. "
            f"Available numeric columns: "
            f"{list(gdf.select_dtypes(include='number').columns)}"
        )

    print(f"  [capacity_map] Columns to plot: {cols_to_plot}")

    # ------------------------------------------------------------------
    # Step 6 — Project to Web Mercator and lock shared extent
    # All maps share the same bounding box so they are visually comparable.
    # ------------------------------------------------------------------
    gdf_web = gdf.to_crs(epsg=3857)
    xmin, ymin, xmax, ymax = gdf_web.total_bounds
    xlim = (xmin, xmax)
    ylim = (ymin, ymax)

    # ------------------------------------------------------------------
    # Step 7 — Render one map per column
    # ------------------------------------------------------------------
    gate_label = gate_col if gate_col else "all_tracts"
    saved: Dict[str, Path] = {}
    for col in cols_to_plot:
        out_path = out_dir / f"{gate_label}_gate__{col}.png"
        result   = _render_capacity_map(gdf_web, col, gate_col or col, xlim, ylim, out_path)
        if result is not None:
            saved[col] = result

    if not saved:
        raise ValueError(
            "No maps were saved — all requested columns were empty after filtering."
        )

    return saved


if __name__ == "__main__":
    print("capacity_map_visual module loaded successfully.")