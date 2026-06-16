"""
main.py
-------
FastAPI Backend — SCAL Digital Assistant Suite
Exposes /api/v1/compute-scal with full method dispatch and agent validation.
"""

import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional

from corey_engine import (
    corey, let_kr, burdine, brooks_corey, chierici,
    export_to_eclipse_inc, export_to_excel
)
from agents import agent_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("SCAL_API")

app = FastAPI(
    title="SCAL Digital Assistant Suite — API",
    version="3.0.0",
    description="Multi-method SCAL engine with LangGraph QA and Eclipse .INC export."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# REQUEST SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class CoreyParams(BaseModel):
    nw:      float = Field(default=3.0, ge=1.0, le=8.0)
    n_phase: float = Field(default=2.0, ge=1.0, le=8.0)


class LETParams(BaseModel):
    Lw: float = Field(default=2.0, gt=0)
    Ew: float = Field(default=1.0, gt=0)
    Tw: float = Field(default=2.0, gt=0)
    Lp: float = Field(default=2.0, gt=0)
    Ep: float = Field(default=1.0, gt=0)
    Tp: float = Field(default=2.0, gt=0)


class BurdineParams(BaseModel):
    lambda_b: float = Field(default=2.0, gt=0)


class BrooksCoreyParams(BaseModel):
    lambda_bc: float = Field(default=2.0, gt=0)


class ChiericiParams(BaseModel):
    aw: float = Field(default=0.5, gt=0)
    bw: float = Field(default=1.0, gt=0)
    ap: float = Field(default=0.5, gt=0)
    bp: float = Field(default=1.0, gt=0)


class SCALPayload(BaseModel):
    method:        str   = Field(default="Corey")       # Corey | LET | Burdine | Brooks-Corey | Chierici
    system:        str   = Field(default="Oil-Water")   # Oil-Water | Gas-Water
    swc:           float = Field(default=0.20, ge=0.0,  le=0.5)
    s_res:         float = Field(default=0.25, ge=0.0,  le=0.5)
    krw_end:       float = Field(default=0.30, ge=0.0,  le=1.0)
    kr_phase_end:  float = Field(default=0.80, ge=0.0,  le=1.0)
    include_pc:    bool  = Field(default=True)
    pc_entry:      float = Field(default=1.0,  gt=0)
    lambda_pc:     float = Field(default=2.0,  gt=0)
    uncertainty:   float = Field(default=0.0,  ge=0.0, le=0.3)
    n_points:      int   = Field(default=30,   ge=10,  le=100)

    # Method-specific sub-schemas (mutually exclusive in practice)
    corey_params:        Optional[CoreyParams]        = None
    let_params:          Optional[LETParams]          = None
    burdine_params:      Optional[BurdineParams]      = None
    brooks_corey_params: Optional[BrooksCoreyParams]  = None
    chierici_params:     Optional[ChiericiParams]     = None


# ─────────────────────────────────────────────────────────────────────────────
# HELPER — extract method_params dict for agent state
# ─────────────────────────────────────────────────────────────────────────────

def _method_params_dict(payload: SCALPayload) -> dict:
    m = payload.method
    if m == "Corey":
        p = payload.corey_params or CoreyParams()
        return p.model_dump()
    if m == "LET":
        p = payload.let_params or LETParams()
        return p.model_dump()
    if m == "Burdine":
        p = payload.burdine_params or BurdineParams()
        return p.model_dump()
    if m == "Brooks-Corey":
        p = payload.brooks_corey_params or BrooksCoreyParams()
        return p.model_dump()
    if m == "Chierici":
        p = payload.chierici_params or ChiericiParams()
        return p.model_dump()
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# HELPER — dispatch to correct engine function
# ─────────────────────────────────────────────────────────────────────────────

def _run_engine(payload: SCALPayload):
    kw = dict(
        system=payload.system,
        swc=payload.swc,
        s_res=payload.s_res,
        krw_end=payload.krw_end,
        kr_phase_end=payload.kr_phase_end,
        include_pc=payload.include_pc,
        pc_entry=payload.pc_entry,
        lambda_pc=payload.lambda_pc,
        uncert_pct=payload.uncertainty,
        n_points=payload.n_points,
    )

    m = payload.method

    if m == "Corey":
        p = payload.corey_params or CoreyParams()
        return corey(nw=p.nw, n_phase=p.n_phase, **kw)

    if m == "LET":
        p = payload.let_params or LETParams()
        return let_kr(
            Lw=p.Lw, Ew=p.Ew, Tw=p.Tw,
            Lp=p.Lp, Ep=p.Ep, Tp=p.Tp,
            **kw
        )

    if m == "Burdine":
        p = payload.burdine_params or BurdineParams()
        kw.pop("lambda_pc")  # Burdine uses lambda_b for both kr and pc
        return burdine(lambda_b=p.lambda_b, **kw)

    if m == "Brooks-Corey":
        p = payload.brooks_corey_params or BrooksCoreyParams()
        kw.pop("lambda_pc")
        return brooks_corey(lambda_bc=p.lambda_bc, **kw)

    if m == "Chierici":
        p = payload.chierici_params or ChiericiParams()
        return chierici(aw=p.aw, bw=p.bw, ap=p.ap, bp=p.bp, **kw)

    raise ValueError(f"Unknown method: {m}")


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "SCAL Suite API v3.0 — online"}


@app.get("/api/v1/methods")
def list_methods():
    """Returns available kr methods and their parameter descriptions."""
    return {
        "methods": {
            "Corey": {
                "description": "Classical power-law. Best for clean sands / carbonates with simple wetting.",
                "params": ["nw (1–8)", "n_phase (1–8)"],
                "reference": "Corey (1954)"
            },
            "LET": {
                "description": "Modified Corey with S-shaped flexibility. Preferred for heterogeneous/mixed-wet systems.",
                "params": ["Lw, Ew, Tw (water)", "Lp, Ep, Tp (phase)"],
                "reference": "Lomeland, Ebeltoft, Thomas (2005) SPE-89352"
            },
            "Burdine": {
                "description": "Pore-size-distribution model. Good for tighter formations.",
                "params": ["lambda_b (pore distribution index, >0)"],
                "reference": "Burdine (1953)"
            },
            "Brooks-Corey": {
                "description": "Extended Burdine with explicit pore-size-distribution index controlling both kr and Pc.",
                "params": ["lambda_bc (0.2 broad-psd to 7.0 narrow-psd)"],
                "reference": "Brooks & Corey (1964)"
            },
            "Chierici": {
                "description": "Exponential model; avoids crossover by construction. Suited to fractured/vuggy carbonates.",
                "params": ["aw, bw (water shape)", "ap, bp (phase shape)"],
                "reference": "Chierici (1984)"
            }
        }
    }


@app.post("/api/v1/compute-scal")
async def compute_scal(payload: SCALPayload):
    logger.info(f"Request: method={payload.method}, system={payload.system}, "
                f"swc={payload.swc}, s_res={payload.s_res}")

    # ── Agent validation ──
    agent_state = {
        "method":         payload.method,
        "system":         payload.system,
        "swc":            payload.swc,
        "s_res":          payload.s_res,
        "krw_end":        payload.krw_end,
        "kr_phase_end":   payload.kr_phase_end,
        "include_pc":     payload.include_pc,
        "method_params":  _method_params_dict(payload),
        "physics_ok":     True,
        "physics_errors": [],
        "engineering_feedback": "",
        "final_report":   "",
    }

    agent_result = agent_router.invoke(agent_state)

    if not agent_result["physics_ok"]:
        logger.error("Physics validation failed.")
        raise HTTPException(
            status_code=400,
            detail={
                "errors": agent_result["physics_errors"],
                "report": agent_result["final_report"]
            }
        )

    # ── Engine run ──
    try:
        df = _run_engine(payload)
    except Exception as exc:
        logger.exception("Engine error.")
        raise HTTPException(status_code=500, detail=str(exc))

    # ── Export files ──
    inc_file  = export_to_eclipse_inc(
        df, payload.system, payload.method,
        payload.swc, payload.s_res, payload.include_pc,
        filename="SCAL_FUNCTIONS.INC"
    )
    xlsx_file = export_to_excel(df, payload.system, payload.method,
                                filename="SCAL_Report.xlsx")

    logger.info(f"Computation complete. INC={inc_file}, XLSX={xlsx_file}")

    return {
        "status":               "success",
        "method":               payload.method,
        "system":               payload.system,
        "agent_report":         agent_result["final_report"],
        "engineering_feedback": agent_result.get("engineering_feedback", ""),
        "eclipse_inc_file":     inc_file,
        "excel_report_file":    xlsx_file,
        "data":                 df.to_dict(orient="records"),
        "columns":              list(df.columns),
    }
