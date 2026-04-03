"""
=============================================================================
CAPACITY MAP VISUALIZATION
=============================================================================

OVERVIEW
--------
This module plots decile choropleth maps of capacity metrics for docked
bike-share systems at the census-tract level.

It is purpose-built for the docked-system capacity CSV, which contains
one or more normalised capacity columns (total_capacity_norm,
vehicle_capacity_norm, dock_capacity_norm, etc.).  Only tracts that have
at least one bike-share station are shown — the service-area universe is
defined entirely by the capacity CSV, matching the professor's approach.

Each column requested produces one PNG:
    NYC_ONLY_total_capacity_norm_gate__total_capacity_norm.png
    NYC_ONLY_total_capacity_norm_gate__vehicle_capacity_norm.png
    ...

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
        tract_shp    = r"path/to/tl_2024_36_tract.shp",
        output_dir   = "CAPACITY_MAPS_OUT",
    )

=============================================================================
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple, Union

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

# NYC borough GEOID prefixes — tracts outside these are excluded
_NYC_BOROUGH_PREFIXES = ("36061", "36047", "36081", "36005")

# Default capacity columns to map — only those present in the file are used
_DEFAULT_VALUE_COLS = [
    "total_capacity_norm",
    "vehicle_capacity_norm",
    "dock_capacity_norm",
    "occupancy_rate",
    "return_pressure",
]


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


def _add_decile_labels(gdf: gpd.GeoDataFrame, value_col: str, label_col: str) -> None:
    """
    Bin tracts into deciles (1-10%, 11-20%, … 91-100%) based on their
    percentile rank for value_col.  Adds the label string to label_col.
    """
    pct = gdf[value_col].rank(pct=True, method="average")
    bins   = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    labels = [
        "1-10%", "11-20%", "21-30%", "31-40%", "41-50%",
        "51-60%", "61-70%", "71-80%", "81-90%", "91-100%",
    ]
    gdf[label_col] = pd.cut(pct, bins=bins, labels=labels, include_lowest=True)


def _add_compass(ax, xlim: tuple, ylim: tuple) -> None:
    """Draw a compass rose in the top-right corner of the map."""
    w = xlim[1] - xlim[0]
    h = ylim[1] - ylim[0]
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
    w = xlim[1] - xlim[0]
    h = ylim[1] - ylim[0]
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

    # Lock extent before basemap so it doesn't auto-zoom out
    ax.set_xlim(xlim)
    ax.set_ylim(ylim)

    if _STYLE["add_basemap"]:
        ctx.add_basemap(ax, source=ctx.providers.OpenStreetMap.Mapnik)
        # Re-lock after basemap (basemap can shift the extent slightly)
        ax.set_xlim(xlim)
        ax.set_ylim(ylim)

    if _STYLE["add_compass"]:
        _add_compass(ax, xlim, ylim)

    if _STYLE["add_scalebar"]:
        _add_scalebar(ax, xlim, ylim, _STYLE["scalebar_segments_km"])

    ax.set_title(col.replace("_", " ").title(), fontsize=15, fontweight="bold")
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
    capacity_csv:       Union[str, Path],
    tract_shp:          Union[str, Path],
    output_dir:         Union[str, Path],
    # ---- column names ----
    csv_tract_col:      str = "census_tract",
    shp_geoid_col:      str = "GEOID",
    capacity_norm_col:  str = "total_capacity_norm",
    station_count_col:  str = "num_station",
    # ---- service-area filtering ----
    # Tracts with fewer than min_stations stations are excluded
    min_stations:       int = 1,
    # gate_col: tracts where this column is NaN (or 0 if drop_zeros=True) are dropped
    # defaults to capacity_norm_col when None
    gate_col:           Optional[str] = None,
    drop_zeros:         bool = True,
    # ---- which columns to map ----
    # Defaults to all recognised capacity columns found in the file
    value_cols:         Optional[Sequence[str]] = None,
) -> Dict[str, Path]:
    """
    Plot decile choropleth maps for all capacity columns in the capacity CSV.

    Only census tracts that have at least one bike-share station
    (station_count_col >= min_stations) are included — this is the
    professor-style docked service-area definition.

    Parameters
    ----------
    capacity_csv      : path to the normalised capacity tract CSV
    tract_shp         : path to the census-tract shapefile
    output_dir        : folder where PNGs are saved (created if absent)
    csv_tract_col     : tract ID column in the capacity CSV
    shp_geoid_col     : tract ID column in the shapefile
    capacity_norm_col : primary normalised capacity column
                        (used as the default gate and in the filename)
    station_count_col : column in capacity CSV that holds station count
                        per tract — used to define the service area
    min_stations      : minimum number of stations for a tract to be included
    gate_col          : tracts where this column is NaN are excluded;
                        defaults to capacity_norm_col
    drop_zeros        : also exclude tracts where gate_col == 0
    value_cols        : columns to plot; defaults to all recognised
                        capacity columns found in the file

    Returns
    -------
    dict mapping column name → saved PNG path
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if gate_col is None:
        gate_col = capacity_norm_col

    # ------------------------------------------------------------------
    # Step 1 — Load shapefile and filter to NYC boroughs
    # ------------------------------------------------------------------
    tracts = gpd.read_file(str(tract_shp))
    if shp_geoid_col not in tracts.columns:
        raise KeyError(
            f"Shapefile missing column '{shp_geoid_col}'. "
            f"Available: {list(tracts.columns)}"
        )
    tracts[shp_geoid_col] = _to_geoid11(tracts[shp_geoid_col])
    tracts_nyc = tracts[
        tracts[shp_geoid_col].str.startswith(_NYC_BOROUGH_PREFIXES)
    ].copy()

    if tracts_nyc.empty:
        raise ValueError(
            "NYC borough filter returned 0 tracts. "
            "Check shapefile GEOID formatting or borough prefixes."
        )

    # ------------------------------------------------------------------
    # Step 2 — Load capacity CSV and aggregate to one row per tract
    # Multiple rows per tract can appear when stations are listed
    # individually — we sum capacities and sum station counts.
    # ------------------------------------------------------------------
    cap_raw = pd.read_csv(capacity_csv)
    for col in [csv_tract_col, station_count_col, gate_col]:
        if col not in cap_raw.columns:
            raise KeyError(
                f"capacity_csv missing column '{col}'. "
                f"Available: {list(cap_raw.columns)}"
            )

    cap_raw[csv_tract_col] = _to_geoid11(cap_raw[csv_tract_col])

    # Build aggregation rules:
    #   capacity columns → sum  (e.g. total_capacity_norm summed across stations)
    #   rate / ratio cols → mean
    agg: Dict = {}
    for c in cap_raw.select_dtypes(include="number").columns:
        if "capacity" in c:
            agg[c] = "sum"
        elif c in {"occupancy_rate", "return_pressure"}:
            agg[c] = "mean"
        else:
            agg[c] = "mean"
    # Always sum the station count column
    agg[station_count_col] = "sum"

    cap = cap_raw.groupby(csv_tract_col, as_index=False).agg(agg)

    # ------------------------------------------------------------------
    # Step 3 — Define service area: tracts with enough stations
    # ------------------------------------------------------------------
    service_tracts = cap.loc[
        cap[station_count_col].fillna(0) >= min_stations, csv_tract_col
    ].unique()

    if len(service_tracts) == 0:
        raise ValueError(
            f"0 tracts have {station_count_col} >= {min_stations}. "
            f"Check station_count_col or lower min_stations."
        )

    # ------------------------------------------------------------------
    # Step 4 — Filter NYC tracts to service area, then merge capacity data
    # ------------------------------------------------------------------
    tracts_nyc = tracts_nyc[
        tracts_nyc[shp_geoid_col].isin(service_tracts)
    ].copy()

    if tracts_nyc.empty:
        raise ValueError(
            "0 NYC tracts remain after service-area filter. "
            "GEOID formats likely differ between CSV and shapefile."
        )

    gdf = tracts_nyc.merge(
        cap, left_on=shp_geoid_col, right_on=csv_tract_col, how="left"
    )

    # Apply gate: drop tracts where the gate column is NaN (and optionally 0)
    gdf = gdf.dropna(subset=[gate_col]).copy()
    if drop_zeros:
        gdf = gdf[gdf[gate_col] > 0].copy()

    if gdf.empty:
        raise ValueError(
            f"0 rows remain after gating on '{gate_col}' "
            f"(drop_zeros={drop_zeros}). Try drop_zeros=False to debug."
        )

    # ------------------------------------------------------------------
    # Step 5 — Resolve which columns to plot
    # ------------------------------------------------------------------
    cols_to_plot = list(value_cols) if value_cols else _DEFAULT_VALUE_COLS
    # Only keep columns that actually exist in the merged GeoDataFrame
    cols_to_plot = [c for c in cols_to_plot if c in gdf.columns]

    if not cols_to_plot:
        raise KeyError(
            f"None of the requested value_cols exist in the merged data. "
            f"Available numeric columns: "
            f"{list(gdf.select_dtypes(include='number').columns)}"
        )

    # ------------------------------------------------------------------
    # Step 6 — Project to Web Mercator and compute shared extent
    # Locking the extent to the same bbox for all maps keeps them
    # visually comparable side-by-side.
    # ------------------------------------------------------------------
    gdf_web = gdf.to_crs(epsg=3857)
    xmin, ymin, xmax, ymax = gdf_web.total_bounds
    xlim = (xmin, xmax)
    ylim = (ymin, ymax)

    # ------------------------------------------------------------------
    # Step 7 — Render one map per column
    # ------------------------------------------------------------------
    saved: Dict[str, Path] = {}
    for col in cols_to_plot:
        out_path = out_dir / f"NYC_ONLY_{capacity_norm_col}_gate__{col}.png"
        result = _render_capacity_map(gdf_web, col, gate_col, xlim, ylim, out_path)
        if result is not None:
            saved[col] = result

    if not saved:
        raise ValueError(
            "No maps were saved — all requested columns were empty after filtering."
        )

    return saved


if __name__ == "__main__":
    print("capacity_map_visual module loaded successfully.")