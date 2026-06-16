"""
app_ui.py
---------
Streamlit Dashboard — SCAL Digital Assistant Suite v3.0
Supports: Corey, LET, Burdine, Brooks-Corey, Chierici
"""

import io
import zipfile
import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="SCAL Digital Assistant Suite",
    page_icon="🛢️",
    layout="wide",
    initial_sidebar_state="expanded"
)

API_URL = "http://localhost:8000/api/v1/compute-scal"

METHOD_DESCRIPTIONS = {
    "Corey":        "Classical power-law. Best for clean sands and simple wetting systems. (Corey, 1954)",
    "LET":          "Modified Corey with S-shaped flexibility for mixed-wet / heterogeneous rocks. (SPE-89352, 2005)",
    "Burdine":      "Pore-size-distribution bundle model; suited to tighter formations. (Burdine, 1953)",
    "Brooks-Corey": "Extended pore-size-distribution with lambda governing both kr and Pc. (Brooks & Corey, 1964)",
    "Chierici":     "Exponential model; avoids crossover by construction. Ideal for fractured carbonates. (Chierici, 1984)",
}

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR — PARAMETER INPUT
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/3/36/Petroleum_icon.svg/100px-Petroleum_icon.svg.png", width=55)
    st.title("SCAL Suite v3.0")
    st.caption("Relative Permeability & Capillary Pressure")
    st.divider()

    # ── Method & System ──
    st.subheader("1 — Model Selection")
    method = st.selectbox(
        "Kr Method",
        ["Corey", "LET", "Burdine", "Brooks-Corey", "Chierici"],
        help="Select the relative permeability correlation to apply."
    )
    st.caption(f"_{METHOD_DESCRIPTIONS[method]}_")
    st.divider()

    system = st.selectbox(
        "Fluid System",
        ["Oil-Water", "Gas-Water"],
        help="Determines SWOF or SGOF Eclipse keyword output."
    )
    include_pc = st.checkbox("Include Capillary Pressure (Pc)", value=True)
    st.divider()

    # ── Saturation Endpoints ──
    st.subheader("2 — Saturation Endpoints")
    swc   = st.slider("Connate Water Saturation — Swc",   0.05, 0.45, 0.20, 0.01)
    s_res = st.slider("Residual Phase Saturation — Sor/Sgr", 0.05, 0.45, 0.25, 0.01)

    if (swc + s_res) >= 1.0:
        st.error(f"Swc + S_res = {swc+s_res:.2f} ≥ 1.0 — unphysical! Reduce one or both.")

    krw_end      = st.slider("End-point Krw",      0.05, 1.0, 0.30, 0.01,
                             help="Max water relative permeability (at 1 - S_res)")
    kr_phase_end = st.slider("End-point Kro/Krg",  0.05, 1.0, 0.80, 0.01,
                             help="Max oil/gas relative permeability (at Swc)")
    st.divider()

    # ── Method-specific parameters ──
    st.subheader("3 — Method Parameters")

    method_payload = {}

    if method == "Corey":
        nw      = st.number_input("Water Corey Exponent nw",      1.0, 8.0, 3.0, 0.5)
        n_phase = st.number_input("Phase Corey Exponent no/ng",   1.0, 8.0, 2.0, 0.5)
        method_payload["corey_params"] = {"nw": nw, "n_phase": n_phase}

    elif method == "LET":
        st.caption("Water phase LET parameters:")
        Lw = st.number_input("Lw (water L-shape)", 0.1, 10.0, 2.0, 0.1)
        Ew = st.number_input("Ew (water E-shape)", 0.1, 10.0, 1.0, 0.1)
        Tw = st.number_input("Tw (water T-shape)", 0.1, 10.0, 2.0, 0.1)
        st.caption("Non-wetting phase LET parameters:")
        Lp = st.number_input("Lp (phase L-shape)", 0.1, 10.0, 2.0, 0.1)
        Ep = st.number_input("Ep (phase E-shape)", 0.1, 10.0, 1.0, 0.1)
        Tp = st.number_input("Tp (phase T-shape)", 0.1, 10.0, 2.0, 0.1)
        method_payload["let_params"] = {"Lw": Lw, "Ew": Ew, "Tw": Tw,
                                         "Lp": Lp, "Ep": Ep, "Tp": Tp}

    elif method == "Burdine":
        lambda_b = st.number_input(
            "Pore Distribution Index λ (Burdine)",
            0.1, 10.0, 2.0, 0.1,
            help="Broad PSD → low λ; narrow PSD → high λ. Typical: 1.5–4.0"
        )
        method_payload["burdine_params"] = {"lambda_b": lambda_b}

    elif method == "Brooks-Corey":
        lambda_bc = st.number_input(
            "Pore Distribution Index λ (Brooks-Corey)",
            0.2, 10.0, 2.0, 0.1,
            help="λ controls curvature of both kr and Pc. Clean well-sorted sands: λ≈4–7"
        )
        method_payload["brooks_corey_params"] = {"lambda_bc": lambda_bc}

    elif method == "Chierici":
        st.caption("Water shape parameters:")
        aw = st.number_input("aw", 0.01, 5.0, 0.5, 0.05)
        bw = st.number_input("bw", 0.01, 5.0, 1.0, 0.05)
        st.caption("Phase shape parameters:")
        ap = st.number_input("ap", 0.01, 5.0, 0.5, 0.05)
        bp = st.number_input("bp", 0.01, 5.0, 1.0, 0.05)
        method_payload["chierici_params"] = {"aw": aw, "bw": bw, "ap": ap, "bp": bp}

    st.divider()

    # ── Pc params (shown if Pc enabled) ──
    if include_pc:
        st.subheader("4 — Capillary Pressure")
        pc_entry  = st.number_input("Entry Pressure Pc_entry (bar)", 0.01, 50.0, 1.0, 0.1)
        if method not in ("Burdine", "Brooks-Corey"):
            lambda_pc = st.number_input("Pc Lambda (pore distribution)", 0.5, 10.0, 2.0, 0.1)
        else:
            lambda_pc = 2.0  # unused; engine uses lambda_b/lambda_bc
        st.divider()
    else:
        pc_entry  = 1.0
        lambda_pc = 2.0

    # ── Advanced ──
    st.subheader("5 — Advanced")
    uncertainty = st.slider("Endpoint Uncertainty Band", 0.0, 0.3, 0.0, 0.01,
                            help="Monte Carlo jitter on Swc / S_res for uncertainty realisation.")
    n_points = st.select_slider("Table Resolution (pts)", options=[20, 30, 50, 100], value=30)
    st.divider()

    run_btn = st.button("Run SCAL Engine", type="primary", use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PANEL
# ─────────────────────────────────────────────────────────────────────────────

st.title("SCAL Digital Assistant & Simulation Suite")
st.caption(
    "Multi-method Special Core Analysis — Relative Permeability & Capillary Pressure "
    "with Eclipse .INC export and LangGraph QA."
)

if not run_btn:
    # ── Landing info panel ──
    col1, col2, col3 = st.columns(3)
    with col1:
        st.info("**Step 1** — Select Kr method and fluid system in the sidebar.")
    with col2:
        st.info("**Step 2** — Set saturation endpoints and method parameters.")
    with col3:
        st.info("**Step 3** — Click **Run SCAL Engine** to generate curves and Eclipse files.")

    st.subheader("Available Kr Methods")
    for name, desc in METHOD_DESCRIPTIONS.items():
        st.markdown(f"**{name}** — {desc}")
    st.stop()


# ─────────────────────────────────────────────────────────────────────────────
# API CALL
# ─────────────────────────────────────────────────────────────────────────────

payload = {
    "method":        method,
    "system":        system,
    "swc":           swc,
    "s_res":         s_res,
    "krw_end":       krw_end,
    "kr_phase_end":  kr_phase_end,
    "include_pc":    include_pc,
    "pc_entry":      pc_entry,
    "lambda_pc":     lambda_pc,
    "uncertainty":   uncertainty,
    "n_points":      n_points,
    **method_payload
}

with st.spinner("Running simulation and agent QA..."):
    try:
        res = requests.post(API_URL, json=payload, timeout=60)
    except requests.ConnectionError:
        st.error(
            "Cannot reach FastAPI backend at localhost:8000. "
            "Start the backend: `uvicorn main:app --reload`"
        )
        st.stop()

if res.status_code != 200:
    err = res.json()
    st.error(f"**Error {res.status_code}**")
    if "errors" in err.get("detail", {}):
        for e in err["detail"]["errors"]:
            st.warning(f"Physics: {e}")
    if "report" in err.get("detail", {}):
        st.code(err["detail"]["report"])
    st.stop()

data = res.json()
df   = pd.DataFrame(data["data"])
cols = data["columns"]
phase_col = cols[2]  # "Kro" or "Krg"

# ─────────────────────────────────────────────────────────────────────────────
# RESULTS DISPLAY
# ─────────────────────────────────────────────────────────────────────────────

st.success(f"Simulation complete — {method} | {system}")

# ── Agent diagnostic ──
with st.expander("Agent QA Diagnostic Report", expanded=False):
    st.code(data["agent_report"], language="text")
    if data.get("engineering_feedback"):
        st.info(data["engineering_feedback"])

# ── Metrics ──
col_a, col_b, col_c, col_d = st.columns(4)
col_a.metric("Swc",          f"{df['Sw'].min():.3f}")
col_b.metric("1 - S_res",    f"{df['Sw'].max():.3f}")
col_c.metric(f"Max Krw",     f"{df['Krw'].max():.4f}")
col_d.metric(f"Max {phase_col}", f"{df[phase_col].max():.4f}")

# ── Kr Plot ──
st.subheader("Relative Permeability Curves")
has_pc = include_pc and "Pc" in df.columns and df["Pc"].sum() > 0

if has_pc:
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=["Kr Functions", "Capillary Pressure Pc"]
    )
else:
    fig = make_subplots(rows=1, cols=1)

fig.add_trace(go.Scatter(
    x=df["Sw"], y=df["Krw"],
    name="Krw", mode="lines+markers",
    line=dict(color="#2196F3", width=2),
    marker=dict(size=4)
), row=1, col=1)

fig.add_trace(go.Scatter(
    x=df["Sw"], y=df[phase_col],
    name=phase_col, mode="lines+markers",
    line=dict(color="#F44336", width=2),
    marker=dict(size=4)
), row=1, col=1)

if has_pc:
    fig.add_trace(go.Scatter(
        x=df["Sw"], y=df["Pc"],
        name="Pc (bar)", mode="lines+markers",
        line=dict(color="#4CAF50", width=2),
        marker=dict(size=4)
    ), row=1, col=2)

fig.update_xaxes(title_text="Sw", row=1, col=1)
fig.update_yaxes(title_text="Kr (fraction)", range=[0, 1], row=1, col=1)
if has_pc:
    fig.update_xaxes(title_text="Sw", row=1, col=2)
    fig.update_yaxes(title_text="Pc (bar)", row=1, col=2)

fig.update_layout(
    height=480,
    title_text=f"{method} — {system}",
    legend=dict(x=0.01, y=0.99),
    hovermode="x unified"
)
st.plotly_chart(fig, use_container_width=True)

# ── Data Table ──
with st.expander("View Saturation Table", expanded=False):
    st.dataframe(df.style.format("{:.6f}"), use_container_width=True)

# ── Eclipse .INC preview ──
with st.expander("Preview Eclipse .INC Content", expanded=False):
    try:
        with open(data["eclipse_inc_file"]) as f:
            inc_text = f.read()
        st.code(inc_text, language="text")
    except Exception:
        st.warning("INC file not available for preview from this browser session.")

# ─────────────────────────────────────────────────────────────────────────────
# DOWNLOAD SECTION — .ZIP
# ─────────────────────────────────────────────────────────────────────────────

st.subheader("Download Deliverables")
st.caption("All outputs bundled as a single .zip archive.")

try:
    # Read files generated by backend
    with open(data["eclipse_inc_file"], "rb") as f:
        inc_bytes = f.read()
    with open(data["excel_report_file"], "rb") as f:
        xlsx_bytes = f.read()

    # Build in-memory zip
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("SCAL_FUNCTIONS.INC",  inc_bytes)
        zf.writestr("SCAL_Report.xlsx",    xlsx_bytes)
        zf.writestr("saturation_table.csv", df.to_csv(index=False).encode())
        zf.writestr("agent_report.txt",     data["agent_report"].encode())
    zip_buffer.seek(0)

    col_zip, col_inc, col_xlsx = st.columns(3)

    with col_zip:
        st.download_button(
            label="📦 Download Full Package (.zip)",
            data=zip_buffer,
            file_name=f"SCAL_{method}_{system.replace('-','_')}.zip",
            mime="application/zip",
        )
    with col_inc:
        st.download_button(
            label="📄 Eclipse .INC Only",
            data=inc_bytes,
            file_name="SCAL_FUNCTIONS.INC",
            mime="text/plain",
        )
    with col_xlsx:
        st.download_button(
            label="📊 Excel Report Only",
            data=xlsx_bytes,
            file_name="SCAL_Report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

except FileNotFoundError:
    st.warning(
        "Download files are generated server-side. "
        "When running locally, files will appear in the working directory."
    )
