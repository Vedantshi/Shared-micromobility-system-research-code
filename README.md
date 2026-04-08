# Mobility Package

### A Python Package for Multidimensional Fairness Analysis of Shared Micromobility Systems

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![GeoPandas](https://img.shields.io/badge/GeoPandas-0.14%2B-green)
![Matplotlib](https://img.shields.io/badge/Matplotlib-3.8%2B-orange)
![License](https://img.shields.io/badge/License-MIT-lightgrey)
![Status](https://img.shields.io/badge/Status-Research-darkblue)

---

## Overview

This package provides a structured Python implementation for computing, analyzing, and visualizing fairness metrics in shared micromobility systems (SMS). It was developed as the computational backbone of the research paper:

> **Evaluating Multidimensional Fairness in Shared Micromobility: Case Studies of Docked and Dockless Systems**
> *Tara Zibandehkhooy, Violet (Xinying) Chen*
> Preprint submitted to Journal of Transport Geography, September 2025

The framework operationalizes a pipeline that moves from raw GBFS (General Bikeshare Feed Specification) snapshots through utility computation, fairness measurement, and spatial visualization. It supports both docked systems (e.g. Citi Bike NYC) and dockless systems (e.g. Lime, Bird, Spin in San Francisco and Seattle), and is designed to be extensible to other cities and system types.

The package distinguishes between **static decision outcomes** — capacity and safety — which reflect long-term operator and policymaker decisions, and **dynamic system outcomes** — availability, usage, and idle time — which emerge from real-time user behavior. Fairness is evaluated across both dimensions using established inequality metrics (Gini coefficient) and combined fairness-efficiency metrics (Alpha fairness at α = 1).

---

## Pipeline Architecture

```
Raw GBFS Snapshot (.txt)
         |
         v
+------------------------------------------+
|  docked_wrapper                          |
|  for docked systems                      |
|  (NYC, NJ, Pittsburgh)                   |
|                                          |
|  dockless_wrapper                        |
|  for dockless systems                    |
|  (SF Lime/Spin, Seattle Bird/Lime)       |
+------------------------------------------+
         |
         |  Produces per-tract CSVs:
         |  availability, capacity,
         |  usage, idle_time, safety
         v
+------------------------------------------+
|  fairness_calculation                    |
|  Gini coefficient + Alpha fairness       |
+------------------------------------------+
         |
         v
+------------------------------------------+
|  Visualization Modules                   |
|                                          |
|  map_visual       Utility choropleth maps|
|  capacity_map_visual  Capacity decile    |
|  correlation_visual   4-quadrant maps    |
|  scatter_visual   Supply-demand scatter  |
|  trend_visual     Weekly time-series     |
|  table_visual     Fairness summary table |
+------------------------------------------+
```

---

## Supported Systems

| City          | Operator     | System Type | `system_key` / `city` argument |
|---------------|--------------|-------------|-------------------------------|
| New York City | Citi Bike    | Docked      | `city="NYC"`                  |
| New Jersey    | Citi Bike    | Docked      | `city="NJ"`                   |
| Pittsburgh    | Healthy Ride | Docked      | `city="PITT"`                 |
| San Francisco | Lime         | Dockless    | `system_key="SF_LIME_DOCKLESS"`|
| San Francisco | Spin         | Dockless    | `system_key="SF_SPIN_DOCKLESS"`|
| Seattle       | Bird         | Dockless    | `system_key="SEATTLE_BIRD_DOCKLESS"`|
| Seattle       | Lime         | Dockless    | `system_key="SEATTLE_LIME_DOCKLESS"`|

---

## Package Structure

```
mobility_package/
│
├── __init__.py                  Package entry point — imports all modules
│
├── docked_wrapper.py            Utility computation for docked systems
├── dockless_wrapper.py          Utility computation for dockless systems
├── fairness_calculation.py      Gini and Alpha fairness computation
│
├── map_visual.py                Utility choropleth maps
├── capacity_map_visual.py       Capacity decile choropleth maps
├── correlation_visual.py        Two-metric correlation quadrant maps
├── scatter_visual.py            Supply-demand classification scatter plots
├── trend_visual.py              Weekly fairness time-series visualization
└── table_visual.py              Paper-style fairness summary table

example_notebooks/
├── example_run_pitt_docked.ipynb     Full pipeline — Pittsburgh (docked)
└── example_run_seattle_dockless.ipynb Full pipeline — Seattle Bird (dockless)
```

---

## Example Notebooks and Data

Two fully worked example notebooks are included, one for a docked system (Pittsburgh) and one for a dockless system (Seattle Bird). Each notebook runs the complete pipeline end to end: data loading → metric computation → fairness calculation → all visualizations.

### Pittsburgh — Docked System

**Notebook:** `example_notebooks/example_run_pitt_docked.ipynb`

**Example dataset:** [Download from Google Drive](https://drive.google.com/drive/folders/1DdybTTZJmnQ6n1rI1R65yhCoGpYTqFh8?usp=drive_link)

The dataset contains one day of Pittsburgh Healthy Ride GBFS data (June 9, 2025) including station status snapshots, station information, trip records, and all required spatial assets (census blocks, tract shapefile, street centerlines, bike lane shapefile).

After downloading, place the folder next to the notebook so your structure looks like:

```
example_run_pitt_docked.ipynb
PITT_ASSETS/
  pitt_docked_station_status_6_9.txt
  pitt_station_information_06_09.csv
  pitt_tripdata_june_2025.csv
  tl_2024_42_tract.shp   (+ .dbf .prj .shx)
  tl_2024_42_tabblock20.shp  (+ .dbf .prj .shx)
  centroid_tract_pa.csv
  Pittsburgh_Street_Centerline.shp
  Bike_Lanes.shp
```

### Seattle Bird — Dockless System

**Notebook:** `example_notebooks/example_run_seattle_dockless.ipynb`

**Example dataset:** [Download from Google Drive](https://drive.google.com/drive/folders/1oitn7K7Hje81o7qr2VgxwHCjwdOhAFPF?usp=drive_link)

The dataset contains one day of Seattle Bird dockless GBFS snapshot data (June 15, 2025) and all required spatial assets (census blocks, tract shapefile, street centerlines, bike facility geojson, planned bike lanes shapefile).

After downloading, place the folder next to the notebook so your structure looks like:

```
example_run_seattle_dockless.ipynb
SEATTLE_BIRD_ASSETS/
  seattle_bird_freebike_status.txt
  tl_2024_53_tabblock20.shp  (+ .dbf .prj .shx)
  tl_2024_53_tract.shp       (+ .dbf .prj .shx)
  Seattle_Streets.shp        (+ .dbf .prj .shx)
  SDOT_Bike_Facilities.geojson
  Planned_Bike_Facilities.shp (+ .dbf .prj .shx)
```

### Note on Trend Plots

The fairness trend visualization (`trend_visual`) is the only step in both notebooks that requires more than one day of data. When running with a single day the plots will execute but will show a flat line — this is expected. To produce meaningful trend plots, collect 7 consecutive days of daily metric CSVs and pass the folder path instead of a single file path. Both notebooks explain this with a `TREND_MODE` flag that lets you switch between single-day and weekly mode without changing anything else.

---

## Installation

Clone the repository and install the required dependencies:

```bash
git clone https://github.com/your-username/mobility-package.git
cd mobility-package
pip install -r requirements.txt
```

**`requirements.txt`**

```
pandas>=2.0
numpy>=1.24
geopandas>=0.14
shapely>=2.0
contextily>=1.4
matplotlib>=3.8
requests>=2.31
tqdm>=4.66
```

---

## Quick Start

The following example runs the complete pipeline for the NYC docked system from raw GBFS data to a fairness table.

```python
from mobility_package import (
    docked_wrapper,
    fairness_calculation,
    map_visual,
    trend_visual,
    table_visual,
)

# Step 1 — Load context
ctx = docked_wrapper.load_docked_context(
    city                    = "NYC",
    station_status_txt      = r"path/to/nyc_station_status.txt",
    station_information_csv = r"path/to/nyc_station_information.csv",
    output_dir              = "NYC_OUTPUT",
)

# Step 2 — Compute all utility metrics
results = docked_wrapper.compute_all(
    ctx,
    trip_csv   = r"path/to/citibike_tripdata/",
    time_start = "2025-04-06 00:00:00",
    time_end   = "2025-04-06 23:59:59",
)

# Step 3 — Compute fairness metrics
fairness_calculation.run_paper_style_fairness(
    city_key         = "NYC_DOCKED",
    save_directory   = "NYC_OUTPUT/FAIRNESS",
    availability_csv = "NYC_OUTPUT/availability__norm__tract.csv",
    usage_csv        = "NYC_OUTPUT/usage_norm_hourly_tract.csv",
    idle_time_csv    = "NYC_OUTPUT/idle_time_norm_tract.csv",
    capacity_csv     = "NYC_OUTPUT/capacity_tract_with_vehicle_and_docks_norm.csv",
    safety_csv       = "NYC_OUTPUT/safety_bike_lane_norm_tract.csv",
    filter_to_capacity_service_area = True,
)

# Step 4 — Visualize utility maps
map_visual.plot_all(
    availability_csv = "NYC_OUTPUT/availability__norm__tract.csv",
    usage_csv        = "NYC_OUTPUT/usage_norm_hourly_tract.csv",
    idle_time_csv    = "NYC_OUTPUT/idle_time_norm_tract.csv",
    safety_csv       = "NYC_OUTPUT/safety_bike_lane_norm_tract.csv",
    capacity_csv     = "NYC_OUTPUT/capacity_tract_norm.csv",
    tract_shp        = r"path/to/tl_2024_36_tract.shp",
    output_dir       = "NYC_OUTPUT/MAPS",
)

# Step 5 — Display fairness summary table (in Jupyter)
table_visual.make_table(
    csv_path = "NYC_OUTPUT/FAIRNESS/NYC_DOCKED_fairness_results.csv"
)
```

---

## Module Reference

---

### 1. `docked_wrapper`

Processes raw GBFS station-status snapshots for docked bike-share systems and computes all utility metrics at the census-tract level.

**Supported cities:** NYC, NJ, Pittsburgh

**Metrics produced:**

| Metric       | Description                                         | Output CSV                                          |
|--------------|-----------------------------------------------------|-----------------------------------------------------|
| Availability | Vehicles and docks available per tract per hour     | `availability__norm__tract.csv`                     |
| Capacity     | Peak-hour vehicle and dock count per tract          | `capacity_tract_norm.csv`<br>`capacity_tract_with_vehicle_and_docks_norm.csv` |
| Usage        | Trip starts and ends per tract per hour             | `usage_norm_hourly_tract.csv`                       |
| Idle Time    | Average time vehicles sit unused per tract per hour | `idle_time_norm_tract.csv`                          |
| Safety       | Bike-lane ratio per tract                           | `safety_bike_lane_norm_tract.csv`                   |

**Usage:**

```python
from mobility_package import docked_wrapper

# Step 1 — Always call this first
ctx = docked_wrapper.load_docked_context(
    city                    = "NYC",       # "NYC" | "NJ" | "PITT"
    station_status_txt      = r"path/to/station_status.txt",
    station_information_csv = r"path/to/station_information.csv",
    output_dir              = "NYC_OUTPUT",
    remove_tz_suffix        = " EDT",      # strip timezone suffix from timestamps
)

# Step 2a — All metrics at once
results = docked_wrapper.compute_all(
    ctx,
    trip_csv   = r"path/to/tripdata/",
    time_start = "2025-04-06 00:00:00",
    time_end   = "2025-04-06 23:59:59",
)

# Step 2b — Or individual metrics
avail  = docked_wrapper.compute_availability(ctx, time_start=..., time_end=...)
cap    = docked_wrapper.compute_capacity(ctx,     time_start=..., time_end=...)
safety = docked_wrapper.compute_safety(ctx,       time_start=..., time_end=...)
usage  = docked_wrapper.compute_usage(ctx,        trip_csv=..., time_start=..., time_end=...)
idle   = docked_wrapper.compute_idle_time(ctx,    trip_csv=..., time_start=..., time_end=...)
```

**Required assets per city:**

Each city requires a set of spatial and tabular asset files. These are configured in the `CITY_CONFIG` dictionary inside `docked_wrapper.py`. The table below lists what each city needs and where to obtain it.

| Asset | Description | Source |
|-------|-------------|--------|
| Census blocks shapefile (`tl_YYYY_SS_tabblock20.shp`) | Block-level polygons for geocoding stations | [US Census TIGER/Line](https://www.census.gov/cgi-bin/geo/shapefiles/index.php) — select "Census Blocks" for your state |
| Census tract shapefile (`tl_YYYY_SS_tract.shp`) | Tract-level polygons for aggregation and mapping | [US Census TIGER/Line](https://www.census.gov/cgi-bin/geo/shapefiles/index.php) — select "Census Tracts" for your state |
| Street centerline | Road network geometry for bike-lane ratio computation | City open data portal (e.g. NYC Open Data, WPRDC for Pittsburgh) |
| Bike lanes | Bike lane geometry for safety metric | City open data portal |
| Station information CSV | Station lat/lon and capacity | GBFS `station_information.json` feed |
| Station status TXT | Timestamped station status snapshots | Collected from GBFS `station_status.json` feed |
| Trip data CSV/folder | Trip-level records for usage and idle time | Operator open data (e.g. Citi Bike trip data) |

**State FIPS codes for shapefile download:**

| City | State | FIPS Code | Shapefile prefix |
|------|-------|-----------|-----------------|
| New York City | New York | 36 | `tl_2024_36_` |
| New Jersey | New Jersey | 34 | `tl_2024_34_` |
| Pittsburgh | Pennsylvania | 42 | `tl_2024_42_` |

**How to identify your data's timestamp format:**

When calling `load_docked_context`, the `remove_tz_suffix` parameter strips a timezone string from timestamps before parsing. To find out what suffix your data uses, open your station status `.txt` file, parse one line as JSON, and look at the timestamp key:

```python
import json

with open("your_station_status.txt") as f:
    line = json.loads(f.readline())
    ts = list(line.keys())[0]
    print(ts)   # e.g. "2025-04-06 14:32:00 EDT"
                # → remove_tz_suffix=" EDT"
```

---

### 2. `dockless_wrapper`

Processes raw GBFS free-bike-status snapshots for dockless systems. Because dockless systems do not provide explicit trip records, usage is inferred from consecutive vehicle location changes across 5-minute snapshot windows.

**Supported systems:** SF Lime, SF Spin, Seattle Bird, Seattle Lime

**Metrics produced:**

| Metric       | Description                                          | Output CSV (tagged with vendor name)         |
|--------------|------------------------------------------------------|----------------------------------------------|
| Availability | Non-reserved, non-disabled vehicles per tract/hour   | `availability_norm_hourly_tract_*.csv`        |
| Capacity     | Peak-snapshot vehicle count per tract                | `capacity_tract_*.csv`                        |
| Usage        | Inferred trip starts/ends per tract per hour         | `usage_norm_hourly_tract_*.csv`               |
| Idle Time    | Ping count × 5 minutes per vehicle per tract         | `idle_norm_hourly_tract_*.csv`                |
| Safety       | Bike-lane ratio per tract                            | `safety_tract_*.csv`                          |

**Usage:**

```python
from mobility_package import dockless_wrapper

# Step 1 — Always call this first
ctx = dockless_wrapper.load_dockless_context(
    system_key          = "SEATTLE_BIRD_DOCKLESS",
    freebike_status_txt = r"path/to/seattle_bird_status.txt",
    output_dir          = "SEATTLE_BIRD_OUTPUT",
    time_start          = "2025-06-15 00:00:00",
    time_end            = "2025-06-15 23:59:59",

    # Override asset paths when running from a portable folder
    census_blocks_shp       = r"path/to/tl_2024_53_tabblock20.shp",
    centerline_streets_path = r"path/to/Seattle_Streets.shp",
    bike_lanes_path         = r"path/to/SDOT_Bike_Facilities.geojson",
    planned_bike_lanes_path = r"path/to/Planned_Bike_Facilities.shp",
    centroid_tract_path     = r"path/to/tl_2024_53_tract.shp",
)

# Step 2a — All metrics at once (no trip CSV needed)
results = dockless_wrapper.compute_all(ctx)

# Step 2b — Or individual metrics
avail  = dockless_wrapper.compute_availability(ctx)
cap    = dockless_wrapper.compute_capacity(ctx)
usage  = dockless_wrapper.compute_usage(ctx)
idle   = dockless_wrapper.compute_idle_time(ctx)
safety = dockless_wrapper.compute_safety(ctx)
```

**Required assets per dockless system:**

| Asset | Description | Source |
|-------|-------------|--------|
| Census blocks shapefile | Block-level polygons for geocoding pings | [US Census TIGER/Line](https://www.census.gov/cgi-bin/geo/shapefiles/index.php) — select "Census Blocks" for your state |
| Census tract shapefile or centroid CSV | Tract universe for aggregation | [US Census TIGER/Line](https://www.census.gov/cgi-bin/geo/shapefiles/index.php) — select "Census Tracts" for your state |
| Street centerline | Road network geometry | City open data portal |
| Bike lanes file | Bike lane geometry (shapefile or GeoJSON) | City open data portal |
| Planned bike lanes (optional) | For Seattle systems — combined with existing lanes | City open data portal |
| Free-bike-status TXT | Timestamped GBFS snapshot file | Collected from GBFS `free_bike_status.json` feed |

**State FIPS codes for shapefile download:**

| City | State | FIPS Code | Shapefile prefix |
|------|-------|-----------|-----------------|
| San Francisco | California | 06 | `tl_2024_06_` |
| Seattle | Washington | 53 | `tl_2024_53_` |

**How to check your snapshot file format:**

Open your free-bike-status `.txt` file and inspect one line to confirm the expected JSON structure:

```python
import json

with open("your_freebike_status.txt") as f:
    line = json.loads(f.readline())
    ts = list(line.keys())[0]
    vehicles = line[ts]
    print("Timestamp:", ts)
    print("First vehicle:", vehicles[0])
    # Expected keys: bike_id or vehicle_id, lat, lon, is_reserved, is_disabled
```

The vehicle ID column name varies by vendor (`bike_id` for Bird, `vehicle_id` for Lime/Spin). The wrapper detects this automatically.

---

### 3. `fairness_calculation`

Computes two fairness metrics — Gini coefficient and Alpha fairness (α = 1) — for each utility metric across all census tracts. Column names are resolved automatically so the same function works for both docked and dockless output CSVs without any manual configuration.

**Fairness metrics:**

| Metric                 | Formula                                   | Interpretation |
|------------------------|-------------------------------------------|----------------|
| Gini Coefficient       | `(n + 1 - 2 * Σ(cumulative) / total) / n` | 0 = perfect equality, 1 = complete concentration |
| Alpha Fairness (α = 1) | `Σ log(x_i + 1)` across all tracts       | Higher = more total utility delivered fairly |

**Usage:**

```python
from mobility_package import fairness_calculation

fairness_calculation.run_paper_style_fairness(
    city_key         = "PITT_DOCKED",
    save_directory   = "PITT_OUTPUT/FAIRNESS",

    capacity_csv     = "PITT_OUTPUT/capacity_tract_with_vehicle_and_docks_norm.csv",
    availability_csv = "PITT_OUTPUT/availability__norm__tract.csv",
    safety_csv       = "PITT_OUTPUT/safety_bike_lane_norm_tract.csv",
    usage_csv        = "PITT_OUTPUT/usage_norm_hourly_tract.csv",
    idle_time_csv    = "PITT_OUTPUT/idle_time_norm_tract.csv",

    # True for docked (restrict to tracts with stations)
    # False for dockless (no fixed station boundary)
    filter_to_capacity_service_area = True,
)
```

**Output:** `<city_key>_fairness_results.csv` and `<city_key>_fairness_input_summary.csv`

The module prints which column it selected for each metric so you can verify the auto-resolution:

```
[fairness] Availability: Total vehicles available → 'total_vehicle_available'
[fairness] Usage: Trips starting → 'trips_starting', Trips ending → 'trips_ending'
[fairness] Idle Time: Average idle time → 'avg_idle_time'
```

---

### 4. `map_visual`

Produces static choropleth maps for all utility metrics at the census-tract level. Each map uses the RdYlBu colormap with an OpenStreetMap basemap, compass rose, and scale bar. Works automatically for both docked and dockless CSVs — value columns are auto-resolved by keyword scoring.

**Usage:**

```python
from mobility_package import map_visual

# All four metrics at once
map_visual.plot_all(
    availability_csv = "OUTPUT/availability__norm__tract.csv",
    usage_csv        = "OUTPUT/usage_norm_hourly_tract.csv",
    idle_time_csv    = "OUTPUT/idle_time_norm_tract.csv",
    safety_csv       = "OUTPUT/safety_bike_lane_norm_tract.csv",
    capacity_csv     = "OUTPUT/capacity_tract_norm.csv",
    tract_shp        = r"path/to/tract.shp",
    output_dir       = "OUTPUT/MAPS",
)

# Single metric
map_visual.plot_map(
    metric       = "availability",    # "availability" | "usage" | "idle_time" | "safety"
    csv          = "OUTPUT/availability__norm__tract.csv",
    capacity_csv = "OUTPUT/capacity_tract_norm.csv",
    tract_shp    = r"path/to/tract.shp",
    output_dir   = "OUTPUT/MAPS",
)
```

**Output files:** `availability_rank__mean.png`, `usage_rank__mean.png`, `idle_time_rank__mean.png`, `safety_rank__mean.png`

---

### 5. `capacity_map_visual`

Produces decile choropleth maps for capacity metrics. Tracts are binned into ten equal-percentile groups (1–10%, 11–20%, … 91–100%). Works for both docked (uses `num_station` and `total_capacity_norm`) and dockless (uses `vehicle_capacity` and `vehicle_capacity_norm`) capacity CSVs — column names are resolved automatically.

**Usage:**

```python
from mobility_package import capacity_map_visual

capacity_map_visual.plot_capacity(
    capacity_csv      = "OUTPUT/capacity_tract_with_vehicle_and_docks_norm.csv",
    tract_shp         = r"path/to/tract.shp",
    output_dir        = "OUTPUT/CAPACITY_MAPS",
    capacity_norm_col = "total_capacity_norm",   # auto-resolved if not found
    station_count_col = "num_station",           # auto-resolved if not found
    min_stations      = 1,
    drop_zeros        = True,
)
```

**Output files:** One PNG per capacity column found in the CSV, named `<gate_col>_gate__<column>.png`.

---

### 6. `correlation_visual`

Produces four-quadrant correlation maps comparing any two utility metrics. Each census tract is classified based on whether its values fall above or below a threshold, producing four categories. Works for both docked and dockless CSVs automatically.

**Categories:**

| Category        | Color        | Meaning                          |
|-----------------|--------------|----------------------------------|
| High X + High Y | Dark blue    | Both metrics are high            |
| High X + Low Y  | Light blue   | First metric high, second low    |
| Low X + High Y  | Light orange | First metric low, second high    |
| Low X + Low Y   | Dark orange  | Both metrics are low             |

**Usage:**

```python
from mobility_package import correlation_visual

correlation_visual.plot_correlation(
    metric_x     = "availability",
    csv_x        = "OUTPUT/availability__norm__tract.csv",
    metric_y     = "usage",
    csv_y        = "OUTPUT/usage_norm_hourly_tract.csv",
    capacity_csv = "OUTPUT/capacity_tract_norm.csv",
    tract_shp    = r"path/to/tract.shp",
    output_dir   = "OUTPUT/CORRELATION_MAPS",
)
```

**Available metrics:** `"availability"`, `"usage"`, `"idle_time"`, `"safety"`

**Output files:** `correlation_<metric_x>_vs_<metric_y>__mean__quantile.png`

---

### 7. `scatter_visual`

Classifies each census tract into a supply-demand category based on the relationship between availability (supply) and usage (demand) and produces two side-by-side scatter plots. Value columns are auto-resolved so docked and dockless CSVs both work without specifying column names.

**Categories:**

| Category                  | Color  | Condition                          |
|---------------------------|--------|------------------------------------|
| Undersupply               | Red    | Low availability + High usage      |
| Oversupply                | Orange | High availability + Low usage      |
| High demand + High supply | Green  | Both high                          |
| Balanced / Other          | Blue   | Everything else                    |

**Usage:**

```python
from mobility_package import scatter_visual

master, class_df, fig = scatter_visual.plot_scatter(
    availability_csv          = "OUTPUT/availability__norm__tract.csv",
    usage_csv                 = "OUTPUT/usage_norm_hourly_tract.csv",
    idle_csv                  = "OUTPUT/idle_time_norm_tract.csv",
    output_dir                = "OUTPUT/SCATTER",
    threshold_method          = "percent",
    use_symmetric_percentiles = True,
    availability_low_pct      = 30,
    usage_high_pct            = 70,
    show_threshold_debug      = True,
)
```

**Output files:** `scatter_supply_demand.png`, `tract_supply_demand_classification.csv`, `classification_summary_counts.csv`

---

### 8. `trend_visual`

Computes and plots Gini coefficient and Alpha fairness trends over time. Produces three plots per metric: Mean ± SD, Gini coefficient, and Alpha fairness over time. Each plot includes weekday peak-hour shading (7:30–9:00 am and 3:30–6:00 pm), day-of-week labels, and vertical day-boundary dividers.

**Important:** This module is designed for a full week of data. A single day of input will run without error but will produce a flat trend line. Pass a folder of 7 daily CSVs for meaningful results — the module auto-concatenates all CSVs it finds in the folder.

**Usage:**

```python
from mobility_package import trend_visual

# All metrics at once
trend_visual.plot_all(
    city_key       = "PITT_DOCKED",
    output_dir     = "OUTPUT/TREND",
    capacity_input = "OUTPUT/capacity_tract_with_vehicle_and_docks_norm.csv",

    # Pass a single CSV path for one day, or a folder path for a full week
    availability_input = "OUTPUT/WEEKLY/availability",
    usage_input        = "OUTPUT/WEEKLY/usage",
    idle_time_input    = "OUTPUT/WEEKLY/idle_time",

    filter_to_capacity_service_area = True,   # False for dockless
    band_alpha                      = 0.20,
)

# Or one metric at a time
trend_visual.plot_availability_trend(city_key=..., output_dir=...,
    availability_input=..., capacity_input=..., filter_to_capacity_service_area=True)
trend_visual.plot_usage_trend(...)
trend_visual.plot_idle_time_trend(...)
```

**Output files per metric column:**
- `MeanSD_Overall_<metric>.png`
- `Gini_Overall_<metric>.png`
- `AlphaFairness_Overall_<metric>.png`
- `<city_key>__results_ordered_df_week.csv`

---

### 9. `table_visual`

Generates a publication-ready grouped fairness summary table from the fairness results CSV. Grouped by utility with bold group headers, three-line border structure, and Times New Roman font. Returns a pandas Styler that renders inline in Jupyter, or a plain DataFrame for export.

**Usage:**

```python
from mobility_package import table_visual

# Renders inline in Jupyter
table_visual.make_table(
    csv_path    = "OUTPUT/FAIRNESS/PITT_DOCKED_fairness_results.csv",
    decimals    = 3,
    font_family = "Times New Roman",
    render      = "styler",
)

# Export as plain DataFrame
df = table_visual.make_table(
    csv_path = "OUTPUT/FAIRNESS/PITT_DOCKED_fairness_results.csv",
    render   = "dataframe",
)
df.to_csv("fairness_table_export.csv", index=False)
```

**Required CSV columns:** `Utility`, `Metric`, `Min`, `Max`, `Mean`, `StDev`, `Gini Coefficient`, `Alpha Fairness (α = 1, Normalized)`

---

## Adding a New City or System

The package is designed to be extended to new cities. The steps differ slightly between docked and dockless systems.

### Adding a New Docked City

Open `docked_wrapper.py` and add an entry to the `CITY_CONFIG` dictionary following the pattern of the existing cities:

```python
CITY_CONFIG["CHICAGO"] = {
    "use_api_fallback": True,
    "assets": {
        "census_blocks": r"path/to/tl_2024_17_tabblock20.shp",
        "tracts":        r"path/to/tl_2024_17_tract.shp",
        "centroid_csv":  r"path/to/centroid_tract_il.csv",
        "centerline":    r"path/to/chicago_street_centerline.shp",
        "bike_lanes":    r"path/to/chicago_bike_routes.shp",
    },
    "geo": {
        "blocks_id":             "GEOID20",
        "tract_id":              "GEOID",
        "crs":                   "EPSG:4326",
        "metric_crs":            "EPSG:32616",   # UTM Zone 16N for Chicago
        "safety_type":           "shp",           # "shp" or "csv_wkt"
        "wkt_candidates":        (),
        "external_tract_prefix": None,
        "drop_staten_island":    False,
    },
    "safety_rule": {
        "col_candidates": ("facility", "type", "class", "lane_type"),
        "match_type":     "contains",             # "contains" | "equals" | "not_empty_or_contains"
        "match_value":    "PROTECT",
    },
}
```

Then call it the same way as any supported city:

```python
ctx = docked_wrapper.load_docked_context(city="CHICAGO", ...)
```

**Key configuration decisions:**

`metric_crs` — the projected CRS used for measuring street lengths in the safety calculation. Choose the UTM zone for your city. You can look this up at [epsg.io](https://epsg.io) by searching your city name.

`safety_type` — set to `"shp"` if your street and bike lane files are shapefiles, or `"csv_wkt"` if they are CSV files with a WKT geometry column.

`safety_rule` — controls how protected bike lanes are identified. Inspect the attribute table of your bike lanes file to find which column and value distinguishes protected lanes from regular ones.

`external_tract_prefix` — set to the 2-digit FIPS code of a neighboring state if your GBFS data crosses a state boundary and you want to exclude those tracts. For most cities this is `None`.

### Adding a New Dockless System

Open `dockless_wrapper.py` and add an entry to the `_SYSTEMS` dictionary:

```python
_SYSTEMS["AUSTIN_LIME_DOCKLESS"] = {
    "city":                "Austin",
    "vendor":              "Lime",
    "tag":                 "austin_lime",
    "default_output_dir":  "AUSTIN_LIME_DOCKLESS_FULL_RUN",
    "raw_csv":             "austin_lime_status_raw.csv",
    "done_csv":            "austin_lime_status_done.csv",
    "assets": {
        "census_blocks_shp":        r"path/to/tl_2024_48_tabblock20.shp",
        "centerline_streets_path":  r"path/to/austin_street_centerline.shp",
        "bike_lanes_path":          r"path/to/austin_bike_lanes.shp",
        "centroid_tract_path":      r"path/to/tl_2024_48_tract.shp",
    },
    "safety_epsg": 32614,   # UTM Zone 14N for Austin
}
```

Then call it the same way:

```python
ctx = dockless_wrapper.load_dockless_context(system_key="AUSTIN_LIME_DOCKLESS", ...)
```

**Finding the right UTM zone (`safety_epsg`):** Search for your city at [epsg.io](https://epsg.io) or use the rule of thumb that UTM zones cover 6° of longitude — find your city's longitude and divide by 6 to get the zone number, then add 32600 for the northern hemisphere EPSG code.

**Finding the right census blocks shapefile:** Go to the [US Census TIGER/Line Shapefiles page](https://www.census.gov/cgi-bin/geo/shapefiles/index.php), select the year, choose "Census Blocks" as the layer type, and select your state. The state FIPS code is part of the filename — Texas is 48, so the file would be `tl_2024_48_tabblock20.shp`.

**Checking your snapshot file structure:** Different vendors use slightly different field names. Run this to inspect yours before configuring:

```python
import json
with open("your_freebike_status.txt") as f:
    blob = json.loads(f.readline())
    ts = list(blob.keys())[0]
    print(blob[ts][0])
# Should show: bike_id/vehicle_id, lat, lon, is_reserved, is_disabled, etc.
```

---

## Data Format Reference

The following table lists the key output column names produced by each wrapper. The `fairness_calculation`, `map_visual`, `correlation_visual`, and `scatter_visual` modules all resolve column names automatically so you do not need to specify them manually.

| Module | Column | Description |
|--------|--------|-------------|
| `docked_wrapper` | `census_tract` | 11-digit GEOID |
| | `time_slot` | Hourly timestamp |
| | `total_vehicle_available_norm` | Normalised vehicle availability |
| | `trips_starting_norm` | Normalised trip starts |
| | `trips_ending_norm` | Normalised trip ends |
| | `avg_idle_time_norm` | Normalised idle time |
| | `total_capacity_norm` | Normalised total dock capacity |
| | `bike_lane_ratio_norm` | Normalised bike-lane ratio |
| `dockless_wrapper` | `census_tract` | 11-digit GEOID |
| | `time_slot` | Hourly timestamp |
| | `total_available_norm` | Normalised vehicle availability |
| | `starts_norm` | Normalised inferred trip starts |
| | `ends_norm` | Normalised inferred trip ends |
| | `avg_idle_time_minutes_norm` | Normalised idle time (minutes) |
| | `vehicle_capacity_norm` | Normalised vehicle capacity |
| | `bike_lane_ratio_norm` | Normalised bike-lane ratio |

---

## Fairness Metrics

**Gini Coefficient**

Measures inequality in the distribution of a utility metric across census tracts. A value of 0 indicates perfect equality. A value of 1 indicates complete concentration in a single tract.

```
G = (n + 1 - 2 * Σ(cumulative values) / total) / n
```

**Alpha Fairness (α = 1)**

A combined fairness-efficiency metric. At α = 1 this reduces to proportional fairness — the sum of log utilities across all tracts. Higher values indicate greater total log-utility delivered equitably across the system.

```
F = Σ log(x_i + 1)   for all tracts i
```

---

## Output Reference

| Module                 | Output Files |
|------------------------|-------------|
| `docked_wrapper`       | Per-metric CSVs in the specified `output_dir` |
| `dockless_wrapper`     | Per-metric CSVs tagged with the vendor name |
| `fairness_calculation` | `<city_key>_fairness_results.csv`, `<city_key>_fairness_input_summary.csv` |
| `map_visual`           | `availability_rank__mean.png`, `usage_rank__mean.png`, `idle_time_rank__mean.png`, `safety_rank__mean.png` |
| `capacity_map_visual`  | One PNG per capacity column: `<gate_col>_gate__<column>.png` |
| `correlation_visual`   | `correlation_<x>_vs_<y>__mean__quantile.png` per metric pair |
| `scatter_visual`       | `scatter_supply_demand.png`, `tract_supply_demand_classification.csv`, `classification_summary_counts.csv` |
| `trend_visual`         | `MeanSD_Overall_<metric>.png`, `Gini_Overall_<metric>.png`, `AlphaFairness_Overall_<metric>.png` per metric column |
| `table_visual`         | In-memory Styler or DataFrame — no file written to disk |

---

## Research Context

This package was developed to support the empirical analysis in:

> Zibandehkhooy, T., & Chen, V. (X.). (2025).
> *Evaluating Multidimensional Fairness in Shared Micromobility: Case Studies of Docked and Dockless Systems.*
> Preprint submitted to Journal of Transport Geography.

The framework distinguishes between static decision outcomes (capacity, safety) shaped by long-term operator and policymaker decisions, and dynamic system outcomes (availability, usage, idle time) that emerge from real-time user behavior. Fairness is evaluated from horizontal equity (Gini coefficient) and combined fairness-efficiency (Alpha fairness) perspectives, applied across census tracts as the spatial unit of analysis.

---

## Citation

If you use this package or the associated framework in your research, please cite:

```
@article{zibandehkhooy2025fairness,
  title   = {Evaluating Multidimensional Fairness in Shared Micromobility:
             Case Studies of Docked and Dockless Systems},
  author  = {Zibandehkhooy, Tara and Chen, Violet (Xinying)},
  journal = {Journal of Transport Geography},
  year    = {2025},
  note    = {Preprint}
}
```

---

## Authors

**Research Paper**
Tara Zibandehkhooy, Violet (Xinying) Chen
*Journal of Transport Geography, 2025 (Preprint)*

**Package Implementation**
Developed as the computational implementation of the above research.
All module design, code architecture, and pipeline engineering were independently authored to support the paper's empirical analysis.

---

## License

MIT License. See `LICENSE` for details.
