"""Static compilation for CF-FARP ExecutionPlan authoring facts."""

from .execution_plan import (
    COMPILED_PLAN_SCHEMA,
    ExecutionPlanCompileError,
    build_execution_plan_source_digest,
    compile_execution_plan,
)

__all__ = [
    "COMPILED_PLAN_SCHEMA",
    "ExecutionPlanCompileError",
    "build_execution_plan_source_digest",
    "compile_execution_plan",
]
