"""PRAMAANA — MLflow 3 agentic tracing wrappers.

Every tool call, every agent step, every LLM invocation passes through here.
This is what wins us the 10% UX/Transparency bucket.
"""
import functools
import os
import mlflow
from typing import Callable, Any


def _init_experiment() -> None:
    """Set MLflow experiment from env; call after dotenv is loaded.

    Do NOT call set_tracking_uri() in Databricks notebooks — it reads
    spark.mlflow.modelRegistryUri which is unavailable on serverless.
    Databricks auto-configures the MLflow tracking server.
    """
    experiment_name = os.environ.get("MLFLOW_EXPERIMENT_NAME", "/pramaana")
    mlflow.set_experiment(experiment_name)


def _require_tracing() -> None:
    """Fail loudly when MLflow tracing is unavailable; serves UX/Transparency."""
    if not hasattr(mlflow, "start_span"):
        raise RuntimeError(
            f"MLflow {mlflow.__version__} does not expose mlflow.start_span(). "
            "Install MLflow >= 3.1.0 in the Databricks runtime before running agents."
        )


def _trace_safe(value: Any) -> Any:
    """Convert Pydantic and Python objects into MLflow trace-safe payloads."""
    if hasattr(value, "model_dump"):
        return _trace_safe(value.model_dump())
    if isinstance(value, dict):
        return {str(k): _trace_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_trace_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def traced_tool(tool_name: str, span_type: str = "TOOL"):
    """Decorator to trace any agent tool call.
    
    Usage:
        @traced_tool("tavily_web_search", span_type="RETRIEVER")
        def search_web(query: str) -> dict:
            ...
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> Any:
            _require_tracing()
            with mlflow.start_span(name=tool_name, span_type=span_type) as span:
                span.set_inputs(_trace_safe({"args": args, "kwargs": kwargs}))
                try:
                    result = fn(*args, **kwargs)
                    span.set_outputs(_trace_safe({"result": result}))
                    return result
                except Exception as e:
                    span.set_status("ERROR", description=str(e))
                    raise
        return wrapper
    return decorator


def trace_agent_run(agent_name: str):
    """Wrap an entire multi-step agent run as a parent span."""
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> Any:
            _require_tracing()
            with mlflow.start_span(name=f"agent::{agent_name}", span_type="AGENT") as span:
                span.set_inputs(_trace_safe({"args": args, "kwargs": kwargs}))
                result = fn(*args, **kwargs)
                span.set_outputs(_trace_safe({"result": result}))
                return result
        return wrapper
    return decorator