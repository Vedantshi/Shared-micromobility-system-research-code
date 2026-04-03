# ============================================================
# capacity_map_visual — decile choropleth maps of capacity
# ============================================================
from mobility_package import capacity_map_visual

saved = capacity_map_visual.plot_capacity(
    # Normalised capacity CSV (output of docked_wrapper.compute_capacity)
    capacity_csv = r"D:\Research Fellowship\NYC_Docked_Output_v2\capacity_tract_with_vehicle_and_docks_norm.csv",

    # Census-tract shapefile for New York State
    tract_shp = r"D:\Research Fellowship\Summer Research Stuff\Clean_Utilities\Capacity\NYC\tl_2024_36_tract.shp",

    # Folder where PNGs are saved (created automatically)
    output_dir = r"D:\Research Fellowship\NYC_Docked_Output_v2\CAPACITY_MAPS_OUT",

    # Primary normalised capacity column — used as the gate and in the filename
    capacity_norm_col = "total_capacity_norm",

    # Column in the CSV that holds station count per tract
    # Tracts with fewer than min_stations are excluded from all maps
    station_count_col = "num_station",
    min_stations      = 1,

    # Also exclude tracts where capacity_norm_col == 0
    drop_zeros = True,

    # Columns to map — defaults to all recognised capacity columns
    # found in the file. Override to plot only specific ones:
    # value_cols = ["total_capacity_norm", "vehicle_capacity_norm"]
)

# saved is a dict: { "total_capacity_norm": Path(...), "vehicle_capacity_norm": Path(...), ... }
print(saved)
