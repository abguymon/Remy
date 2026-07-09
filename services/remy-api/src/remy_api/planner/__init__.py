"""Planner: the plain, persisted state machine driving the golden path (T5).

Public surface is :mod:`remy_api.planner.machine` (used by ``routers/plan.py`` and,
later, the MCP facade T6). Steps, consolidation, and substitution are internal.
"""

from remy_api.planner import machine
from remy_api.planner.schemas import PlanSnapshot

__all__ = ["machine", "PlanSnapshot"]
