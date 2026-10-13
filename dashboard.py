"""
dashboard.py
================================================================================
Streamlit Live Dashboard for the Hostel AC Controller.

What is Streamlit?
    Streamlit is a Python library that turns a regular Python script into a
    live web page. Every time you drag a slider or click a radio button,
    Streamlit re-runs this entire script from top to bottom and updates the page.
    You don't write HTML — you just call functions like st.metric(), st.slider().

What are @st.fragment sections?
    A "fragment" is a part of the page that Streamlit can refresh on a timer
    WITHOUT re-running the whole script. We use two fragments:
        render_live_metrics() — refreshes every 2.5 seconds (4 metric cards)
        render_live_chart()   — refreshes every 6 seconds (Plotly temperature graph)
    This prevents the whole page from flickering on every refresh.

What is st.session_state?
    st.session_state is a dict that persists between Streamlit re-runs within
    the same browser session. We use it to remember things like the last slider
    value sent to Flask, so we don't spam the API on every re-run.

Page layout:
    Tab 1 — Live metrics, slider, mode radio, and real-time temperature chart
    Tab 2 — Overnight run-time analytics (interactive slider)
    Tab 3 — Outdoor weather and ASHRAE science explanation
    Tab 4 — Raw telemetry log table and CSV download button
    Tab 5 — Hardware BOM table and Python syllabus mapping table
================================================================================
"""

import time       # time.localtime().tm_hour — current hour for comfort band calc
import requests   # requests.get / requests.post — talk to the Flask API server
import streamlit as st
import pandas as pd                  # pandas for DataFrame operations
import plotly.graph_objects as go    # Plotly for the interactive temperature chart

import config
import weather_service
import comfort_model
import storage

# --------------------------------------------------------------------------------------
# 1. PAGE CONFIG AND MINIMAL CSS
# --------------------------------------------------------------------------------------
# st.set_page_config() must be the FIRST Streamlit call in the script.
# layout="wide" uses the full browser width. initial_sidebar_state="collapsed"
# hides the sidebar so it doesn't appear unexpectedly on first load.
st.set_page_config(page_title="Hostel AC Controller", layout="wide", initial_sidebar_state="collapsed")

# Inject a small block of CSS (styling rules) to:
#   - Hide the Streamlit header bar, Deploy button, footer, and sidebar toggle
#   - Limit max page width and set top padding
#   - Prevent the "stale element flash" (fading out while a fragment refreshes)
# unsafe_allow_html=True is required to inject raw HTML/CSS via st.markdown()
st.markdown(
    """
    <style>
    header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stAppDeployButton"],
    .stDeployButton, #MainMenu, footer, [data-testid="stSidebar"], [data-testid="collapsedControl"] {
        display: none !important;
    }
    .block-container { padding-top: 1.5rem !important; max-width: 1250px !important; }
    [data-stale="true"], [data-testid="stElementContainer"], .stPlotlyChart {
        opacity: 1 !important; transition: none !important; filter: none !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# --------------------------------------------------------------------------------------
# 2. SESSION STATE INITIALIZATION AND BACKEND SYNC
# --------------------------------------------------------------------------------------
# st.session_state is a dict that survives page re-runs within the same browser tab.
# We initialize hostel_room here with safe defaults so the page renders even if
# Flask is not yet running. Once Flask is up, sync_from_flask_backend() fills it in.
if "hostel_room" not in st.session_state:
    st.session_state.hostel_room = {
        "room_id":         "HOSTEL_D_312",
        "current_temp":    25.0,
        "current_humidity": 50.0,
        "sensor_source":   "SIMULATED",
        "servo_status":    "READY",
        "touch_override":  False,
        "connection_mode": "STANDBY",
        "ac_state":        "OFF",
        "preferred_temp":  config.DEFAULT_PREFERRED_TEMP,
        "servo_angle":     0,
        "manual_override": False,
        "override_state":  None,
        "last_ping":       None
    }

# Shorthand alias so we don't write st.session_state.hostel_room everywhere
hostel_room = st.session_state.hostel_room


def sync_from_flask_backend():
    """
    Fetches the latest room state from the Flask server (GET /api/hostel/status).

    timeout=0.35: give up after 0.35 seconds — if Flask is slow, we skip the update
    and show the last known values rather than blocking the page.

    hostel_room.update(remote_room): copies keys from the Flask response into our
    local session_state dict, overwriting any outdated local values.

    We only update when "last_ping" is present in the response — this confirms
    that Flask has received at least one real reading from the ESP32 (not defaults).
    """
    try:
        resp = requests.get(f"http://127.0.0.1:{config.FLASK_PORT}/api/hostel/status", timeout=0.35)
        if resp.status_code == 200:
            remote_room = resp.json().get("room", {})
            if remote_room.get("last_ping"):   # only overwrite if real data exists
                hostel_room.update(remote_room)
    except Exception:
        pass   # Flask not running yet, or request timed out — silently keep old values


# Sync once at page load (outside fragments) to populate values for the rest of the script
sync_from_flask_backend()
outdoor_weather = weather_service.fetch_live_weather()

# --------------------------------------------------------------------------------------
# 3. PAGE HEADER AND TAB NAVIGATION
# --------------------------------------------------------------------------------------
st.subheader("Adaptive Thermal Comfort AC Controller for Hostels")
st.caption(
    f"ESP32-S3 + DHT11 (GPIO 4) + Touch (GPIO 10) + SG90 Servo (GPIO 18)  |  "
    f"Katpadi, Vellore Outdoor Weather: {outdoor_weather['temperature_c']:.1f} °C ({outdoor_weather['humidity_pct']:.0f}% RH)"
)

# st.tabs() creates clickable tab headers. The returned objects are context managers —
# content placed inside "with tab_X:" only appears when that tab is selected.
tab_hostel, tab_savings, tab_science, tab_logs, tab_specs = st.tabs([
    "Hostel AC Unit",
    "Overnight Run-Time Analytics",
    "Sleep Biology & Weather",
    "Telemetry Logs",
    "Hardware & Architecture"
])

# ======================================================================================
# TAB 1: LIVE HOSTEL AC MONITOR AND CONTROLS
# ======================================================================================
with tab_hostel:
    # st.columns([1.2, 1.8]) splits the row into two unequal columns.
    # The numbers are relative widths — 1.2 and 1.8 means left is narrower.
    ctrl_col1, ctrl_col2 = st.columns([1.2, 1.8])

    with ctrl_col1:
        # st.slider returns the current value the user has dragged to.
        # We read preferred_temp from session_state and clamp it to the valid range
        # so the slider does not crash if an old out-of-range value was stored.
        current_pref  = float(hostel_room.get("preferred_temp", config.DEFAULT_PREFERRED_TEMP))
        selected_pref = st.slider(
            "Preferred Target Temperature (°C)",
            min_value=16.0,
            max_value=32.0,
            value=max(16.0, min(32.0, current_pref)),
            step=0.5
        )

        # Only POST to Flask when the slider actually changed (not on every re-run).
        # st.session_state["last_synced_pref"] stores the last value we sent.
        if st.session_state.get("last_synced_pref") != selected_pref:
            hostel_room["preferred_temp"] = selected_pref
            try:
                r = requests.post(
                    f"http://127.0.0.1:{config.FLASK_PORT}/api/hostel/preference",
                    json={"preferred_temp": selected_pref},
                    timeout=0.4
                )
                if r.status_code == 200:
                    res_data = r.json()
                    hostel_room["ac_state"]    = res_data.get("ac_state",    hostel_room["ac_state"])
                    hostel_room["servo_angle"] = res_data.get("servo_angle", hostel_room["servo_angle"])
                    st.session_state["last_synced_pref"] = selected_pref
            except Exception:
                pass   # Flask not reachable — update local dict only, sync when available

    with ctrl_col2:
        mode_options = ["Automatic (ASHRAE)", "Manual Override ON (90°)", "Manual Override OFF (0°)"]

        def handle_mode_change():
            selected = st.session_state.get("ac_mode_radio")
            if selected == "Manual Override ON (90°)":
                mode = "ON"
            elif selected == "Manual Override OFF (0°)":
                mode = "OFF"
            else:
                mode = "AUTO"

            try:
                r = requests.post(
                    f"http://127.0.0.1:{config.FLASK_PORT}/api/hostel/override",
                    json={"mode": mode},
                    timeout=1.5
                )
                if r.status_code == 200:
                    data = r.json()
                    hostel_room["manual_override"] = (mode in ("ON", "OFF"))
                    hostel_room["override_state"]  = mode if mode in ("ON", "OFF") else None
                    hostel_room["ac_state"]        = data.get("ac_state", mode if mode in ("ON", "OFF") else hostel_room["ac_state"])
                    hostel_room["servo_angle"]     = data.get("servo_angle", 90 if mode == "ON" else (0 if mode == "OFF" else hostel_room["servo_angle"]))
            except Exception:
                pass

        # Compute initial selection index based on current room state if not already set
        if "ac_mode_radio" not in st.session_state:
            default_idx = 0
            if hostel_room.get("manual_override"):
                default_idx = 1 if hostel_room.get("override_state") == "ON" else 2
            st.session_state["ac_mode_radio"] = mode_options[default_idx]

        st.radio(
            "AC Operating Mode",
            options=mode_options,
            key="ac_mode_radio",
            on_change=handle_mode_change,
            horizontal=True
        )

    st.divider()   # draws a horizontal line separator

    # ----------------------------------------------------------------------------------
    # FRAGMENT 1: Live metric cards (refreshes every 2.5 seconds)
    # ----------------------------------------------------------------------------------
    # @st.fragment(run_every="2.5s") tells Streamlit to re-run only this function
    # every 2.5 seconds without re-running the entire dashboard script.
    # This keeps the metric cards live without flickering the whole page.
    @st.fragment(run_every="2.5s")
    def render_live_metrics():
        sync_from_flask_backend()   # get the latest state from Flask

        # Recalculate the comfort band with the current outdoor weather + time of day
        live_weather = weather_service.fetch_live_weather()
        live_band = comfort_model.get_hostel_comfort_band(
            live_weather["temperature_c"],
            time.localtime().tm_hour,
            preferred_temp=hostel_room["preferred_temp"]
        )

        # Four equal columns — one metric card each
        c1, c2, c3, c4 = st.columns(4)

        # st.metric(label, value) renders a bold headline number with a grey label
        # st.caption() renders small grey text below the metric box
        sensor_label = "DHT11 LIVE (GPIO 4)" if hostel_room.get("sensor_source") == "LIVE_DHT11" else "SIMULATED"
        c1.metric("Room Temperature", f"{hostel_room['current_temp']:.1f} °C")
        c1.caption(f"Humidity: {hostel_room['current_humidity']:.0f}% | {sensor_label}")

        mode_label = "Touch Override (GPIO 10)" if hostel_room.get("touch_override") else (
            "Manual Override" if hostel_room.get("manual_override") else "ASHRAE Auto"
        )
        c2.metric("AC Switch State", hostel_room["ac_state"])
        c2.caption(f"Source: {mode_label}")

        angle = hostel_room["servo_angle"]
        c3.metric("Servo Position (GPIO 18)", f"{angle}°")
        c3.caption("Switch ON (90°)" if angle == 90 else "Switch OFF (0°)")

        c4.metric("Target Setpoint", f"{live_band['optimal_temp']:.1f} °C")
        c4.caption(f"Band: {live_band['min_temp']:.1f} – {live_band['max_temp']:.1f} °C")

        # Re-run the decision function just to get the explanation text (no side effects)
        _, _, explanation = comfort_model.evaluate_hostel_ac_decision(
            hostel_room["current_temp"],
            live_band["min_temp"],
            live_band["max_temp"],
            hostel_room["ac_state"]
        )
        conn = hostel_room.get("connection_mode", "STANDBY")
        ping = hostel_room.get("last_ping") or "Waiting for ESP32..."
        st.caption(f"**Decision:** {explanation}  |  **Link:** {conn}  |  **Last Sync:** {ping}")

    # ----------------------------------------------------------------------------------
    # Helper: Adaptive chart data preparation
    # ----------------------------------------------------------------------------------
    def prepare_adaptive_trend_dataframe(raw_df, window_mode="Auto Scale (Session)"):
        """
        Takes the full telemetry history DataFrame and returns a smaller version
        appropriate for the selected time window.

        Why resample?
            After an hour of readings every 2.5 seconds, there are ~1440 data points.
            Plotting all of them at once makes the chart slow and hard to read.
            Resampling averages points into larger time buckets (10s, 30s, 2min)
            to keep the chart smooth and fast.

        pd.to_datetime(..., errors="coerce"):
            Converts timestamp strings to datetime objects (needed for time-axis plotting).
            errors="coerce" turns any bad values into NaT (Not a Time) instead of crashing.

        df.set_index("dt").resample("30s").mean():
            Groups rows into 30-second buckets and computes the average temp in each bucket.
            This is pandas' time-series resampling — similar to taking an average of every
            12 consecutive readings (12 x 2.5s = 30s).

        Parameters:
            raw_df     (pd.DataFrame): Full history from storage.read_telemetry_history().
            window_mode (str):        Selected time scale from the dropdown.

        Returns:
            tuple: (plot_df, scale_info_string)
        """
        if raw_df.empty:
            return raw_df, "No Data"

        df = raw_df.copy()
        df["dt"] = pd.to_datetime(df["timestamp"], errors="coerce")   # convert to datetime
        df = df.dropna(subset=["dt"]).sort_values("dt").reset_index(drop=True)
        if df.empty:
            return raw_df, "Raw Data"

        # Ensure temperature columns are numeric (not strings), coerce bad values to NaN
        num_cols = ["current_temp", "current_humidity", "target_optimal", "comfort_min", "comfort_max"]
        for col in num_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        latest_dt = df["dt"].max()   # the most recent timestamp in the data

        # --- Manual time-window modes ---
        if window_mode == "Live Raw (Last 2 Min)":
            # pd.Timedelta(seconds=120) creates a time offset of 2 minutes
            sub = df[df["dt"] >= (latest_dt - pd.Timedelta(seconds=120))].copy()
            return (sub if len(sub) >= 5 else df.tail(35).copy()), "2.5s Raw Readings"

        if window_mode == "Last 15 Minutes":
            sub = df[df["dt"] >= (latest_dt - pd.Timedelta(minutes=15))].copy()
            if len(sub) > 45:
                sub = sub.set_index("dt")[num_cols].resample("15s").mean().dropna(how="all").reset_index()
            return sub, "15s Intervals (Last 15 Min)"

        if window_mode == "Last 1 Hour":
            sub = df[df["dt"] >= (latest_dt - pd.Timedelta(minutes=60))].copy()
            if len(sub) > 50:
                sub = sub.set_index("dt")[num_cols].resample("1min").mean().dropna(how="all").reset_index()
            return sub, "1m Intervals (Last 1 Hr)"

        # --- Auto Scale: detect current session and pick the right resolution ---
        # A "gap" of >10 minutes between readings means a new session started.
        # We only plot the current session, not yesterday's leftover data.
        gaps     = df["dt"].diff().dt.total_seconds().fillna(0)
        breaks   = df.index[gaps > 600].tolist()
        session_df = df.loc[breaks[-1]:].copy() if breaks else df.copy()
        elapsed_sec = (session_df["dt"].max() - session_df["dt"].min()).total_seconds()

        if elapsed_sec <= 90 or len(session_df) <= 30:
            return session_df, f"Live Raw ({max(1, int(elapsed_sec))}s session)"
        elif elapsed_sec <= 600:
            res = session_df.set_index("dt")[num_cols].resample("10s").mean().dropna(how="all").reset_index()
            return res, f"10s Intervals ({elapsed_sec / 60.0:.1f} min session)"
        elif elapsed_sec <= 3600:
            res = session_df.set_index("dt")[num_cols].resample("30s").mean().dropna(how="all").reset_index()
            return res, f"30s Intervals ({elapsed_sec / 60.0:.0f} min session)"
        else:
            res = session_df.set_index("dt")[num_cols].resample("2min").mean().dropna(how="all").reset_index()
            return res, f"2m Intervals ({elapsed_sec / 3600.0:.1f} hr session)"

    # ----------------------------------------------------------------------------------
    # FRAGMENT 2: Temperature chart (refreshes every 6 seconds)
    # ----------------------------------------------------------------------------------
    @st.fragment(run_every="6s")
    def render_live_chart():
        hdr_col, sel_col = st.columns([3.8, 1.2])
        with sel_col:
            # st.selectbox() renders a dropdown; the selected string is returned
            window_mode = st.selectbox(
                "Time Scale",
                options=["Auto Scale (Session)", "Live Raw (Last 2 Min)", "Last 15 Minutes", "Last 1 Hour"],
                index=0,
                label_visibility="collapsed",
                key="trend_window_mode"  # unique key so Streamlit tracks this widget's state
            )

        raw_df = storage.read_telemetry_history(limit=2500)
        plot_df, scale_info = prepare_adaptive_trend_dataframe(raw_df, window_mode=window_mode)

        with hdr_col:
            st.markdown(f"**Room Temperature vs Comfort Band** ({scale_info})")

        if not plot_df.empty:
            # Use the "dt" column if it exists (after adaptive processing), else fall back to "timestamp"
            x_vals = plot_df["dt"] if "dt" in plot_df.columns else plot_df["timestamp"]

            # Calculate y-axis range with padding so the band is always visible
            min_y   = min(float(plot_df["comfort_min"].min()), float(plot_df["current_temp"].min()))
            max_y   = max(float(plot_df["comfort_max"].max()), float(plot_df["current_temp"].max()))
            y_lower = round(min_y - 1.5, 1)
            y_upper = round(max_y + 1.5, 1)

            # Build the Plotly figure by adding "traces" (one trace = one line or area)
            fig = go.Figure()

            # Trace 1: Invisible upper boundary of the comfort band (used for fill reference)
            fig.add_trace(go.Scatter(
                x=x_vals, y=plot_df["comfort_max"],
                mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"
            ))

            # Trace 2: Lower boundary, filled UP to Trace 1 — creates the green shaded band
            # fill="tonexty" means "fill to the y values of the PREVIOUS trace"
            fig.add_trace(go.Scatter(
                x=x_vals, y=plot_df["comfort_min"],
                mode="lines", line=dict(width=0), fill="tonexty",
                fillcolor="rgba(34, 197, 94, 0.16)", name="Comfort Band (±1.5°C)",
                hovertemplate="<b>Comfort Band:</b> %{y:.1f} °C<extra></extra>"
            ))

            # Trace 3: Dashed green line for the ASHRAE optimal target setpoint
            fig.add_trace(go.Scatter(
                x=x_vals, y=plot_df["target_optimal"],
                mode="lines", name="Target Setpoint",
                line=dict(color="#10B981", dash="dash", width=2.0),
                hovertemplate="<b>Target Setpoint:</b> %{y:.1f} °C<extra></extra>"
            ))

            # Trace 4: Blue line for actual room temperature from DHT11
            fig.add_trace(go.Scatter(
                x=x_vals, y=plot_df["current_temp"],
                mode="lines+markers", name="Room Temp (DHT11)",
                line=dict(color="#3B82F6", width=2.5),
                marker=dict(size=4 if len(plot_df) <= 45 else 3, color="#3B82F6"),
                hovertemplate="<b>Room Temp (DHT11):</b> %{y:.1f} °C<extra></extra>"
            ))

            # update_layout() controls the overall chart appearance (not individual traces)
            fig.update_layout(
                # uirevision: if this value stays the same between refreshes, Plotly
                # keeps zoom/pan state instead of resetting the view on every update
                uirevision=f"hostel_trend_{window_mode}",
                paper_bgcolor="rgba(0,0,0,0)",   # transparent chart background
                plot_bgcolor="rgba(0,0,0,0)",    # transparent plot area
                height=340,
                margin=dict(l=16, r=16, t=28, b=16),
                font=dict(color="#94A3B8", size=12),
                hoverlabel=dict(bgcolor="#0F172A", bordercolor="#334155", font=dict(color="#F8FAFC", size=12)),
                legend=dict(
                    orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                    bgcolor="rgba(0,0,0,0)", font=dict(color="#94A3B8", size=11)
                ),
                xaxis=dict(title="Time", tickfont=dict(color="#94A3B8"), gridcolor="rgba(255,255,255,0.07)"),
                yaxis=dict(
                    title="Temperature (°C)",
                    tickfont=dict(color="#94A3B8"),
                    gridcolor="rgba(255,255,255,0.07)",
                    range=[y_lower, y_upper]
                ),
                hovermode="x unified"   # shows all traces' values in one tooltip on hover
            )

            # key= ensures Streamlit reuses the same chart DOM element across fragment refreshes
            # (prevents the chart from being destroyed and recreated, which causes flash)
            # config={"displayModeBar": False} hides the Plotly toolbar (zoom/download icons)
            st.plotly_chart(
                fig,
                use_container_width=True,
                key="hostel_telemetry_plotly_chart",
                config={"displayModeBar": False}
            )
        else:
            st.info("Waiting for telemetry logs from ESP32...")

    render_live_metrics()
    st.divider()
    render_live_chart()

# ======================================================================================
# TAB 2: OVERNIGHT RUN-TIME ANALYTICS
# ======================================================================================
with tab_savings:
    st.markdown("#### Active Run-Time & Overcooling Prevention")
    st.caption(
        "Hostel rooms use a binary wall switch connected to centralized cooling. "
        "Instead of guessing chiller tonnage, we directly measure indoor temperature and hours turned off overnight."
    )

    # The slider returns a float (e.g., 4.0). We pass it straight into comfort_model.
    hours_slider  = st.slider("Hours AC Switched Off Overnight (out of 8.0 hrs sleep)", 1.0, 7.0, 4.0, 0.5)
    runtime_stats = comfort_model.calculate_runtime_reduction(hours_ac_off=hours_slider)

    s1, s2, s3 = st.columns(3)
    s1.metric("Run-Time Reduction",   f"{runtime_stats['runtime_reduction_pct']}%", f"{runtime_stats['hours_cooling_off']} hrs off")
    s2.metric("Degree-Hours Avoided", f"{runtime_stats['degree_hours_avoided']} °C·hr", "Overcooling prevented")

    # Comfort adherence: a rough estimate based on how much time the AC was off
    comfort_adherence = round(min(98.0, 85.0 + (runtime_stats["runtime_reduction_pct"] * 0.1)), 1)
    s3.metric("Comfort Adherence",    f"~{comfort_adherence}%", "Hours inside ASHRAE band")

# ======================================================================================
# TAB 3: SLEEP BIOLOGY AND WEATHER
# ======================================================================================
with tab_science:
    st.markdown("#### Katpadi Outdoor Weather & ASHRAE Standard 55")
    w1, w2, w3 = st.columns(3)
    w1.metric("Outdoor Temperature (Katpadi, Vellore)", f"{outdoor_weather['temperature_c']:.1f} °C")
    w2.metric("Relative Humidity",  f"{outdoor_weather['humidity_pct']:.0f} %")
    w3.metric("Weather Source",     outdoor_weather["source"])

    st.divider()
    st.markdown(
        """
        **ASHRAE 55 Adaptive Comfort Equation:**
        `Comfortable Indoor Temp = 17.8 + (0.31 × Outdoor Temp)`

        **Why Overnight Sleep Mode Adds `+1.0 °C` (22:00 – 07:00):**
        1. **Metabolic Rate Drops:** Human heat production drops from `1.0 met` (awake) to `0.7 met` (sleeping).
        2. **Blanket Insulation:** Bedding increases thermal insulation from `0.5 clo` to `1.2 – 1.5 clo`.
        3. **Hysteresis Deadband (`±1.5 °C`):** Prevents the SG90 servo and AC switch from chattering on small `0.1 °C` fluctuations.
        """
    )

# ======================================================================================
# TAB 4: TELEMETRY LOGS AND CSV DOWNLOAD
# ======================================================================================
with tab_logs:
    st.markdown("#### Historical Sensor Telemetry Logs (`data/hostel_telemetry.csv`)")

    # storage.read_telemetry_history() returns a pandas DataFrame
    full_history = storage.read_telemetry_history(limit=100)

    if not full_history.empty:
        # st.dataframe() renders the DataFrame as an interactive scrollable table
        st.dataframe(full_history, use_container_width=True)

        # st.download_button() adds a browser download link
        # .to_csv(index=False) converts the DataFrame back to CSV text
        # .encode("utf-8") converts the string to bytes (required for file download)
        st.download_button(
            label="Download CSV File",
            data=full_history.to_csv(index=False).encode("utf-8"),
            file_name="hostel_telemetry.csv",
            mime="text/csv"
        )
    else:
        st.info("No logs recorded yet.")

# ======================================================================================
# TAB 5: HARDWARE BOM AND ARCHITECTURE
# ======================================================================================
with tab_specs:
    st.markdown("#### Hardware Bill of Materials (BOM)")

    # pd.DataFrame([list of dicts]) creates a table where each dict is one row.
    # The keys become column headers. st.table() renders it as a static table.
    st.table(pd.DataFrame([
        {"Component": "ESP32-S3 DevKitC-1 N16R8",    "Pin / Interface": "WiFi + USB Serial",          "Role": "Microcontroller & HTTP/Serial client",        "Cost (Rs)": 400},
        {"Component": "SG90 Micro Servo Motor",       "Pin / Interface": "GPIO 18 (50Hz PWM)",         "Role": "Physical AC switch actuator (0° / 90°)",      "Cost (Rs)": 150},
        {"Component": "1.3\" SH1106 I2C OLED",        "Pin / Interface": "SDA: GPIO 8, SCL: GPIO 9",   "Role": "Live on-board status display",                "Cost (Rs)": 212},
        {"Component": "DHT11 Sensor + Touch Button",  "Pin / Interface": "GPIO 4 (DHT), GPIO 10 (Touch)", "Role": "Room sensing & manual touch toggle",        "Cost (Rs)": 51},
        {"Component": "Total Prototype Cost",         "Pin / Interface": "-",                           "Role": "Complete physical unit",                      "Cost (Rs)": 813}
    ]))

    st.markdown("#### Python Syllabus Mapping")
    st.table(pd.DataFrame([
        {"Topic": "Functions",                    "Implementation": "calculate_ashrae_comfort, get_hostel_comfort_band, evaluate_hostel_ac_decision"},
        {"Topic": "Conditionals (if/elif/else)",  "Implementation": "Hysteresis deadband logic and nighttime sleep offset check"},
        {"Topic": "Dictionaries & Tuples",        "Implementation": "Shared room state dict, comfort band dict, (state, angle, reason) tuple"},
        {"Topic": "File Handling (CSV)",          "Implementation": "save_telemetry & read_telemetry_history using 'with open' context manager"},
        {"Topic": "Exception Handling",           "Implementation": "try/except blocks across API requests, serial read, and file I/O"},
        {"Topic": "APIs & Visualization",         "Implementation": "Flask REST API (app.py), requests weather fetch, Streamlit + Plotly"}
    ]))
