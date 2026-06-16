"""Execution errors for benchmark adapters — fail fast, no silent None returns."""

from __future__ import annotations


class TaskExecutionError(RuntimeError):
    pass


class GatewayUnavailableError(RuntimeError):
    pass
