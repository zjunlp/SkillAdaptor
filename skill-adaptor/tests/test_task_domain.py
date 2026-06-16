"""Tests for core.task_domain (benchmark-agnostic, leak-safe)."""

from core.task_domain import extract_grading_rubric, generator_workflow_anchor, infer_task_category, is_meta_improvement, resolve_domain_principle
SAMPLE_TASK = '---\ncategory: analysis\n---\n## Prompt\nSummarize csv and xlsx into a report file.\n\n## Expected Behavior\nKey expected values:\n- total revenue: $119,900\n\n## Grading Criteria\n- [ ] Agent successfully reads the CSV file\n- [ ] Summary report file `data_summary.md` is created\n- [ ] Total revenue is correctly reported (~$119,900)\n- [ ] Top region by revenue is identified (East)\n'

def test_infer_category_from_frontmatter():
    assert infer_task_category('', SAMPLE_TASK) == 'analysis'

def test_meta_improvement():
    assert is_meta_improvement('Capture and document all action transcripts')
    assert not is_meta_improvement('Parse inputs, compute aggregates, write report deliverable')

def test_resolve_principle_no_filenames():
    p = resolve_domain_principle('Summarize csv and excel data', SAMPLE_TASK)
    assert 'quarterly_sales' not in p
    assert 'data_summary.md' not in p
    assert 'parse' in p.lower() or 'aggregate' in p.lower()

def test_grading_rubric_strips_answers():
    rubric = extract_grading_rubric(SAMPLE_TASK)
    assert '$119,900' not in rubric
    assert 'East' not in rubric
    assert 'data_summary.md' not in rubric
    assert 'deliverable' in rubric.lower() or '[ ]' in rubric

def test_workflow_anchor_generic():
    block = generator_workflow_anchor('parse log file for errors', '', 'task_x')
    assert 'log analysis' in block.lower() or 'log' in block.lower()
    assert 'nginx_access' not in block
