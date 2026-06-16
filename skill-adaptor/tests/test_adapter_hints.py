"""Adapter hint registration tests."""

from __future__ import annotations
from core.adapter_hints import get_active_hints, reset_adapter_hints
from adapters.pinchbench_adapter.hints import install_pinchbench_hints
from adapters.webshop_adapter.hints import install_webshop_hints

def test_pinchbench_hints_active() -> None:
    reset_adapter_hints()
    install_pinchbench_hints()
    hints = get_active_hints()
    assert hints.benchmark == 'pinchbench'
    assert 'PinchBench adapter' in hints.generator_supplement
    assert 'EvoSkill' not in hints.generator_supplement
    assert 'SkillsBench' not in hints.localizer_supplement

def test_webshop_hints_switch() -> None:
    reset_adapter_hints()
    install_webshop_hints()
    hints = get_active_hints()
    assert hints.benchmark == 'webshop'
    assert 'click[buy]' in hints.generator_supplement or 'purchase' in hints.generator_supplement.lower()
