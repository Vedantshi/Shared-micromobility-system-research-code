"""
run_nyc_scatter.py
==================
Example script for running the scatter-plot supply-demand classification
on the NYC docked-station tract outputs.

All column names and aggregation defaults already match the NYC files so
you normally only need to change the three CSV paths and the output_dir.

Threshold method recap
----------------------
threshold_method="percent" with use_symmetric_percentiles=True

    availability_low_pct=30   → tracts below the 30th percentile = low supply
    usage_high_pct=70         → tracts above the 70th percentile = high demand

    The other two cutoffs are derived automatically:
        availability_high_pct = 100 - 30 = 70  (above 70th pct = high supply)
        usage_low_pct         = 100 - 70 = 30  (below 30th pct = low demand)

Four output categories
----------------------
    Undersupply             (red)    low supply  + high demand
    Oversupply              (orange) high supply + low demand
    High demand+High supply (green)  both high
    Balanced / Other        (blue)   everything else
"""

from mobility_package import scatter_visual

# -----------------------------------------------------------------------
# Input CSVs — adjust paths to match your machine
# -----------------------------------------------------------------------
AVAILABILITY_CSV = r"D:\Research Fellowship\NYC_Docked_Output_v2\availability__norm__tract.csv"
USAGE_CSV        = r"D:\Research Fellowship\NYC_Docked_Output_v2\usage_norm_hourly_tract.csv"
IDLE_CSV         = r"D:\Research Fellowship\NYC_Docked_Output_v2\idle_time_norm_tract.csv"

# -----------------------------------------------------------------------
# Output folder — created automatically if it does not exist
# -----------------------------------------------------------------------
OUTPUT_DIR = "UTILITY_INTERACTIONS_OUT"

# -----------------------------------------------------------------------
# Run the analysis
# -----------------------------------------------------------------------
master, class_df, fig = scatter_visual.plot_scatter(
    availability_csv = AVAILABILITY_CSV,
    usage_csv        = USAGE_CSV,
    idle_csv         = IDLE_CSV,
    output_dir       = OUTPUT_DIR,

    # Threshold settings
    threshold_method          = "percent",
    use_symmetric_percentiles = True,
    availability_low_pct      = 30,
    usage_high_pct            = 70,

    # Print numeric threshold values to the console for verification
    show_threshold_debug = True,
)

# Show the figure interactively when running from a notebook or IDE
import matplotlib.pyplot as plt
plt.show()