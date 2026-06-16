"""Benchmark-agnostic task domain helpers for Localizer / Generator."""

from __future__ import annotations
import re
from typing import Optional
_META_IMPROVEMENT_TOKENS = ('transcript', 'capture action', 'capture and document', 'log all action', 'document action', 'action logging', 'session_status', 'observability', 'monitor agent', 'record every step', 'logging protocol')
_PROCEDURE_TOKENS = ('read', 'parse', 'write', 'compute', 'verify', 'validate', 'run', 'test', 'grep', 'search', 'edit', 'fix', 'inspect', 'aggregate', 'fallback', 'recompute', 'retry', 'check', 'execute', 'apply', 'rename', 'refactor', 'output', 'report', 'command', 'file', 'artifact', 'deliverable')
PROCEDURE_VOCABULARY = _PROCEDURE_TOKENS
_CATEGORY_KEYWORDS = {'analysis': ('csv', 'excel', 'xlsx', 'spreadsheet', 'data file', 'aggregate', 'summarize', 'summary report', 'calculate', 'statistics', 'tabular'), 'log_analysis': ('log file', 'log analysis', 'parse log', 'grep', 'json line', 'error rate', 'access log', 'auth log', 'syslog', 'nginx', 'apache'), 'shell': ('shell command', 'command.txt', 'terminal request', 'bash', 'recursive find'), 'coding': ('test suite', 'pytest', 'playwright', 'selector', 'refactor', 'unit test', 'source file', 'implement', 'fix the', 'update the', 'write a test'), 'devops': ('git', 'kubectl', 'kubernetes', 'deployment', 'manifest', 'recovery', 'docker', 'helm', 'yaml'), 'web': ('browser', 'click', 'search[', 'buy[', 'navigate', 'e-commerce', 'product')}
_CATEGORY_PRINCIPLES = {'analysis': 'Read every provided data artifact; parse tabular or structured formats; compute aggregates required by the prompt; write the requested summary deliverable; if primary parser fails, try an alternate read path and recompute before finalizing.', 'log_analysis': 'Stream-parse the log artifact line by line; extract metrics the prompt asks for; aggregate with verifiable counts; write a structured report deliverable; skip or quarantine malformed lines and note the skip count.', 'shell': 'Translate the prompt into one executable shell command matching all constraints; save only the command to the required output artifact; sanity-run in workspace if possible.', 'coding': "Inspect relevant source artifacts before editing; make minimal targeted changes; run the project's test or lint command; iterate until automated checks pass.", 'devops': 'Inspect system or repo state read-only before any mutation; use concrete values from inspection (no placeholders); validate configuration before apply.', 'web': 'Decompose constraints from the instruction; verify each attribute before commitment; prefer inspect-then-act over blind navigation loops.', 'general': 'Parse objective and hard constraints from the prompt; execute a short action chain; on tool or parse failure switch to a named fallback; verify required deliverables exist and match rubric-shaped checks before finishing.'}
_WORKFLOW_ANCHORS = {'analysis': '\n## Workflow anchor (category: data analysis)\n- **Primary**: open/read inputs → parse → compute required aggregates → write summary deliverable.\n- **Fallback**: if format parser fails, try alternate reader or partial sheet discovery.\n- **Verify**: recompute key totals; revise deliverable if internal consistency fails.\n- **Scope**: skill applies only when task involves tabular/data summarization (not generic logging).\n', 'log_analysis': '\n## Workflow anchor (category: log analysis)\n- **Primary**: load log → parse lines → filter/aggregate per prompt → write report deliverable.\n- **Fallback**: tolerate bad lines; keep running counts consistent.\n- **Verify**: counts reconcile with line totals cited in report.\n- **Scope**: skill applies only for log parsing/report tasks.\n', 'shell': '\n## Workflow anchor (category: shell)\n- **Primary**: one command satisfying all prompt constraints → save to required output artifact.\n- **Verify**: command is non-empty, executable, no prose mixed in.\n- **Scope**: skill applies only when deliverable is a shell command file.\n', 'coding': '\n## Workflow anchor (category: coding)\n- **Primary**: read sources → minimal edit or generate tests → run test runner.\n- **Fallback**: after two failed attempts, re-read structure and change approach.\n- **Verify**: automated test or lint signal passes.\n- **Scope**: skill applies only for code/test maintenance tasks.\n', 'devops': '\n## Workflow anchor (category: devops)\n- **Primary**: read-only inspect → plan → mutate with concrete values → validate.\n- **Verify**: dry-run or status command confirms expected state.\n- **Scope**: skill applies only for infra/repo operations tasks.\n', 'web': '\n## Workflow anchor (category: web interaction)\n- **Primary**: search/browse → inspect candidate → verify attributes → commit action.\n- **Verify**: chosen item satisfies all stated constraints.\n- **Scope**: skill applies only for interactive shopping/navigation tasks.\n', 'general': '\n## Workflow anchor (general)\n- **Primary**: constraint parse → short action chain → deliverable write.\n- **Fallback**: on repeated failure, switch tactic (max 3 identical retries).\n- **Verify**: required output artifacts exist and pass rubric-shaped checks.\n- **Scope**: keep skill narrow—state observation triggers, not task names or IDs.\n'}
_ANSWER_LEAK_PATTERNS = [re.compile('\\$[\\d,]+(?:\\.\\d+)?'), re.compile('~\\$[\\d,]+'), re.compile('\\b\\d{1,3}(?:,\\d{3})*(?:\\.\\d+)?\\s*%'), re.compile('\\bscore[:\\s]+[\\d.]+', re.I), re.compile('key expected values?:.*', re.I), re.compile('total (?:revenue|profit|expenses?).*:\\s*\\$', re.I), re.compile('top (?:region|product|department|employee).*[\\(:]', re.I)]
_FILENAME_IN_BACKTICKS = re.compile('`([^`]+)`')
_FRONTMATTER_CATEGORY = re.compile('^category:\\s*(\\w+)', re.MULTILINE)

def infer_task_category(task_description: str='', task_brief: str='', task_id: str='') -> str:
    combined = f'{task_description}\n{task_brief}'.lower()
    m = _FRONTMATTER_CATEGORY.search(task_brief)
    if m:
        raw = m.group(1).lower()
        if raw in _CATEGORY_PRINCIPLES:
            return raw
        if raw in ('skills', 'workflow', 'research'):
            return 'general'
    scores: dict[str, int] = {cat: 0 for cat in _CATEGORY_KEYWORDS}
    for cat, keywords in _CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in combined:
                scores[cat] += 1
    best = max(scores, key=scores.get)
    if scores[best] > 0:
        return best
    tid = task_id.lower().replace('-', '_')
    for cat, keywords in _CATEGORY_KEYWORDS.items():
        if any((kw.replace(' ', '_') in tid for kw in keywords)):
            return cat
    return 'general'

def is_meta_improvement(text: str) -> bool:
    lower = text.lower()
    if any((tok in lower for tok in _PROCEDURE_TOKENS)):
        meta_hits = sum((1 for t in _META_IMPROVEMENT_TOKENS if t in lower))
        proc_hits = sum((1 for t in _PROCEDURE_TOKENS if t in lower))
        return meta_hits >= 2 and proc_hits < 2
    return any((t in lower for t in _META_IMPROVEMENT_TOKENS))

def resolve_domain_principle(task_description: str='', task_brief: str='', task_id: str='') -> str:
    cat = infer_task_category(task_description, task_brief, task_id)
    return _CATEGORY_PRINCIPLES.get(cat, _CATEGORY_PRINCIPLES['general'])

def generator_workflow_anchor(task_description: str='', task_brief: str='', task_id: str='') -> str:
    cat = infer_task_category(task_description, task_brief, task_id)
    return _WORKFLOW_ANCHORS.get(cat, _WORKFLOW_ANCHORS['general']).strip()

def _generalize_criterion_line(line: str) -> Optional[str]:
    stripped = line.strip()
    if not stripped:
        return None
    lower = stripped.lower()
    if any((p.search(stripped) for p in _ANSWER_LEAK_PATTERNS)):
        return None
    if 'expected values' in lower or 'key expected' in lower:
        return None
    if re.search('\\(~?\\$?', stripped) and re.search('\\d', stripped):
        if 'correctly' in lower or 'identified' in lower or 'reported' in lower:
            return re.sub('\\[?\\]?\\s*-?\\s*\\[?\\s*\\]?\\s*', '', '- [ ] Numeric or ranked result matches independently recomputed values') if 'correctly' in lower or '~' in stripped else None

    def _repl_file(m: re.Match) -> str:
        name = m.group(1).lower()
        if any((name.endswith(ext) for ext in ('.md', '.txt', '.json', '.csv', '.xlsx', '.log', '.py', '.sh'))):
            if 'test' in name or name.startswith('test_'):
                return '[test artifact]'
            if 'command' in name:
                return '[command output artifact]'
            if name.endswith('.md'):
                return '[report deliverable]'
            if name.endswith(('.csv', '.xlsx')):
                return '[input data file]'
            if name.endswith('.log'):
                return '[log input file]'
            return '[workspace artifact]'
        return '[artifact]'
    generalized = _FILENAME_IN_BACKTICKS.sub(_repl_file, stripped)
    generalized = re.sub('\\s*\\([^)]*\\d[^)]*\\)\\s*', ' ', generalized)
    generalized = re.sub('\\s+', ' ', generalized).strip()
    shape_rules = [('reads? the (?:csv|excel|input)', '- [ ] Required input data artifacts are read successfully'), ('reads?.*file', '- [ ] Required input artifacts are read successfully'), ('creates?|writes?.*report|summary', '- [ ] Required summary/report deliverable is created'), ('command.*created|non-empty', '- [ ] Command deliverable exists and is executable shell'), ('test.*pass|pytest|test suite', '- [ ] Automated tests pass or test artifact meets coverage rubric'), ('well-structured|readable', '- [ ] Output structure matches prompt format requirements'), ('correctly (?:reported|calculated|identified)', '- [ ] Stated metrics match recomputed values')]
    for pattern, replacement in shape_rules:
        if re.search(pattern, generalized, re.I):
            return replacement
    if stripped.startswith('- [ ]') or stripped.startswith('* [ ]'):
        out = re.sub('`[^`]+`', '[artifact]', generalized)
        out = re.sub('\\$[\\d,.]+', '[metric]', out)
        out = re.sub('~\\$[\\d,.]+', '[metric]', out)
        out = re.sub('\\b\\d{2,}\\b', '[n]', out)
        if '[metric]' in out or '[artifact]' in out or '[n]' in out:
            return out
        if re.search('\\b[A-Z][a-z]+ [A-Z][a-z]+\\b', out):
            return None
        return out
    return None

def extract_grading_rubric(task_markdown: str, *, max_items: int=8) -> str:
    if not task_markdown.strip():
        return ''
    sections: list[str] = []
    for header in ('## Grading Criteria', '## Automated Checks', '## Expected Behavior'):
        idx = task_markdown.find(header)
        if idx < 0:
            continue
        chunk = task_markdown[idx:idx + 4000]
        next_sec = re.search('\\n## (?!#)', chunk[10:])
        if next_sec:
            chunk = chunk[:10 + next_sec.start()]
        lines = chunk.splitlines()
        rubric_lines: list[str] = []
        for line in lines:
            if line.strip().startswith('- [ ]') or line.strip().startswith('* [ ]'):
                gen = _generalize_criterion_line(line)
                if gen and gen not in rubric_lines:
                    rubric_lines.append(gen)
            elif re.match('^\\d+\\.\\s+', line.strip()):
                gen = _generalize_criterion_line('- [ ] ' + line.strip().split('.', 1)[-1].strip())
                if gen and gen not in rubric_lines:
                    rubric_lines.append(gen)
        if rubric_lines:
            sections.extend(rubric_lines[:max_items])
            break
    if not sections:
        return 'Rubric shapes (generic): deliverable exists; inputs read; metrics internally consistent; format matches prompt.'
    return 'Leak-free rubric shapes (verify procedure against these, not specific answers):\n' + '\n'.join(sections[:max_items])
task_category = infer_task_category
resolve_domain_hint = resolve_domain_principle
generator_domain_block = generator_workflow_anchor
extract_grading_snippet = extract_grading_rubric
