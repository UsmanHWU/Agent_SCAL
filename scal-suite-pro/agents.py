"""
agents.py
---------
LangGraph agentic workflow for SCAL parameter validation and QC.
Nodes:
  1. PhysicsCheck    — hard mathematical sanity checks (no LLM needed)
  2. EngineeringQA   — LLM-assisted interpretation of Corey exponents / LET params
  3. ReportSynthesis — generates a plain-text diagnostic summary
"""

import os
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage


# ─────────────────────────────────────────────────────────────────────────────
# STATE SCHEMA
# ─────────────────────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    # Inputs
    method: str
    system: str
    swc: float
    s_res: float
    krw_end: float
    kr_phase_end: float
    include_pc: bool
    # Method-specific params (serialised as dict)
    method_params: dict
    # Outputs
    physics_ok: bool
    physics_errors: list
    engineering_feedback: str
    final_report: str


# ─────────────────────────────────────────────────────────────────────────────
# NODE 1 — Physics / sanity checks (deterministic, no LLM)
# ─────────────────────────────────────────────────────────────────────────────

def physics_check_node(state: AgentState) -> dict:
    """
    Enforces hard physical constraints on SCAL inputs.
    Catches unphysical configurations before expensive simulation.
    """
    errors = []
    swc    = state["swc"]
    s_res  = state["s_res"]
    krw    = state["krw_end"]
    krp    = state["kr_phase_end"]
    mp     = state.get("method_params", {})
    method = state["method"]

    # Saturation constraint
    if (swc + s_res) >= 1.0:
        errors.append(
            f"Saturation violation: Swc ({swc:.3f}) + S_res ({s_res:.3f}) = "
            f"{swc+s_res:.3f} ≥ 1.0. Reduce either endpoint."
        )

    # Minimum mobile saturation window
    if (1.0 - swc - s_res) < 0.05:
        errors.append(
            f"Mobile saturation window too narrow ({1-swc-s_res:.3f}). "
            "Consider reducing Swc or S_res."
        )

    # End-point bounds
    if not (0.0 < krw <= 1.0):
        errors.append(f"Krw_end ({krw}) must be in (0, 1].")
    if not (0.0 < krp <= 1.0):
        errors.append(f"Kr_phase_end ({krp}) must be in (0, 1].")

    # Method-specific checks
    if method == "Corey":
        for key in ("nw", "n_phase"):
            val = mp.get(key, 0)
            if val < 1.0 or val > 8.0:
                errors.append(f"Corey exponent {key}={val} outside typical range [1, 8].")

    elif method == "LET":
        for key in ("Lw", "Ew", "Tw", "Lp", "Ep", "Tp"):
            val = mp.get(key, 0)
            if val <= 0:
                errors.append(f"LET parameter {key}={val} must be > 0.")

    elif method in ("Brooks-Corey", "Burdine"):
        lam = mp.get("lambda_bc", mp.get("lambda_b", 0))
        if lam <= 0:
            errors.append(f"Pore-size distribution index lambda must be > 0 (got {lam}).")

    elif method == "Chierici":
        for key in ("aw", "bw", "ap", "bp"):
            val = mp.get(key, 0)
            if val <= 0:
                errors.append(f"Chierici parameter {key}={val} must be > 0.")

    return {
        "physics_ok": len(errors) == 0,
        "physics_errors": errors
    }


# ─────────────────────────────────────────────────────────────────────────────
# NODE 2 — Engineering QA via LLM (only if physics passed)
# ─────────────────────────────────────────────────────────────────────────────

def engineering_qa_node(state: AgentState) -> dict:
    """
    Uses Claude claude-sonnet-4-6 to provide a brief engineering-quality assessment of
    the selected method and parameters against reservoir engineering conventions.
    """
    if not state["physics_ok"]:
        return {"engineering_feedback": "Skipped — physics check failed."}

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {
            "engineering_feedback":
                "ANTHROPIC_API_KEY not set — engineering QA skipped. "
                "Physics checks passed; parameters appear physically consistent."
        }

    try:
        llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0, max_tokens=400)

        prompt = f"""You are a senior reservoir engineer reviewing SCAL model inputs.
System    : {state['system']}
Method    : {state['method']}
Swc       : {state['swc']:.3f}
S_res     : {state['s_res']:.3f}
Krw_end   : {state['krw_end']:.3f}
Kr_phase  : {state['kr_phase_end']:.3f}
Params    : {state['method_params']}

Provide a concise 2-3 sentence engineering assessment:
1. Are the parameters consistent with typical oilfield SCAL data for this system?
2. Flag any concerns (e.g. unusually low/high exponents, wettability implications).
3. Comment on suitability for Eclipse reservoir simulation.
Reply in plain text, no bullet points."""

        resp = llm.invoke([HumanMessage(content=prompt)])
        return {"engineering_feedback": resp.content.strip()}

    except Exception as exc:
        return {"engineering_feedback": f"LLM QA unavailable ({exc}). Physics checks passed."}


# ─────────────────────────────────────────────────────────────────────────────
# NODE 3 — Final report synthesis
# ─────────────────────────────────────────────────────────────────────────────

def report_synthesis_node(state: AgentState) -> dict:
    """
    Assembles the final diagnostic report from upstream node outputs.
    """
    lines = [
        "=" * 60,
        "SCAL AGENT DIAGNOSTIC REPORT",
        "=" * 60,
        f"Method  : {state['method']}",
        f"System  : {state['system']}",
        f"Swc     : {state['swc']:.4f}   S_res : {state['s_res']:.4f}",
        f"Krw_end : {state['krw_end']:.4f}   Kr_phase : {state['kr_phase_end']:.4f}",
        "",
        "── Physics Check ──",
        "PASSED" if state["physics_ok"] else "FAILED",
    ]

    if state["physics_errors"]:
        for err in state["physics_errors"]:
            lines.append(f"  ✗ {err}")

    lines += [
        "",
        "── Engineering QA ──",
        state.get("engineering_feedback", "N/A"),
        "=" * 60,
    ]

    return {"final_report": "\n".join(lines)}


# ─────────────────────────────────────────────────────────────────────────────
# ROUTING LOGIC
# ─────────────────────────────────────────────────────────────────────────────

def route_after_physics(state: AgentState) -> str:
    """Skip EngineeringQA if physics failed — go straight to report."""
    return "EngineeringQA" if state["physics_ok"] else "ReportSynthesis"


# ─────────────────────────────────────────────────────────────────────────────
# BUILD GRAPH
# ─────────────────────────────────────────────────────────────────────────────

def build_agent():
    wf = StateGraph(AgentState)
    wf.add_node("PhysicsCheck",    physics_check_node)
    wf.add_node("EngineeringQA",   engineering_qa_node)
    wf.add_node("ReportSynthesis", report_synthesis_node)

    wf.set_entry_point("PhysicsCheck")
    wf.add_conditional_edges("PhysicsCheck", route_after_physics)
    wf.add_edge("EngineeringQA",   "ReportSynthesis")
    wf.add_edge("ReportSynthesis", END)

    return wf.compile()


agent_router = build_agent()
