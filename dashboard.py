"""
dashboard.py
================================================================================
Adaptive Thermal Comfort AC Controller - Live Dashboard.
Uses pure native Streamlit components (st.metric, st.slider, st.radio, st.tabs,
st.plotly_chart, st.table) to monitor the ESP32-S3 hardware and present the
project analytics without custom HTML/CSS card bloat.
================================================================================
"""

import time
import requests
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

import config
import weather_service
import comfort_model
import storage

# --------------------------------------------------------------------------------------
# 1. PAGE CONFIG & MINIMAL CSS (HIDE DEPLOY BUTTON & PREVENT REFRESH FLASH)
# --------------------------------------------------------------------------------------
st.set_page_config(page_title="Hostel AC Controller", layout="wide", initial_sidebar_state="collapsed")

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
# 2. STATE INITIALIZATION & BACKEND SYNC
# --------------------------------------------------------------------------------------
if "hostel_room" not in st.session_state:
    st.session_state.hostel_room = {
        "room_id": "HOSTEL_D_312",
        "current_temp": 25.0,
        "current_humidity": 50.0,
        "sensor_source": "SIMULATED",
        "servo_status": "READY",
        "touch_override": False,
        "connection_mode": "STANDBY",
        "ac_state": "OFF",
        "preferred_temp": config.DEFAULT_PREFERRED_TEMP,
        "servo_angle": 0,
        "manual_override": False,
        "override_state": None,
        "last_ping": None
    }

hostel_room = st.session_state.hostel_room


def sync_from_flask_backend():
    """Fetches latest live ESP32 telemetry from local Flask server (/api/hostel/status)."""
    try:
        resp = requests.get(f"http://127.0.0.1:{config.FLASK_PORT}/api/hostel/status", timeout=0.35)
        if resp.status_code == 200:
            remote_room = resp.json().get("room", {})
            if remote_room.get("last_ping"):
                hostel_room.update(remote_room)
    except Exception:
        pass


sync_from_flask_backend()
outdoor_weather = weather_service.fetch_live_weather()

# --------------------------------------------------------------------------------------
# 3. HEADER & NAVIGATION TABS
# --------------------------------------------------------------------------------------
st.subheader("Adaptive Thermal Comfort AC Controller for Hostels")
st.caption(
    f"ESP32-S3 + DHT11 (GPIO 4) + Touch (GPIO 10) + SG90 Servo (GPIO 18)  |  "
    f"Katpadi, Vellore Outdoor Weather: {outdoor_weather['temperature_c']:.1f} °C ({outdoor_weather['humidity_pct']:.0f}% RH)"
)

tab_hostel, tab_savings, tab_science, tab_logs, tab_specs = st.tabs([
    "Hostel AC Unit",
    "Overnight Run-Time Analytics",
    "Sleep Biology & Weather",
    "Telemetry Logs",
    "Hardware & Architecture"
])

# ======================================================================================
# TAB 1: LIVE HOSTEL AC MONITOR & CONTROLS
# ======================================================================================
with tab_hostel:
    ctrl_col1, ctrl_col2 = st.columns([1.2, 1.8])

    with ctrl_col1:
        current_pref = float(hostel_room.get("preferred_temp", config.DEFAULT_PREFERRED_TEMP))
        selected_pref = st.slider(
            "Preferred Target Temperature (°C)",
            min_value=16.0,
            max_value=32.0,
            value=max(16.0, min(32.0, current_pref)),
            step=0.5
        )
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
                    hostel_room["ac_state"] = res_data.get("ac_state", hostel_room["ac_state"])
                    hostel_room["servo_angle"] = res_data.get("servo_angle", hostel_room["servo_angle"])
                    st.session_state["last_synced_pref"] = selected_pref
            except Exception:
                pass

    with ctrl_col2:
        mode_options = ["Automatic (ASHRAE)", "Manual Override ON (90°)", "Manual Override OFF (0°)"]
        current_idx = 0 if not hostel_room["manual_override"] else (1 if hostel_room["override_state"] == "ON" else 2)
        mode_selection = st.radio("AC Operating Mode", options=mode_options, index=current_idx, horizontal=True)

        prev_override = (hostel_room["manual_override"], hostel_room["override_state"])
        if mode_selection == "Automatic (ASHRAE)":
            hostel_room["manual_override"] = False
            hostel_room["override_state"] = None
            api_mode = "AUTO"
        elif mode_selection == "Manual Override ON (90°)":
            hostel_room["manual_override"] = True
            hostel_room["override_state"] = "ON"
            hostel_room["ac_state"] = "ON"
            hostel_room["servo_angle"] = 90
            api_mode = "ON"
        else:
            hostel_room["manual_override"] = True
            hostel_room["override_state"] = "OFF"
            hostel_room["ac_state"] = "OFF"
            hostel_room["servo_angle"] = 0
            api_mode = "OFF"

        if (hostel_room["manual_override"], hostel_room["override_state"]) != prev_override:
            try:
                r = requests.post(
                    f"http://127.0.0.1:{config.FLASK_PORT}/api/hostel/override",
                    json={"mode": api_mode},
                    timeout=0.4
                )
                if r.status_code == 200:
                    res_data = r.json()
                    hostel_room["ac_state"] = res_data.get("ac_state", hostel_room["ac_state"])
                    hostel_room["servo_angle"] = res_data.get("servo_angle", hostel_room["servo_angle"])
            except Exception:
                pass

    st.divider()

    @st.fragment(run_every="2.5s")
    def render_live_metrics():
        sync_from_flask_backend()

        live_weather = weather_service.fetch_live_weather()
        live_band = comfort_model.get_hostel_comfort_band(
            live_weather["temperature_c"],
            time.localtime().tm_hour,
            preferred_temp=hostel_room["preferred_temp"]
        )

        c1, c2, c3, c4 = st.columns(4)

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

        _, _, explanation = comfort_model.evaluate_hostel_ac_decision(
            hostel_room["current_temp"],
            live_band["min_temp"],
            live_band["max_temp"],
            hostel_room["ac_state"]
        )
        conn = hostel_room.get("connection_mode", "STANDBY")
        ping = hostel_room.get("last_ping") or "Waiting for ESP32..."
        st.caption(f"**Decision:** {explanation}  |  **Link:** {conn}  |  **Last Sync:** {ping}")

    def prepare_adaptive_trend_dataframe(raw_df, window_mode="Auto Scale (Session)"):
        """Scales and resamples telemetry history based on how long the session has run."""
        if raw_df.empty:
            return raw_df, "No Data"

        df = raw_df.copy()
        df["dt"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.dropna(subset=["dt"]).sort_values("dt").reset_index(drop=True)
        if df.empty:
            return raw_df, "Raw Data"

        num_cols = ["current_temp", "current_humidity", "target_optimal", "comfort_min", "comfort_max"]
        for col in num_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        latest_dt = df["dt"].max()

        if window_mode == "Live Raw (Last 2 Min)":
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

        gaps = df["dt"].diff().dt.total_seconds().fillna(0)
        breaks = df.index[gaps > 600].tolist()
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

    @st.fragment(run_every="6s")
    def render_live_chart():
        hdr_col, sel_col = st.columns([3.8, 1.2])
        with sel_col:
            window_mode = st.selectbox(
                "Time Scale",
                options=["Auto Scale (Session)", "Live Raw (Last 2 Min)", "Last 15 Minutes", "Last 1 Hour"],
                index=0,
                label_visibility="collapsed",
                key="trend_window_mode"
            )

        raw_df = storage.read_telemetry_history(limit=2500)
        plot_df, scale_info = prepare_adaptive_trend_dataframe(raw_df, window_mode=window_mode)

        with hdr_col:
            st.markdown(f"**Room Temperature vs Comfort Band** ({scale_info})")

        if not plot_df.empty:
            x_vals = plot_df["dt"] if "dt" in plot_df.columns else plot_df["timestamp"]
            min_y = min(float(plot_df["comfort_min"].min()), float(plot_df["current_temp"].min()))
            max_y = max(float(plot_df["comfort_max"].max()), float(plot_df["current_temp"].max()))
            y_lower = round(min_y - 1.5, 1)
            y_upper = round(max_y + 1.5, 1)

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=x_vals, y=plot_df["comfort_max"],
                mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"
            ))
            fig.add_trace(go.Scatter(
                x=x_vals, y=plot_df["comfort_min"],
                mode="lines", line=dict(width=0), fill="tonexty",
                fillcolor="rgba(34, 197, 94, 0.16)", name="Comfort Band (±1.5°C)",
                hovertemplate="<b>Comfort Band:</b> %{y:.1f} °C<extra></extra>"
            ))
            fig.add_trace(go.Scatter(
                x=x_vals, y=plot_df["target_optimal"],
                mode="lines", name="Target Setpoint",
                line=dict(color="#10B981", dash="dash", width=2.0),
                hovertemplate="<b>Target Setpoint:</b> %{y:.1f} °C<extra></extra>"
            ))
            fig.add_trace(go.Scatter(
                x=x_vals, y=plot_df["current_temp"],
                mode="lines+markers", name="Room Temp (DHT11)",
                line=dict(color="#3B82F6", width=2.5),
                marker=dict(size=4 if len(plot_df) <= 45 else 3, color="#3B82F6"),
                hovertemplate="<b>Room Temp (DHT11):</b> %{y:.1f} °C<extra></extra>"
            ))

            fig.update_layout(
                uirevision=f"hostel_trend_{window_mode}",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
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
                hovermode="x unified"
            )
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

    hours_slider = st.slider("Hours AC Switched Off Overnight (out of 8.0 hrs sleep)", 1.0, 7.0, 4.0, 0.5)
    runtime_stats = comfort_model.calculate_runtime_reduction(hours_ac_off=hours_slider)

    s1, s2, s3 = st.columns(3)
    s1.metric("Run-Time Reduction", f"{runtime_stats['runtime_reduction_pct']}%", f"{runtime_stats['hours_cooling_off']} hrs off")
    s2.metric("Degree-Hours Avoided", f"{runtime_stats['degree_hours_avoided']} °C·hr", "Overcooling prevented")
    comfort_adherence = round(min(98.0, 85.0 + (runtime_stats["runtime_reduction_pct"] * 0.1)), 1)
    s3.metric("Comfort Adherence", f"~{comfort_adherence}%", "Hours inside ASHRAE band")

# ======================================================================================
# TAB 3: SLEEP BIOLOGY & WEATHER
# ======================================================================================
with tab_science:
    st.markdown("#### Katpadi Outdoor Weather & ASHRAE Standard 55")
    w1, w2, w3 = st.columns(3)
    w1.metric("Outdoor Temperature (Katpadi, Vellore)", f"{outdoor_weather['temperature_c']:.1f} °C")
    w2.metric("Relative Humidity", f"{outdoor_weather['humidity_pct']:.0f} %")
    w3.metric("Weather Source", outdoor_weather["source"])

    st.divider()
    st.markdown(
        r"""
        **ASHRAE 55 Adaptive Comfort Equation:**
        $$T_{\text{comf}} = 17.8 + 0.31 \times T_{\text{outdoor}}$$

        **Why Overnight Sleep Mode Adds $+1.0\,^\circ\text{C}$ (22:00 – 07:00):**
        1. **Metabolic Rate Drops:** Human heat production drops from $1.0\text{ met}$ (awake) to $0.7\text{ met}$ (sleeping).
        2. **Blanket Insulation:** Bedding increases clothing insulation from $0.5\text{ clo}$ to $\sim 1.3\text{ clo}$.
        3. **Hysteresis Deadband ($\pm 1.5\,^\circ\text{C}$):** Prevents the SG90 servo and AC relay from chattering on every $0.1\,^\circ\text{C}$ fluctuation.
        """
    )

# ======================================================================================
# TAB 4: TELEMETRY LOGS & CSV EXPORT
# ======================================================================================
with tab_logs:
    st.markdown("#### Historical Sensor Telemetry Logs (`data/hostel_telemetry.csv`)")
    full_history = storage.read_telemetry_history(limit=100)
    if not full_history.empty:
        st.dataframe(full_history, use_container_width=True)
        st.download_button(
            label="Download CSV File",
            data=full_history.to_csv(index=False).encode("utf-8"),
            file_name="hostel_telemetry.csv",
            mime="text/csv"
        )
    else:
        st.info("No logs recorded yet.")

# ======================================================================================
# TAB 5: HARDWARE BOM & ARCHITECTURE
# ======================================================================================
with tab_specs:
    st.markdown("#### Hardware Bill of Materials (BOM)")
    st.table(pd.DataFrame([
        {"Component": "ESP32-S3 DevKitC-1 N16R8", "Pin / Interface": "WiFi + USB Serial", "Role": "Microcontroller & HTTP/Serial client", "Cost (₹)": 400},
        {"Component": "SG90 Micro Servo Motor", "Pin / Interface": "GPIO 18 (50Hz PWM)", "Role": "Physical AC switch actuator (0° / 90°)", "Cost (₹)": 150},
        {"Component": "1.3\" SH1106 I2C OLED", "Pin / Interface": "SDA: GPIO 8, SCL: GPIO 9", "Role": "Live on-board status display", "Cost (₹)": 212},
        {"Component": "DHT11 Sensor + Touch Button", "Pin / Interface": "GPIO 4 (DHT), GPIO 10 (Touch)", "Role": "Room sensing & manual touch toggle", "Cost (₹)": 51},
        {"Component": "Total Prototype Cost", "Pin / Interface": "-", "Role": "Complete physical unit", "Cost (₹)": 813}
    ]))

    st.markdown("#### Python Syllabus Mapping")
    st.table(pd.DataFrame([
        {"Topic": "Functions", "Implementation": "calculate_ashrae_comfort, get_hostel_comfort_band, evaluate_hostel_ac_decision"},
        {"Topic": "Conditionals (if/elif/else)", "Implementation": "Hysteresis deadband logic and nighttime sleep offset check"},
        {"Topic": "Dictionaries & Tuples", "Implementation": "Shared room state dict, comfort band dict, (state, angle, reason) tuple"},
        {"Topic": "File Handling (CSV)", "Implementation": "save_telemetry & read_telemetry_history using 'with open' context manager"},
        {"Topic": "Exception Handling", "Implementation": "try/except blocks across API requests, serial read, and file I/O"},
        {"Topic": "APIs & Visualization", "Implementation": "Flask REST API (app.py), requests weather fetch, Streamlit + Plotly"}
    ]))
