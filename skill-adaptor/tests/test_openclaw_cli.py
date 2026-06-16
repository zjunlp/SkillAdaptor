"""OpenClaw CLI resolution on Windows npm shims."""

from __future__ import annotations
import os
import sys
import pytest
from core.openclaw_cli import resolve_openclaw_executable
from core.openclaw_hygiene import openclaw_agent_id, openclaw_agent_slug

def test_openclaw_agent_id_normalizes_dots():
    assert openclaw_agent_id('gpt-4.1') == 'bench-gpt-4-1'
    assert openclaw_agent_slug('openrouter/openai/gpt-4o-mini') == 'openrouter-openai-gpt-4o-mini'

def test_resolve_openclaw_finds_npm_shim():
    npm = os.path.join(os.environ.get('USERPROFILE', ''), 'AppData', 'Roaming', 'npm')
    if not os.path.isdir(npm):
        pytest.skip('npm global bin not present')
    path = os.environ.get('PATH', '')
    os.environ['PATH'] = npm + os.pathsep + path
    exe = resolve_openclaw_executable()
    assert exe.lower().endswith(('openclaw', 'openclaw.cmd', 'openclaw.exe'))
