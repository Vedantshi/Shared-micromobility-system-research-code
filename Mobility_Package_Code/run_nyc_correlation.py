from mobility_package import correlation_visual

CAPACITY_CSV = r"D:\Research Fellowship\NYC_Docked_Output_v2\capacity_tract_norm.csv"
TRACT_SHP    = r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Capacity\NYC\tl_2024_36_tract.shp"
OUTPUT_DIR   = "CORRELATION_MAPS_OUT"

# ------------------------------------------------------------------
# availability vs usage
# ------------------------------------------------------------------
correlation_visual.plot_correlation(
    metric_x     = "availability",
    csv_x        = r"D:\Research Fellowship\NYC_Docked_Output_v2\availability__norm__tract.csv",
    metric_y     = "usage",
    csv_y        = r"D:\Research Fellowship\NYC_Docked_Output_v2\usage_norm_hourly_tract.csv",
    capacity_csv = CAPACITY_CSV,
    tract_shp    = TRACT_SHP,
    output_dir   = OUTPUT_DIR,
)

# ------------------------------------------------------------------
# availability vs idle time
# ------------------------------------------------------------------
correlation_visual.plot_correlation(
    metric_x     = "availability",
    csv_x        = r"D:\Research Fellowship\NYC_Docked_Output_v2\availability__norm__tract.csv",
    metric_y     = "idle_time",
    csv_y        = r"D:\Research Fellowship\NYC_Docked_Output_v2\idle_time_norm_tract.csv",
    capacity_csv = CAPACITY_CSV,
    tract_shp    = TRACT_SHP,
    output_dir   = OUTPUT_DIR,
)

# ------------------------------------------------------------------
# availability vs safety
# ------------------------------------------------------------------
correlation_visual.plot_correlation(
    metric_x     = "availability",
    csv_x        = r"D:\Research Fellowship\NYC_Docked_Output_v2\availability__norm__tract.csv",
    metric_y     = "safety",
    csv_y        = r"D:\Research Fellowship\NYC_Docked_Output_v2\safety_bike_lane_norm_tract.csv",
    capacity_csv = CAPACITY_CSV,
    tract_shp    = TRACT_SHP,
    output_dir   = OUTPUT_DIR,
)

# ------------------------------------------------------------------
# usage vs idle time
# ------------------------------------------------------------------
correlation_visual.plot_correlation(
    metric_x     = "usage",
    csv_x        = r"D:\Research Fellowship\NYC_Docked_Output_v2\usage_norm_hourly_tract.csv",
    metric_y     = "idle_time",
    csv_y        = r"D:\Research Fellowship\NYC_Docked_Output_v2\idle_time_norm_tract.csv",
    capacity_csv = CAPACITY_CSV,
    tract_shp    = TRACT_SHP,
    output_dir   = OUTPUT_DIR,
)

# ------------------------------------------------------------------
# usage vs safety
# ------------------------------------------------------------------
correlation_visual.plot_correlation(
    metric_x     = "usage",
    csv_x        = r"D:\Research Fellowship\NYC_Docked_Output_v2\usage_norm_hourly_tract.csv",
    metric_y     = "safety",
    csv_y        = r"D:\Research Fellowship\NYC_Docked_Output_v2\safety_bike_lane_norm_tract.csv",
    capacity_csv = CAPACITY_CSV,
    tract_shp    = TRACT_SHP,
    output_dir   = OUTPUT_DIR,
)

# ------------------------------------------------------------------
# idle time vs safety
# ------------------------------------------------------------------
correlation_visual.plot_correlation(
    metric_x     = "idle_time",
    csv_x        = r"D:\Research Fellowship\NYC_Docked_Output_v2\idle_time_norm_tract.csv",
    metric_y     = "safety",
    csv_y        = r"D:\Research Fellowship\NYC_Docked_Output_v2\safety_bike_lane_norm_tract.csv",
    capacity_csv = CAPACITY_CSV,
    tract_shp    = TRACT_SHP,
    output_dir   = OUTPUT_DIR,
)