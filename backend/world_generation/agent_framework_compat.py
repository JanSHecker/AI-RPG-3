from __future__ import annotations

from functools import update_wrapper
from typing import Any, Awaitable, Callable, Optional


AGENT_FRAMEWORK_AVAILABLE = False

try:
    from agent_framework import step as _agent_framework_step
    from agent_framework import workflow as _agent_framework_workflow

    AGENT_FRAMEWORK_AVAILABLE = True
except ImportError:
    _agent_framework_step = None
    _agent_framework_workflow = None


class WorkflowRunResultShim:
    def __init__(self, output: Any):
        self._output = output

    def get_outputs(self) -> list[Any]:
        return [self._output]

    def get_intermediate_outputs(self) -> list[Any]:
        return []

    def get_request_info_events(self) -> list[Any]:
        return []

    def get_final_state(self) -> str:
        return "IDLE"


class FunctionalWorkflowShim:
    def __init__(self, func: Callable[..., Awaitable[Any]], name: Optional[str] = None):
        self._func = func
        self.name = name or func.__name__
        update_wrapper(self, func)

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return await self._func(*args, **kwargs)

    async def run(self, *args: Any, **kwargs: Any) -> WorkflowRunResultShim:
        return WorkflowRunResultShim(await self._func(*args, **kwargs))


def workflow(
    func: Optional[Callable[..., Awaitable[Any]]] = None,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    checkpoint_storage: Any = None,
):
    if _agent_framework_workflow is not None:
        return _agent_framework_workflow(
            func,
            name=name,
            description=description,
            checkpoint_storage=checkpoint_storage,
        )

    def decorator(target: Callable[..., Awaitable[Any]]) -> FunctionalWorkflowShim:
        return FunctionalWorkflowShim(target, name=name)

    if func is not None:
        return decorator(func)
    return decorator


def step(func: Optional[Callable[..., Awaitable[Any]]] = None, *, name: Optional[str] = None):
    if _agent_framework_step is not None:
        return _agent_framework_step(func, name=name)

    def decorator(target: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        return target

    if func is not None:
        return decorator(func)
    return decorator
