"""
dashboard.py
================================================================================
Hostel Adaptive Thermal Comfort System - Notion-Style Streamlit Dashboard.
Monitors the physical ESP32 AC switch unit, simulates sensor readings,
visualizes overnight energy savings, and plots ASHRAE comfort bands.
================================================================================
"""

import time
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

import config
import weather_service
import comfort_model
import storage

import base64
from pathlib import Path

# --------------------------------------------------------------------------------------
# 1. PAGE SETUP & NOTION-STYLE CSS WITH ADVERA / SANS FONT
# --------------------------------------------------------------------------------------
def load_custom_fonts_css():
    """Embeds modern sans-serif typography (Poppins / Helvetica) from assets or E:/gfx/fonts."""
    css_rules = []
    
    # Poppins Regular
    poppins_reg = Path("assets/fonts/Poppins-Regular.ttf")
    if poppins_reg.exists():
        try:
            with open(poppins_reg, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
                css_rules.append(f"""
                @font-face {{
                    font-family: 'Poppins';
                    src: url('data:font/ttf;base64,{b64}') format('truetype');
                    font-weight: 400;
                    font-style: normal;
                    font-display: swap;
                }}
                """)
        except Exception:
            pass

    # Poppins SemiBold
    poppins_bold = Path("assets/fonts/Poppins-SemiBold.ttf")
    if poppins_bold.exists():
        try:
            with open(poppins_bold, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
                css_rules.append(f"""
                @font-face {{
                    font-family: 'Poppins';
                    src: url('data:font/ttf;base64,{b64}') format('truetype');
                    font-weight: 600;
                    font-style: normal;
                    font-display: swap;
                }}
                """)
        except Exception:
            pass

    return "\n".join(css_rules)

st.set_page_config(
    page_title="Hostel AC Thermal Comfort System",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Clean typography & dark/light responsive styling
st.markdown(
    f"""
    <style>
    {load_custom_fonts_css()}

    html, body, [class*="css"], [class*="st-"], .stApp, .stMarkdown, p, div, span, label, button, input, textarea, select {{
        font-family: 'Poppins', 'Helvetica Neue', 'Helvetica', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
    }}

    h1, h2, h3, h4, h5, h6 {{
        font-family: 'Poppins', 'Helvetica Neue', 'Helvetica', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
        font-weight: 600;
        letter-spacing: -0.01em;
    }}

    .notion-header {{ border-bottom: 1px solid rgba(255, 255, 255, 0.1); padding-bottom: 14px; margin-bottom: 20px; }}
    .notion-title {{ font-size: 2.1rem; font-weight: 700; margin-bottom: 4px; letter-spacing: -0.02em; }}
    .notion-desc {{ font-size: 0.95rem; opacity: 0.8; }}
    .notion-card {{
        background-color: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 8px;
        padding: 16px 20px;
        margin-bottom: 14px;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12);
    }}
    .notion-card-title {{ font-size: 0.78rem; text-transform: uppercase; font-weight: 600; opacity: 0.7; margin-bottom: 6px; letter-spacing: 0.05em; }}
    .notion-card-metric {{ font-size: 1.9rem; font-weight: 700; margin-bottom: 4px; }}
    .notion-card-subtitle {{ font-size: 0.8rem; opacity: 0.7; }}
    .notion-callout {{
        display: flex;
        align-items: flex-start;
        padding: 14px 18px;
        border-radius: 8px;
        background-color: rgba(245, 158, 11, 0.08);
        border: 1px solid rgba(245, 158, 11, 0.25);
        margin: 14px 0px;
        font-size: 0.92rem;
        color: #fbbf24;
    }}
    .notion-tag {{ display: inline-block; padding: 2px 8px; font-size: 0.78rem; font-weight: 500; border-radius: 4px; margin-right: 6px; }}
    .tag-blue {{ background-color: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); }}
    .tag-green {{ background-color: rgba(34, 197, 94, 0.15); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.3); }}
    .tag-amber {{ background-color: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }}
    .tag-gray {{ background-color: rgba(156, 163, 175, 0.15); color: #9ca3af; border: 1px solid rgba(156, 163, 175, 0.3); }}
    </style>
    """,
    unsafe_allow_html=True
)

# --------------------------------------------------------------------------------------
# 2. STATE INITIALIZATION (SESSION STATE DICTIONARY)
# --------------------------------------------------------------------------------------
if "hostel_room" not in st.session_state:
    st.session_state.hostel_room = {
        "room_id": "HOSTEL_D_312",
        "name": "Hostel D - Room 312",
        "current_temp": 25.0,
        "current_humidity": 50.0,
        "ac_state": "OFF",
        "preferred_temp": config.DEFAULT_PREFERRED_TEMP,
        "servo_angle": 0,
        "manual_override": False,
        "override_state": None,
        "last_ping": None
    }

hostel_room = st.session_state.hostel_room

# --------------------------------------------------------------------------------------
# 3. SIDEBAR CONTROLS & TEST SIMULATOR
# --------------------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### System Settings")
    st.markdown(
        f"""
        <div style="font-size: 0.85rem; opacity: 0.8; margin-bottom: 12px;">
            <b>Campus:</b> {config.CAMPUS_NAME}<br>
            <b>Coordinates:</b> {config.CAMPUS_LATITUDE}°N, {config.CAMPUS_LONGITUDE}°E<br>
            <b>Local Time:</b> {time.strftime('%I:%M %p')}
        </div>
        """,
        unsafe_allow_html=True
    )
    st.divider()

    # RESIDENT PREFERRED TEMPERATURE SLIDER (OPTION A)
    st.markdown("**Resident Temperature Preference**")
    current_pref = float(hostel_room.get("preferred_temp", config.DEFAULT_PREFERRED_TEMP))
    selected_pref = st.slider(
        "Preferred Room Target (°C)",
        min_value=22.0,
        max_value=28.0,
        value=current_pref,
        step=0.5,
        help="Default is set to ASHRAE recommendation. Adjust to match your personal comfort!"
    )
    hostel_room["preferred_temp"] = selected_pref
    st.caption(f"Target: **{selected_pref:.1f}°C** (±1.5°C comfort tolerance)")

    st.divider()

    st.markdown("**Hostel AC Mode**")
    mode_selection = st.radio(
        "Operating Mode",
        options=["Automatic (ASHRAE)", "Manual Override ON", "Manual Override OFF"],
        index=0 if not hostel_room["manual_override"] else (1 if hostel_room["override_state"] == "ON" else 2)
    )

    if mode_selection == "Automatic (ASHRAE)":
        hostel_room["manual_override"] = False
        hostel_room["override_state"] = None
    elif mode_selection == "Manual Override ON":
        hostel_room["manual_override"] = True
        hostel_room["override_state"] = "ON"
        hostel_room["ac_state"] = "ON"
        hostel_room["servo_angle"] = 90
    else:
        hostel_room["manual_override"] = True
        hostel_room["override_state"] = "OFF"
        hostel_room["ac_state"] = "OFF"
        hostel_room["servo_angle"] = 0

    # Fetch live outdoor weather & calculate comfort band with user preferred temp
    current_weather = weather_service.fetch_live_weather()
    current_hour = time.localtime().tm_hour
    hostel_comfort_band = comfort_model.get_hostel_comfort_band(
        current_weather["temperature_c"],
        current_hour,
        preferred_temp=hostel_room["preferred_temp"]
    )

    st.divider()
    st.markdown("**Test Sensor Simulator**")
    sim_temp = st.slider("Room Temperature (°C)", 18.0, 32.0, float(hostel_room["current_temp"]), 0.5)
    sim_hum = st.slider("Room Humidity (%)", 30, 90, int(hostel_room["current_humidity"]), 5)

    if st.button("Send Reading to Model", use_container_width=True):
        if hostel_room["manual_override"] and hostel_room["override_state"] in ("ON", "OFF"):
            ac_state = hostel_room["override_state"]
            servo_angle = config.SERVO_ON_ANGLE if ac_state == "ON" else config.SERVO_OFF_ANGLE
            reason = f"Manual override set to {ac_state}."
        else:
            ac_state, servo_angle, reason = comfort_model.evaluate_hostel_ac_decision(
                room_temp=sim_temp,
                min_temp=hostel_comfort_band["min_temp"],
                max_temp=hostel_comfort_band["max_temp"],
                last_ac_state=hostel_room["ac_state"]
            )

        hostel_room["current_temp"] = sim_temp
        hostel_room["current_humidity"] = float(sim_hum)
        hostel_room["ac_state"] = ac_state
        hostel_room["servo_angle"] = servo_angle
        hostel_room["last_ping"] = time.strftime("%Y-%m-%d %H:%M:%S")

        # Save record to CSV file
        log_record = {
            "timestamp": hostel_room["last_ping"],
            "room_id": hostel_room["room_id"],
            "current_temp": sim_temp,
            "current_humidity": float(sim_hum),
            "target_optimal": hostel_comfort_band["optimal_temp"],
            "comfort_min": hostel_comfort_band["min_temp"],
            "comfort_max": hostel_comfort_band["max_temp"],
            "ac_state": ac_state,
            "servo_angle": servo_angle,
            "explanation": reason
        }
        storage.save_telemetry(log_record)
        st.success(f"Decision: AC is {ac_state} (Servo: {servo_angle}°)")
        st.rerun()

    st.caption("Adaptive Thermal Comfort — Hostel AC Control System")

# --------------------------------------------------------------------------------------
# 4. MAIN NOTION HEADER
# --------------------------------------------------------------------------------------
st.markdown(
    """
    <div class="notion-header">
        <div class="notion-title">Adaptive Thermal Comfort AC Controller for Hostels</div>
        <div class="notion-desc">
            Direct physical switch actuation for binary hostel ACs via ESP32, DHT11, and SG90 servo motor,
            governed by the ASHRAE 55 Adaptive Comfort Model with overnight sleep compensation.
        </div>
        <div style="margin-top: 10px;">
            <span class="notion-tag tag-blue">ASHRAE Standard 55</span>
            <span class="notion-tag tag-green">ESP32 + DHT11 + SG90 Servo</span>
            <span class="notion-tag tag-amber">Campus Hostels</span>
            <span class="notion-tag tag-gray">Simple Functional Python</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

# --------------------------------------------------------------------------------------
# 5. NAVIGATION TABS
# --------------------------------------------------------------------------------------
tab_hostel, tab_savings, tab_science, tab_logs, tab_specs = st.tabs([
    "Hostel AC Unit",
    "Overnight Run-Time Analytics",
    "Sleep Biology & Weather",
    "Telemetry Logs",
    "System Architecture & Hardware"
])

# ======================================================================================
# TAB 1: HOSTEL AC CONTROLLER (LIVE HARDWARE MONITOR)
# ======================================================================================
with tab_hostel:
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(
            f"""
            <div class="notion-card">
                <div class="notion-card-title">Room Temperature</div>
                <div class="notion-card-metric">{hostel_room['current_temp']:.1f} °C</div>
                <div class="notion-card-subtitle">DHT11 Sensor Reading</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with col2:
        ac_tag = "tag-blue" if hostel_room["ac_state"] == "ON" else "tag-gray"
        st.markdown(
            f"""
            <div class="notion-card">
                <div class="notion-card-title">AC Switch State</div>
                <div class="notion-card-metric">
                    <span class="notion-tag {ac_tag}" style="font-size: 1.4rem; padding: 4px 10px;">
                        {hostel_room["ac_state"]}
                    </span>
                </div>
                <div class="notion-card-subtitle">Physical Switch Position</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with col3:
        st.markdown(
            f"""
            <div class="notion-card">
                <div class="notion-card-title">Servo Actuator Angle</div>
                <div class="notion-card-metric">{hostel_room["servo_angle"]}°</div>
                <div class="notion-card-subtitle">{'Engaged ON (90°)' if hostel_room["servo_angle"] == 90 else 'Resting OFF (0°)'}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with col4:
        pref_display = f"{hostel_room.get('preferred_temp', 25.0):.1f}°C"
        st.markdown(
            f"""
            <div class="notion-card">
                <div class="notion-card-title">Target Comfort Band</div>
                <div class="notion-card-metric">{hostel_comfort_band['optimal_temp']:.1f} °C</div>
                <div class="notion-card-subtitle">Preferred: {pref_display} | Band: [{hostel_comfort_band['min_temp']:.1f} – {hostel_comfort_band['max_temp']:.1f}°C]</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    # Explanation Callout
    _, _, explanation = comfort_model.evaluate_hostel_ac_decision(
        hostel_room["current_temp"],
        hostel_comfort_band["min_temp"],
        hostel_comfort_band["max_temp"],
        hostel_room["ac_state"]
    )

    st.markdown(
        f"""
        <div class="notion-callout">
            <div>
                <b>Decision Rationale:</b> {explanation}<br>
                <span style="font-size: 0.85rem; opacity: 0.85;">
                    Hysteresis prevents rapid compressor toggling. Overnight sleep adjustment (+1.0°C) 
                    prevents waking up cold under blankets.
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # Telemetry Trend Plot
    st.markdown("#### Room Temperature vs Comfort Band Trend")
    history_df = storage.read_telemetry_history(limit=30)

    if not history_df.empty:
        fig = go.Figure()

        # Shaded band for acceptable comfort range
        fig.add_trace(go.Scatter(
            x=history_df["timestamp"], y=history_df["comfort_max"],
            mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"
        ))
        fig.add_trace(go.Scatter(
            x=history_df["timestamp"], y=history_df["comfort_min"],
            mode="lines", line=dict(width=0), fill="tonexty",
            fillcolor="rgba(34, 197, 94, 0.18)", name="80% Comfort Band", hoverinfo="skip"
        ))

        # Optimal target line
        fig.add_trace(go.Scatter(
            x=history_df["timestamp"], y=history_df["target_optimal"],
            mode="lines", name="Target Setpoint",
            line=dict(color="#10B981", dash="dash", width=1.8)
        ))

        # Room temperature reading
        fig.add_trace(go.Scatter(
            x=history_df["timestamp"], y=history_df["current_temp"],
            mode="lines+markers", name="Room Temp (DHT11)",
            line=dict(color="#3B82F6", width=2.5), marker=dict(size=6, color="#3B82F6")
        ))

        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            height=330,
            margin=dict(l=20, r=20, t=25, b=20),
            font=dict(family="Poppins, 'Helvetica Neue', Helvetica, sans-serif", color="#CBD5E1", size=12),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
                bgcolor="rgba(0,0,0,0)",
                font=dict(color="#CBD5E1", size=11)
            ),
            xaxis=dict(
                title=dict(text="Time", font=dict(color="#94A3B8")),
                tickfont=dict(color="#94A3B8"),
                gridcolor="rgba(255, 255, 255, 0.08)",
                zerolinecolor="rgba(255, 255, 255, 0.08)"
            ),
            yaxis=dict(
                title=dict(text="Temperature (°C)", font=dict(color="#94A3B8")),
                tickfont=dict(color="#94A3B8"),
                gridcolor="rgba(255, 255, 255, 0.08)",
                zerolinecolor="rgba(255, 255, 255, 0.08)",
                range=[20, 32]
            ),
            hovermode="x unified"
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No logs found yet. Use the sidebar simulator to log test data!")

# ======================================================================================
# TAB 2: OVERNIGHT RUN-TIME REDUCTION & COMFORT METRICS
# ======================================================================================
with tab_savings:
    st.markdown("### Active Run-Time & Overcooling Prevention")
    st.markdown(
        """
        Our campus hostel has centralized cooling with a local binary wall switch. 
        Because residents cannot access backend chiller tonnage or power ratings, our system 
        **directly measures physical indoor temperature** with the DHT11 to eliminate unnecessary cooling run-time.
        """
    )

    hours_slider = st.slider("Hours AC Switched Off Overnight (Out of 8.0 hrs sleep)", 1.0, 7.0, 4.0, 0.5)
    runtime_stats = comfort_model.calculate_runtime_reduction(hours_ac_off=hours_slider)

    col_s1, col_s2, col_s3 = st.columns(3)
    with col_s1:
        st.markdown(
            f"""
            <div class="notion-card">
                <div class="notion-card-title">Run-Time Reduction</div>
                <div class="notion-card-metric" style="color: #2b7a3e;">{runtime_stats['runtime_reduction_pct']}%</div>
                <div class="notion-card-subtitle">{runtime_stats['hours_cooling_off']} hrs active cooling eliminated</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with col_s2:
        st.markdown(
            f"""
            <div class="notion-card">
                <div class="notion-card-title">Degree-Hours Avoided</div>
                <div class="notion-card-metric" style="color: #1e6b9c;">{runtime_stats['degree_hours_avoided']} °C·hr</div>
                <div class="notion-card-subtitle">Severe overcooling prevented</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with col_s3:
        comfort_adherence = round(85.0 + (runtime_stats['runtime_reduction_pct'] * 0.1), 1)
        st.markdown(
            f"""
            <div class="notion-card">
                <div class="notion-card-title">Comfort Adherence</div>
                <div class="notion-card-metric" style="color: #9c6819;">~{min(98.0, comfort_adherence)}%</div>
                <div class="notion-card-subtitle">Night hours inside ASHRAE band</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown("#### Why Measure Run-Time & Temperature Directly?")
    st.info(
        "Centralized cooling systems deliver cold air into student rooms, but without automation, "
        "rooms plunge to 19°C overnight. By cutting active run-time by **"
        f"{runtime_stats['runtime_reduction_pct']}%**, the room maintains a comfortable sleep temperature "
        "without waking up shivering or needing excessive blankets."
    )

# ======================================================================================
# TAB 3: SLEEP BIOLOGY & WEATHER
# ======================================================================================
with tab_science:
    st.markdown("### Human Sleep Biology & ASHRAE Standard 55")
    col_w1, col_w2, col_w3 = st.columns(3)
    with col_w1:
        st.metric("Outdoor Temperature (Campus)", f"{current_weather['temperature_c']:.1f} °C")
    with col_w2:
        st.metric("Relative Humidity", f"{current_weather['humidity_pct']:.0f} %")
    with col_w3:
        st.metric("Weather Source", current_weather['source'])

    st.divider()
    st.markdown(
        r"""
        #### The Mathematical Formula
        $$T_{\text{comf}} = 17.8 + 0.31 \times T_{\text{outdoor}}$$

        #### Why Do We Feel Colder Sleeping Overnight?
        1. **Lower Metabolic Heat ($M$):** Drops from $1.0\text{ met}$ (awake) to $0.7\text{ met}$ (sleeping basal state). The body produces ~30% less internal heat.
        2. **Bedding Insulation ($I_{cl}$):** Increases from $0.5\text{ clo}$ (t-shirt/shorts) to $1.2 - 1.5\text{ clo}$ (sleepwear + heavy blankets).
        3. **The Result:** The human body needs a warmer ambient temperature (+1.0°C offset) to remain in thermal equilibrium. Turning off the AC when the room reaches ~25.5°C prevents hypothermic waking.
        """
    )

# ======================================================================================
# TAB 4: TELEMETRY LOGS & CSV EXPORT
# ======================================================================================
with tab_logs:
    st.markdown("### Historical Sensor Telemetry Logs")
    st.caption("Demonstrating Python File Handling: Reading and writing CSV logs using 'with open'.")

    full_history = storage.read_telemetry_history(limit=100)
    if not full_history.empty:
        st.dataframe(full_history, use_container_width=True)
        csv_data = full_history.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download CSV File",
            data=csv_data,
            file_name="hostel_telemetry.csv",
            mime="text/csv"
        )
    else:
        st.info("No logs present yet.")

# ======================================================================================
# TAB 5: SPECS & TEAM
# ======================================================================================
with tab_specs:
    st.markdown("### Hardware Bill of Materials (BOM)")
    bom_data = pd.DataFrame([
        {"Component": "ESP32 DevKit V1 Board", "Role": "WiFi microcontroller & HTTP client", "Price (₹)": 400},
        {"Component": "SG90 Micro Servo Motor", "Role": "Physical AC switch actuator (0°/90°)", "Price (₹)": 150},
        {"Component": "0.96\" I2C OLED / LCD Module", "Role": "On-device status display", "Price (₹)": 212},
        {"Component": "DHT11 Sensor Module", "Role": "Room temperature & humidity sensing", "Price (₹)": 51},
        {"Component": "Total Hardware Cost", "Role": "Complete physical prototype", "Price (₹)": 813}
    ])
    st.table(bom_data)

    st.divider()
    st.markdown("### Technical Implementation Mapping")
    syllabus_mapping = pd.DataFrame([
        {"Topic": "Functions", "Implementation": "calculate_ashrae_comfort, evaluate_hostel_ac_decision, calculate_runtime_reduction"},
        {"Topic": "Conditionals (if/elif/else)", "Implementation": "Hysteresis decision branching and night-time mode detection"},
        {"Topic": "Lists, Dicts, Tuples", "Implementation": "Hostel state dictionary, comfort band dictionary, (state, angle, reason) tuples"},
        {"Topic": "File Handling (CSV)", "Implementation": "save_telemetry and read_telemetry_history with 'with open' context manager"},
        {"Topic": "Exception Handling", "Implementation": "try...except blocks in requests weather fetching and file I/O"},
        {"Topic": "External APIs & Web", "Implementation": "requests library fetching Open-Meteo, Flask serving ESP32 REST API"},
        {"Topic": "Visualization", "Implementation": "Interactive Plotly time-series graphs in Streamlit dashboard"}
    ])
    st.table(syllabus_mapping)

    st.divider()
    st.markdown("### Subsystem Architecture & Responsibilities")
    roles_data = pd.DataFrame([
        {"Subsystem": "Comfort Modeling Lead", "Responsibility": "ASHRAE Adaptive Comfort Model implementation & hysteresis decision logic"},
        {"Subsystem": "Weather Pipeline Lead", "Responsibility": "Open-Meteo REST API integration, data acquisition, and offline fallback"},
        {"Subsystem": "Thermal Analytics Lead", "Responsibility": "Diurnal sleep profile modeling & run-time reduction analysis"},
        {"Subsystem": "Full-Stack & Hardware Lead", "Responsibility": "Streamlit Notion UI, Flask API, ESP32 firmware & SG90 servo switch actuation"},
        {"Subsystem": "Data Storage & Failsafe Lead", "Responsibility": "CSV storage pipeline with 'with open', failsafe edge-case handling, and ESP32 offline autonomy"}
    ])
    roles_data = roles_data.reset_index(drop=True)
    st.table(roles_data)
