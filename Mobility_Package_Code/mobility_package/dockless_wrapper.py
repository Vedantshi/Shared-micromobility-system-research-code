"""
=============================================================================
DOCKLESS BIKE SHARE UTILITY ANALYTICS PIPELINE (PRODUCTION v2)
=============================================================================

OVERVIEW
--------
This module provides modular functions to compute dockless bike share utility
metrics. Each metric has its own function that can be called independently.

AVAILABLE METRICS & THEIR FUNCTIONS
------------------------------------
    compute_availability()  - available vehicles per census block and tract
    compute_usage()         - vehicle starts and ends per block and tract
    compute_idle_time()     - average idle time per block and tract
    compute_safety()        - bike lane and protected lane ratios per tract

SUPPORTED SYSTEMS
-----------------
    "SF_LIME_DOCKLESS"      - San Francisco, Lime
    "SF_SPIN_DOCKLESS"      - San Francisco, Spin
    "SEATTLE_BIRD_DOCKLESS" - Seattle, Bird
    "SEATTLE_LIME_DOCKLESS" - Seattle, Lime

HOW TO USE
----------
    Step 1 — load the shared context (always required first)
    Step 2 — call whichever metric(s) you want

    Dependencies between metrics are handled internally.
    The user never needs to pass results between functions.

EXAMPLE — single metric
-----------------------
    ctx   = load_dockless_context(system_key="SF_LIME_DOCKLESS", ...)
    avail = compute_availability(ctx)

EXAMPLE — metrics that need no extra inputs
--------------------------------------------
    ctx   = load_dockless_context(system_key="SF_LIME_DOCKLESS", ...)
    usage = compute_usage(ctx)
    idle  = compute_idle_time(ctx)
    safe  = compute_safety(ctx)

EXAMPLE — all metrics at once
------------------------------
    ctx     = load_dockless_context(system_key="SF_LIME_DOCKLESS", ...)
    results = compute_all(ctx)

NOTE
----
    Unlike the docked system, dockless vehicles carry their own location
    so there is no separate trip CSV. All metrics derive from the
    freebike_status_txt snapshot file loaded in load_dockless_context().
=============================================================================
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from shapely import wkt
from shapely.geometry import Point
from tqdm import tqdm

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)


# ---------------------------------------------------------------------------
# System configuration
# ---------------------------------------------------------------------------

SYSTEM_CONFIG: Dict[str, Dict[str, Any]] = {
    "SF_LIME_DOCKLESS": {
        "city":                "San Francisco",
        "vendor":              "Lime",
        "tag":                 "sf_lime",
        "default_output_dir":  "SF_LIME_DOCKLESS_FULL_RUN",
        "raw_csv":             "san_fran_lime_status_raw.csv",
        "done_csv":            "san_fran_lime_status_done.csv",
        "assets": {
            "census_blocks_shp":       r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\GBFS_Census_Tract\San_Fran_Lime\tl_2024_06_tabblock20.shp",
            "centerline_streets_path": r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Safety\San_Fran_Lime\Centerline.csv",
            "bike_lanes_path":         r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Safety\San_Fran_Lime\Bikelane.csv",
            "centroid_tract_path":     r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Capacity\San_Fran_Baywheels\centroid_tract_ca.csv",
        },
        "safety_epsg":   26910,
        "idle_decimals": 4,
    },

    "SF_SPIN_DOCKLESS": {
        "city":                "San Francisco",
        "vendor":              "Spin",
        "tag":                 "sf_spin",
        "default_output_dir":  "SF_SPIN_DOCKLESS_FULL_RUN",
        "raw_csv":             "san_fran_spin_status_raw.csv",
        "done_csv":            "san_fran_spin_status_done.csv",
        "assets": {
            "census_blocks_shp":       r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\GBFS_Census_Tract\San_Fran_Lime\tl_2024_06_tabblock20.shp",
            "centerline_streets_path": r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Safety\San_Fran_Lime\Centerline.csv",
            "bike_lanes_path":         r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Safety\San_Fran_Lime\Bikelane.csv",
            "centroid_tract_path":     r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Capacity\San_Fran_Baywheels\centroid_tract_ca.csv",
        },
        "safety_epsg":   26910,
        "idle_decimals": 4,
    },

    "SEATTLE_BIRD_DOCKLESS": {
        "city":                "Seattle",
        "vendor":              "Bird",
        "tag":                 "seattle_bird",
        "default_output_dir":  "SEATTLE_BIRD_DOCKLESS_FULL_RUN",
        "raw_csv":             "seattle_bird_status_raw.csv",
        "done_csv":            "seattle_bird_status_done.csv",
        "assets": {
            "census_blocks_shp":        r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Safety\Seattle_Bird\Seattle Census Block\tl_2024_53_tabblock20.shp",
            "centerline_streets_path":  r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Safety\Seattle_Bird\Seattle_Streets.shp",
            "bike_lanes_path":          r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Safety\Seattle_Bird\SDOT_Bike_Facilities_5512142703833213564.geojson",
            "planned_bike_lanes_path":  r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Safety\Seattle_Bird\Planned Seattle Bike Lanes\Planned_Bike_Facilities.shp",
            "centroid_tract_path":      r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Avalibility\Seattle_Bird\tl_2024_53_tract.shp",
        },
        "safety_epsg":   2285,
        "safety_config": {
            "bike_lane_class_col":    "CATEGORY",
            "protected_values":       ["BKF-PBL"],
            "protected_match_mode":   "exact",
        },
        "idle_decimals": 3,
    },

    "SEATTLE_LIME_DOCKLESS": {
        "city":                "Seattle",
        "vendor":              "Lime",
        "tag":                 "seattle_lime",
        "default_output_dir":  "SEATTLE_LIME_DOCKLESS_FULL_RUN",
        "raw_csv":             "seattle_lime_status_raw.csv",
        "done_csv":            "seattle_lime_status_done.csv",
        "assets": {
            "census_blocks_shp":        r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Safety\Seattle_Bird\Seattle Census Block\tl_2024_53_tabblock20.shp",
            "centerline_streets_path":  r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Safety\Seattle_Bird\Seattle_Streets.shp",
            "bike_lanes_path":          r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Safety\Seattle_Bird\SDOT_Bike_Facilities_5512142703833213564.geojson",
            "planned_bike_lanes_path":  r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Safety\Seattle_Bird\Planned Seattle Bike Lanes\Planned_Bike_Facilities.shp",
            "centroid_tract_path":      r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Avalibility\Seattle_Bird\tl_2024_53_tract.shp",
        },
        "safety_epsg":   2285,
        "safety_config": {
            "bike_lane_class_col":    "CATEGORY",
            "protected_values":       ["BKF-PBL"],
            "protected_match_mode":   "exact",
        },
        "idle_decimals": 4,
    },
}


# ===========================================================================
# INTERNAL HELPER CLASS
# Not meant to be called directly by the user.
# ===========================================================================

class MetricHelper:
    """Core calculation routines shared across all compute functions."""

    @staticmethod
    def minmax_normalize(series: pd.Series) -> pd.Series:
        """Min-max normalize a numeric series to the range [0, 1]."""
        s      = pd.to_numeric(series, errors="coerce")
        mn, mx = s.min(skipna=True), s.max(skipna=True)
        if pd.isna(mn) or pd.isna(mx) or mx <= mn:
            return pd.Series(0.0, index=s.index)
        return (s - mn) / (mx - mn)

    @staticmethod
    def calc_availability(
        done_df: pd.DataFrame,
        block_granularity: str,
        tract_granularity: str,
        output_tag: str,
        out_dir: Path,
        save: bool,
        normalize: bool,
    ) -> Dict[str, pd.DataFrame]:
        """
        Count available (non-reserved, non-disabled) vehicles per block and tract.

        Parameters
        ----------
        done_df            : geocoded vehicle status dataframe
        block_granularity  : time bucket for block-level output e.g. "5min"
        tract_granularity  : time bucket for tract-level output e.g. "1h"
        output_tag         : system tag used in output filenames
        out_dir            : output directory path
        save               : whether to write CSV files
        normalize          : whether to add a normalized column to tract output
        """
        df = done_df.copy()
        df["slot"] = df["timestamp"].dt.floor(block_granularity)

        # default reserved/disabled to 0 if not present in data
        if "is_reserved" not in df.columns:
            df["is_reserved"] = 0
        if "is_disabled" not in df.columns:
            df["is_disabled"] = 0

        # only count vehicles that are available — not reserved or disabled
        av = df[(df["is_reserved"] == 0) & (df["is_disabled"] == 0)]

        av_blk   = av.groupby(["census_block", "slot"]).size().reset_index(name="total_available")
        av["h_slot"] = av["timestamp"].dt.floor(tract_granularity)
        av_tract = av.groupby(["census_tract", "h_slot"]).size().reset_index(name="total_available")

        if normalize:
            av_tract["total_available_norm"] = MetricHelper.minmax_normalize(av_tract["total_available"]).round(5)

        if save:
            av_blk.to_csv(out_dir   / f"availability_block_{output_tag}.csv",         index=False)
            av_tract.to_csv(out_dir / f"availability_tract_hourly_raw_{output_tag}.csv", index=False)

        return {"block": av_blk, "tract": av_tract}

    @staticmethod
    def calc_usage(
        done_df: pd.DataFrame,
        base_slot: str,
        aggregate_slot: str,
        rounding_decimals: int,
        tract_digits: int,
        output_tag: str,
        out_dir: Path,
        save: bool,
        normalize: bool,
    ) -> Dict[str, pd.DataFrame]:
        """
        Infer vehicle starts and ends by comparing consecutive location snapshots.

        A "start" is when a vehicle disappears from a location (someone picked it up).
        An "end" is when a vehicle appears at a location (someone dropped it off).

        Parameters
        ----------
        done_df           : geocoded vehicle status dataframe
        base_slot         : fine-grained time bucket e.g. "5min"
        aggregate_slot    : coarser time bucket for tract rollup e.g. "1h"
        rounding_decimals : decimal places for lat/lon when detecting position changes
        tract_digits      : number of characters used to derive tract from block ID
        output_tag        : system tag used in output filenames
        out_dir           : output directory path
        save              : whether to write CSV files
        normalize         : whether to add normalized columns
        """
        df = done_df.copy()
        df["slot"]  = df["timestamp"].dt.floor(base_slot)
        df["lat_r"] = df["lat"].round(rounding_decimals)
        df["lon_r"] = df["lon"].round(rounding_decimals)

        # count vehicles at each rounded location per slot
        cnts = df.groupby(["census_block", "slot", "lat_r", "lon_r"]).size().reset_index(name="cnt")

        # shift counts forward by one slot to compare consecutive snapshots
        prev = cnts.copy()
        prev["slot"] += pd.to_timedelta(base_slot)

        flux = prev.merge(
            cnts, on=["census_block", "slot", "lat_r", "lon_r"],
            how="outer", suffixes=("_prev", "_curr")
        ).fillna(0)

        # vehicles that decreased at a location = starts (picked up)
        # vehicles that increased at a location = ends (dropped off)
        flux["starts"] = (flux["cnt_prev"] - flux["cnt_curr"]).clip(lower=0)
        flux["ends"]   = (flux["cnt_curr"] - flux["cnt_prev"]).clip(lower=0)

        use_blk = flux.groupby(["census_block", "slot"])[["starts", "ends"]].sum().reset_index()
        use_blk["h_slot"]       = use_blk["slot"].dt.floor(aggregate_slot)
        use_blk["census_tract"] = use_blk["census_block"].str[:tract_digits]

        use_tract = use_blk.groupby(["census_tract", "h_slot"])[["starts", "ends"]].sum().reset_index()

        if normalize:
            use_tract["starts_norm"] = MetricHelper.minmax_normalize(use_tract["starts"]).round(5)
            use_tract["ends_norm"]   = MetricHelper.minmax_normalize(use_tract["ends"]).round(5)

        if save:
            use_blk.to_csv(out_dir   / f"usage_5min_block_{output_tag}.csv",   index=False)
            use_tract.to_csv(out_dir / f"usage_hourly_tract_{output_tag}.csv", index=False)

        return {"block": use_blk, "tract": use_tract}

    @staticmethod
    def calc_idle_time(
        done_df: pd.DataFrame,
        vehicle_id_col: str,
        vehicle_type_col: str,
        default_vehicle_type: str,
        hour_bucket_freq: str,
        tract_digits: int,
        output_tag: str,
        out_dir: Path,
        save: bool,
        normalize: bool,
    ) -> Dict[str, pd.DataFrame]:
        """
        Compute average idle time by counting how many consecutive 5-min snapshots
        a vehicle stays at the same location without being picked up.

        Each ping represents one 5-minute interval of idleness, so
        avg_idle_time_minutes = ping_count * 5.

        Parameters
        ----------
        done_df              : geocoded vehicle status dataframe
        vehicle_id_col       : column name for vehicle ID
        vehicle_type_col     : column name for vehicle type (e-bike, scooter etc.)
        default_vehicle_type : value to use when vehicle type is missing
        hour_bucket_freq     : time bucket for hourly rollup e.g. "1h"
        tract_digits         : number of characters used to derive tract from block ID
        output_tag           : system tag used in output filenames
        out_dir              : output directory path
        save                 : whether to write CSV files
        normalize            : whether to add a normalized column to tract output
        """
        df = done_df.copy()

        # resolve vehicle type column — fall back gracefully if not present
        if vehicle_type_col not in df.columns:
            if "vehicle_type" in df.columns:
                vehicle_type_col = "vehicle_type"
            else:
                df[vehicle_type_col] = default_vehicle_type

        df[vehicle_type_col] = df[vehicle_type_col].fillna(default_vehicle_type)
        df = df.sort_values([vehicle_id_col, "timestamp"]).reset_index(drop=True)
        df["h_bucket"] = df["timestamp"].dt.floor(hour_bucket_freq)

        # each row = one 5-min snapshot of a vehicle sitting idle at its location
        idle_res = df.groupby(
            ["census_block", "h_bucket", vehicle_type_col]
        ).size().reset_index(name="ping_count")

        idle_res["avg_idle_time_minutes"] = idle_res["ping_count"] * 5
        idle_res["num_idle_segments"]     = idle_res["ping_count"]
        idle_res["census_tract"]          = idle_res["census_block"].str[:tract_digits]

        idle_tract = idle_res.groupby(
            ["census_tract", "h_bucket", vehicle_type_col]
        )[["avg_idle_time_minutes", "num_idle_segments"]].sum().reset_index()

        if normalize:
            idle_tract["avg_idle_time_minutes_norm"] = MetricHelper.minmax_normalize(
                idle_tract["avg_idle_time_minutes"]
            ).round(5)

        if save:
            idle_res.to_csv(out_dir   / f"idle_summary_block_{output_tag}.csv",      index=False)
            idle_tract.to_csv(out_dir / f"idle_summary_tract_{output_tag}.csv",      index=False)
            idle_tract.to_csv(out_dir / f"idle_summary_tract_norm_{output_tag}.csv", index=False)

        return {"block": idle_res, "tract": idle_tract}

    @staticmethod
    def calc_safety(
        done_df: pd.DataFrame,
        census_blocks_shp: str,
        centerline_streets_path: str,
        bike_lanes_path: str,
        centroid_tract_path: str,
        safety_working_epsg: int,
        safety_input_crs: str,
        safety_centerline_wkt_col: str,
        safety_bike_lane_wkt_col: str,
        safety_bike_lane_class_col: Optional[str],
        safety_protected_values: Optional[List[str]],
        safety_protected_match_mode: str,
        planned_bike_lanes_path: Optional[str],
        tract_digits: int,
        output_tag: str,
        out_dir: Path,
        save: bool,
    ) -> Dict[str, pd.DataFrame]:
        """
        Compute bike lane and protected lane ratios per census block and tract.

        Intersects street and bike lane geometries with census blocks to get
        lengths, then aggregates to tract level and merges with centroid metadata.

        Parameters
        ----------
        done_df                     : geocoded vehicle status dataframe
                                      (used only to scope the service area)
        census_blocks_shp           : path to census block shapefile
        centerline_streets_path     : path to street centerline file (.shp or .csv with WKT)
        bike_lanes_path             : path to bike lane file (.shp, .geojson, or .csv with WKT)
        centroid_tract_path         : path to tract centroid file (.csv or .shp)
        safety_working_epsg         : EPSG code for metric CRS used in length calculations
        safety_input_crs            : CRS string for raw geometry inputs e.g. "EPSG:4326"
        safety_centerline_wkt_col   : column name for WKT geometry in centerline CSV
        safety_bike_lane_wkt_col    : column name for WKT geometry in bike lane CSV
        safety_bike_lane_class_col  : column used to identify protected lanes (or None)
        safety_protected_values     : values that indicate a protected lane
        safety_protected_match_mode : "exact" or "contains"
        planned_bike_lanes_path     : optional path to planned lanes file to include
        tract_digits                : number of characters used to derive tract from block ID
        output_tag                  : system tag used in output filenames
        out_dir                     : output directory path
        save                        : whether to write CSV files
        """
        # load census blocks and reproject to metric CRS for length calculations
        blocks = gpd.read_file(str(census_blocks_shp))
        if safety_working_epsg:
            blocks = blocks.to_crs(epsg=int(safety_working_epsg))

        # load street centerlines — supports both CSV with WKT and shapefiles
        st_path = Path(centerline_streets_path)
        if st_path.suffix.lower() == ".csv":
            st_df = pd.read_csv(st_path)
            st_df["geometry"] = st_df[safety_centerline_wkt_col].apply(
                lambda x: wkt.loads(x) if isinstance(x, str) else None
            )
            st = gpd.GeoDataFrame(st_df, geometry="geometry", crs=safety_input_crs)
        else:
            st = gpd.read_file(st_path).to_crs(safety_input_crs)
        st = st.to_crs(blocks.crs)

        # load bike lanes — supports CSV with WKT, shapefiles, and GeoJSON
        bl_path = Path(bike_lanes_path)
        if bl_path.suffix.lower() == ".csv":
            bl_df = pd.read_csv(bl_path)
            bl_df["geometry"] = bl_df[safety_bike_lane_wkt_col].apply(
                lambda x: wkt.loads(x) if isinstance(x, str) else None
            )
            bl = gpd.GeoDataFrame(bl_df, geometry="geometry", crs=safety_input_crs)
        else:
            bl = gpd.read_file(bl_path).to_crs(safety_input_crs)

        # optionally append planned bike lanes
        if planned_bike_lanes_path:
            pl = gpd.read_file(str(planned_bike_lanes_path)).to_crs(safety_input_crs)
            bl = pd.concat([bl, pl], ignore_index=True)

        bl = bl.to_crs(blocks.crs)

        # filter to protected lanes based on system-specific configuration
        prot = bl.iloc[0:0]
        if safety_bike_lane_class_col and safety_bike_lane_class_col in bl.columns and safety_protected_values:
            if safety_protected_match_mode == "exact":
                prot = bl[bl[safety_bike_lane_class_col].isin(safety_protected_values)]
            else:
                pattern = "|".join(safety_protected_values)
                prot = bl[bl[safety_bike_lane_class_col].astype(str).str.contains(pattern, case=False, na=False)]

        def _get_len(lines: gpd.GeoDataFrame, poly: gpd.GeoDataFrame, name: str) -> pd.DataFrame:
            """Compute total length of lines within each census block polygon."""
            if lines.empty:
                return pd.DataFrame({"census_block": [], name: []})
            clipped = gpd.overlay(lines, poly, how="intersection")
            clipped["l"] = clipped.geometry.length
            bid = "GEOID20" if "GEOID20" in poly.columns else "GEOID"
            return clipped.groupby(bid)["l"].sum().reset_index(name=name).rename(
                columns={bid: "census_block"}
            )

        s_len = _get_len(st,   blocks, "st_len")
        b_len = _get_len(bl,   blocks, "bl_len")
        p_len = _get_len(prot, blocks, "pr_len")

        safe = s_len.merge(b_len, on="census_block", how="left") \
                    .merge(p_len, on="census_block", how="left").fillna(0)
        safe["census_tract"] = safe["census_block"].astype(str).str[:tract_digits]

        # load tract centroid file — supports both CSV and shapefile formats
        ct_path = Path(centroid_tract_path)
        ct = pd.read_csv(ct_path) if ct_path.suffix.lower() == ".csv" else gpd.read_file(ct_path)

        cid = next((c for c in ["GEOID", "GEOID20", "TRACTCE", "census_tract"] if c in ct.columns), None)

        if cid:
            def _clean_id(x: Any) -> str:
                """Strip trailing .0 from numeric-looking IDs."""
                s = str(x).strip()
                return s[:-2] if s.endswith(".0") else s

            base = pd.DataFrame({"census_tract": ct[cid].apply(_clean_id)})
            safe["census_tract"] = safe["census_tract"].apply(_clean_id)

            # align ID lengths between base and safe — zero-pad the shorter one
            len_base = base["census_tract"].str.len().mode()[0]
            len_safe = safe["census_tract"].str.len().mode()[0]

            if len_base < len_safe:
                base["census_tract"] = base["census_tract"].str.zfill(int(len_safe))
            elif len_safe < len_base:
                safe["census_tract"] = safe["census_tract"].str.zfill(int(len_base))
        else:
            base = pd.DataFrame({"census_tract": []})

        tract_safe = safe.groupby("census_tract")[["st_len", "bl_len", "pr_len"]].sum().reset_index()
        final = base.merge(tract_safe, on="census_tract", how="left").fillna(0)

        final["ratio_bl"] = np.where(final["st_len"] > 0, final["bl_len"] / final["st_len"], 0)
        final["ratio_pr"] = np.where(final["st_len"] > 0, final["pr_len"] / final["st_len"], 0)

        if save:
            safe.to_csv(out_dir  / f"safety_block_{output_tag}.csv", index=False)
            final.to_csv(out_dir / f"safety_tract_{output_tag}.csv", index=False)

        return {"block": safe, "tract": final}


# ===========================================================================
# STEP 1 — CONTEXT LOADER
# Always call this first. It parses the freebike status file, geocodes
# all vehicle locations to census blocks, and applies the time filter.
# Pass the returned ctx to whichever compute_*() functions you need.
# ===========================================================================

def load_dockless_context(
    *,
    system_key: str,
    freebike_status_txt: Union[str, Path],
    output_dir: Optional[Union[str, Path]] = None,
    time_start: Optional[Union[str, pd.Timestamp]] = None,
    time_end: Optional[Union[str, pd.Timestamp]] = None,
    save_outputs: bool = True,
    fill_missing_with_census_api: bool = True,
    census_benchmark: str = "Public_AR_Census2020",
    census_vintage: str = "2020",
    blocks_target_epsg: int = 4326,
    drop_cols_if_present: Optional[List[str]] = None,
    tract_digits: int = 11,
) -> Dict[str, Any]:
    """
    Parse the freebike status file, geocode vehicle locations to census
    blocks, and apply the time window filter.

    Always call this first and pass the returned ctx to whichever
    compute_*() functions you need.

    Parameters
    ----------
    system_key                   : system identifier — see SUPPORTED SYSTEMS above
    freebike_status_txt          : path to the raw freebike status snapshot file (.txt)
    output_dir                   : folder where output files will be saved
    time_start                   : start of the analysis window
    time_end                     : end of the analysis window
    save_outputs                 : write the raw and geocoded CSVs to disk
    fill_missing_with_census_api : use the Census API to fill any vehicle
                                   locations that could not be geocoded locally
    census_benchmark             : Census API benchmark string
    census_vintage               : Census API vintage string
    blocks_target_epsg           : EPSG code to reproject census blocks to
    drop_cols_if_present         : list of columns to drop from the raw data
    tract_digits                 : number of characters used to derive tract
                                   from block GEOID e.g. 11 for standard tracts

    Returns
    -------
    ctx : dict — pass this as the first argument to any compute_*() function
    """
    if system_key not in SYSTEM_CONFIG:
        raise ValueError(f"Unknown system_key '{system_key}'. Valid options: {list(SYSTEM_CONFIG.keys())}")

    preset     = SYSTEM_CONFIG[system_key]
    output_tag = preset["tag"]
    assets     = preset.get("assets", {})

    out_dir = Path(output_dir or preset["default_output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_path  = out_dir / preset["raw_csv"]
    done_path = out_dir / preset["done_csv"]

    if not Path(freebike_status_txt).exists():
        raise FileNotFoundError(f"Freebike status file not found: {freebike_status_txt}")

    # parse the JSONL-style snapshot file into a flat dataframe
    print(f"[{system_key}] Parsing freebike status file...")
    rows = []
    with Path(freebike_status_txt).open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                blob = json.loads(line)
                ts   = list(blob.keys())[0]
                for entry in blob[ts]:
                    if "vehicle_types_available" in entry:
                        for vt in entry.get("vehicle_types_available", []):
                            entry[f"vehicle_type_{vt.get('vehicle_type_id', 'unknown')}_count"] = vt.get("count", 0)
                        del entry["vehicle_types_available"]
                    entry["timestamp"] = ts
                    rows.append(entry)
            except Exception:
                continue

    raw_df = pd.DataFrame(rows)
    if raw_df.empty:
        raise ValueError("No data found in the freebike status file.")

    # detect vehicle ID column — naming varies across vendors
    vehicle_id_col = next((c for c in ["bike_id", "vehicle_id", "id"] if c in raw_df.columns), None)
    if not vehicle_id_col:
        raise ValueError("Could not find vehicle ID column. Checked: bike_id, vehicle_id, id")

    # parse timestamps — try standard format first, fall back to unix seconds
    raw_df["timestamp"] = pd.to_datetime(raw_df["timestamp"], errors="coerce")
    if raw_df["timestamp"].isna().mean() > 0.5:
        raw_df["timestamp"] = pd.to_datetime(raw_df["timestamp"], unit="s", errors="coerce")

    if drop_cols_if_present:
        drop_now = [c for c in drop_cols_if_present if c in raw_df.columns]
        if drop_now:
            raw_df = raw_df.drop(columns=drop_now)

    if save_outputs:
        raw_df.to_csv(raw_path, index=False)

    if not {"lat", "lon"}.issubset(raw_df.columns):
        raise ValueError("Input data is missing lat and/or lon columns.")

    # geocode vehicle locations to census blocks via spatial join
    print(f"[{system_key}] Geocoding vehicle locations to census blocks...")
    latlon = raw_df[["lat", "lon"]].drop_duplicates()
    gdf    = gpd.GeoDataFrame(
        latlon,
        geometry=[Point(xy) for xy in zip(latlon.lon, latlon.lat)],
        crs="EPSG:4326",
    )
    blocks = gpd.read_file(str(assets["census_blocks_shp"])).to_crs(epsg=blocks_target_epsg)
    b_col  = "GEOID20" if "GEOID20" in blocks.columns else "GEOID"

    joined = gpd.sjoin(gdf, blocks[[b_col, "geometry"]], how="left", predicate="within")
    joined = joined.rename(columns={b_col: "census_block"})

    done_df = raw_df.merge(joined[["lat", "lon", "census_block"]], on=["lat", "lon"], how="left")

    # fill any remaining missing blocks using the Census Geocoder API
    if fill_missing_with_census_api:
        missing = done_df[done_df["census_block"].isna()][["lat", "lon"]].drop_duplicates()
        if not missing.empty and len(missing) < 1000:
            tqdm.pandas(desc="API Geocoding Fallback")

            def _fetch_block(r: pd.Series) -> Optional[str]:
                try:
                    url = (
                        f"https://geocoding.geo.census.gov/geocoder/geographies/coordinates"
                        f"?x={r.lon}&y={r.lat}&benchmark={census_benchmark}"
                        f"&vintage={census_vintage}&format=json"
                    )
                    res = requests.get(url, timeout=5).json()
                    return res["result"]["geographies"]["2020 Census Blocks"][0]["GEOID"]
                except Exception:
                    return None

            missing["cb_new"] = missing.progress_apply(_fetch_block, axis=1)
            done_df = done_df.merge(missing, on=["lat", "lon"], how="left")
            done_df["census_block"] = done_df["census_block"].fillna(done_df["cb_new"])
            done_df.drop(columns=["cb_new"], inplace=True, errors="ignore")

    done_df["census_block"] = done_df["census_block"].fillna("unknown").astype(str)
    done_df["census_tract"] = done_df["census_block"].str[:tract_digits]

    # apply the time window filter
    if time_start:
        done_df = done_df[done_df["timestamp"] >= pd.to_datetime(time_start)]
    if time_end:
        done_df = done_df[done_df["timestamp"] < pd.to_datetime(time_end)]

    if save_outputs:
        done_df.to_csv(done_path, index=False)

    return {
        "system_key":    system_key,
        "preset":        preset,
        "output_tag":    output_tag,
        "assets":        assets,
        "out_dir":       out_dir,
        "done_df":       done_df,
        "vehicle_id_col": vehicle_id_col,
        "tract_digits":  tract_digits,
        "save_outputs":  save_outputs,
    }


# ===========================================================================
# STEP 2 — METRIC FUNCTIONS
# Call whichever ones you need. Each one takes ctx as the first argument.
# No result passing between functions — every function is self-contained.
# ===========================================================================

def compute_availability(
    ctx: Dict[str, Any],
    *,
    block_granularity: str = "5min",
    tract_granularity: str = "1h",
    normalize: bool = True,
    save_outputs: Optional[bool] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Compute available (non-reserved, non-disabled) vehicles per block and tract.

    Parameters
    ----------
    ctx               : returned by load_dockless_context()
    block_granularity : time bucket for block-level output e.g. "5min"
    tract_granularity : time bucket for tract-level output e.g. "1h"
    normalize         : add a normalized column to the tract output
    save_outputs      : write result CSVs (default: inherits from context)

    Returns
    -------
    dict with keys:
        block : available vehicle counts per block per time slot
        tract : available vehicle counts per tract per hour
    """
    save = save_outputs if save_outputs is not None else ctx["save_outputs"]

    print(f"[{ctx['system_key']}] Computing availability...")

    return MetricHelper.calc_availability(
        done_df=ctx["done_df"],
        block_granularity=block_granularity,
        tract_granularity=tract_granularity,
        output_tag=ctx["output_tag"],
        out_dir=ctx["out_dir"],
        save=save,
        normalize=normalize,
    )


def compute_usage(
    ctx: Dict[str, Any],
    *,
    base_time_slot: str = "5min",
    aggregate_time_slot: str = "1h",
    rounding_decimals: int = 4,
    normalize: bool = True,
    save_outputs: Optional[bool] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Compute vehicle starts and ends per census block and tract.

    Vehicle starts and ends are inferred by comparing consecutive
    location snapshots — no separate trip data file is needed.

    Parameters
    ----------
    ctx                  : returned by load_dockless_context()
    base_time_slot       : fine-grained time bucket for detection e.g. "5min"
    aggregate_time_slot  : coarser bucket for tract rollup e.g. "1h"
    rounding_decimals    : decimal places for lat/lon position comparison
    normalize            : add normalized columns to tract output
    save_outputs         : write result CSVs (default: inherits from context)

    Returns
    -------
    dict with keys:
        block : starts and ends per block per 5-min slot
        tract : starts and ends per tract per hour
    """
    save = save_outputs if save_outputs is not None else ctx["save_outputs"]

    print(f"[{ctx['system_key']}] Computing usage...")

    return MetricHelper.calc_usage(
        done_df=ctx["done_df"],
        base_slot=base_time_slot,
        aggregate_slot=aggregate_time_slot,
        rounding_decimals=rounding_decimals,
        tract_digits=ctx["tract_digits"],
        output_tag=ctx["output_tag"],
        out_dir=ctx["out_dir"],
        save=save,
        normalize=normalize,
    )


def compute_idle_time(
    ctx: Dict[str, Any],
    *,
    vehicle_type_col: str = "vehicle_type_id",
    default_vehicle_type: str = "",
    hour_bucket_freq: str = "1h",
    normalize: bool = True,
    save_outputs: Optional[bool] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Compute average idle time per census block and tract.

    Idle time is measured by counting how many consecutive 5-minute
    snapshots a vehicle remains at the same location without being
    picked up. Each snapshot = 5 minutes of idle time.

    Parameters
    ----------
    ctx                  : returned by load_dockless_context()
    vehicle_type_col     : column name for vehicle type (e-bike, scooter etc.)
    default_vehicle_type : value to use when vehicle type is missing
    hour_bucket_freq     : time bucket for hourly rollup e.g. "1h"
    normalize            : add a normalized column to the tract output
    save_outputs         : write result CSVs (default: inherits from context)

    Returns
    -------
    dict with keys:
        block : idle time per block per hour per vehicle type
        tract : idle time per tract per hour per vehicle type (normalized)
    """
    save = save_outputs if save_outputs is not None else ctx["save_outputs"]

    print(f"[{ctx['system_key']}] Computing idle time...")

    return MetricHelper.calc_idle_time(
        done_df=ctx["done_df"],
        vehicle_id_col=ctx["vehicle_id_col"],
        vehicle_type_col=vehicle_type_col,
        default_vehicle_type=default_vehicle_type,
        hour_bucket_freq=hour_bucket_freq,
        tract_digits=ctx["tract_digits"],
        output_tag=ctx["output_tag"],
        out_dir=ctx["out_dir"],
        save=save,
        normalize=normalize,
    )


def compute_safety(
    ctx: Dict[str, Any],
    *,
    safety_centerline_wkt_col: str = "line",
    safety_bike_lane_wkt_col: str = "shape",
    safety_input_crs: str = "EPSG:4326",
    save_outputs: Optional[bool] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Compute bike lane and protected lane ratios per census block and tract.

    All geometry paths and protected lane classification rules are read
    from the system configuration — no extra arguments needed for most users.

    Parameters
    ----------
    ctx                       : returned by load_dockless_context()
    safety_centerline_wkt_col : column name for WKT geometry in centerline CSV
    safety_bike_lane_wkt_col  : column name for WKT geometry in bike lane CSV
    safety_input_crs          : CRS of the raw geometry inputs
    save_outputs              : write result CSVs (default: inherits from context)

    Returns
    -------
    dict with keys:
        block : bike lane ratios at census block level
        tract : bike lane ratios at census tract level
    """
    save   = save_outputs if save_outputs is not None else ctx["save_outputs"]
    preset = ctx["preset"]
    assets = ctx["assets"]

    # read safety classification rules from system config
    safe_conf = preset.get("safety_config", {})

    print(f"[{ctx['system_key']}] Computing safety...")

    return MetricHelper.calc_safety(
        done_df=ctx["done_df"],
        census_blocks_shp=assets["census_blocks_shp"],
        centerline_streets_path=assets["centerline_streets_path"],
        bike_lanes_path=assets["bike_lanes_path"],
        centroid_tract_path=assets["centroid_tract_path"],
        safety_working_epsg=preset.get("safety_epsg", 26910),
        safety_input_crs=safety_input_crs,
        safety_centerline_wkt_col=safety_centerline_wkt_col,
        safety_bike_lane_wkt_col=safety_bike_lane_wkt_col,
        safety_bike_lane_class_col=safe_conf.get("bike_lane_class_col"),
        safety_protected_values=safe_conf.get("protected_values"),
        safety_protected_match_mode=safe_conf.get("protected_match_mode", "contains"),
        planned_bike_lanes_path=assets.get("planned_bike_lanes_path"),
        tract_digits=ctx["tract_digits"],
        output_tag=ctx["output_tag"],
        out_dir=ctx["out_dir"],
        save=save,
    )


# ===========================================================================
# CONVENIENCE FUNCTION — runs all metrics in one call
# ===========================================================================

def compute_all(
    ctx: Dict[str, Any],
    *,
    save_outputs: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Run all four metrics in one call.

    This is a convenience wrapper that calls compute_availability(),
    compute_usage(), compute_idle_time(), and compute_safety() and
    returns all results together.

    Parameters
    ----------
    ctx          : returned by load_dockless_context()
    save_outputs : write all result CSVs (default: inherits from context)

    Returns
    -------
    dict with keys: availability, usage, idle_time, safety
    """
    avail = compute_availability(ctx, save_outputs=save_outputs)
    usage = compute_usage(ctx,        save_outputs=save_outputs)
    idle  = compute_idle_time(ctx,    save_outputs=save_outputs)
    safe  = compute_safety(ctx,       save_outputs=save_outputs)

    print(f"--- Done. Outputs saved to {ctx['out_dir']} ---")

    return {
        "availability": avail,
        "usage":        usage,
        "idle_time":    idle,
        "safety":       safe,
    }


if __name__ == "__main__":
    print("dockless_wrapper module loaded successfully")