"""PRAMAANA — MLflow 3 agentic tracing wrappers.

Every tool call, every agent step, every LLM invocation passes through here.
This is what wins us the 10% UX/Transparency bucket.
"""
import functools
import os
import mlflow
from typing import Callable, Any


def _init_experiment() -> None:
    """Set MLflow experiment from env; must be called after dotenv is loaded."""
    experiment_name = os.environ.get("MLFLOW_EXPERIMENT_NAME", "/pramaana")
    mlflow.set_experiment(experiment_name)


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
            with mlflow.start_span(name=tool_name, span_type=span_type) as span:
                span.set_inputs({"args": args, "kwargs": kwargs})
                try:
                    result = fn(*args, **kwargs)
                    span.set_outputs({"result": result})
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
            with mlflow.start_span(name=f"agent::{agent_name}", span_type="AGENT") as span:
                span.set_inputs({"args": args, "kwargs": kwargs})
                result = fn(*args, **kwargs)
                span.set_outputs({"result": result})
                return result
        return wrapper
    return decorator