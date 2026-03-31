from mobility_package import docked_wrapper

# ------------------------------------------------------------------
# STEP 1 — always required first, regardless of which metric you want
# ------------------------------------------------------------------
ctx = docked_wrapper.load_docked_context(
    city="NYC",  # NYC / NJ / PITT / SF
    station_status_txt=r"D:\Research Fellowship\NYC Trend Visual Docs\Station Status 1 Week Information\nyc_station_status_4_6.txt",
    station_information_csv=r"D:\Research Fellowship\NYC Trend Visual Docs\NYC April Station Information\NYC station information 03_04 done.csv",
    output_dir=r"NYC_New_Trend_Visual 1 Week\4-6",
)

# ------------------------------------------------------------------
# OPTION A — all metrics at once
# ------------------------------------------------------------------
results = docked_wrapper.compute_all(
    ctx,
    trip_csv=r"D:\Research Fellowship\NYC Trend Visual Docs\202504-citibike-tripdata",
    time_start="2025-04-06 00:00:00",
    time_end="2025-04-06 23:59:59",
)

# ------------------------------------------------------------------
# OPTION B — single metrics, pick whichever one(s) you need
# ------------------------------------------------------------------

# # availability only
# avail = docked_wrapper.compute_availability(
#     ctx,
#     time_start="2025-04-06 00:00:00",
#     time_end="2025-04-06 23:59:59",
# )

# # capacity only
# cap = docked_wrapper.compute_capacity(
#     ctx,
#     time_start="2025-04-06 00:00:00",
#     time_end="2025-04-06 23:59:59",
# )

# # safety only
# safe = docked_wrapper.compute_safety(
#     ctx,
#     time_start="2025-04-06 00:00:00",
#     time_end="2025-04-06 23:59:59",
# )

# # usage only
# usage = docked_wrapper.compute_usage(
#     ctx,
#     trip_csv=r"D:\Research Fellowship\NYC Trend Visual Docs\202504-citibike-tripdata",
#     time_start="2025-04-06 00:00:00",
#     time_end="2025-04-06 23:59:59",
# )

# # idle time only
# idle = docked_wrapper.compute_idle_time(
#     ctx,
#     trip_csv=r"D:\Research Fellowship\NYC Trend Visual Docs\202504-citibike-tripdata",
#     time_start="2025-04-06 00:00:00",
#     time_end="2025-04-06 23:59:59",
# )

# ------------------------------------------------------------------
# print whichever result you care about
# ------------------------------------------------------------------
print(results)