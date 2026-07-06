"""Install adapter-specific runtime (hints + optional task context hooks)."""

from __future__ import annotations
from runtime.adapter_registry import AdapterSpec

def bootstrap_adapter_runtime(spec: AdapterSpec) -> None:
    key = spec.benchmark_key
    if key in ('pinchbench',):
        from adapters.pinchbench_adapter.hints import install_pinchbench_hints
        install_pinchbench_hints()
        return
    if key in ('workspace', 'openclaw-generic', 'openclaw'):
        from core.adapter_hints import activate_benchmark_hints
        activate_benchmark_hints('generic')
        return
    if key == 'webshop':
        from adapters.webshop_adapter.hints import install_webshop_hints
        install_webshop_hints()
        return
    if key in ('claw-eval', 'claw_eval'):
        from adapters.claw_eval_adapter.hints import install_claw_eval_hints
        install_claw_eval_hints()
        return
    from core.adapter_hints import activate_benchmark_hints
    activate_benchmark_hints('generic')
