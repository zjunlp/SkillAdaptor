"""Tests for task context registry and PinchBench adapter provider."""

from pathlib import Path
from adapters.pinchbench_adapter.task_context import PinchBenchTaskContextProvider, install_pinchbench_task_context
from core.task_context import load_task_context_for_inference, load_task_markdown, register_task_context_provider, truncate_task_markdown_for_inference

def test_truncate_strips_answers():
    md = '## Prompt\nDo stuff.\n\n## Grading Criteria\n- [ ] x\n'
    out = truncate_task_markdown_for_inference(md)
    assert 'Grading' not in out
    assert 'Do stuff' in out

def test_pinchbench_provider(tmp_path: Path):
    tasks = tmp_path / 'tasks'
    tasks.mkdir()
    (tasks / 'task_a.md').write_text('## Prompt\nAnalyze logs.\n\n## Expected Behavior\nsecret answers\n', encoding='utf-8')
    register_task_context_provider(PinchBenchTaskContextProvider(str(tmp_path), 'tasks'))
    assert 'secret' not in load_task_context_for_inference('task_a')
    assert 'secret' in load_task_markdown('task_a')
    register_task_context_provider(None)
