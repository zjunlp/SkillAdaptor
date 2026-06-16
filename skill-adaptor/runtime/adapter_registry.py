"""Pluggable benchmark adapters — core TGWS pipeline stays fixed; env wiring varies."""

from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Callable, Optional

@dataclass(frozen=True)
class AdapterSpec:
    name: str
    benchmark_key: str
    run_fn_name: str
    requires_path_env: Optional[str] = None

def resolve_adapter(env: Optional[str]=None, *, prefer_openclaw: bool=True) -> AdapterSpec:
    key = (env or os.environ.get('SkillAdaptor_BENCHMARK_ENV', '')).strip().lower()
    if key in ('pinchbench', 'pb'):
        return AdapterSpec('pinchbench', 'pinchbench', 'run_pinchbench', 'PINCHBENCH_PATH')
    if key in ('claw-eval', 'claw_eval', 'claweval'):
        return AdapterSpec('claw-eval', 'claw-eval', 'run_claw_eval', 'CLAW_EVAL_PATH')
    if key in ('webshop', 'ws'):
        return AdapterSpec('webshop', 'webshop', 'run_webshop', 'WEBSHOP_PATH')
    if not key and os.environ.get('PINCHBENCH_PATH'):
        return AdapterSpec('pinchbench', 'pinchbench', 'run_pinchbench', 'PINCHBENCH_PATH')
    if not key and os.environ.get('CLAW_EVAL_PATH'):
        return AdapterSpec('claw-eval', 'claw-eval', 'run_claw_eval', 'CLAW_EVAL_PATH')
    if not key and os.environ.get('WEBSHOP_PATH'):
        return AdapterSpec('webshop', 'webshop', 'run_webshop', 'WEBSHOP_PATH')
    if prefer_openclaw:
        return AdapterSpec('openclaw-generic', 'openclaw-generic', 'run_pinchbench', 'PINCHBENCH_PATH')
    raise ValueError('Cannot resolve adapter: set --env or PINCHBENCH_PATH / CLAW_EVAL_PATH / WEBSHOP_PATH')

def get_run_callable(spec: AdapterSpec) -> Callable:
    from run_skillevolve import run_claw_eval, run_pinchbench, run_webshop
    mapping = {'run_pinchbench': run_pinchbench, 'run_claw_eval': run_claw_eval, 'run_webshop': run_webshop}
    fn = mapping.get(spec.run_fn_name)
    if fn is None:
        raise ValueError(f'Unknown run function: {spec.run_fn_name}')
    return fn
