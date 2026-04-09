"""
=============================================================================
DOCKLESS WRAPPER
=============================================================================

OVERVIEW
--------
This module computes all four utility metrics for dockless bike-share
systems (Lime SF, Spin SF, Bird Seattle, Lime Seattle) from raw GBFS
free-bike-status snapshot data.

USAGE PATTERN
-------------
Every script follows the same two-step pattern:

    Step 1 — load context (always first)
    Step 2 — call individual metric functions or compute_all at once

    from mobility_package import dockless_wrapper

    ctx = dockless_wrapper.load_dockless_context(
        system_key         = "SF_LIME_DOCKLESS",
        freebike_status_txt= r"path/to/sf_lime_freebike_status.txt",
        output_dir         = "SF_LIME_FULL_RUN",
        time_start         = "2025-06-09 06:00:00",
        time_end           = "2025-06-09 12:00:00",
    )

    # Option A — all metrics at once
    results = dockless_wrapper.compute_all(ctx)

    # Option B — individual metrics
    avail  = dockless_wrapper.compute_availability(ctx)
    cap    = dockless_wrapper.compute_capacity(ctx)
    usage  = dockless_wrapper.compute_usage(ctx)
    idle   = dockless_wrapper.compute_idle_time(ctx)
    safety = dockless_wrapper.compute_safety(ctx)

SUPPORTED SYSTEMS
-----------------
    "SF_LIME_DOCKLESS"      San Francisco — Lime
    "SF_SPIN_DOCKLESS"      San Francisco — Spin
    "SEATTLE_BIRD_DOCKLESS" Seattle       — Bird
    "SEATTLE_LIME_DOCKLESS" Seattle       — Lime

METRICS
-------
    compute_availability — non-reserved, non-disabled vehicles per tract
    compute_capacity     — peak-hour vehicle count per tract (same logic
                           as docked capacity: find the time slot with the
                           highest system-wide availability and use that
                           snapshot as the capacity baseline)
    compute_usage        — infers trip starts/ends from consecutive
                           location snapshots (no separate trip CSV needed)
    compute_idle_time    — ping count × 5 minutes per vehicle per tract
    compute_safety       — bike-lane ratio per tract
    compute_all          — runs all five metrics in one call
=============================================================================
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from shapely import wkt
from shapely.geometry import Point
from tqdm import tqdm


# ===========================================================================
# SYSTEM CONFIGURATION TABLE
# All city-specific asset paths and processing parameters live here.
# Individual compute functions read from ctx["_preset"] so they never
# need to know which city they are running against.
# ===========================================================================

# ===========================================================================
# ASSET ROOT
# All spatial assets live under a single `assets/` folder that sits in the
# same directory as the package. Users download the assets folder, place it
# next to mobility_package/, and no other path configuration is needed.
# ===========================================================================

_ASSET_ROOT = Path(__file__).parent.parent / "assets"


def _asset(*parts: str) -> str:
    """Return the absolute path to an asset file relative to the asset root."""
    return str(_ASSET_ROOT.joinpath(*parts))


# ===========================================================================
# SYSTEM CONFIGURATION TABLE
# All city-specific asset paths and processing parameters live here.
# To add a new system: add a new entry following the same structure, then
# place the required files in assets/<CITY_FOLDER>/.
# ===========================================================================

_SYSTEMS: Dict[str, Dict[str, Any]] = {

    "SF_LIME_DOCKLESS": {
        "city":                "San Francisco",
        "vendor":              "Lime",
        "tag":                 "sf_lime",
        "default_output_dir":  "SF_LIME_DOCKLESS_FULL_RUN",
        "raw_csv":             "san_fran_lime_status_raw.csv",
        "done_csv":            "san_fran_lime_status_done.csv",
        "assets": {
            "census_blocks_shp":       _asset("SF", "tl_2024_06_tabblock20.shp"),
            "centerline_streets_path": _asset("SF", "Centerline.csv"),
            "bike_lanes_path":         _asset("SF", "Bikelane.csv"),
            "centroid_tract_path":     _asset("SF", "centroid_tract_ca.csv"),
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
            "census_blocks_shp":       _asset("SF", "tl_2024_06_tabblock20.shp"),
            "centerline_streets_path": _asset("SF", "Centerline.csv"),
            "bike_lanes_path":         _asset("SF", "Bikelane.csv"),
            "centroid_tract_path":     _asset("SF", "centroid_tract_ca.csv"),
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
            "census_blocks_shp":       _asset("SEATTLE", "tl_2024_53_tabblock20.shp"),
            "centerline_streets_path": _asset("SEATTLE", "Seattle_Streets.shp"),
            "bike_lanes_path": _asset("SEATTLE", "SDOT_Bike_Facilities_5512142703833213564.geojson"),
            "planned_bike_lanes_path": _asset("SEATTLE", "Planned_Bike_Facilities.shp"),
            "centroid_tract_path":     _asset("SEATTLE", "tl_2024_53_tract.shp"),
        },
        "safety_epsg":   2285,
        "safety_config": {
            "bike_lane_class_col":  "CATEGORY",
            "protected_values":     ["BKF-PBL"],
            "protected_match_mode": "exact",
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
            "census_blocks_shp":       _asset("SEATTLE", "tl_2024_53_tabblock20.shp"),
            "centerline_streets_path": _asset("SEATTLE", "Seattle_Streets.shp"),
            "bike_lanes_path":         _asset("SEATTLE", "SDOT_Bike_Facilities_5512142703833213564.geojson"),
            "planned_bike_lanes_path": _asset("SEATTLE", "Planned_Bike_Facilities.shp"),
            "centroid_tract_path":     _asset("SEATTLE", "tl_2024_53_tract.shp"),
        },
        "safety_epsg":   2285,
        "safety_config": {
            "bike_lane_class_col":  "CATEGORY",
            "protected_values":     ["BKF-PBL"],
            "protected_match_mode": "exact",
        },
        "idle_decimals": 4,
    },
}


# ===========================================================================
# INTERNAL HELPERS
# ===========================================================================

def _minmax(series: pd.Series) -> pd.Series:
    """
    Min-max normalise a numeric Series to [0, 1].
    Returns all-zero if the range is zero or the series is empty/all-NaN.
    """
    s = pd.to_numeric(series, errors="coerce")
    mn, mx = s.min(skipna=True), s.max(skipna=True)
    if pd.isna(mn) or pd.isna(mx) or mx <= mn:
        return pd.Series(0.0, index=s.index)
    return (s - mn) / (mx - mn)


def _get_centroid_id_col(ct: pd.DataFrame) -> Optional[str]:
    """
    Return the first recognised census-tract / GEOID column name found in
    the centroid DataFrame, or None if none are present.
    """
    candidates = ["GEOID", "GEOID20", "TRACTCE", "census_tract"]
    return next((c for c in candidates if c in ct.columns), None)


def _clean_tract_id(x: Any) -> str:
    """
    Strip trailing '.0' that appears when IDs are stored as floats,
    and strip surrounding whitespace.
    """
    s = str(x).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s


# ===========================================================================
# STEP 1 — CONTEXT LOADER (always call this first)
# ===========================================================================

def load_dockless_context(
    *,
    system_key: str,
    freebike_status_txt: Union[str, Path],
    output_dir: Optional[Union[str, Path]] = None,
    time_start: Optional[Union[str, pd.Timestamp]] = None,
    time_end:   Optional[Union[str, pd.Timestamp]] = None,
    # ---- optional asset path overrides (use if paths differ from defaults) ----
    census_blocks_shp:       Optional[Union[str, Path]] = None,
    centerline_streets_path: Optional[Union[str, Path]] = None,
    bike_lanes_path:         Optional[Union[str, Path]] = None,
    planned_bike_lanes_path: Optional[Union[str, Path]] = None,
    centroid_tract_path:     Optional[Union[str, Path]] = None,
    # ---- geocoding settings ----
    fill_missing_with_census_api: bool = True,
    census_benchmark: str = "Public_AR_Census2020",
    census_vintage:   str = "2020",
    # ---- general settings ----
    tract_digits: int = 11,
    save_outputs: bool = True,
) -> Dict[str, Any]:
    """
    Parse the raw GBFS free-bike-status snapshot file, spatially join
    each ping to a census block, derive the census tract, apply the time
    window filter, and return a context dictionary used by every downstream
    compute_* function.

    Parameters
    ----------
    system_key           : one of the keys in _SYSTEMS
    freebike_status_txt  : path to the raw GBFS snapshot text file
    output_dir           : folder for all outputs (created if absent)
    time_start / time_end: optional ISO-format strings to filter the data
    census_blocks_shp    : override the shapefile from the system config
    fill_missing_with_census_api : call the Census geocoder for pings that
                           did not fall inside any block polygon
    tract_digits         : number of leading GEOID digits that form the
                           tract ID (11 for US census tracts)
    save_outputs         : write raw and spatially-joined CSVs to disk

    Returns
    -------
    ctx : dict — pass this unchanged to every compute_* function
    """
    if system_key not in _SYSTEMS:
        raise ValueError(
            f"Unknown system_key '{system_key}'. "
            f"Valid options: {list(_SYSTEMS.keys())}"
        )

    preset = _SYSTEMS[system_key]
    assets = preset.get("assets", {})

    # Resolve asset paths: explicit argument overrides preset default
    census_blocks_shp       = census_blocks_shp       or assets.get("census_blocks_shp")
    centerline_streets_path = centerline_streets_path or assets.get("centerline_streets_path")
    bike_lanes_path         = bike_lanes_path         or assets.get("bike_lanes_path")
    planned_bike_lanes_path = planned_bike_lanes_path or assets.get("planned_bike_lanes_path")
    centroid_tract_path     = centroid_tract_path     or assets.get("centroid_tract_path")

    out_dir = Path(output_dir or preset["default_output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    tag = preset["tag"]

    # ------------------------------------------------------------------
    # Step A — Parse the snapshot text file
    # Each line is a JSON object keyed by timestamp, containing a list
    # of vehicle records for that snapshot.
    # ------------------------------------------------------------------
    print(f"[{system_key}] Parsing snapshot file: {freebike_status_txt}")
    rows: List[Dict] = []
    with Path(freebike_status_txt).open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                blob = json.loads(line)
                ts = list(blob.keys())[0]
                for entry in blob[ts]:
                    # Flatten nested vehicle_types_available into columns
                    if "vehicle_types_available" in entry:
                        for vt in entry.get("vehicle_types_available", []):
                            col = f"vehicle_type_{vt.get('vehicle_type_id', 'unknown')}_count"
                            entry[col] = vt.get("count", 0)
                        del entry["vehicle_types_available"]
                    entry["timestamp"] = ts
                    rows.append(entry)
            except Exception:
                continue

    raw_df = pd.DataFrame(rows)
    if raw_df.empty:
        raise ValueError("No data found in the snapshot file.")

    # Detect the vehicle ID column (varies by vendor)
    vehicle_id_col = next(
        (c for c in ["bike_id", "vehicle_id", "id"] if c in raw_df.columns), None
    )
    if vehicle_id_col is None:
        raise ValueError(
            "Could not find a vehicle ID column. "
            "Expected one of: bike_id, vehicle_id, id."
        )

    # Parse timestamps — try ISO format first, fall back to Unix epoch
    raw_df["timestamp"] = pd.to_datetime(raw_df["timestamp"], errors="coerce")
    if raw_df["timestamp"].isna().mean() > 0.5:
        raw_df["timestamp"] = pd.to_datetime(
            raw_df["timestamp"], unit="s", errors="coerce"
        )

    if save_outputs:
        raw_df.to_csv(out_dir / preset["raw_csv"], index=False)

    # ------------------------------------------------------------------
    # Step B — Spatial join: ping coordinates → census block
    # ------------------------------------------------------------------
    if not {"lat", "lon"}.issubset(raw_df.columns):
        raise ValueError("Snapshot data is missing lat/lon columns.")

    print(f"[{system_key}] Spatially joining pings to census blocks...")
    latlon = raw_df[["lat", "lon"]].drop_duplicates()
    gdf = gpd.GeoDataFrame(
        latlon,
        geometry=[Point(lon, lat) for lat, lon in zip(latlon["lat"], latlon["lon"])],
        crs="EPSG:4326",
    )

    blocks = gpd.read_file(str(census_blocks_shp)).to_crs(epsg=4326)
    b_col = "GEOID20" if "GEOID20" in blocks.columns else "GEOID"
    joined = gpd.sjoin(gdf, blocks[[b_col, "geometry"]], how="left", predicate="within")
    joined = joined.rename(columns={b_col: "census_block"})

    done_df = raw_df.merge(
        joined[["lat", "lon", "census_block"]], on=["lat", "lon"], how="left"
    )

    # ------------------------------------------------------------------
    # Step C — Fill missing block assignments via Census geocoder API
    # ------------------------------------------------------------------
    if fill_missing_with_census_api:
        missing = (
            done_df[done_df["census_block"].isna()][["lat", "lon"]]
            .drop_duplicates()
        )
        if not missing.empty and len(missing) < 1_000:
            tqdm.pandas(desc="Census API geocode")

            def _geocode(row):
                try:
                    url = (
                        f"https://geocoding.geo.census.gov/geocoder/geographies/"
                        f"coordinates?x={row.lon}&y={row.lat}"
                        f"&benchmark={census_benchmark}&vintage={census_vintage}&format=json"
                    )
                    res = requests.get(url, timeout=5).json()
                    return res["result"]["geographies"]["2020 Census Blocks"][0]["GEOID"]
                except Exception:
                    return None

            missing["cb_new"] = missing.progress_apply(_geocode, axis=1)
            done_df = done_df.merge(missing, on=["lat", "lon"], how="left")
            done_df["census_block"] = done_df["census_block"].fillna(done_df["cb_new"])
            done_df.drop(columns=["cb_new"], inplace=True, errors="ignore")

    done_df["census_block"] = done_df["census_block"].fillna("unknown").astype(str)
    # Derive census tract from the first N digits of the census block GEOID
    done_df["census_tract"] = done_df["census_block"].str[:tract_digits]

    # ------------------------------------------------------------------
    # Step D — Apply time window filter
    # ------------------------------------------------------------------
    if time_start:
        done_df = done_df[done_df["timestamp"] >= pd.to_datetime(time_start)]
    if time_end:
        done_df = done_df[done_df["timestamp"] < pd.to_datetime(time_end)]

    if save_outputs:
        done_df.to_csv(out_dir / preset["done_csv"], index=False)

    print(
        f"[{system_key}] Context ready. "
        f"Rows: {len(done_df):,}  |  "
        f"Tracts: {done_df['census_tract'].nunique()}"
    )

    # ------------------------------------------------------------------
    # Assemble context dictionary
    # All downstream compute_* functions read from this dict.
    # ------------------------------------------------------------------
    return {
        "system_key":            system_key,
        "done_df":               done_df,
        "vehicle_id_col":        vehicle_id_col,
        "out_dir":               out_dir,
        "tag":                   tag,
        "save_outputs":          save_outputs,
        "tract_digits":          tract_digits,
        # Asset paths needed by compute_safety
        "centerline_streets_path":  centerline_streets_path,
        "bike_lanes_path":          bike_lanes_path,
        "planned_bike_lanes_path":  planned_bike_lanes_path,
        "centroid_tract_path":      centroid_tract_path,
        "census_blocks_shp":        census_blocks_shp,
        # Full preset for per-system config values
        "_preset": preset,
    }


# ===========================================================================
# STEP 2a — AVAILABILITY
# ===========================================================================

def compute_availability(
    ctx: Dict[str, Any],
    *,
    block_time_granularity: str = "5min",
    tract_time_granularity: str = "1h",
    reserved_col: str = "is_reserved",
    disabled_col: str = "is_disabled",
    normalize: bool = True,
) -> Dict[str, pd.DataFrame]:
    """
    Count non-reserved, non-disabled vehicles per census tract per hour.

    The raw pings are first bucketed at block level (5-min default) to
    reduce noise, then aggregated to tract × hour.

    Parameters
    ----------
    ctx                    : context from load_dockless_context
    block_time_granularity : time-floor for block-level aggregation
    tract_time_granularity : time-floor for tract-level aggregation
    reserved_col           : column indicating reserved vehicles (0/1)
    disabled_col           : column indicating disabled vehicles (0/1)
    normalize              : add a min-max normalised column

    Returns
    -------
    dict with keys "block" and "tract" — both pd.DataFrames
    """
    done_df  = ctx["done_df"].copy()
    out_dir  = ctx["out_dir"]
    tag      = ctx["tag"]
    save     = ctx["save_outputs"]

    # Add missing flag columns if the vendor doesn't provide them
    for col in [reserved_col, disabled_col]:
        if col not in done_df.columns:
            done_df[col] = 0

    done_df["slot"] = done_df["timestamp"].dt.floor(block_time_granularity)

    # Keep only vehicles that are available (not reserved, not disabled)
    av = done_df[
        (done_df[reserved_col] == 0) & (done_df[disabled_col] == 0)
    ]

    # Block-level count (5-min buckets)
    av_block = (
        av.groupby(["census_block", "slot"])
        .size()
        .reset_index(name="total_available")
    )

    # Tract-level count (hourly buckets)
    av["h_slot"] = av["timestamp"].dt.floor(tract_time_granularity)
    av_tract = (
        av.groupby(["census_tract", "h_slot"])
        .size()
        .reset_index(name="total_available")
    )
    av_tract = av_tract.rename(columns={"h_slot": "time_slot"})

    if normalize:
        av_tract["total_available_norm"] = _minmax(av_tract["total_available"]).round(5)

    if save:
        av_block.to_csv(out_dir / f"availability_block_{tag}.csv",         index=False)
        av_tract.to_csv(out_dir / f"availability_norm_hourly_tract_{tag}.csv", index=False)

    print(f"  [availability] Done. Tract rows: {len(av_tract):,}")
    return {"block": av_block, "tract": av_tract}


# ===========================================================================
# STEP 2b — CAPACITY
# ===========================================================================

def compute_capacity(
    ctx: Dict[str, Any],
    *,
    reserved_col: str = "is_reserved",
    disabled_col: str = "is_disabled",
    normalize: bool = True,
) -> pd.DataFrame:
    """
    Estimate vehicle capacity per census tract for a dockless system.

    Method (identical to the docked-system approach):
        1. For every 5-minute snapshot, sum the number of non-reserved,
           non-disabled vehicles across all tracts to get the system-wide
           total at that moment.
        2. Identify the snapshot with the highest system-wide total —
           this is the "peak availability" moment and serves as the
           capacity baseline (the moment when the most bikes were visible
           in the GBFS feed, i.e. the closest proxy to the fleet size).
        3. Use each tract's vehicle count at that single snapshot as its
           capacity value.
        4. Apply min-max normalisation.

    This is the same logic used in the Seattle Bird notebook:
        peak_time_slot = availability_by_time.idxmax()
        vehicle_capacity = peak_df.groupby('census_tract')['total_available'].sum()

    Parameters
    ----------
    ctx          : context from load_dockless_context
    reserved_col : column indicating reserved vehicles (0/1)
    disabled_col : column indicating disabled vehicles (0/1)
    normalize    : add a min-max normalised column

    Returns
    -------
    pd.DataFrame with columns:
        census_tract, vehicle_capacity[, vehicle_capacity_norm]
    """
    done_df = ctx["done_df"].copy()
    out_dir = ctx["out_dir"]
    tag     = ctx["tag"]
    save    = ctx["save_outputs"]

    # Add missing flag columns if the vendor doesn't provide them
    for col in [reserved_col, disabled_col]:
        if col not in done_df.columns:
            done_df[col] = 0

    # Only count available (not reserved, not disabled) vehicles
    av = done_df[
        (done_df[reserved_col] == 0) & (done_df[disabled_col] == 0)
    ].copy()

    # Bucket timestamps to 5-minute slots for consistent snapshot windows
    av["slot"] = av["timestamp"].dt.floor("5min")

    # ----------------------------------------------------------------
    # Step 1: Find the snapshot (time slot) where system-wide availability
    #         is the highest — this is the peak fleet availability moment.
    # ----------------------------------------------------------------
    system_wide = (
        av.groupby("slot")["census_tract"]
        .count()          # total available pings at each 5-min slot
        .reset_index(name="total_system")
    )

    if system_wide.empty:
        print("  [capacity] WARNING: no available vehicle data found.")
        return pd.DataFrame(columns=["census_tract", "vehicle_capacity"])

    peak_slot = system_wide.loc[
        system_wide["total_system"].idxmax(), "slot"
    ]
    print(
        f"  [capacity] Peak availability slot: {peak_slot}  "
        f"(system total: {system_wide['total_system'].max():,} pings)"
    )

    # ----------------------------------------------------------------
    # Step 2: At the peak snapshot, count vehicles per census tract.
    #         This gives each tract's capacity.
    # ----------------------------------------------------------------
    peak_df = av[av["slot"] == peak_slot]

    cap = (
        peak_df.groupby("census_tract")
        .size()
        .reset_index(name="vehicle_capacity")
    )

    # ----------------------------------------------------------------
    # Step 3: Min-max normalise capacity across all tracts
    # ----------------------------------------------------------------
    if normalize:
        cap["vehicle_capacity_norm"] = _minmax(cap["vehicle_capacity"]).round(5)

    if save:
        cap.to_csv(out_dir / f"capacity_tract_{tag}.csv", index=False)

    print(
        f"  [capacity] Done. "
        f"Tracts with capacity: {len(cap):,}  |  "
        f"Max capacity: {cap['vehicle_capacity'].max()}"
    )
    return cap


# ===========================================================================
# STEP 2c — USAGE
# ===========================================================================

def compute_usage(
    ctx: Dict[str, Any],
    *,
    base_time_slot: str = "5min",
    aggregate_time_slot: str = "1h",
    rounding_decimals: int = 4,
    normalize: bool = True,
) -> Dict[str, pd.DataFrame]:
    """
    Infer trip starts and ends from consecutive location snapshots.

    Because dockless systems do not provide explicit trip records, usage
    is estimated by tracking whether a vehicle was present at a location
    in one 5-minute window but absent (or in a different location) in the
    next — a disappearance is a trip start, a reappearance is a trip end.

    Parameters
    ----------
    ctx                  : context from load_dockless_context
    base_time_slot       : time-floor for detecting location changes (5min)
    aggregate_time_slot  : time-floor for tract-level hourly aggregation
    rounding_decimals    : coordinate rounding for location matching
    normalize            : add min-max normalised starts/ends columns

    Returns
    -------
    dict with keys "block" and "tract" — both pd.DataFrames
    """
    done_df = ctx["done_df"].copy()
    out_dir = ctx["out_dir"]
    tag     = ctx["tag"]
    save    = ctx["save_outputs"]

    done_df["slot"] = done_df["timestamp"].dt.floor(base_time_slot)
    done_df["lat_r"] = done_df["lat"].round(rounding_decimals)
    done_df["lon_r"] = done_df["lon"].round(rounding_decimals)

    # Count vehicles at each (block, slot, rounded location)
    cnts = (
        done_df
        .groupby(["census_block", "slot", "lat_r", "lon_r"])
        .size()
        .reset_index(name="cnt")
    )

    # Shift one slot forward to create "previous" counts
    prev = cnts.copy()
    prev["slot"] += pd.to_timedelta(base_time_slot)

    # Merge current and previous counts to detect changes
    flux = prev.merge(
        cnts,
        on=["census_block", "slot", "lat_r", "lon_r"],
        how="outer",
        suffixes=("_prev", "_curr"),
    ).fillna(0)

    # Decrease in count = bikes left (trip starts)
    # Increase in count = bikes arrived (trip ends)
    flux["starts"] = (flux["cnt_prev"] - flux["cnt_curr"]).clip(lower=0)
    flux["ends"]   = (flux["cnt_curr"] - flux["cnt_prev"]).clip(lower=0)

    use_block = (
        flux.groupby(["census_block", "slot"])[["starts", "ends"]]
        .sum()
        .reset_index()
    )

    # Aggregate to tract × hour
    use_block["h_slot"]      = use_block["slot"].dt.floor(aggregate_time_slot)
    use_block["census_tract"] = use_block["census_block"].str[:ctx["tract_digits"]]
    use_tract = (
        use_block.groupby(["census_tract", "h_slot"])[["starts", "ends"]]
        .sum()
        .reset_index()
        .rename(columns={"h_slot": "time_slot"})
    )

    if normalize:
        use_tract["trips_starting_norm"] = _minmax(use_tract["starts"]).round(5)
        use_tract["trips_ending_norm"]   = _minmax(use_tract["ends"]).round(5)

    if save:
        use_block.to_csv(out_dir / f"usage_5min_block_{tag}.csv",       index=False)
        use_tract.to_csv(out_dir / f"usage_norm_hourly_tract_{tag}.csv", index=False)

    print(f"  [usage] Done. Tract rows: {len(use_tract):,}")
    return {"block": use_block, "tract": use_tract}


# ===========================================================================
# STEP 2d — IDLE TIME
# ===========================================================================

def compute_idle_time(
    ctx: Dict[str, Any],
    *,
    hour_bucket_freq: str = "1h",
    rounding_decimals: int = 4,
    vehicle_type_col: str = "vehicle_type_id",
    default_vehicle_type: str = "",
    normalize: bool = True,
) -> Dict[str, pd.DataFrame]:
    """
    Estimate idle time per vehicle per tract per hour.

    Method: count how many 5-minute pings a vehicle produces within a
    given hour in the same census block.  Each ping represents 5 minutes
    of the vehicle being stationary (idle), so:

        avg_idle_time_minutes = ping_count × 5

    Parameters
    ----------
    ctx                  : context from load_dockless_context
    hour_bucket_freq     : time-floor for hourly aggregation
    rounding_decimals    : kept for API consistency (unused in this method)
    vehicle_type_col     : column holding vehicle type (e-bike, scooter…)
    default_vehicle_type : fallback if the column is absent or null
    normalize            : add a min-max normalised idle-time column

    Returns
    -------
    dict with keys "block" and "tract" — both pd.DataFrames
    """
    done_df = ctx["done_df"].copy()
    out_dir = ctx["out_dir"]
    tag     = ctx["tag"]
    save    = ctx["save_outputs"]
    vid_col = ctx["vehicle_id_col"]

    # Fall back gracefully if the vehicle-type column is missing
    if vehicle_type_col not in done_df.columns:
        if "vehicle_type" in done_df.columns:
            vehicle_type_col = "vehicle_type"
        else:
            done_df[vehicle_type_col] = default_vehicle_type

    done_df[vehicle_type_col] = done_df[vehicle_type_col].fillna(default_vehicle_type)
    done_df = done_df.sort_values([vid_col, "timestamp"]).reset_index(drop=True)
    done_df["h_bucket"] = done_df["timestamp"].dt.floor(hour_bucket_freq)

    # Count pings per (block, hour, vehicle type) — each ping = 5 min idle
    idle_block = (
        done_df
        .groupby(["census_block", "h_bucket", vehicle_type_col])
        .size()
        .reset_index(name="ping_count")
    )
    idle_block["avg_idle_time_minutes"] = idle_block["ping_count"] * 5
    idle_block["num_idle_segments"]     = idle_block["ping_count"]
    idle_block["census_tract"]          = idle_block["census_block"].str[:ctx["tract_digits"]]

    # Aggregate to tract level
    idle_tract = (
        idle_block
        .groupby(["census_tract", "h_bucket", vehicle_type_col])[
            ["avg_idle_time_minutes", "num_idle_segments"]
        ]
        .sum()
        .reset_index()
        .rename(columns={"h_bucket": "time_slot"})
    )

    if normalize:
        idle_tract["avg_idle_time_norm"] = _minmax(
            idle_tract["avg_idle_time_minutes"]
        ).round(5)

    if save:
        idle_block.to_csv(out_dir / f"idle_summary_block_{tag}.csv",      index=False)
        idle_tract.to_csv(out_dir / f"idle_norm_hourly_tract_{tag}.csv",  index=False)

    print(f"  [idle_time] Done. Tract rows: {len(idle_tract):,}")
    return {"block": idle_block, "tract": idle_tract}


# ===========================================================================
# STEP 2e — SAFETY
# ===========================================================================

def compute_safety(
    ctx: Dict[str, Any],
    *,
    input_crs: str = "EPSG:4326",
    centerline_wkt_col: str = "line",
    bike_lane_wkt_col:  str = "shape",
    normalize: bool = True,
) -> pd.DataFrame:
    """
    Compute the bike-lane ratio (bike-lane length / total street length)
    per census tract as a proxy for cycling safety.

    The ratio is calculated at block level then aggregated to tract level.
    A separate "protected ratio" is computed for protected bike lanes
    (class varies by city — see _SYSTEMS safety_config).

    Parameters
    ----------
    ctx                : context from load_dockless_context
    input_crs          : CRS of the street / bike-lane source files
    centerline_wkt_col : WKT geometry column name in Centerline CSVs
    bike_lane_wkt_col  : WKT geometry column name in bike-lane CSVs
    normalize          : add normalised ratio columns

    Returns
    -------
    pd.DataFrame with one row per census tract
    """
    out_dir = ctx["out_dir"]
    tag     = ctx["tag"]
    save    = ctx["save_outputs"]
    preset  = ctx["_preset"]
    tract_d = ctx["tract_digits"]

    # Resolve per-system safety parameters
    safety_epsg = preset.get("safety_epsg", 26910)
    s_conf      = preset.get("safety_config", {})
    bl_class_col       = s_conf.get("bike_lane_class_col")
    protected_values   = s_conf.get("protected_values", [])
    protected_match    = s_conf.get("protected_match_mode", "contains")

    # ------------------------------------------------------------------
    # Load census blocks in the correct projected CRS for length measurement
    # ------------------------------------------------------------------
    blocks = gpd.read_file(str(ctx["census_blocks_shp"])).to_crs(epsg=safety_epsg)
    b_col  = "GEOID20" if "GEOID20" in blocks.columns else "GEOID"

    # ------------------------------------------------------------------
    # Load street centrelines
    # ------------------------------------------------------------------
    st_path = Path(ctx["centerline_streets_path"])
    if st_path.suffix.lower() == ".csv":
        st_df = pd.read_csv(st_path)
        st_df["geometry"] = st_df[centerline_wkt_col].apply(
            lambda x: wkt.loads(x) if isinstance(x, str) else None
        )
        streets = gpd.GeoDataFrame(st_df, geometry="geometry", crs=input_crs)
    else:
        streets = gpd.read_file(st_path).to_crs(input_crs)
    streets = streets.to_crs(blocks.crs)

    # ------------------------------------------------------------------
    # Load bike lanes (and optionally planned bike lanes)
    # ------------------------------------------------------------------
    bl_path = Path(ctx["bike_lanes_path"])
    if bl_path.suffix.lower() == ".csv":
        bl_df = pd.read_csv(bl_path)
        bl_df["geometry"] = bl_df[bike_lane_wkt_col].apply(
            lambda x: wkt.loads(x) if isinstance(x, str) else None
        )
        bike_lanes = gpd.GeoDataFrame(bl_df, geometry="geometry", crs=input_crs)
    else:
        bike_lanes = gpd.read_file(bl_path).to_crs(input_crs)

    if ctx["planned_bike_lanes_path"]:
        planned = gpd.read_file(str(ctx["planned_bike_lanes_path"])).to_crs(input_crs)
        bike_lanes = pd.concat([bike_lanes, planned], ignore_index=True)

    bike_lanes = bike_lanes.to_crs(blocks.crs)

    # Filter to protected lanes if the system config specifies a class column
    if bl_class_col and bl_class_col in bike_lanes.columns and protected_values:
        protected = bike_lanes[bike_lanes[bl_class_col].isin(protected_values)]
    else:
        protected = bike_lanes.iloc[0:0]   # empty — no protected-lane distinction

    # ------------------------------------------------------------------
    # Compute intersected lengths per census block
    # ------------------------------------------------------------------
    def _lengths(lines: gpd.GeoDataFrame, polys: gpd.GeoDataFrame, col_name: str) -> pd.DataFrame:
        if lines.empty:
            return pd.DataFrame({"census_block": [], col_name: []})
        clipped = gpd.overlay(lines, polys, how="intersection")
        clipped["_len"] = clipped.geometry.length
        return (
            clipped.groupby(b_col)["_len"]
            .sum()
            .reset_index(name=col_name)
            .rename(columns={b_col: "census_block"})
        )

    st_len   = _lengths(streets,   blocks, "st_len")
    bl_len   = _lengths(bike_lanes, blocks, "bl_len")
    prot_len = _lengths(protected,  blocks, "pr_len")

    safe = (
        st_len
        .merge(bl_len,   on="census_block", how="left")
        .merge(prot_len, on="census_block", how="left")
        .fillna(0)
    )
    safe["census_tract"] = safe["census_block"].astype(str).str[:tract_d]

    # ------------------------------------------------------------------
    # Load centroid file to define the full tract universe
    # ------------------------------------------------------------------
    ct_path = Path(ctx["centroid_tract_path"])
    ct = (
        gpd.read_file(ct_path)
        if ct_path.suffix.lower() != ".csv"
        else pd.read_csv(ct_path)
    )
    cid = _get_centroid_id_col(ct)

    if cid:
        base = pd.DataFrame({"census_tract": ct[cid]})
        base["census_tract"] = base["census_tract"].apply(_clean_tract_id)
        safe["census_tract"] = safe["census_tract"].apply(_clean_tract_id)

        # Align ID lengths (pad with leading zeros if needed)
        len_base = base["census_tract"].str.len().mode()[0]
        len_safe = safe["census_tract"].str.len().mode()[0]
        if len_base < len_safe:
            base["census_tract"] = base["census_tract"].str.zfill(int(len_safe))
        elif len_safe < len_base:
            safe["census_tract"] = safe["census_tract"].str.zfill(int(len_base))
    else:
        base = pd.DataFrame({"census_tract": []})

    # Aggregate to tract and merge against the full tract universe
    tract_safe = (
        safe.groupby("census_tract")[["st_len", "bl_len", "pr_len"]]
        .sum()
        .reset_index()
    )
    final = base.merge(tract_safe, on="census_tract", how="left").fillna(0)

    final["bike_lane_ratio"]           = np.where(
        final["st_len"] > 0, final["bl_len"] / final["st_len"], 0
    )
    final["protected_bike_lane_ratio"] = np.where(
        final["st_len"] > 0, final["pr_len"] / final["st_len"], 0
    )

    if normalize:
        final["bike_lane_ratio_norm"]           = _minmax(final["bike_lane_ratio"]).round(5)
        final["protected_bike_lane_ratio_norm"] = _minmax(
            final["protected_bike_lane_ratio"]
        ).round(5)

    if save:
        safe.to_csv( out_dir / f"safety_block_{tag}.csv",  index=False)
        final.to_csv(out_dir / f"safety_tract_{tag}.csv",  index=False)

    print(f"  [safety] Done. Tracts: {len(final):,}")
    return final


# ===========================================================================
# CONVENIENCE — compute all metrics in one call
# ===========================================================================

def compute_all(
    ctx: Dict[str, Any],
    *,
    normalize: bool = True,
) -> Dict[str, Any]:
    """
    Run all five metrics in the recommended order and return every result.

    Order:
        1. availability
        2. capacity     (uses the same availability data, no extra input)
        3. usage
        4. idle_time
        5. safety

    Parameters
    ----------
    ctx       : context from load_dockless_context
    normalize : passed through to every individual compute function

    Returns
    -------
    dict with keys:
        availability  — {"block": df, "tract": df}
        capacity      — pd.DataFrame
        usage         — {"block": df, "tract": df}
        idle_time     — {"block": df, "tract": df}
        safety        — pd.DataFrame
    """
    print(f"\n[{ctx['system_key']}] Running compute_all...")

    avail  = compute_availability(ctx, normalize=normalize)
    cap    = compute_capacity(ctx, normalize=normalize)
    usage  = compute_usage(ctx, normalize=normalize)
    idle   = compute_idle_time(ctx, normalize=normalize)
    safety = compute_safety(ctx, normalize=normalize)

    print(f"[{ctx['system_key']}] All metrics complete. Outputs in: {ctx['out_dir']}")
    return {
        "availability": avail,
        "capacity":     cap,
        "usage":        usage,
        "idle_time":    idle,
        "safety":       safety,
    }


if __name__ == "__main__":
    print("dockless_wrapper module loaded successfully.")