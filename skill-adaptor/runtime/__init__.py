"""Pluggable plugin runtime (benchmark-agnostic entry)."""

from .adapter_registry import AdapterSpec, resolve_adapter
from .plugin_host import PluginHost
from .task_loader import TaskManifest, load_tasks_from_workspace
__all__ = ['AdapterSpec', 'PluginHost', 'TaskManifest', 'load_tasks_from_workspace', 'resolve_adapter']
