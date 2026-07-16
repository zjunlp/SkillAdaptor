"""Shared skill injection helpers — every bench / harness must deliver skills to the agent.

Contract:
  1. Normalize SKILL.md (YAML frontmatter + body).
  2. Write to all discovery paths for the harness + benchmark_root.
  3. Verify each write (fail closed).
  4. Prefer also inlining into the agent prompt when the runtime supports it
     (claw-eval system_prompt_prefix, workspace user prompt, WebShop LLM prompt).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from runtime.skill_export import build_frontmatter

EVOLVED_SKILL_DIR = 'skill-adaptor-evolved'
DEFAULT_DESCRIPTION = (
    'SkillAdaptor evolved skill — follow procedures when relevant to the task.'
)


def ensure_skill_markdown(
    skill_text: str,
    *,
    skill_id: str = EVOLVED_SKILL_DIR,
    description: str = DEFAULT_DESCRIPTION,
) -> str:
    """Ensure YAML frontmatter so OpenClaw / Claude / Codex / Hermes can load the skill."""
    if not skill_text or not str(skill_text).strip():
        return ''
    text = str(skill_text)
    if text.lstrip().startswith('---'):
        return text if text.endswith('\n') else text + '\n'
    fm = build_frontmatter(
        skill_id,
        description,
        'Apply when the task matches the failure pattern this skill was adapted for.',
    )
    return fm + text.strip() + '\n'


def skill_content_marker(skill_text: str) -> str:
    if '# SKILLS' in skill_text:
        return '# SKILLS'
    stripped = skill_text.strip()
    return stripped[:80] if stripped else ''


def verify_skill_file(
    path: Path,
    *,
    expected_marker: str = '',
    min_chars: int = 40,
) -> None:
    """Raise RuntimeError if path is missing, empty, or missing frontmatter/name."""
    if not path.exists():
        raise RuntimeError(f'Skill inject verification failed: missing {path}')
    on_disk = path.read_text(encoding='utf-8')
    if len(on_disk.strip()) < min_chars:
        raise RuntimeError(f'Skill inject verification failed: empty/too short {path}')
    stripped = on_disk.lstrip()
    if not stripped.startswith('---'):
        raise RuntimeError(f'Skill inject verification failed: missing YAML frontmatter in {path}')
    parts = stripped.split('---', 2)
    if len(parts) < 3 or 'name:' not in parts[1]:
        raise RuntimeError(f'Skill inject verification failed: frontmatter name missing in {path}')
    if expected_marker and expected_marker not in on_disk:
        raise RuntimeError(
            f'Skill inject verification failed: content mismatch in {path} '
            f'(marker={expected_marker!r})'
        )


def write_and_verify_skill_files(
    paths: Sequence[Path],
    skill_markdown: str,
    *,
    expected_marker: str = '',
) -> List[Path]:
    """Write identical SKILL.md to each path and verify. Returns written paths."""
    if not skill_markdown.strip():
        raise RuntimeError('Skill inject refused empty skill markdown')
    marker = expected_marker or skill_content_marker(skill_markdown)
    written: List[Path] = []
    for path in paths:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(skill_markdown, encoding='utf-8')
        verify_skill_file(path, expected_marker=marker, min_chars=20)
        written.append(path)
    return written


def common_benchmark_skill_paths(
    benchmark_root: Path,
    *,
    task_id: Optional[str] = None,
    tasks_subdir: str = 'tasks',
) -> List[Path]:
    """Disk locations every benchmark agent may discover."""
    root = Path(benchmark_root)
    paths = [
        root / '.skill' / 'SKILL.md',
        root / 'skills' / EVOLVED_SKILL_DIR / 'SKILL.md',
    ]
    if task_id:
        paths.append(root / tasks_subdir / task_id / '.skill' / 'SKILL.md')
        # Workspace plugin tasks are flat markdown briefs, not tasks/<id>/
        paths.append(root / 'input_task' / '.skill' / f'{task_id}.SKILL.md')
    return paths


def openclaw_bound_workspace(benchmark_root: Path) -> Optional[Path]:
    """Workspace bound by OpenClawHarnessRunner (plugin path), if any."""
    marker = Path(benchmark_root) / '.skill-adaptor' / 'openclaw_agent.json'
    if not marker.exists():
        return None
    try:
        data = json.loads(marker.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None
    ws = (data.get('workspace') or '').strip()
    if not ws:
        return None
    path = Path(ws)
    return path if path.exists() else None


def openclaw_skill_targets(benchmark_root: Path, *, task_id: Optional[str] = None) -> List[Path]:
    """All OpenClaw-visible SKILL.md targets (global + bound workspace + bench)."""
    root = Path(benchmark_root)
    targets = common_benchmark_skill_paths(root, task_id=task_id)
    targets.append(Path.home() / '.openclaw' / 'workspace' / 'skills' / EVOLVED_SKILL_DIR / 'SKILL.md')
    bound = openclaw_bound_workspace(root)
    if bound is not None:
        targets.append(bound / 'skills' / EVOLVED_SKILL_DIR / 'SKILL.md')
        targets.append(bound / '.skill' / 'SKILL.md')
    # Deduplicate while preserving order
    seen = set()
    out: List[Path] = []
    for p in targets:
        key = str(p.resolve()) if p.parent.exists() or True else str(p)
        try:
            key = str(p.resolve())
        except OSError:
            key = str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def inline_skill_for_prompt(skill_text: str, *, max_chars: int = 4500) -> str:
    """Agent-visible inline block (does not rely on sandbox/disk skill discovery)."""
    md = ensure_skill_markdown(skill_text)
    if not md:
        return ''
    body = md[:max_chars]
    truncated = len(md) > max_chars
    note = '\n\n<!-- skill truncated for prompt budget -->\n' if truncated else '\n'
    return (
        '# SkillAdaptor evolved skills (INLINED — follow these procedures)\n'
        'The skill body below is authoritative for this task. Prefer it over ad-hoc guesses. '
        'You do not need a separate SKILL.md read to apply it.\n\n'
        f'{body}{note}'
    )


def format_skills_for_llm_prompt(skills: Iterable, *, max_chars: int = 3500) -> str:
    """Full procedure block for WebShop / direct LLM policies (title + when + body)."""
    chunks: List[str] = []
    used = 0
    for i, skill in enumerate(skills, 1):
        title = getattr(skill, 'title', None) or getattr(skill, 'id', f'skill_{i}')
        when = (getattr(skill, 'when_to_apply', None) or '').strip()
        desc = (getattr(skill, 'description', None) or '').strip()
        body = (getattr(skill, 'body', None) or '').strip()
        block = f'### Skill {i}: {title}\n'
        if when:
            block += f'When to apply: {when}\n'
        if desc:
            block += f'{desc}\n'
        if body:
            # Prefer procedure body — this is what agents must follow.
            remain = max_chars - used - len(block) - 20
            if remain < 80:
                break
            block += f'\nProcedure:\n{body[:remain]}\n'
        if used + len(block) > max_chars:
            break
        chunks.append(block)
        used += len(block)
    if not chunks:
        return ''
    return (
        '【Relevant Skills — FOLLOW PROCEDURES WHEN APPLICABLE】\n'
        + '\n---\n'.join(chunks)
        + "\n\nWhen the situation matches a skill's 'when_to_apply', follow that skill's Procedure.\n"
    )
