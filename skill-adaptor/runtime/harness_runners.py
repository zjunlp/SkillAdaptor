from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from adapters.errors import TaskExecutionError
from core.openclaw_agent_setup import prepare_openclaw_for_model, slugify_provider_from_base_url
from core.openclaw_cli import resolve_openclaw_executable
from core.openclaw_hygiene import cleanup_agent_sessions, openclaw_agent_id, require_gateway_running

_USE_SHELL = sys.platform == 'win32'


class HarnessRunner(ABC):
    name: str

    @abstractmethod
    def run_task(
        self,
        *,
        task_id: str,
        prompt: str,
        workspace: Path,
        model: str,
        agent_id: str,
        timeout: int,
    ) -> float:
        ...


class OpenClawHarnessRunner(HarnessRunner):
    name = 'openclaw'

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.api_key = api_key
        self.base_url = base_url

    def _run_openclaw(self, args: list[str], *, cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
        exe = resolve_openclaw_executable()
        return subprocess.run(
            [exe, *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            shell=_USE_SHELL,
        )

    def ensure_agent(self, workspace: Path, model: str) -> str:
        agent_id = openclaw_agent_id(model, prefix='ws')
        prepare_openclaw_for_model(model, api_key=self.api_key, base_url=self.base_url, fix_main_auth=True)
        self._bind_workspace(agent_id, workspace, model)
        return agent_id

    def _bind_workspace(self, agent_id: str, workspace: Path, model: str) -> None:
        ws = workspace.resolve()
        marker = ws / '.skill-adaptor' / 'openclaw_agent.json'
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            json.dumps({'agent_id': agent_id, 'workspace': str(ws)}, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        config_path = Path.home() / '.openclaw' / 'openclaw.json'
        if not config_path.exists():
            return
        try:
            config = json.loads(config_path.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            return
        agents = config.setdefault('agents', {}).setdefault('list', [])
        normalized_id = agent_id.replace(':', '-').lower()
        url = (self.base_url or os.environ.get('OPENAI_API_BASE_URL') or '').strip()
        bare = model.split('/', 1)[-1] if '/' in model else model
        resolved_model = f'{slugify_provider_from_base_url(url)}/{bare}' if url else bare
        found = False
        for entry in agents:
            if not isinstance(entry, dict):
                continue
            entry_id = str(entry.get('id', '')).lower()
            if entry_id in {agent_id.lower(), normalized_id}:
                entry['workspace'] = str(ws)
                if resolved_model:
                    entry['model'] = resolved_model
                found = True
                break
        if not found:
            agents.append({'id': agent_id, 'workspace': str(ws), 'model': resolved_model})
        try:
            config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        except OSError:
            pass

    def run_task(
        self,
        *,
        task_id: str,
        prompt: str,
        workspace: Path,
        model: str,
        agent_id: str,
        timeout: int,
    ) -> float:
        cleanup_agent_sessions(agent_id)
        require_gateway_running(max_wait_s=20.0)
        message = f'[SkillAdaptor task_id={task_id}]\n\n{prompt}'
        result = self._run_openclaw(
            ['agent', '--agent', agent_id, '--message', message, '--local'],
            cwd=workspace,
            timeout=timeout,
        )
        if result.returncode != 0:
            stderr = (result.stderr or result.stdout or '')[:500]
            raise TaskExecutionError(f'OpenClaw task {task_id} failed (exit {result.returncode}): {stderr}')
        return time.time()


class ClaudeCodeHarnessRunner(HarnessRunner):
    name = 'claude-code'

    def run_task(
        self,
        *,
        task_id: str,
        prompt: str,
        workspace: Path,
        model: str,
        agent_id: str,
        timeout: int,
    ) -> float:
        import shutil

        claude = shutil.which('claude')
        if not claude:
            raise TaskExecutionError('claude CLI not found for claude-code harness')
        message = f'[SkillAdaptor task_id={task_id}]\n\n{prompt}'
        cmd = [claude, '-p', message, '--output-format', 'json']
        if model:
            cmd.extend(['--model', model])
        started = time.time()
        result = subprocess.run(
            cmd,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            stderr = (result.stderr or result.stdout or '')[:500]
            raise TaskExecutionError(f'Claude Code task {task_id} failed (exit {result.returncode}): {stderr}')
        out_path = workspace / '.skill-adaptor' / 'artifacts' / 'trajectories' / f'{task_id}_claude_stdout.json'
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(result.stdout or '{}', encoding='utf-8')
        return started


class CodexHarnessRunner(HarnessRunner):
    name = 'codex'

    def run_task(
        self,
        *,
        task_id: str,
        prompt: str,
        workspace: Path,
        model: str,
        agent_id: str,
        timeout: int,
    ) -> float:
        import shutil

        codex = shutil.which('codex')
        if not codex:
            raise TaskExecutionError('codex CLI not found for codex harness')
        message = f'[SkillAdaptor task_id={task_id}]\n\n{prompt}'
        started = time.time()
        result = subprocess.run(
            [codex, 'exec', message, '--full-auto'],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            stderr = (result.stderr or result.stdout or '')[:500]
            raise TaskExecutionError(f'Codex task {task_id} failed (exit {result.returncode}): {stderr}')
        out_path = workspace / '.skill-adaptor' / 'artifacts' / 'trajectories' / f'{task_id}_codex_stdout.txt'
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text((result.stdout or '') + '\n' + (result.stderr or ''), encoding='utf-8')
        return started


class HermesHarnessRunner(HarnessRunner):
    name = 'hermes'

    def run_task(
        self,
        *,
        task_id: str,
        prompt: str,
        workspace: Path,
        model: str,
        agent_id: str,
        timeout: int,
    ) -> float:
        import shutil

        hermes = shutil.which('hermes') or shutil.which('hermes-agent')
        if not hermes:
            raise TaskExecutionError('hermes CLI not found for hermes harness')
        message = f'[SkillAdaptor task_id={task_id}]\n\n{prompt}'
        started = time.time()
        result = subprocess.run(
            [hermes, 'run', message],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env={**os.environ, 'HERMES_HOME': os.environ.get('HERMES_HOME', str(Path.home() / '.hermes'))},
        )
        if result.returncode != 0:
            stderr = (result.stderr or result.stdout or '')[:500]
            raise TaskExecutionError(f'Hermes task {task_id} failed (exit {result.returncode}): {stderr}')
        out_path = workspace / '.skill-adaptor' / 'artifacts' / 'trajectories' / f'{task_id}_hermes_stdout.txt'
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text((result.stdout or '') + '\n' + (result.stderr or ''), encoding='utf-8')
        return started


def get_harness_runner(name: str, *, api_key: Optional[str] = None, base_url: Optional[str] = None) -> HarnessRunner:
    key = (name or 'openclaw').strip().lower()
    if key in ('claude-code', 'claude'):
        return ClaudeCodeHarnessRunner()
    if key == 'codex':
        return CodexHarnessRunner()
    if key == 'hermes':
        return HermesHarnessRunner()
    return OpenClawHarnessRunner(api_key=api_key, base_url=base_url)
