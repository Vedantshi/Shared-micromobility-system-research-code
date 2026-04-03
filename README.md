# mobility-package

### A Python Package for Multidimensional Fairness Analysis of Shared Micromobility Systems

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![GeoPandas](https://img.shields.io/badge/GeoPandas-0.14%2B-green)
![Matplotlib](https://img.shields.io/badge/Matplotlib-3.8%2B-orange)
![License](https://img.shields.io/badge/License-MIT-lightgrey)
![Status](https://img.shields.io/badge/Status-Research-darkblue)

---

## Overview

This package provides a structured Python implementation for computing,
analyzing, and visualizing fairness metrics in shared micromobility systems
(SMS). It was developed as the computational backbone of the research paper:

> **Evaluating Multidimensional Fairness in Shared Micromobility: Case
> Studies of Docked and Dockless Systems**
> *Tara Zibandehkhooy, Violet (Xinying) Chen*
> Preprint submitted to Journal of Transport Geography, September 2025

The framework operationalizes a pipeline that moves from raw GBFS
(General Bikeshare Feed Specification) snapshots through utility
computation, fairness measurement, and spatial visualization. It supports
both docked systems (e.g. Citi Bike, NYC) and dockless systems (e.g. Lime,
Bird, Spin in San Francisco and Seattle), and is designed to be extensible
to other cities and system types.

The package distinguishes between **static decision outcomes** — capacity
and safety — which reflect long-term operator and policymaker decisions,
and **dynamic system outcomes** — availability, usage, and idle time — which
emerge from real-time user behavior. Fairness is evaluated across both
dimensions using established inequality metrics (Gini coefficient) and
combined fairness-efficiency metrics (Alpha fairness at α = 1).

---

## Pipeline Architecture

The following diagram illustrates the full data-to-visualization pipeline
implemented in this package.
```
```
Raw GBFS Snapshot (.txt)
         |
         v
+----------------------------+
|  docked_wrapper            |  for docked systems (NYC, NJ, Pittsburgh)
|  dockless_wrapper          |  for dockless systems (SF Lime/Spin, Seattle Bird/Lime)
+----------------------------+
         |
         |  Produces per-tract CSVs:
         |  availability, capacity, usage, idle_time, safety
         v
+----------------------------+
|  fairness_calculation      |  Gini coefficient + Alpha fairness
+----------------------------+
         |
         v
+-----------------------------------------------------------+
|                    Visualization Modules                  |
|                                                           |
|  map_visual           Utility choropleth maps             |
|  capacity_map_visual  Capacity decile maps                |
|  correlation_visual   4-quadrant metric correlation maps  |
|  scatter_visual       Supply-demand scatter plots         |
|  trend_visual         Weekly fairness time-series plots   |
|  table_visual         Paper-style fairness summary table  |
+-----------------------------------------------------------+
```

---

## Supported Systems

| City          | Operator | System Type | `system_key`             |
|---------------|----------|-------------|--------------------------|
| New York City | Citi Bike | Docked      | `"NYC_DOCKED"`           |
| New Jersey    | Citi Bike | Docked      | `"NJ_DOCKED"`            |
| Pittsburgh    | Healthy Ride | Docked   | `"PITT_DOCKED"`          |
| San Francisco | Lime      | Dockless    | `"SF_LIME_DOCKLESS"`     |
| San Francisco | Spin      | Dockless    | `"SF_SPIN_DOCKLESS"`     |
| Seattle       | Bird      | Dockless    | `"SEATTLE_BIRD_DOCKLESS"`|
| Seattle       | Lime      | Dockless    | `"SEATTLE_LIME_DOCKLESS"`|

---

## Package Structure
```
```
mobility_package/
│
├── __init__.py                  Package entry point — imports all modules
│
├── docked_wrapper.py            Utility computation for docked systems
├── dockless_wrapper.py          Utility computation for dockless systems
├── fairness_calculation.py      Gini and Alpha fairness computation
│
├── map_visual.py                Utility choropleth maps (availability,
│                                usage, idle time, safety)
├── capacity_map_visual.py       Capacity decile choropleth maps
├── correlation_visual.py        Two-metric correlation quadrant maps
├── scatter_visual.py            Supply-demand classification scatter plots
├── trend_visual.py              Weekly fairness time-series visualization
└── table_visual.py              Paper-style fairness summary table
```

---

## Tech Stack

| Library       | Purpose                                              |
|---------------|------------------------------------------------------|
| `pandas`      | Tabular data processing and aggregation              |
| `numpy`       | Numerical computation for fairness metrics           |
| `geopandas`   | Spatial joins, shapefile handling, choropleth maps   |
| `shapely`     | Geometry operations for safety (bike lane analysis)  |
| `contextily`  | OpenStreetMap basemap tiles                          |
| `matplotlib`  | All plot rendering                                   |
| `requests`    | Census geocoder API calls for coordinate resolution  |
| `tqdm`        | Progress bars for long-running spatial joins         |

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

The following example runs the complete pipeline for the NYC docked
system — from raw GBFS data to a fairness table — in a single script.
```python
from mobility_package import (
    docked_wrapper,
    fairness_calculation,
    map_visual,
    trend_visual,
    table_visual,
)

# Step 1 — Load context (parse GBFS snapshot, geocode, filter time window)
ctx = docked_wrapper.load_docked_context(
    city                = "NYC",
    station_status_txt  = r"path/to/nyc_station_status.txt",
    station_information_csv = r"path/to/nyc_station_information.csv",
    output_dir          = "NYC_OUTPUT",
    time_start          = "2025-04-06 00:00:00",
    time_end            = "2025-04-06 23:59:59",
)

# Step 2 — Compute all utility metrics
results = docked_wrapper.compute_all(
    ctx,
    trip_csv = r"path/to/citibike_tripdata/",
)

# Step 3 — Compute fairness metrics
fairness_calculation.compute_fairness(
    city_key   = "NYC_DOCKED",
    output_dir = "NYC_OUTPUT/FAIRNESS",
    availability_input = "NYC_OUTPUT/availability__norm__tract.csv",
    usage_input        = "NYC_OUTPUT/usage_norm_hourly_tract.csv",
    idle_time_input    = "NYC_OUTPUT/idle_time_norm_tract.csv",
    capacity_input     = "NYC_OUTPUT/capacity_tract_norm.csv",
    safety_input       = "NYC_OUTPUT/safety_bike_lane_norm_tract.csv",
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

Processes raw GBFS station-status snapshots for docked bike-share systems
and computes all utility metrics at the census-tract level.

**Supported cities:** NYC, NJ, Pittsburgh (SF via Baywheels)

**Metrics produced:**

| Metric       | Description                                              | Output CSV                              |
|--------------|----------------------------------------------------------|-----------------------------------------|
| Availability | Non-empty, non-disabled docks per tract per hour         | `availability__norm__tract.csv`         |
| Capacity     | Peak-hour vehicle and dock count per tract               | `capacity_tract_norm.csv`               |
| Usage        | Trip starts and ends per tract per hour                  | `usage_norm_hourly_tract.csv`           |
| Idle Time    | Average time vehicles sit unused per tract per hour      | `idle_time_norm_tract.csv`              |
| Safety       | Bike-lane ratio per tract                                | `safety_bike_lane_norm_tract.csv`       |

**Usage:**
```python
from mobility_package import docked_wrapper

# Step 1 — Always call this first
ctx = docked_wrapper.load_docked_context(
    city                    = "NYC",
    station_status_txt      = r"path/to/station_status.txt",
    station_information_csv = r"path/to/station_information.csv",
    output_dir              = "NYC_OUTPUT",
    time_start              = "2025-04-06 00:00:00",
    time_end                = "2025-04-06 23:59:59",
)

# Step 2a — All metrics at once
results = docked_wrapper.compute_all(ctx, trip_csv=r"path/to/tripdata/")

# Step 2b — Or one at a time
avail  = docked_wrapper.compute_availability(ctx)
cap    = docked_wrapper.compute_capacity(ctx)
safety = docked_wrapper.compute_safety(ctx)
usage  = docked_wrapper.compute_usage(ctx, trip_csv=r"path/to/tripdata/")
idle   = docked_wrapper.compute_idle_time(ctx, trip_csv=r"path/to/tripdata/")
```

---

### 2. `dockless_wrapper`

Processes raw GBFS free-bike-status snapshots for dockless systems.
Because dockless systems do not provide explicit trip records, usage is
inferred from consecutive vehicle location changes across 5-minute
snapshot windows.

**Supported systems:** SF Lime, SF Spin, Seattle Bird, Seattle Lime

**Metrics produced:**

| Metric       | Description                                              | Output CSV                               |
|--------------|----------------------------------------------------------|------------------------------------------|
| Availability | Non-reserved, non-disabled vehicles per tract per hour   | `availability_norm_hourly_tract_*.csv`   |
| Capacity     | Peak-snapshot vehicle count per tract                    | `capacity_tract_*.csv`                   |
| Usage        | Inferred trip starts/ends per tract per hour             | `usage_norm_hourly_tract_*.csv`          |
| Idle Time    | Ping count × 5 minutes per vehicle per tract             | `idle_norm_hourly_tract_*.csv`           |
| Safety       | Bike-lane ratio per tract                                | `safety_tract_*.csv`                     |

**Usage:**
```python
from mobility_package import dockless_wrapper

# Step 1 — Always call this first
ctx = dockless_wrapper.load_dockless_context(
    system_key          = "SF_LIME_DOCKLESS",
    freebike_status_txt = r"path/to/sf_lime_freebike_status.txt",
    output_dir          = "SF_LIME_OUTPUT",
    time_start          = "2025-06-09 06:00:00",
    time_end            = "2025-06-09 12:00:00",
)

# Step 2a — All metrics at once
results = dockless_wrapper.compute_all(ctx)

# Step 2b — Or one at a time
avail  = dockless_wrapper.compute_availability(ctx)
cap    = dockless_wrapper.compute_capacity(ctx)
usage  = dockless_wrapper.compute_usage(ctx)
idle   = dockless_wrapper.compute_idle_time(ctx)
safety = dockless_wrapper.compute_safety(ctx)
```

---

### 3. `fairness_calculation`

Computes two fairness metrics — Gini coefficient and Alpha fairness
(α = 1) — for each utility metric across all census tracts. Results are
aggregated into a single paper-ready CSV.

**Fairness metrics:**

| Metric                  | Definition                                          |
|-------------------------|-----------------------------------------------------|
| Gini Coefficient        | Standard inequality measure. 0 = perfectly equal,  |
|                         | 1 = completely concentrated in one tract.           |
| Alpha Fairness (α = 1)  | Proportional fairness. Σ log(x + 1) across tracts. |
|                         | Higher = more total utility distributed fairly.     |

**Usage:**
```python
from mobility_package import fairness_calculation

fairness_calculation.compute_fairness(
    city_key           = "NYC_DOCKED",
    output_dir         = "NYC_OUTPUT/FAIRNESS",
    availability_input = "NYC_OUTPUT/availability__norm__tract.csv",
    usage_input        = "NYC_OUTPUT/usage_norm_hourly_tract.csv",
    idle_time_input    = "NYC_OUTPUT/idle_time_norm_tract.csv",
    capacity_input     = "NYC_OUTPUT/capacity_tract_norm.csv",
    safety_input       = "NYC_OUTPUT/safety_bike_lane_norm_tract.csv",
)
```

**Output:** `NYC_DOCKED_fairness_results.csv`

---

### 4. `map_visual`

Produces static choropleth maps for all utility metrics at the census-tract
level. Each map uses the RdYlBu colormap with an OpenStreetMap basemap,
compass rose, and scale bar. Maps can be generated for individual metrics
or all at once.

**Usage:**
```python
from mobility_package import map_visual

# Single metric
map_visual.plot_map(
    metric       = "availability",
    csv          = "NYC_OUTPUT/availability__norm__tract.csv",
    capacity_csv = "NYC_OUTPUT/capacity_tract_norm.csv",
    tract_shp    = r"path/to/tl_2024_36_tract.shp",
    output_dir   = "NYC_OUTPUT/MAPS",
)

# All metrics at once
map_visual.plot_all(
    availability_csv = "NYC_OUTPUT/availability__norm__tract.csv",
    usage_csv        = "NYC_OUTPUT/usage_norm_hourly_tract.csv",
    idle_time_csv    = "NYC_OUTPUT/idle_time_norm_tract.csv",
    safety_csv       = "NYC_OUTPUT/safety_bike_lane_norm_tract.csv",
    capacity_csv     = "NYC_OUTPUT/capacity_tract_norm.csv",
    tract_shp        = r"path/to/tl_2024_36_tract.shp",
    output_dir       = "NYC_OUTPUT/MAPS",
)
```

**Available metrics:** `"availability"`, `"usage"`, `"idle_time"`, `"safety"`

---

### 5. `capacity_map_visual`

Produces decile choropleth maps specifically for capacity metrics. Tracts
are binned into ten equal-percentile groups (1-10%, 11-20%, … 91-100%).
Only tracts with at least one bike-share station are included, consistent
with the professor-style docked service-area definition used in the paper.

**Usage:**
```python
from mobility_package import capacity_map_visual

capacity_map_visual.plot_capacity(
    capacity_csv      = "NYC_OUTPUT/capacity_tract_norm.csv",
    tract_shp         = r"path/to/tl_2024_36_tract.shp",
    output_dir        = "NYC_OUTPUT/CAPACITY_MAPS",
    capacity_norm_col = "total_capacity_norm",
    station_count_col = "num_station",
    min_stations      = 1,
    drop_zeros        = True,
)
```

**Output per column:** `NYC_ONLY_total_capacity_norm_gate__<column>.png`

---

### 6. `correlation_visual`

Produces four-quadrant correlation maps comparing any two utility metrics.
Each census tract is classified based on whether its values for each metric
fall above or below a threshold, resulting in four categories plotted as a
choropleth map.

**Categories:**

| Category               | Color       | Interpretation                        |
|------------------------|-------------|---------------------------------------|
| High X + High Y        | Dark blue   | Both metrics are high                 |
| High X + Low Y         | Light blue  | First metric high, second low         |
| Low X + High Y         | Light orange| First metric low, second high         |
| Low X + Low Y          | Dark orange | Both metrics are low                  |

**Usage:**
```python
from mobility_package import correlation_visual

# Any two metrics can be compared
correlation_visual.plot_correlation(
    metric_x     = "availability",
    csv_x        = "NYC_OUTPUT/availability__norm__tract.csv",
    metric_y     = "usage",
    csv_y        = "NYC_OUTPUT/usage_norm_hourly_tract.csv",
    capacity_csv = "NYC_OUTPUT/capacity_tract_norm.csv",
    tract_shp    = r"path/to/tl_2024_36_tract.shp",
    output_dir   = "NYC_OUTPUT/CORRELATION_MAPS",
)
```

**Available metrics:** `"availability"`, `"usage"`, `"idle_time"`, `"safety"`

---

### 7. `scatter_visual`

Classifies each census tract into a supply-demand category based on
the relationship between availability (supply) and usage (demand), and
produces two side-by-side scatter plots: availability vs. usage and
usage vs. idle time.

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
    availability_csv     = "NYC_OUTPUT/availability__norm__tract.csv",
    usage_csv            = "NYC_OUTPUT/usage_norm_hourly_tract.csv",
    idle_csv             = "NYC_OUTPUT/idle_time_norm_tract.csv",
    output_dir           = "NYC_OUTPUT/SCATTER",
    threshold_method     = "percent",
    availability_low_pct = 30,
    usage_high_pct       = 70,
)
```

**Outputs:**
- `scatter_supply_demand.png`
- `tract_supply_demand_classification.csv`
- `classification_summary_counts.csv`

---

### 8. `trend_visual`

Computes and plots Gini coefficient and Alpha fairness trends over a full
week of hourly data. Accepts either a single weekly CSV or a folder of
daily CSVs that are automatically concatenated. Produces three plots per
metric: Mean ± SD, Gini coefficient, and Alpha fairness over time.

Each plot includes weekday peak-hour shading (7:30–9:00 am and
3:30–6:00 pm), day-of-week labels, and vertical day-boundary dividers.

**Usage:**
```python
from mobility_package import trend_visual

# One metric at a time
trend_visual.plot_availability_trend(
    city_key           = "NYC_DOCKED",
    output_dir         = "NYC_OUTPUT/TREND",
    availability_input = r"path/to/availability_weekly_folder/",
    capacity_input     = "NYC_OUTPUT/capacity_tract_norm.csv",
)

trend_visual.plot_usage_trend(
    city_key      = "NYC_DOCKED",
    output_dir    = "NYC_OUTPUT/TREND",
    usage_input   = r"path/to/usage_weekly_folder/",
    capacity_input= "NYC_OUTPUT/capacity_tract_norm.csv",
)

trend_visual.plot_idle_time_trend(
    city_key        = "NYC_DOCKED",
    output_dir      = "NYC_OUTPUT/TREND",
    idle_time_input = r"path/to/idle_weekly_folder/",
    capacity_input  = "NYC_OUTPUT/capacity_tract_norm.csv",
)

# Or all at once
trend_visual.plot_all(
    city_key           = "NYC_DOCKED",
    output_dir         = "NYC_OUTPUT/TREND",
    capacity_input     = "NYC_OUTPUT/capacity_tract_norm.csv",
    availability_input = r"path/to/availability_weekly_folder/",
    usage_input        = r"path/to/usage_weekly_folder/",
    idle_time_input    = r"path/to/idle_weekly_folder/",
)
```

**Outputs per metric column:**
- `MeanSD_Overall_<metric>.png`
- `Gini_Overall_<metric>.png`
- `AlphaFairness_Overall_<metric>.png`
- `NYC_DOCKED__<metric>_trend.csv`

---

### 9. `table_visual`

Generates a publication-ready grouped fairness summary table from the
fairness results CSV. The table format matches the paper's presentation
style: grouped by utility, bold group headers, three-line border structure,
Times New Roman font. Returns a pandas Styler that renders inline in
Jupyter, or a plain DataFrame for export.

**Usage:**
```python
from mobility_package import table_visual

# Renders inline in Jupyter
table_visual.make_table(
    csv_path    = "NYC_OUTPUT/FAIRNESS/NYC_DOCKED_fairness_results.csv",
    decimals    = 3,
    font_family = "Times New Roman",
    render      = "styler",
)

# As a plain DataFrame for export
df = table_visual.make_table(
    csv_path = "NYC_OUTPUT/FAIRNESS/NYC_DOCKED_fairness_results.csv",
    render   = "dataframe",
)
df.to_csv("fairness_table_export.csv", index=False)
```

**Required CSV columns:**

| Column                              |
|-------------------------------------|
| `Utility`                           |
| `Metric`                            |
| `Min`                               |
| `Max`                               |
| `Mean`                              |
| `StDev`                             |
| `Gini Coefficient`                  |
| `Alpha Fairness (α = 1, Normalized)`|

---

## Fairness Metrics

This package implements two fairness metrics as defined in the paper.

**Gini Coefficient**

Measures inequality in the distribution of a utility metric across
census tracts. A value of 0 indicates perfect equality — every tract
receives the same level of utility. A value of 1 indicates complete
concentration — all utility is received by a single tract.
```
G = (n + 1 - 2 * Σ(cumulative values) / total) / n
```

**Alpha Fairness (α = 1)**

A combined fairness-efficiency metric from the Alpha fairness family
(Mo and Walrand 2000). At α = 1, this reduces to proportional fairness —
the sum of log utilities across all tracts. Higher values indicate
greater total log-utility delivered equitably across the system.
```
F = Σ log(x_i + 1)   for all tracts i
```

Both metrics are computed per time slot for dynamic metrics (availability,
usage, idle time) and as a single value for static metrics (capacity, safety).

---

## Data Format Reference

The following table lists the expected column names in each metric CSV
as produced by `docked_wrapper` and `dockless_wrapper`.

| Module                 | CSV Column                    | Description                        |
|------------------------|-------------------------------|------------------------------------|
| `docked_wrapper`       | `census_tract`                | 11-digit GEOID                     |
|                        | `time_slot`                   | Hourly timestamp                   |
|                        | `total_vehicle_available_norm`| Normalised vehicle availability    |
|                        | `trips_starting_norm`         | Normalised trip starts             |
|                        | `trips_ending_norm`           | Normalised trip ends               |
|                        | `avg_idle_time_norm`          | Normalised idle time               |
|                        | `total_capacity_norm`         | Normalised total capacity          |
|                        | `bike_lane_ratio_norm`        | Normalised bike-lane ratio         |
| `dockless_wrapper`     | `census_tract`                | 11-digit GEOID                     |
|                        | `time_slot`                   | Hourly timestamp                   |
|                        | `total_available_norm`        | Normalised vehicle availability    |
|                        | `trips_starting_norm`         | Normalised inferred trip starts    |
|                        | `avg_idle_time_norm`          | Normalised idle time               |
|                        | `vehicle_capacity_norm`       | Normalised vehicle capacity        |
|                        | `bike_lane_ratio_norm`        | Normalised bike-lane ratio         |

---

## Output Reference

| Module                | Output Files                                              |
|-----------------------|-----------------------------------------------------------|
| `docked_wrapper`      | Per-metric CSVs in the specified `output_dir`             |
| `dockless_wrapper`    | Per-metric CSVs tagged with the system name               |
| `fairness_calculation`| `<city_key>_fairness_results.csv`                         |
| `map_visual`          | One PNG per metric: `<metric>_<agg>_<threshold>.png`      |
| `capacity_map_visual` | One PNG per capacity column                               |
| `correlation_visual`  | One PNG per metric pair                                   |
| `scatter_visual`      | Scatter PNG + two classification CSVs                     |
| `trend_visual`        | Three PNGs per metric column + one fairness CSV           |
| `table_visual`        | In-memory Styler or DataFrame (no file written)           |

---

## Research Context

This package was developed to support the empirical analysis in:

> Zibandehkhooy, T., & Chen, V. (X.). (2025).
> *Evaluating Multidimensional Fairness in Shared Micromobility:
> Case Studies of Docked and Dockless Systems.*
> Preprint submitted to Journal of Transport Geography.

The framework distinguishes between static decision outcomes (capacity,
safety) shaped by long-term operator and policymaker decisions, and dynamic
system outcomes (availability, usage, idle time) that emerge from real-time
user behavior. Fairness is evaluated from horizontal equity (Gini
coefficient), and combined fairness-efficiency perspectives (Alpha fairness),
applied across census tracts as the spatial unit of analysis.

---

## Citation

If you use this package or the associated framework in your research,
please cite:
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
All module design, code architecture, and pipeline engineering were
independently authored to support the paper's empirical analysis.

---

## License

MIT License. See `LICENSE` for details.
