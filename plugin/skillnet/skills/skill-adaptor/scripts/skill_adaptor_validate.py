#!/usr/bin/env python3
"""Offline structural validation for the skill-adaptor Agent Skill package."""

from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Dict, List, Optional

REQUIRED_FRONTMATTER = {'name', 'description'}
NAME_PATTERN = re.compile(r'^[a-z][a-z0-9-]*[a-z0-9]$')
MAX_DESCRIPTION_LINES = 15
MAX_SKILL_MD_LINES = 500


def parse_frontmatter(text: str) -> Optional[Dict[str, str]]:
    if not text.startswith('---'):
        return None
    end = text.find('\n---', 3)
    if end == -1:
        return None
    block = text[3:end].strip()
    result: Dict[str, str] = {}
    current_key: str | None = None
    for line in block.split('\n'):
        if ':' in line and not line.startswith((' ', '\t')):
            key, _, val = line.partition(':')
            key = key.strip()
            val = val.strip()
            if val == '|':
                current_key = key
                result[key] = ''
            else:
                current_key = None
                result[key] = val
        elif current_key and line.startswith((' ', '\t')):
            result[current_key] += line.strip() + '\n'
    for k, v in list(result.items()):
        if isinstance(v, str):
            result[k] = v.strip()
    return result


def validate(skill_dir: str, strict: bool = False) -> List[str]:
    issues: List[str] = []
    skill_md = os.path.join(skill_dir, 'SKILL.md')
    if not os.path.isfile(skill_md):
        issues.append('SKILL.md not found')
        return issues
    with open(skill_md, encoding='utf-8') as f:
        content = f.read()
    lines = content.split('\n')
    if len(lines) > MAX_SKILL_MD_LINES:
        issues.append(f'SKILL.md is {len(lines)} lines (recommended ≤{MAX_SKILL_MD_LINES})')
    fm = parse_frontmatter(content)
    if fm is None:
        issues.append('No YAML frontmatter (expected --- delimiters)')
        return issues
    for field in REQUIRED_FRONTMATTER:
        if field not in fm or not fm[field]:
            issues.append(f'Missing required frontmatter field: {field}')
    name = fm.get('name', '')
    if name and not NAME_PATTERN.match(name):
        issues.append(f"Name '{name}' should be lowercase alphanumeric with hyphens")
    desc = fm.get('description', '')
    if desc:
        desc_lines = [ln for ln in desc.split('\n') if ln.strip()]
        if len(desc_lines) > MAX_DESCRIPTION_LINES:
            issues.append(f'Description is {len(desc_lines)} lines (recommended ≤{MAX_DESCRIPTION_LINES})')
    if strict:
        for sub in ('references', 'scripts'):
            if not os.path.isdir(os.path.join(skill_dir, sub)):
                issues.append(f'Missing {sub}/ directory (recommended)')
    for root, _dirs, files in os.walk(skill_dir):
        for fname in files:
            fpath = os.path.join(root, fname)
            if os.path.getsize(fpath) == 0:
                issues.append(f'Empty file: {os.path.relpath(fpath, skill_dir)}')
    return issues


def main() -> None:
    parser = argparse.ArgumentParser(description='Validate skill-adaptor skill directory (offline).')
    parser.add_argument('skill_dir', nargs='?', default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    parser.add_argument('--strict', action='store_true')
    args = parser.parse_args()
    if not os.path.isdir(args.skill_dir):
        print(f'ERROR: Not a directory: {args.skill_dir}', file=sys.stderr)
        raise SystemExit(1)
    issues = validate(args.skill_dir, strict=args.strict)
    if not issues:
        print(f'OK {os.path.basename(args.skill_dir)}: all checks passed')
        raise SystemExit(0)
    print(f'WARN {os.path.basename(args.skill_dir)}: {len(issues)} issue(s):')
    for issue in issues:
        print(f'  - {issue}')
    raise SystemExit(1)


if __name__ == '__main__':
    main()
