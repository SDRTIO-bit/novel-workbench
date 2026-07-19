"""Standalone, filesystem-scoped MCP server for external evaluation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from tools.novel_eval_mcp.storage import EvaluationStore


REPO_ROOT = Path(__file__).resolve().parents[2]
# This service is intentionally not configurable to another directory: its
# sole mutable capability is writing validated result files below this root.
EVALUATION_ROOT = REPO_ROOT / "__evaluation"
store = EvaluationStore(EVALUATION_ROOT)
mcp = FastMCP("novel-workbench-evaluation")


@mcp.tool()
def list_evaluation_cases() -> list[dict[str, Any]]:
    """List frozen evaluation cases and their execution status."""
    return store.list_evaluation_cases()


@mcp.tool()
def get_blind_pair(case_id: str) -> dict[str, str]:
    """Return only the anonymous A/B reader package for one evaluation case."""
    return store.get_blind_pair(case_id)


@mcp.tool()
def get_planner_contract(case_id: str) -> dict[str, Any]:
    """Return the Planner contract after the anonymous assessment is recorded."""
    return store.get_planner_contract(case_id)


@mcp.tool()
def get_pipeline_evidence(case_id: str) -> dict[str, Any]:
    """Return source-attributed pipeline evidence after contract auditing."""
    return store.get_pipeline_evidence(case_id)


@mcp.tool()
def save_evaluation_result(case_id: str, result: dict[str, Any]) -> dict[str, Any]:
    """Validate and save an external evaluation only under __evaluation/results/."""
    return store.save_evaluation_result(case_id, result)


@mcp.tool()
def get_evaluation_summary() -> dict[str, Any]:
    """Return the saved external-evaluation results and remaining cases."""
    return store.get_evaluation_summary()


if __name__ == "__main__":
    mcp.run()
