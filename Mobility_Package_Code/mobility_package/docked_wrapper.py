"""
=============================================================================
DOCKED BIKE SHARE UTILITY ANALYTICS PIPELINE (PRODUCTION v4)
=============================================================================

OVERVIEW
--------
This module provides modular functions to compute docked bike share utility
metrics. Each metric has its own function that can be called independently.

AVAILABLE METRICS & THEIR FUNCTIONS
------------------------------------
    compute_availability()  - bikes, e-bikes, and docks available per block/tract
    compute_capacity()      - station capacity and vehicle occupancy per tract
    compute_safety()        - bike lane and protected lane ratios per tract
    compute_usage()         - trip starts and ends per block/tract
    compute_idle_time()     - average idle time per block/tract

HOW TO USE
----------
    Step 1 — load the shared context (always required first)
    Step 2 — call whichever metric(s) you want

    Dependencies between metrics are handled internally.
    The user never needs to pass results between functions.

EXAMPLE — single metric
-----------------------
    ctx  = load_docked_context(city="NYC", ...)
    safe = compute_safety(ctx, time_start="2025-04-06 00:00:00", time_end="2025-04-06 23:59:59")

EXAMPLE — metrics that need trip data
--------------------------------------
    ctx  = load_docked_context(city="NYC", ...)
    idle = compute_idle_time(ctx, trip_csv=r"path/to/trips", time_start="...", time_end="...")

EXAMPLE — all metrics at once
------------------------------
    ctx     = load_docked_context(city="NYC", ...)
    results = compute_all(ctx, trip_csv=r"path/to/trips", time_start="...", time_end="...")

NOTE
----
    trip_csv is only required for compute_usage() and compute_idle_time().
    You can omit it entirely if you only need availability, capacity, or safety.
=============================================================================
"""

from __future__ import annotations

import json
import warnings
import zipfile
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

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
# City configuration
# ---------------------------------------------------------------------------

CITY_CONFIG: Dict[str, Dict[str, Any]] = {
    "SF": {
        "use_api_fallback": True,
        "assets": {
            "census_blocks": r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Usage\San_Fran_Baywheels\tl_2024_06_tabblock20.shp",
            "tracts":        r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Capacity\San_Fran_Baywheels\tl_2024_06_tract.shp",
            "centerline":    r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Safety\San_Fran_Baywheels\Streets___Active_and_Retired_20250626 (1).csv",
            "bike_lanes":    r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Safety\San_Fran_Baywheels\Bikelane.csv",
        },
        "geo": {
            "blocks_id":             "GEOID20",
            "tract_id":              "GEOID",
            "crs":                   "EPSG:4326",
            "metric_crs":            "EPSG:26910",
            "safety_type":           "csv_wkt",
            "wkt_candidates":        ("geometry", "shape", "line", "the_geom", "wkt", "geometry_wkt", "WKT", "geom"),
            "external_tract_prefix": None,
            "drop_staten_island":    False,
        },
        "safety_rule": {
            "col_candidates": ("BARRIER", "FACILITY_T", "BUFFERED", "RAISED", "SYMBOLOGY"),
            "match_type":     "not_empty_or_contains",
            "match_value":    r"PROTECT|SEPARAT|CYCLETRACK|BARRIER|RAISED|BUFFER",
        },
    },

    "NJ": {
        "use_api_fallback": False,
        "assets": {
            "census_blocks": r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Safety\NJ\tl_2024_34_tabblock20.shp",
            "tracts":        r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Capacity\NJ\tl_2024_34_tract.shp",
            "centroid_csv":  r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Capacity\NJ\centroid_tract_nj.csv",
            "centerline":    r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Safety\NJ\Tran_road.shp",
            "bike_lanes":    r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Safety\NJ\bike-lanes-2020-division-of-transportation.shp",
        },
        "geo": {
            "blocks_id":             "GEOID20",
            "tract_id":              "GEOID",
            "crs":                   "EPSG:4326",
            "metric_crs":            "EPSG:32618",
            "safety_type":           "shp",
            "wkt_candidates":        (),
            "external_tract_prefix": None,
            "drop_staten_island":    False,
        },
        "safety_rule": {
            "col_candidates": ("type", "facility", "facilitycl", "class", "lane_type"),
            "match_type":     "contains",
            "match_value":    "PROTECT",
        },
    },

    "NYC": {
        "use_api_fallback": True,
        "assets": {
            "census_blocks": r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\GBFS_Census_Tract\NYC\tl_2024_36_tabblock20.shp",
            "tracts":        r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Capacity\NYC\tl_2024_36_tract.shp",
            "centroid_csv":  r"D:\Research Fellowship\Capacity_NYC\centroid_tract_computed.csv",
            "centerline":    r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Safety\NYC\CSCL_PlowNYC_20250619.csv",
            "bike_lanes":    r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Safety\NYC\New_York_City_Bike_Routes_20250619.csv",
        },
        "geo": {
            "blocks_id":             "GEOID20",
            "tract_id":              "GEOID",
            "crs":                   "EPSG:4326",
            "metric_crs":            "EPSG:32618",
            "safety_type":           "csv_wkt",
            "wkt_candidates":        ("geometry", "the_geom", "wkt", "geometry_wkt", "WKT"),
            "external_tract_prefix": "34",
            "drop_staten_island":    True,
        },
        "safety_rule": {
            "col_candidates": ("facilitycl", "facility", "class", "ft", "type"),
            "match_type":     "equals",
            "match_value":    "I",
        },
    },

    "PITT": {
        "use_api_fallback": True,
        "assets": {
            "census_blocks": r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Safety\Pitt\tl_2024_42_tabblock20.shp",
            "tracts":        r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Capacity\Pitt\tl_2024_42_tract.shp",
            "centroid_csv":  r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Capacity\Pitt\centroid_tract_pa.csv",
            "centerline":    r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Safety\Pitt\Pittsburgh_Street_Centerline.shp",
            "bike_lanes":    r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Safety\Pitt\Bike Map\Bike Lanes.shp",
        },
        "geo": {
            "blocks_id":             "GEOID20",
            "tract_id":              "GEOID",
            "crs":                   "EPSG:4326",
            "metric_crs":            "EPSG:32617",
            "safety_type":           "shp",
            "wkt_candidates":        (),
            "external_tract_prefix": None,
            "drop_staten_island":    False,
        },
        "safety_rule": {
            "col_candidates": ("facility", "type", "class", "status", "lane_type", "BIKE_FACIL", "CATEGORY"),
            "match_type":     "contains",
            "match_value":    "PROTECT",
        },
    },
}


# ===========================================================================
# INTERNAL HELPER CLASSES
# These are not meant to be called directly by the user.
# ===========================================================================

class DataHelper:
    """Handles all data loading and column normalization."""

    @staticmethod
    def pick_col(df: pd.DataFrame, candidates: Sequence[str], required: bool = False, label: str = "") -> Optional[str]:
        """Return the first matching column from candidates that exists in df."""
        cols = set(df.columns)
        for c in candidates:
            if c in cols:
                return c
        if required:
            raise ValueError(f"Missing required column for {label}. Tried: {candidates}")
        return None

    @staticmethod
    def normalize_id(s: pd.Series) -> pd.Series:
        """Standardize IDs to uppercase strings, stripping trailing .0"""
        return s.astype(str).str.strip().str.upper().str.replace(r"\.0$", "", regex=True)

    @staticmethod
    def normalize_tract(s: pd.Series) -> pd.Series:
        """Zero-pad census tract IDs to 11 characters."""
        return s.astype(str).str.split(".").str[0].str.zfill(11)

    @staticmethod
    def tract_from_block(s: pd.Series) -> pd.Series:
        """Derive the 11-character census tract ID from a census block ID."""
        return s.astype(str).str.split(".").str[0].str[:11]

    @classmethod
    def load_stations(cls, path: Path) -> pd.DataFrame:
        """
        Load station information CSV and normalize column names.
        Handles varying column naming conventions across cities.
        """
        df      = pd.read_csv(path)
        mapping = {
            cls.pick_col(df, ["station_id", "stationId", "id", "Station ID"], True, "station_id"): "station_id",
            cls.pick_col(df, ["lat", "latitude", "y"],                         True, "lat"):        "lat",
            cls.pick_col(df, ["lon", "lng", "longitude", "x"],                 True, "lon"):        "lon",
            cls.pick_col(df, ["capacity", "dock_count", "num_docks"],          True, "capacity"):   "capacity",
        }
        out = df.rename(columns=mapping)
        out["station_id"] = cls.normalize_id(out["station_id"])

        cb = cls.pick_col(out, ["census_block", "block_geoid", "GEOID20"])
        if cb and cb != "census_block":
            out = out.rename(columns={cb: "census_block"})

        ct = cls.pick_col(out, ["census_tract", "tract_geoid", "GEOID"])
        if ct and ct != "census_tract":
            out = out.rename(columns={ct: "census_tract"})

        return out

    @classmethod
    def load_trips(cls, path: Union[str, Path]) -> pd.DataFrame:
        """
        Load trip data from a CSV file, folder of CSVs, or ZIP archive.
        Normalizes column names across different city data formats.
        """
        path = Path(path)
        dfs  = []

        print(f"   -> Reading trip data from: {path}")

        if path.is_dir():
            files = sorted(path.glob("*.csv"))
            if not files:
                raise ValueError(f"No .csv files found in directory: {path}")
            print(f"   -> Found {len(files)} trip files. Aggregating...")
            for f in files:
                dfs.append(pd.read_csv(f, engine="c", low_memory=False))

        elif path.suffix.lower() == ".zip":
            print("   -> Detected ZIP file. Reading internal CSVs...")
            with zipfile.ZipFile(path) as z:
                for name in z.namelist():
                    if name.lower().endswith(".csv") and not name.startswith("__MACOSX"):
                        with z.open(name) as f:
                            dfs.append(pd.read_csv(f, low_memory=False))
        else:
            dfs.append(pd.read_csv(path, engine="c", low_memory=False))

        if not dfs:
            raise ValueError("No trip data found.")

        df = pd.concat(dfs, ignore_index=True) if len(dfs) > 1 else dfs[0]

        mapping = {
            cls.pick_col(df, ["started_at", "start_time", "starttime", "Start Date"], True, "start"): "started_at",
            cls.pick_col(df, ["ended_at",   "end_time",   "stoptime",  "End Date"],   True, "end"):   "ended_at",
        }
        opt_map = {
            cls.pick_col(df, ["rideable_type", "bike_type", "vehicle_type"]):  "rideable_type",
            cls.pick_col(df, ["start_lat", "startLatitude", "StartLat"]):      "start_lat",
            cls.pick_col(df, ["start_lng", "startLongitude", "StartLng"]):     "start_lng",
            cls.pick_col(df, ["end_lat",   "endLatitude",   "EndLat"]):        "end_lat",
            cls.pick_col(df, ["end_lng",   "endLongitude",  "EndLng"]):        "end_lng",
            cls.pick_col(df, ["start_station_id", "Start Station Id"]):        "start_station_id",
            cls.pick_col(df, ["end_station_id",   "End Station Id"]):          "end_station_id",
        }
        mapping.update({k: v for k, v in opt_map.items() if k})
        df = df.rename(columns=mapping)

        if "start_station_id" in df.columns:
            df["start_station_id"] = cls.normalize_id(df["start_station_id"])
        if "end_station_id" in df.columns:
            df["end_station_id"] = cls.normalize_id(df["end_station_id"])

        return df


class GeoHelper:
    """Handles all spatial operations: loading network files and geocoding points."""

    @staticmethod
    def load_network_lines(path: Path, kind: str, target_crs, candidates: tuple) -> gpd.GeoDataFrame:
        """
        Load street or bike lane geometry from a shapefile or WKT CSV.
        Reprojects to target CRS for accurate length calculations.
        """
        if kind == "shp":
            gdf = gpd.read_file(path)
            if gdf.crs is None:
                raise ValueError(f"No CRS found in {path}")
            return gdf.to_crs(target_crs)

        if isinstance(candidates, str):
            candidates = (candidates,)
        df      = pd.read_csv(path, engine="c")
        wkt_col = DataHelper.pick_col(df, candidates, True, "WKT Column")

        def safe_load(x):
            try:
                return wkt.loads(str(x))
            except Exception:
                return None

        df["geometry"] = df[wkt_col].apply(safe_load)
        gdf = gpd.GeoDataFrame(df[df["geometry"].notna()], geometry="geometry", crs="EPSG:4326")
        return gdf.to_crs(target_crs)

    @staticmethod
    def geocode_points(df: pd.DataFrame, lon_col: str, lat_col: str, blocks_gdf: gpd.GeoDataFrame, id_col: str) -> pd.DataFrame:
        """
        Spatially join lat/lon points to census blocks.
        Returns a mapping of (lon, lat) -> census_block.
        """
        points = df[[lon_col, lat_col]].dropna().drop_duplicates()
        if points.empty:
            return pd.DataFrame(columns=[lon_col, lat_col, "census_block"])

        gdf    = gpd.GeoDataFrame(
            points,
            geometry=[Point(xy) for xy in zip(points[lon_col], points[lat_col])],
            crs="EPSG:4326",
        )
        joined = gpd.sjoin(gdf, blocks_gdf[[id_col, "geometry"]], how="left", predicate="within")
        joined = joined.rename(columns={id_col: "census_block"})
        return joined[[lon_col, lat_col, "census_block"]].copy().rename(
            columns={lon_col: "lon", lat_col: "lat"}
        )

    @staticmethod
    def api_fill_blocks(df: pd.DataFrame, benchmark: str, vintage: str) -> pd.DataFrame:
        """
        Fill missing census block assignments using the Census Geocoder API.
        Capped at 5000 points to avoid excessive API calls.
        """
        missing = df[df["census_block"].isna()][["lat", "lon"]].drop_duplicates()
        if missing.empty:
            return df

        if len(missing) > 5000:
            print(f"⚠️ Warning: {len(missing)} missing blocks. Capping API fallback at 5000 points.")
            missing = missing.head(5000)

        def fetch(r):
            try:
                url = (
                    "https://geocoding.geo.census.gov/geocoder/geographies/coordinates"
                    f"?x={r.lon}&y={r.lat}&benchmark={benchmark}&vintage={vintage}&format=json"
                )
                js = requests.get(url, timeout=5).json()
                return js["result"]["geographies"]["2020 Census Blocks"][0]["GEOID"]
            except Exception:
                return None

        tqdm.pandas(desc="API Geocoding Fallback")
        missing["new_block"] = missing.progress_apply(fetch, axis=1)

        merged = df.merge(missing, on=["lat", "lon"], how="left")
        if "new_block" in merged.columns:
            merged["census_block"] = merged["census_block"].fillna(merged["new_block"])
            merged = merged.drop(columns=["new_block"])
        return merged


class MetricHelper:
    """
    Core calculation routines shared across all compute functions.

    Each method here is a pure calculation — it takes dataframes in
    and returns dataframes out with no side effects. This makes them
    easy to test and reuse across metrics.
    """

    @staticmethod
    def normalize(series: pd.Series) -> pd.Series:
        """Min-max normalize a numeric series to the range [0, 1]."""
        s      = pd.to_numeric(series, errors="coerce")
        mn, mx = s.min(skipna=True), s.max(skipna=True)
        if pd.isna(mn) or pd.isna(mx) or mx <= mn:
            return pd.Series(0.0, index=s.index)
        return (s - mn) / (mx - mn)

    @staticmethod
    def safe_ratio(numer: pd.Series, denom: pd.Series) -> pd.Series:
        """Divide two series, returning 0 wherever the denominator is 0."""
        return numer.div(denom.where(denom > 0, other=pd.NA)).fillna(0)

    @staticmethod
    def calc_availability(
        df: pd.DataFrame,
        level: str,
        gran: str,
        out_dir: Path,
        save: bool,
        ext_prefix: str = None,
    ) -> Dict[str, pd.DataFrame]:
        """
        Aggregate station status snapshots into availability metrics.

        Parameters
        ----------
        df         : station status dataframe filtered to the time window
        level      : "block" or "tract"
        gran       : time bucket e.g. "1h" or "5min"
        out_dir    : output directory path
        save       : whether to write CSV files
        ext_prefix : census tract prefix to exclude e.g. NJ tracts from NYC
        """
        geo = "census_block" if level == "block" else "census_tract"
        agg = df.groupby([geo, "timestamp"], as_index=False)[
            ["num_bikes_available", "num_ebikes_available", "num_docks_available", "total_vehicle_available"]
        ].sum()

        agg["time_slot"] = agg["timestamp"].dt.floor(gran)
        raw = agg.groupby([geo, "time_slot"], as_index=False).mean(numeric_only=True).round(0)

        for c in raw.columns:
            if "available" in c:
                raw[c] = raw[c].astype(int)

        if level == "tract":
            raw["census_tract"] = DataHelper.normalize_tract(raw["census_tract"])
            if ext_prefix:
                raw = raw[~raw["census_tract"].str.startswith(ext_prefix)]

        norm = raw.copy()
        for c in ["num_bikes_available", "num_ebikes_available", "num_docks_available", "total_vehicle_available"]:
            norm[f"{c}_norm"] = MetricHelper.normalize(norm[c]).round(5)

        if save:
            raw.to_csv(out_dir  / f"availability__raw__{level}.csv",  index=False)
            norm.to_csv(out_dir / f"availability__norm__{level}.csv", index=False)

        return {"raw": raw, "norm": norm}

    @staticmethod
    def calc_usage(
        trips: pd.DataFrame,
        time_range: Tuple[pd.Timestamp, pd.Timestamp],
        blocks: List[str],
        gran_str: str,
        out_name: str,
        out_dir: Path,
        save: bool,
    ) -> pd.DataFrame:
        """
        Count trip starts and ends per census block per time slot.

        Parameters
        ----------
        trips      : enriched trip dataframe with slot_start / slot_end columns
        time_range : (start, end) timestamps defining the full grid
        blocks     : all census block IDs to include
        gran_str   : pandas frequency string e.g. "1h" or "5min"
        out_name   : filename stem for the output CSV
        out_dir    : output directory path
        save       : whether to write the CSV file
        """
        starts = trips.groupby(["start_census_block", "slot_start"]).size().rename("trips_starting")
        ends   = trips.groupby(["end_census_block",   "slot_end"]).size().rename("trips_ending")

        slots = pd.date_range(
            start=time_range[0].floor(gran_str),
            end=time_range[1].ceil(gran_str),
            freq=gran_str,
        )
        grid = pd.MultiIndex.from_product(
            [blocks, slots], names=["census_block", "time_slot"]
        ).to_frame(index=False)

        out = grid.merge(starts, left_on=["census_block", "time_slot"], right_index=True, how="left")
        out = out.merge(ends,   left_on=["census_block", "time_slot"], right_index=True, how="left")
        out = out.fillna(0).astype({"trips_starting": int, "trips_ending": int})

        if save:
            out.to_csv(out_dir / f"{out_name}.csv", index=False)
        return out

    @staticmethod
    def map_rideable_type(trips: pd.DataFrame) -> pd.DataFrame:
        """Add a boolean _is_ebike column derived from the rideable_type field."""
        df = trips.copy()
        if "rideable_type" not in df.columns:
            return df
        t = df["rideable_type"].astype(str).str.lower()
        df["_is_ebike"] = t.str.contains("electric|ebike|e-bike|assist", na=False)
        return df

    @staticmethod
    def calc_idle_time(
        m: pd.DataFrame,
        out_dir: Path,
        save: bool,
        ext: Optional[str],
    ) -> Dict[str, pd.DataFrame]:
        """
        Compute average idle duration per vehicle per census block per hour.

        Uses a queue-based algorithm: vehicles that are present in a slot
        but not moved are tracked. When they eventually move, the time they
        sat idle is recorded. The average across all vehicles per block per
        hour is the idle time metric.

        This is extracted as a static method so it is consistent with how
        calc_availability and calc_usage are structured — a pure calculation
        that takes dataframes in and returns dataframes out.

        Parameters
        ----------
        m       : merged inventory + flux dataframe at 5-min resolution
                  must have columns: census_block, time_slot, hour,
                  idle_vehicles
        out_dir : output directory path
        save    : whether to write CSV files
        ext     : external tract prefix to exclude (or None)
        """
        idle_res = []

        for block, b_df in m.groupby("census_block"):
            for hour, h_df in b_df.groupby("hour"):
                h_df = h_df.sort_values("time_slot")

                # pool tracks when each idle vehicle started sitting still
                # durations collects how long each vehicle was idle before moving
                pool, durations = deque(), []

                for _, row in h_df.iterrows():
                    curr_t = row["time_slot"]
                    cnt    = int(row["idle_vehicles"])

                    # more idle vehicles than tracked — new vehicles became idle
                    while cnt > len(pool):
                        pool.append(curr_t)

                    # fewer idle vehicles than tracked — some vehicles moved
                    while cnt < len(pool):
                        start_t = pool.popleft()
                        durations.append((curr_t - start_t).total_seconds() / 60.0)

                # any vehicles still idle at end of hour get their duration closed out
                final_t = hour + pd.Timedelta(hours=1)
                while pool:
                    start_t = pool.popleft()
                    durations.append((final_t - start_t).total_seconds() / 60.0)

                avg = round(sum(durations) / len(durations), 2) if durations else 0.0
                idle_res.append({"census_block": block, "hour": hour, "avg_idle_time": avg})

        idle_df = pd.DataFrame(idle_res)

        if save:
            idle_df.to_csv(out_dir / "idle_time_block.csv", index=False)

        if idle_df.empty:
            return {"idle_block": idle_df, "idle_tract": pd.DataFrame()}

        # aggregate from block to tract level
        idle_df["census_tract"] = DataHelper.normalize_tract(
            DataHelper.tract_from_block(idle_df["census_block"].astype(str))
        )
        if ext:
            idle_df = idle_df[~idle_df["census_tract"].str.startswith(ext)]

        i_tract = idle_df.groupby(["census_tract", "hour"], as_index=False)["avg_idle_time"].mean()
        i_tract["avg_idle_time_norm"] = MetricHelper.normalize(i_tract["avg_idle_time"]).round(5)

        if save:
            i_tract.to_csv(out_dir / "idle_time_norm_tract.csv", index=False)

        return {"idle_block": idle_df, "idle_tract": i_tract}


# ===========================================================================
# INTERNAL SHARED UTILITIES
# These are used internally by the compute_*() functions to avoid
# repeating the same logic across metrics that share dependencies.
# ===========================================================================

def _load_and_enrich_trips(
    ctx: Dict[str, Any],
    trip_csv: Union[str, Path],
    time_start: Optional[Union[str, pd.Timestamp]],
    time_end: Optional[Union[str, pd.Timestamp]],
) -> Dict[str, Any]:
    """
    Load trip data, assign census blocks to each trip start/end,
    and filter to the requested time window.

    Used internally by compute_usage() and compute_idle_time().
    Returns the enriched trips dataframe plus derived values needed
    by both metrics so the work is never duplicated.
    """
    si         = ctx["si"]
    blocks_gdf = ctx["blocks_gdf"]
    blocks_id  = ctx["blocks_id"]

    trips = DataHelper.load_trips(trip_csv)
    trips["started_at"] = pd.to_datetime(trips["started_at"], errors="coerce")
    trips["ended_at"]   = pd.to_datetime(trips["ended_at"],   errors="coerce")

    t_min, t_max = trips["started_at"].min(), trips["started_at"].max()
    t_win_s = pd.to_datetime(time_start) if time_start else t_min
    t_win_e = pd.to_datetime(time_end)   if time_end   else t_max

    if t_win_s > t_max or t_win_e < t_min:
        print(f"⚠️ WARNING: Request window ({t_win_s} - {t_win_e}) does not overlap trip data ({t_min} - {t_max}).")

    trips = trips[(trips["started_at"] >= t_win_s) & (trips["started_at"] <= t_win_e)].copy()

    # assign start census block via station ID lookup
    sm = si[["station_id", "census_block"]].copy()

    if "start_station_id" in trips.columns:
        if "start_census_block" in trips.columns:
            trips.drop(columns=["start_census_block"], inplace=True)
        trips = trips.merge(sm, left_on="start_station_id", right_on="station_id", how="left") \
                     .rename(columns={"census_block": "start_census_block"}) \
                     .drop(columns=["station_id"])

    if "end_station_id" in trips.columns:
        if "end_census_block" in trips.columns:
            trips.drop(columns=["end_census_block"], inplace=True)
        trips = trips.merge(sm, left_on="end_station_id", right_on="station_id", how="left") \
                     .rename(columns={"census_block": "end_census_block"}) \
                     .drop(columns=["station_id"])

    # fallback: geocode by lat/lon if station IDs didn't resolve blocks well
    if "start_census_block" not in trips.columns or trips["start_census_block"].isna().mean() > 0.5:
        print("   -> Fallback: Geocoding trips by lat/lon...")
        s_map = GeoHelper.geocode_points(trips, "start_lng", "start_lat", blocks_gdf, blocks_id)
        if "start_census_block" in trips.columns:
            trips.drop(columns=["start_census_block"], inplace=True)
        trips = trips.merge(s_map, left_on=["start_lng", "start_lat"], right_on=["lon", "lat"], how="left") \
                     .rename(columns={"census_block": "start_census_block"}) \
                     .drop(columns=["lon", "lat"])

        e_map = GeoHelper.geocode_points(trips, "end_lng", "end_lat", blocks_gdf, blocks_id)
        if "end_census_block" in trips.columns:
            trips.drop(columns=["end_census_block"], inplace=True)
        trips = trips.merge(e_map, left_on=["end_lng", "end_lat"], right_on=["lon", "lat"], how="left") \
                     .rename(columns={"census_block": "end_census_block"}) \
                     .drop(columns=["lon", "lat"])

    trips["start_census_block"] = trips["start_census_block"].astype(str).str.split(".").str[0]
    trips["end_census_block"]   = trips["end_census_block"].astype(str).str.split(".").str[0]

    all_blocks = [
        x for x in pd.concat([trips["start_census_block"], trips["end_census_block"]]).unique()
        if x != "nan"
    ]

    trips["slot_start"] = trips["started_at"].dt.floor("5min")
    trips["slot_end"]   = trips["ended_at"].dt.floor("5min")

    return {"trips": trips, "all_blocks": all_blocks, "t_win_s": t_win_s, "t_win_e": t_win_e}


def _run_availability_internal(
    ctx: Dict[str, Any],
    time_start: Optional[Union[str, pd.Timestamp]],
    time_end: Optional[Union[str, pd.Timestamp]],
    granularity: str,
    group_level: str,
) -> Dict[str, Dict[str, pd.DataFrame]]:
    """
    Run availability silently as an internal dependency for capacity and safety.
    Files are never saved when called this way — only the result is returned.
    """
    ss_done = ctx["ss_done"]
    out_dir = ctx["out_dir"]
    ext     = ctx["ext"]

    t_s = pd.to_datetime(time_start) if time_start else None
    t_e = pd.to_datetime(time_end)   if time_end   else None

    ss_filt = ss_done.copy()
    if t_s is not None:
        ss_filt = ss_filt[ss_filt["timestamp"] >= t_s]
    if t_e is not None:
        ss_filt = ss_filt[ss_filt["timestamp"] < t_e]

    avail_res = {}
    if group_level in {"block", "both"}:
        avail_res["block"] = MetricHelper.calc_availability(ss_filt, "block", granularity, out_dir, save=False)
    if group_level in {"tract", "both"}:
        avail_res["tract"] = MetricHelper.calc_availability(ss_filt, "tract", granularity, out_dir, save=False, ext_prefix=ext)

    return avail_res


def _run_capacity_internal(
    ctx: Dict[str, Any],
    avail_result: Dict[str, Dict[str, pd.DataFrame]],
    peak_time_slot: Optional[Union[str, pd.Timestamp]],
    peak_metric: str,
    drop_staten_island: Optional[bool],
) -> Dict[str, pd.DataFrame]:
    """
    Run capacity silently as an internal dependency for safety.
    centroid_tract_computed.csv is always written since safety reads it.
    Capacity output files are not saved when called this way.
    """
    cfg     = ctx["cfg"]
    si      = ctx["si"]
    out_dir = ctx["out_dir"]
    ext     = ctx["ext"]

    tract_gdf = gpd.read_file(cfg["assets"]["tracts"]).to_crs(epsg=4326)

    _drop_si = drop_staten_island if drop_staten_island is not None else cfg["geo"].get("drop_staten_island", False)
    if _drop_si and "COUNTYFP" in tract_gdf.columns:
        tract_gdf = tract_gdf[tract_gdf["COUNTYFP"].astype(str) != "085"].copy()

    centroids = pd.DataFrame({
        "census_tract": DataHelper.normalize_tract(tract_gdf[cfg["geo"]["tract_id"]]),
        "centroid_lon": tract_gdf.geometry.centroid.x,
        "centroid_lat": tract_gdf.geometry.centroid.y,
    })
    # always written — safety reads this file regardless of save_outputs
    centroids.to_csv(out_dir / "centroid_tract_computed.csv", index=False)

    cap_tract_agg = si.groupby("census_tract", as_index=False).agg(
        total_capacity=("capacity", "sum"),
        num_station=("station_id", "count"),
    )
    cap_tract = centroids[["census_tract"]].merge(cap_tract_agg, on="census_tract", how="left").fillna(0)

    if ext:
        cap_tract = cap_tract[~cap_tract["census_tract"].str.startswith(ext)]

    cap_tract["total_capacity_norm"] = MetricHelper.normalize(cap_tract["total_capacity"]).round(5)
    cap_tract["num_station_norm"]    = MetricHelper.normalize(cap_tract["num_station"]).round(5)

    tract_av = avail_result["tract"]["norm"]
    peak_ts  = peak_time_slot if peak_time_slot else tract_av.groupby("time_slot")[peak_metric].sum().idxmax()

    peak_data = tract_av[tract_av["time_slot"] == peak_ts][
        ["census_tract", "total_vehicle_available", "num_docks_available"]
    ].rename(columns={
        "total_vehicle_available": "vehicle_capacity",
        "num_docks_available":     "dock_capacity",
    })

    cap_df = cap_tract.merge(peak_data, on="census_tract", how="left").fillna(0)
    cap_df["vehicle_capacity_norm"] = MetricHelper.normalize(cap_df["vehicle_capacity"]).round(5)
    cap_df["dock_capacity_norm"]    = MetricHelper.normalize(cap_df["dock_capacity"]).round(5)
    cap_df["occupancy_rate"]        = MetricHelper.safe_ratio(cap_df["vehicle_capacity"], cap_df["total_capacity"])
    cap_df["return_pressure"]       = 1.0 - MetricHelper.safe_ratio(cap_df["dock_capacity"], cap_df["total_capacity"])

    return {"cap_tract": cap_tract, "cap_df": cap_df}


# ===========================================================================
# STEP 1 — CONTEXT LOADER
# Always call this first. It loads all shared data every metric needs.
# ===========================================================================

def load_docked_context(
    *,
    city: str,
    station_status_txt: Union[str, Path],
    station_information_csv: Union[str, Path],
    output_dir: Optional[Union[str, Path]] = None,
    fill_missing_with_census_api: bool = True,
    remove_tz_suffix: str = " EDT",
    census_geocoder_benchmark: str = "Public_AR_Census2020",
    census_geocoder_vintage: str = "Census2020_Current",
) -> Dict[str, Any]:
    """
    Load all shared station data needed by every metric function.

    Always call this first and pass the returned ctx to whichever
    compute_*() functions you need.

    Parameters
    ----------
    city                         : "NYC", "NJ", "PITT", or "SF"
    station_status_txt           : path to the raw station status file (.txt)
    station_information_csv      : path to the station information file (.csv)
    output_dir                   : folder where output files will be saved
    fill_missing_with_census_api : use the Census API to fill any stations
                                   that could not be geocoded locally
    remove_tz_suffix             : timezone string to strip from timestamps
    census_geocoder_benchmark    : Census API benchmark string
    census_geocoder_vintage      : Census API vintage string

    Returns
    -------
    ctx : dict — pass this as the first argument to any compute_*() function
    """
    city_key = city.strip().upper()
    aliases  = {"PITTSBURGH": "PITT", "PIT": "PITT", "SANFRAN": "SF", "SAN FRANCISCO": "SF", "BAYWHEELS": "SF"}
    city_key = aliases.get(city_key, city_key)

    if city_key not in CITY_CONFIG:
        raise ValueError(f"City '{city_key}' not found. Valid options: {list(CITY_CONFIG.keys())}")

    cfg     = CITY_CONFIG[city_key]
    out_dir = Path(output_dir or f"./{city_key}_outputs")
    out_dir.mkdir(parents=True, exist_ok=True)

    should_api_fill = cfg.get("use_api_fallback", fill_missing_with_census_api)
    blocks_id       = str(cfg["geo"]["blocks_id"])

    print(f"[{city_key}] Loading spatial assets...")
    blocks_gdf = gpd.read_file(cfg["assets"]["census_blocks"]).to_crs(epsg=4326)

    print(f"[{city_key}] Loading station status...")
    records = []
    with Path(station_status_txt).open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                js = json.loads(line)
                ts = list(js.keys())[0]
                for entry in js[ts]:
                    for vt in entry.get("vehicle_types_available", []):
                        entry[f"vehicle_type_{vt['vehicle_type_id']}_count"] = vt["count"]
                    entry.pop("vehicle_types_available", None)
                    entry["timestamp"] = ts
                    records.append(entry)
            except Exception:
                continue

    ss_df = pd.DataFrame(records)
    ss_df["timestamp"]  = pd.to_datetime(
        ss_df["timestamp"].astype(str).str.replace(remove_tz_suffix, "", regex=False),
        errors="coerce",
    )
    ss_df["station_id"] = DataHelper.normalize_id(ss_df["station_id"])

    print(f"[{city_key}] Geocoding stations to census blocks...")
    si = DataHelper.load_stations(Path(station_information_csv))

    if "census_block" not in si.columns or si["census_block"].isna().any():
        mapping = GeoHelper.geocode_points(si, "lon", "lat", blocks_gdf, blocks_id)
        si      = si.merge(mapping, on=["lon", "lat"], how="left", suffixes=("", "_new"))
        if "census_block_new" in si.columns:
            si["census_block"] = si["census_block"].fillna(si["census_block_new"])
            si = si.drop(columns=["census_block_new"])
        if should_api_fill:
            si = GeoHelper.api_fill_blocks(si, census_geocoder_benchmark, census_geocoder_vintage)

    si["census_block"] = si["census_block"].astype(str).str.split(".").str[0]
    si["census_tract"] = DataHelper.normalize_tract(DataHelper.tract_from_block(si["census_block"]))

    ss_done = ss_df.merge(si[["station_id", "census_block", "census_tract"]], on="station_id", how="left")

    for c in ["num_bikes_available", "num_docks_available"]:
        if c not in ss_done.columns:
            ss_done[c] = 0
        ss_done[c] = pd.to_numeric(ss_done[c], errors="coerce").fillna(0).astype(int)

    if "num_ebikes_available" not in ss_done.columns:
        ss_done["num_ebikes_available"] = 0
        if "vehicle_type_EFIT_count" in ss_done.columns:
            ss_done["num_ebikes_available"] = pd.to_numeric(
                ss_done["vehicle_type_EFIT_count"], errors="coerce"
            ).fillna(0).astype(int)

    ss_done["total_vehicle_available"] = ss_done["num_bikes_available"] + ss_done["num_ebikes_available"]

    return {
        "city_key":   city_key,
        "cfg":        cfg,
        "out_dir":    out_dir,
        "blocks_gdf": blocks_gdf,
        "blocks_id":  blocks_id,
        "si":         si,
        "ss_done":    ss_done,
        "ext":        cfg["geo"]["external_tract_prefix"],
    }


# ===========================================================================
# STEP 2 — METRIC FUNCTIONS
# Call whichever ones you need. Each one takes ctx as the first argument.
# Dependencies are handled internally — you never need to pass results
# from one function into another.
# ===========================================================================

def compute_availability(
    ctx: Dict[str, Any],
    *,
    time_start: Optional[Union[str, pd.Timestamp]] = None,
    time_end: Optional[Union[str, pd.Timestamp]] = None,
    granularity: str = "1h",
    group_level: str = "both",
    save_outputs: bool = True,
) -> Dict[str, Dict[str, pd.DataFrame]]:
    """
    Compute bikes, e-bikes, and docks available per census block and/or tract.

    Parameters
    ----------
    ctx          : returned by load_docked_context()
    time_start   : start of the analysis window (default: all available data)
    time_end     : end of the analysis window   (default: all available data)
    granularity  : time bucket size e.g. "1h", "30min"
    group_level  : "block", "tract", or "both"
    save_outputs : write result CSVs to the output directory

    Returns
    -------
    dict with keys "block" and/or "tract"
    each containing "raw" and "norm" DataFrames
    """
    city_key = ctx["city_key"]
    ss_done  = ctx["ss_done"]
    out_dir  = ctx["out_dir"]
    ext      = ctx["ext"]

    t_s = pd.to_datetime(time_start) if time_start else None
    t_e = pd.to_datetime(time_end)   if time_end   else None

    ss_filt = ss_done.copy()
    if t_s is not None:
        ss_filt = ss_filt[ss_filt["timestamp"] >= t_s]
    if t_e is not None:
        ss_filt = ss_filt[ss_filt["timestamp"] < t_e]

    print(f"[{city_key}] Computing availability...")
    avail_res = {}

    if group_level in {"block", "both"}:
        avail_res["block"] = MetricHelper.calc_availability(
            ss_filt, "block", granularity, out_dir, save_outputs
        )
    if group_level in {"tract", "both"}:
        avail_res["tract"] = MetricHelper.calc_availability(
            ss_filt, "tract", granularity, out_dir, save_outputs, ext
        )

    return avail_res


def compute_capacity(
    ctx: Dict[str, Any],
    *,
    time_start: Optional[Union[str, pd.Timestamp]] = None,
    time_end: Optional[Union[str, pd.Timestamp]] = None,
    granularity: str = "1h",
    peak_time_slot: Optional[Union[str, pd.Timestamp]] = None,
    peak_metric: str = "total_vehicle_available",
    drop_staten_island: Optional[bool] = None,
    save_outputs: bool = True,
) -> Dict[str, pd.DataFrame]:
    """
    Compute station capacity and vehicle occupancy per census tract.

    Availability is computed internally as a dependency — you do not
    need to call compute_availability() first.

    Parameters
    ----------
    ctx                : returned by load_docked_context()
    time_start         : start of the analysis window
    time_end           : end of the analysis window
    granularity        : time bucket used for the internal availability step
    peak_time_slot     : fix a specific peak hour for capacity calculations
                         (default: auto-detected from availability data)
    peak_metric        : column used to identify the peak time slot
    drop_staten_island : exclude Staten Island tracts — NYC only
    save_outputs       : write result CSVs to the output directory

    Returns
    -------
    dict with keys:
        cap_tract : capacity per tract (station count and total dock capacity)
        cap_df    : capacity merged with peak-hour vehicle and dock availability
    """
    city_key = ctx["city_key"]
    out_dir  = ctx["out_dir"]

    print(f"[{city_key}] Computing capacity...")

    # run availability silently as an internal dependency — files not saved
    avail_result = _run_availability_internal(ctx, time_start, time_end, granularity, group_level="both")

    cap_result = _run_capacity_internal(ctx, avail_result, peak_time_slot, peak_metric, drop_staten_island)

    if save_outputs:
        cap_result["cap_tract"].to_csv(out_dir / "capacity_tract_norm.csv",                        index=False)
        cap_result["cap_df"].to_csv(out_dir    / "capacity_tract_with_vehicle_and_docks_norm.csv", index=False)

    return cap_result


def compute_safety(
    ctx: Dict[str, Any],
    *,
    time_start: Optional[Union[str, pd.Timestamp]] = None,
    time_end: Optional[Union[str, pd.Timestamp]] = None,
    granularity: str = "1h",
    peak_time_slot: Optional[Union[str, pd.Timestamp]] = None,
    peak_metric: str = "total_vehicle_available",
    drop_staten_island: Optional[bool] = None,
    save_outputs: bool = True,
) -> Dict[str, pd.DataFrame]:
    """
    Compute bike lane and protected lane ratios per census block and tract.

    Availability and capacity are computed internally as dependencies —
    you do not need to call those functions first.

    Parameters
    ----------
    ctx                : returned by load_docked_context()
    time_start         : start of the analysis window
    time_end           : end of the analysis window
    granularity        : time bucket used for the internal availability step
    peak_time_slot     : fix a specific peak hour for internal capacity step
    peak_metric        : column used to identify the peak time slot
    drop_staten_island : exclude Staten Island tracts — NYC only
    save_outputs       : write result CSVs to the output directory

    Returns
    -------
    dict with keys:
        safe_block : bike lane ratios at census block level
        safe_tract : bike lane ratios at census tract level
        safe_norm  : normalized ratios filtered to the service area
    """
    city_key   = ctx["city_key"]
    cfg        = ctx["cfg"]
    blocks_gdf = ctx["blocks_gdf"]
    blocks_id  = ctx["blocks_id"]
    out_dir    = ctx["out_dir"]

    print(f"[{city_key}] Computing safety...")

    # run availability and capacity silently as internal dependencies
    avail_result = _run_availability_internal(ctx, time_start, time_end, granularity, group_level="both")
    cap_result   = _run_capacity_internal(ctx, avail_result, peak_time_slot, peak_metric, drop_staten_island)
    cap_tract    = cap_result["cap_tract"]

    metric_crs = cfg["geo"]["metric_crs"]

    streets = GeoHelper.load_network_lines(
        Path(cfg["assets"]["centerline"]),
        cfg["geo"]["safety_type"],
        metric_crs,
        cfg["geo"].get("wkt_candidates", ()),
    )
    lanes = GeoHelper.load_network_lines(
        Path(cfg["assets"]["bike_lanes"]),
        cfg["geo"]["safety_type"],
        metric_crs,
        cfg["geo"].get("wkt_candidates", ()),
    )

    # filter to protected lanes only using city-specific rules
    rule  = cfg["safety_rule"]
    p_col = DataHelper.pick_col(lanes, list(rule.get("col_candidates", [])), False)

    if p_col:
        match_val = rule["match_value"]
        if rule["match_type"] == "contains":
            mask = lanes[p_col].astype(str).str.upper().str.contains(str(match_val).upper(), na=False)
        elif rule["match_type"] == "equals":
            mask = lanes[p_col].astype(str).str.upper() == str(match_val).upper()
        else:
            mask = lanes[p_col].astype(str).str.contains(match_val, case=False, regex=True)
        protected = lanes[mask]
    else:
        protected = lanes.iloc[0:0]

    blocks_metric = blocks_gdf.to_crs(metric_crs)

    def _len(lines, name):
        """Compute total length of lines within each census block."""
        if lines.empty:
            return pd.DataFrame({"census_block": [], name: []})
        ov = gpd.overlay(lines, blocks_metric, how="intersection", keep_geom_type=False)
        ov["len"] = ov.geometry.length
        return ov.groupby(blocks_id)["len"].sum().reset_index().rename(
            columns={blocks_id: "census_block", "len": name}
        )

    st = _len(streets,   "streets_leng")
    bl = _len(lanes,     "total_bike_lane_length")
    pr = _len(protected, "protected_bike_lane_length")

    safe = st.merge(bl, on="census_block", how="left").merge(pr, on="census_block", how="left").fillna(0)
    safe["census_tract"]              = DataHelper.normalize_tract(DataHelper.tract_from_block(safe["census_block"]))
    safe["bike_lane_ratio"]           = MetricHelper.safe_ratio(safe["total_bike_lane_length"],     safe["streets_leng"]).round(3)
    safe["protected_bike_lane_ratio"] = MetricHelper.safe_ratio(safe["protected_bike_lane_length"], safe["streets_leng"]).round(3)

    safe_tract = safe.groupby("census_tract", as_index=False)[
        ["streets_leng", "total_bike_lane_length", "protected_bike_lane_length"]
    ].sum()

    meta = pd.read_csv(out_dir / "centroid_tract_computed.csv", dtype={"census_tract": str})
    meta["census_tract"] = DataHelper.normalize_tract(meta["census_tract"])
    safe_tract = meta.merge(safe_tract, on="census_tract", how="left").fillna(0)
    safe_tract["bike_lane_ratio"]           = MetricHelper.safe_ratio(safe_tract["total_bike_lane_length"],     safe_tract["streets_leng"])
    safe_tract["protected_bike_lane_ratio"] = MetricHelper.safe_ratio(safe_tract["protected_bike_lane_length"], safe_tract["streets_leng"])

    # filter to the service area defined by capacity
    safe_service = safe_tract[safe_tract["census_tract"].isin(set(cap_tract["census_tract"].unique()))].copy()
    safe_norm    = safe_service.copy()
    safe_norm["bike_lane_ratio_norm"]           = MetricHelper.normalize(safe_norm["bike_lane_ratio"]).round(5)
    safe_norm["protected_bike_lane_ratio_norm"] = MetricHelper.normalize(safe_norm["protected_bike_lane_ratio"]).round(5)

    if save_outputs:
        safe.to_csv(out_dir         / "safety_bike_lane_block.csv",        index=False)
        safe_tract.to_csv(out_dir   / "safety_bike_lane_tract.csv",        index=False)
        safe_service.to_csv(out_dir / "safety_bike_lane_service_area.csv", index=False)
        safe_norm.to_csv(out_dir    / "safety_bike_lane_norm_tract.csv",   index=False)

    return {"safe_block": safe, "safe_tract": safe_tract, "safe_norm": safe_norm}


def compute_usage(
    ctx: Dict[str, Any],
    *,
    trip_csv: Union[str, Path],
    time_start: Optional[Union[str, pd.Timestamp]] = None,
    time_end: Optional[Union[str, pd.Timestamp]] = None,
    tracts_to_remove: Optional[Sequence[str]] = None,
    save_outputs: bool = True,
) -> Dict[str, Any]:
    """
    Compute trip starts and ends per census block and tract.

    Parameters
    ----------
    ctx              : returned by load_docked_context()
    trip_csv         : path to trip data — CSV file, folder of CSVs, or ZIP
    time_start       : start of the analysis window (default: earliest trip)
    time_end         : end of the analysis window   (default: latest trip)
    tracts_to_remove : census tract IDs to exclude from the output
    save_outputs     : write result CSVs to the output directory

    Returns
    -------
    dict with keys:
        usage_tract : hourly trip counts per tract with normalized columns
    """
    city_key = ctx["city_key"]
    out_dir  = ctx["out_dir"]
    ext      = ctx["ext"]

    print(f"[{city_key}] Computing usage...")

    trip_data = _load_and_enrich_trips(ctx, trip_csv, time_start, time_end)
    trips      = trip_data["trips"]
    all_blocks = trip_data["all_blocks"]
    t_win_s    = trip_data["t_win_s"]
    t_win_e    = trip_data["t_win_e"]

    MetricHelper.calc_usage(trips, (t_win_s, t_win_e), all_blocks, "5min", "usage_5min_block",  out_dir, save_outputs)
    u_hr = MetricHelper.calc_usage(trips, (t_win_s, t_win_e), all_blocks, "1h",  "usage_hourly_block", out_dir, save_outputs)

    u_hr["census_tract"] = DataHelper.normalize_tract(DataHelper.tract_from_block(u_hr["census_block"]))
    if ext:
        u_hr = u_hr[~u_hr["census_tract"].str.startswith(ext)]

    u_tract = u_hr.groupby(["census_tract", "time_slot"], as_index=False)[["trips_starting", "trips_ending"]].sum()
    if tracts_to_remove:
        u_tract = u_tract[~u_tract["census_tract"].isin(tracts_to_remove)]

    u_tract["trips_starting_norm"] = MetricHelper.normalize(u_tract["trips_starting"]).round(5)
    u_tract["trips_ending_norm"]   = MetricHelper.normalize(u_tract["trips_ending"]).round(5)

    if save_outputs:
        u_tract.to_csv(out_dir / "usage_hourly_tract_raw.csv",  index=False)
        u_tract.to_csv(out_dir / "usage_norm_hourly_tract.csv", index=False)

    return {"usage_tract": u_tract}


def compute_idle_time(
    ctx: Dict[str, Any],
    *,
    trip_csv: Union[str, Path],
    time_start: Optional[Union[str, pd.Timestamp]] = None,
    time_end: Optional[Union[str, pd.Timestamp]] = None,
    save_outputs: bool = True,
) -> Dict[str, pd.DataFrame]:
    """
    Compute average bike idle time per census block and tract.

    Usage is computed internally as a dependency — you do not need to
    call compute_usage() first.

    Parameters
    ----------
    ctx          : returned by load_docked_context()
    trip_csv     : path to trip data — CSV file, folder of CSVs, or ZIP
    time_start   : start of the analysis window (default: earliest trip)
    time_end     : end of the analysis window   (default: latest trip)
    save_outputs : write result CSVs to the output directory

    Returns
    -------
    dict with keys:
        idle_block : average idle time per census block per hour
        idle_tract : average idle time per census tract per hour (normalized)
    """
    city_key = ctx["city_key"]
    ss_done  = ctx["ss_done"]
    out_dir  = ctx["out_dir"]
    ext      = ctx["ext"]

    print(f"[{city_key}] Computing idle time...")

    # load and enrich trips internally — usage is a silent dependency here
    trip_data  = _load_and_enrich_trips(ctx, trip_csv, time_start, time_end)
    trips      = trip_data["trips"]
    all_blocks = trip_data["all_blocks"]
    t_win_s    = trip_data["t_win_s"]
    t_win_e    = trip_data["t_win_e"]

    if "rideable_type" in trips.columns:
        trips        = MetricHelper.map_rideable_type(trips)
        has_rideable = True
    else:
        has_rideable = False

    # build 5-min inventory snapshots from station status
    ss_idle = ss_done[(ss_done["timestamp"] >= t_win_s) & (ss_done["timestamp"] <= t_win_e)].copy()
    ss_idle["time_slot"] = ss_idle["timestamp"].dt.floor("5min") - pd.Timedelta(minutes=5)

    inv  = ss_idle.groupby(["census_block", "time_slot"], as_index=False)[["total_vehicle_available"]].sum()
    flux = MetricHelper.calc_usage(trips, (t_win_s, t_win_e), all_blocks, "5min", "temp_flux", out_dir, False)
    flux["vehicles_moved"] = flux["trips_starting"] + flux["trips_ending"]

    # split vehicle movement by bike type if rideable_type is available
    if has_rideable:
        ts_ = trips.groupby(["start_census_block", "slot_start", "_is_ebike"]).size().unstack(fill_value=0).reset_index()
        ts_ = ts_.rename(columns={"start_census_block": "census_block", "slot_start": "time_slot",
                                   False: "trips_starting_bike", True: "trips_starting_ebike"})
        te_ = trips.groupby(["end_census_block", "slot_end", "_is_ebike"]).size().unstack(fill_value=0).reset_index()
        te_ = te_.rename(columns={"end_census_block": "census_block", "slot_end": "time_slot",
                                   False: "trips_ending_bike", True: "trips_ending_ebike"})
        flux = flux.merge(ts_, on=["census_block", "time_slot"], how="left") \
                   .merge(te_, on=["census_block", "time_slot"], how="left").fillna(0)

        for c in ["trips_starting_bike", "trips_starting_ebike", "trips_ending_bike", "trips_ending_ebike"]:
            if c in flux.columns:
                flux[c] = flux[c].astype(int)

        flux["vehicles_moved_bike"]  = flux.get("trips_starting_bike",  0) + flux.get("trips_ending_bike",  0)
        flux["vehicles_moved_ebike"] = flux.get("trips_starting_ebike", 0) + flux.get("trips_ending_ebike", 0)

    # merge inventory with flux and compute idle vehicle count per 5-min slot
    m = inv.merge(flux, on=["census_block", "time_slot"], how="left").fillna(0)
    m["idle_vehicles"] = (m["total_vehicle_available"] - m["vehicles_moved"]).clip(lower=0)
    m["hour"]          = m["time_slot"].dt.floor("1h")

    if save_outputs:
        m.to_csv(out_dir / "idle_merged_5min.csv", index=False)

    # delegate the queue algorithm to MetricHelper so it stays consistent
    # with how calc_availability and calc_usage are structured
    return MetricHelper.calc_idle_time(m, out_dir, save_outputs, ext)


# ===========================================================================
# CONVENIENCE FUNCTION — runs all metrics in one call
# ===========================================================================

def compute_all(
    ctx: Dict[str, Any],
    *,
    trip_csv: Union[str, Path],
    time_start: Optional[Union[str, pd.Timestamp]] = None,
    time_end: Optional[Union[str, pd.Timestamp]] = None,
    save_outputs: bool = True,
) -> Dict[str, Any]:
    """
    Run all five metrics in one call.

    This is a convenience wrapper that calls each compute_*() function
    in the correct order and returns all results together.

    Parameters
    ----------
    ctx          : returned by load_docked_context()
    trip_csv     : path to trip data — required for usage and idle time
    time_start   : start of the analysis window applied to all metrics
    time_end     : end of the analysis window applied to all metrics
    save_outputs : write all result CSVs to the output directory

    Returns
    -------
    dict with keys: availability, capacity, safety, usage, idle_time
    """
    avail = compute_availability(ctx, time_start=time_start, time_end=time_end, save_outputs=save_outputs)
    cap   = compute_capacity(ctx,    time_start=time_start, time_end=time_end, save_outputs=save_outputs)
    safe  = compute_safety(ctx,      time_start=time_start, time_end=time_end, save_outputs=save_outputs)
    usage = compute_usage(ctx,       trip_csv=trip_csv, time_start=time_start, time_end=time_end, save_outputs=save_outputs)
    idle  = compute_idle_time(ctx,   trip_csv=trip_csv, time_start=time_start, time_end=time_end, save_outputs=save_outputs)

    print(f"--- Done. Outputs saved to {ctx['out_dir']} ---")

    return {
        "availability": avail,
        "capacity":     cap,
        "safety":       safe,
        "usage":        usage,
        "idle_time":    idle,
    }


if __name__ == "__main__":
    print("docked_wrapper module loaded successfully")