from mobility_package import trend_visual

# -----------------------------------------------------------------------
# ALL METRICS IN ONE CALL
# Runs availability + usage + idle time in sequence.
# All three share the same capacity, output folder, and settings.
# Pass False for any metric you want to skip.
# -----------------------------------------------------------------------
trend_visual.plot_all(
    city_key   = "NYC_DOCKED",
    output_dir = r"D:\Research Fellowship\NYC_Docked_Output_v2\FAIRNESS_TREND_OUT",

    # Capacity CSV — shared across all three metrics
    capacity_input = r"D:\Research Fellowship\NYC_New_Trend_Visual 1 Week\COLLECTED\capacity_tract_with_vehicle_and_docks_norm\capacity_tract_with_vehicle_and_docks_norm_3-31.csv",

    # Each metric input: folder, single CSV, or False to skip
    availability_input = r"D:\Research Fellowship\NYC_New_Trend_Visual 1 Week\COLLECTED\availability__norm__tract",
    usage_input        = r"D:\Research Fellowship\NYC_New_Trend_Visual 1 Week\COLLECTED\usage_norm_hourly_tract",
    idle_time_input    = r"D:\Research Fellowship\NYC_New_Trend_Visual 1 Week\COLLECTED\idle_time_norm_tract",

    # Only include tracts that have capacity > 0 in the fairness computation
    filter_to_capacity_service_area = True,

    # Drop specific bad timestamps if needed
    invalid_time_slots = None,

    # SD band transparency on Mean±SD plots
    band_alpha = 0.20,
)



# Individual trend functions for each metric
# -----------------------------------------------------------------------
# AVAILABILITY TREND
# Plots how availability fairness changes hour by hour over the week.
# Produces 3 PNGs:
#   MeanSD_Overall_Availability_total_vehicle_available_norm.png
#   Gini_Overall_Availability_total_vehicle_available_norm.png
#   AlphaFairness_Overall_Availability_total_vehicle_available_norm.png
# -----------------------------------------------------------------------
trend_visual.plot_availability_trend(
    # City/system key — drives color scheme and borough inference
    city_key = "NYC_DOCKED",

    # Folder where all PNGs and the fairness CSV will be saved
    output_dir = r"D:\Research Fellowship\NYC_Docked_Output_v2\FAIRNESS_TREND_OUT",

    # Availability input — can be:
    #   a single weekly CSV  → r"path/to/availability_week.csv"
    #   a folder of daily CSVs (auto-concatenated) → r"path/to/folder/"
    #   False → skip this metric entirely
    availability_input = r"D:\Research Fellowship\NYC_New_Trend_Visual 1 Week\COLLECTED\availability__norm__tract",

    # Capacity CSV — used to define which tracts are in the service area.
    # Only tracts with capacity > 0 are included in the fairness computation.
    # Pass False if you want to include all tracts regardless.
    capacity_input = r"D:\Research Fellowship\NYC_New_Trend_Visual 1 Week\COLLECTED\capacity_tract_with_vehicle_and_docks_norm\capacity_tract_with_vehicle_and_docks_norm_3-31.csv",

    # Set to False if you want ALL tracts included, not just service-area ones
    filter_to_capacity_service_area = True,

    # Optional: exclude specific timestamps that had data issues
    # e.g. a snapshot that was corrupted or missing
    invalid_time_slots = None,   # e.g. ["2025-04-06 03:00:00"]

    # Transparency of the ±SD shaded band on the Mean±SD plot
    band_alpha = 0.20,
)


# -----------------------------------------------------------------------
# USAGE TREND
# Plots how trip-start/end fairness changes hour by hour over the week.
# Produces 3 PNGs per column found (trips_starting_norm, trips_ending_norm)
# -----------------------------------------------------------------------
trend_visual.plot_usage_trend(
    city_key   = "NYC_DOCKED",
    output_dir = r"D:\Research Fellowship\NYC_Docked_Output_v2\FAIRNESS_TREND_OUT",

    # Same folder / CSV / False options as availability_input above
    usage_input = r"D:\Research Fellowship\NYC_New_Trend_Visual 1 Week\COLLECTED\usage_norm_hourly_tract",

    capacity_input = r"D:\Research Fellowship\NYC_New_Trend_Visual 1 Week\COLLECTED\capacity_tract_with_vehicle_and_docks_norm\capacity_tract_with_vehicle_and_docks_norm_3-31.csv",

    filter_to_capacity_service_area = True,
    invalid_time_slots = None,
    band_alpha = 0.20,
)


# -----------------------------------------------------------------------
# IDLE TIME TREND
# Plots how idle-time fairness changes hour by hour over the week.
# Produces 3 PNGs:
#   MeanSD_Overall_Idle_Time_avg_idle_time_norm.png
#   Gini_Overall_Idle_Time_avg_idle_time_norm.png
#   AlphaFairness_Overall_Idle_Time_avg_idle_time_norm.png
# -----------------------------------------------------------------------
trend_visual.plot_idle_time_trend(
    city_key   = "NYC_DOCKED",
    output_dir = r"D:\Research Fellowship\NYC_Docked_Output_v2\FAIRNESS_TREND_OUT",

    idle_time_input = r"D:\Research Fellowship\NYC_New_Trend_Visual 1 Week\COLLECTED\idle_time_norm_tract",

    capacity_input = r"D:\Research Fellowship\NYC_New_Trend_Visual 1 Week\COLLECTED\capacity_tract_with_vehicle_and_docks_norm\capacity_tract_with_vehicle_and_docks_norm_3-31.csv",

    filter_to_capacity_service_area = True,
    invalid_time_slots = None,
    band_alpha = 0.20,
)