from mobility_package import dockless_wrapper

# ------------------------------------------------------------------
# STEP 1 — always required first, regardless of which metric you want
# ------------------------------------------------------------------
ctx = dockless_wrapper.load_dockless_context(
    system_key="SF_LIME_DOCKLESS",  # SF_LIME_DOCKLESS / SF_SPIN_DOCKLESS / SEATTLE_BIRD_DOCKLESS / SEATTLE_LIME_DOCKLESS
    freebike_status_txt=r"D:\Research Fellowship\Summer Research Stuff\Collected Data\Week 1\09-June\san_fran_lime_dkless_freebike_status_6_9.txt",
    output_dir=r"SF_LIME_FULL_RUN",
    time_start="2025-06-09 06:00:00",
    time_end="2025-06-09 12:00:00",
)

# ------------------------------------------------------------------
# OPTION A — all metrics at once
# ------------------------------------------------------------------
results = dockless_wrapper.compute_all(ctx)

# ------------------------------------------------------------------
# OPTION B — single metrics, pick whichever one(s) you need
# ------------------------------------------------------------------

# # availability only
# avail = dockless_wrapper.compute_availability(ctx)

# # usage only
# usage = dockless_wrapper.compute_usage(ctx)

# # capacity only
# cap = dockless_wrapper.compute_capacity(ctx)

# # idle time only
# idle = dockless_wrapper.compute_idle_time(ctx)

# # safety only
# safe = dockless_wrapper.compute_safety(ctx)

print(results)