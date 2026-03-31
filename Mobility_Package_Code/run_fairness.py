from mobility_package import fairness_calculation

out = fairness_calculation.run_paper_style_fairness(
    city_key="NYC_DOCKED",
    save_directory=r"FAIRNESS_RESULTS",

    capacity_csv=r"D:\Research Fellowship\NYC_Docked_Output_v2\capacity_tract_with_vehicle_and_docks_norm.csv",
    availability_csv=r"D:\Research Fellowship\NYC_Docked_Output_v2\availability__norm__tract.csv",
    safety_csv=r"D:\Research Fellowship\NYC_Docked_Output_v2\safety_bike_lane_norm_tract.csv",
    accessibility_csv=r"D:\Research Fellowship\accessibiliy_norm_tract_nyc.csv",
    idle_time_csv=r"D:\Research Fellowship\NYC_Docked_Output_v2\idle_time_norm_tract.csv",
    usage_csv=False,

    filter_to_capacity_service_area=True,
)

print(out["fairness_table"])