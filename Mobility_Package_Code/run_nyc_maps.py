from mobility_package import map_visual

CAPACITY_CSV = r"D:\Research Fellowship\NYC_Docked_Output_v2\capacity_tract_norm.csv"
TRACT_SHP    = r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Capacity\NYC\tl_2024_36_tract.shp"
OUTPUT_DIR   = "DYNAMIC_TRACT_MAPS_OUT"

# ------------------------------------------------------------------
# OPTION A — all four maps at once
# ------------------------------------------------------------------
results = map_visual.plot_all(
    availability_csv = r"D:\Research Fellowship\NYC_Docked_Output_v2\availability__norm__tract.csv",
    usage_csv        = r"D:\Research Fellowship\NYC_Docked_Output_v2\usage_norm_hourly_tract.csv",
    idle_time_csv    = r"D:\Research Fellowship\NYC_Docked_Output_v2\idle_time_norm_tract.csv",
    safety_csv       = r"D:\Research Fellowship\NYC_Docked_Output_v2\safety_bike_lane_norm_tract.csv",
    capacity_csv     = CAPACITY_CSV,
    tract_shp        = TRACT_SHP,
    output_dir       = OUTPUT_DIR,
)

# ------------------------------------------------------------------
# OPTION B — one map at a time
# ------------------------------------------------------------------
# map_visual.plot_map(
#     metric       = "availability",
#     csv          = r"D:\Research Fellowship\NYC_Docked_Output_v2\availability__norm__tract.csv",
#     capacity_csv = CAPACITY_CSV,
#     tract_shp    = TRACT_SHP,
#     output_dir   = OUTPUT_DIR,
# )

# map_visual.plot_map(
#     metric       = "usage",
#     csv          = r"D:\Research Fellowship\NYC_Docked_Output_v2\usage_norm_hourly_tract.csv",
#     capacity_csv = CAPACITY_CSV,
#     tract_shp    = TRACT_SHP,
#     output_dir   = OUTPUT_DIR,
# )

# map_visual.plot_map(
#     metric       = "idle_time",
#     csv          = r"D:\Research Fellowship\NYC_Docked_Output_v2\idle_time_norm_tract.csv",
#     capacity_csv = CAPACITY_CSV,
#     tract_shp    = TRACT_SHP,
#     output_dir   = OUTPUT_DIR,
# )

# map_visual.plot_map(
#     metric       = "safety",
#     csv          = r"D:\Research Fellowship\NYC_Docked_Output_v2\safety_bike_lane_norm_tract.csv",
#     capacity_csv = CAPACITY_CSV,
#     tract_shp    = TRACT_SHP,
#     output_dir   = OUTPUT_DIR,
# )

print(results)