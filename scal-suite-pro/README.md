# SCAL Digital Assistant & Simulation Suite v3.0

**Multi-method Special Core Analysis — Relative Permeability & Capillary Pressure**
Eclipse-ready `.INC` output | LangGraph QA | Streamlit UI | FastAPI backend

---

## Supported Kr Methods

| Method | Reference | Best For |
|---|---|---|
| **Corey** | Corey (1954) | Clean sands, simple wetting, default baseline |
| **LET (Modified Corey)** | Lomeland, Ebeltoft, Thomas — SPE-89352 (2005) | Mixed-wet, heterogeneous, S-shaped curves |
| **Burdine** | Burdine (1953) Trans. AIME | Tighter formations, pore-bundle theory |
| **Brooks-Corey** | Brooks & Corey (1964) | Pore-size distribution governs both kr and Pc |
| **Chierici** | Chierici (1984) | Fractured / vuggy carbonates, avoids crossover |

---

## Architecture

```
scal-suite-pro/
├── corey_engine.py       # All 5 kr models + Eclipse .INC + Excel export
├── agents.py             # LangGraph: PhysicsCheck → EngineeringQA → ReportSynthesis
├── main.py               # FastAPI: /api/v1/compute-scal  /api/v1/methods
├── app_ui.py             # Streamlit dashboard with method selector
├── utils/
│   └── logger.py         # Structured logging
├── .env.example          # Environment template
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## Quick Start (Local)

### 1. Clone and configure

```bash
git clone <repo>
cd scal-suite-pro
cp .env.example .env
# Edit .env — add your ANTHROPIC_API_KEY
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run backend

```bash
uvicorn main:app --reload --port 8000
```

### 4. Run frontend (separate terminal)

```bash
streamlit run app_ui.py
```

Open: http://localhost:8501

---

## Docker Deployment

```bash
cp .env.example .env   # add ANTHROPIC_API_KEY
docker-compose up --build
```

Frontend: http://localhost:8501  
Backend API docs: http://localhost:8000/docs

---

## Eclipse Output Keywords

| Fluid System | Eclipse Keyword | Column Order |
|---|---|---|
| Oil-Water | `SWOF` | Sw  Krw  Kro  Pc |
| Gas-Water | `SGOF` | Sg  Krg  Krw  Pc |

The `.INC` file is directly referenceable from your Eclipse DATA file:

```
INCLUDE
  'SCAL_FUNCTIONS.INC' /
```

---

## Download Package Contents (.zip)

Each simulation run produces a `.zip` containing:

| File | Description |
|---|---|
| `SCAL_FUNCTIONS.INC` | Eclipse E100/E300 SWOF/SGOF keyword table |
| `SCAL_Report.xlsx` | Data table + embedded native Excel line charts |
| `saturation_table.csv` | Raw Sw/Kr/Pc values |
| `agent_report.txt` | Physics QC + engineering diagnostic log |

---

## API Reference

**POST** `/api/v1/compute-scal`

```json
{
  "method": "LET",
  "system": "Oil-Water",
  "swc": 0.20,
  "s_res": 0.25,
  "krw_end": 0.30,
  "kr_phase_end": 0.80,
  "include_pc": true,
  "pc_entry": 1.0,
  "lambda_pc": 2.0,
  "uncertainty": 0.0,
  "n_points": 30,
  "let_params": {
    "Lw": 2.0, "Ew": 1.0, "Tw": 2.0,
    "Lp": 2.0, "Ep": 1.0, "Tp": 2.0
  }
}
```

**GET** `/api/v1/methods` — returns all available methods with descriptions.

---

## Method Parameter Guide

### Corey (1954)
```
nw       : Water Corey exponent [1–8]   — higher = more curved, water-wet behaviour
n_phase  : Oil/gas Corey exponent [1–8] — nw > n_phase implies water-wet tendency
```

### LET / Modified Corey (SPE-89352)
```
L : Controls the lower saturation curvature (analogue to Corey n at low Sw)
E : Controls the "elevation" — curvature in the middle saturation range
T : Controls upper curvature (analogue to Corey n at high Sw)
Separate L, E, T sets for water and the non-wetting phase.
```

### Burdine (1953)
```
lambda_b : Pore-size distribution index. Broad PSD (sands) ≈ 1.5–3. Narrow (carbonates) ≈ 3–6.
```

### Brooks-Corey (1964)
```
lambda_bc : Same interpretation as Burdine lambda but governs both kr and Pc simultaneously.
            Recommended starting points: clean sandstone 3–5, carbonate 1.5–2.5.
```

### Chierici (1984)
```
aw, bw : Curvature parameters for water phase. Calibrated from SCAL lab data.
ap, bp : Curvature parameters for oil/gas phase.
```

---

## References

- Dake, L.P. (1978). *Fundamentals of Reservoir Engineering*. Elsevier.
- Corey, A.T. (1954). The interrelation between gas and oil relative permeabilities. *Producers Monthly*.
- Burdine, N.T. (1953). Relative permeability calculations from pore-size distribution data. *Trans. AIME*, 198.
- Brooks, R.H. & Corey, A.T. (1964). *Hydraulic Properties of Porous Media*. Colorado State University.
- Lomeland, F., Ebeltoft, E. & Thomas, W.H. (2005). A new versatile relative permeability correlation. *SPE-89352*.
- Chierici, G.L. (1984). Novel relations for drainage and imbibition curves. *SPEJ*, 24(3).
- Whitson, C.H. & Brulé, M.R. (2000). *Phase Behavior*. SPE Monograph Vol. 20.
