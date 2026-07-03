"""Register bench OpenClaw agents and persist API auth (OpenClaw 2026.6+ sqlite store)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from core.openclaw_hygiene import openclaw_agent_id, openclaw_agent_slug
from core.openclaw_cli import resolve_openclaw_executable

_USE_SHELL = sys.platform == 'win32'


def slugify_provider_from_base_url(base_url: str) -> str:
    parsed = urlparse(base_url.rstrip('/'))
    host = (parsed.hostname or 'custom').replace('.', '-')
    if parsed.port:
        host = f'{host}-{parsed.port}'
    return f'custom-{host}'


def _bare_model_id(model_id: str) -> str:
    return model_id.split('/', 1)[-1] if '/' in model_id else model_id


def _run_openclaw(args: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    exe = resolve_openclaw_executable()
    return subprocess.run(
        [exe, *args],
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
        shell=_USE_SHELL,
    )


def paste_api_key(agent_id: str, provider_slug: str, api_key: str) -> bool:
    """Persist key into OpenClaw sqlite auth via CLI (idempotent)."""
    if not api_key or api_key.startswith('${'):
        return False
    result = _run_openclaw(
        ['models', '--agent', agent_id, 'auth', 'paste-api-key', '--provider', provider_slug],
        input_text=f'{api_key}\n',
    )
    if result.returncode != 0:
        msg = (result.stderr or result.stdout or '').strip()
        print(f'[OpenClaw] auth paste-api-key failed for {agent_id}/{provider_slug}: {msg[:200]}')
        return False
    _run_openclaw(['secrets', 'reload'])
    return True


def _agent_store_dir(agent_id: str) -> Path:
    base = Path.home() / '.openclaw' / 'agents'
    direct = base / agent_id
    if direct.exists():
        return direct
    normalized = base / agent_id.replace(':', '-')
    if normalized.exists():
        return normalized
    return direct


def write_agent_models_json(
    agent_id: str,
    *,
    base_url: str,
    api_key: str,
    model: str,
) -> str:
    """Write models.json for custom OpenAI-compatible API; return resolved model id."""
    bare = _bare_model_id(model)
    slug = slugify_provider_from_base_url(base_url)
    resolved = f'{slug}/{bare}'
    agent_dir = _agent_store_dir(agent_id) / 'agent'
    agent_dir.mkdir(parents=True, exist_ok=True)
    models_path = agent_dir / 'models.json'
    data: dict[str, Any] = {}
    if models_path.exists():
        try:
            data = json.loads(models_path.read_text(encoding='utf-8-sig'))
        except (json.JSONDecodeError, OSError):
            data = {}
    providers = data.setdefault('providers', {})
    providers[slug] = {
        'baseUrl': base_url.rstrip('/'),
        'apiKey': api_key,
        'api': 'openai-completions',
        'models': [
            {
                'id': bare,
                'name': bare,
                'reasoning': False,
                'input': ['text'],
                'contextWindow': 200000,
                'maxTokens': 8192,
            }
        ],
    }
    data['defaultProvider'] = slug
    data['defaultModel'] = bare
    models_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    return resolved


def sync_openclaw_json_model(agent_id: str, resolved_model: str) -> None:
    config_path = Path.home() / '.openclaw' / 'openclaw.json'
    if not config_path.exists():
        return
    try:
        config = json.loads(config_path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        return
    agents = config.get('agents', {}).get('list', [])
    normalized_id = agent_id.replace(':', '-').lower()
    for entry in agents:
        if not isinstance(entry, dict):
            continue
        entry_id = str(entry.get('id', '')).lower()
        if entry_id in {agent_id.lower(), normalized_id}:
            entry['model'] = resolved_model
            break
    else:
        return
    try:
        config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    except OSError:
        pass


def _bench_workspace(agent_id: str) -> Path:
    tmp = os.environ.get('PINCHBENCH_TMP') or os.environ.get('TEMP') or '/tmp'
    return Path(tmp) / 'pinchbench' / 'skill-adaptor' / agent_id / 'agent_workspace'


def _import_pinchbench_ensure_agent():
    pinchbench_path = os.environ.get('PINCHBENCH_PATH', '').strip()
    if not pinchbench_path:
        return None
    scripts_dir = Path(pinchbench_path) / 'scripts'
    if not scripts_dir.is_dir():
        return None
    path_str = str(scripts_dir)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)
    try:
        from lib_agent import ensure_agent_exists  # type: ignore import-not-found
        return ensure_agent_exists
    except ImportError:
        return None


def ensure_bench_agent_auth(
    model: str,
    *,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> str:
    """
    Ensure bench-{model} has models.json + sqlite auth before PinchBench runs.
    Returns agent_id.
    """
    key = (api_key or os.environ.get('OPENAI_API_KEY') or os.environ.get('SkillEvolve_API_KEY') or '').strip()
    url = (base_url or os.environ.get('OPENAI_API_BASE_URL') or os.environ.get('SkillEvolve_BASE_URL') or '').strip()
    if not key or not url:
        raise RuntimeError(
            'OpenClaw bench agent needs API key and base URL. '
            'Set OPENAI_API_KEY + OPENAI_API_BASE_URL (or run resolve_and_apply first).'
        )

    agent_id = openclaw_agent_id(model)
    workspace = _bench_workspace(agent_id)
    workspace.mkdir(parents=True, exist_ok=True)

    ensure_fn = _import_pinchbench_ensure_agent()
    if ensure_fn is not None:
        ensure_fn(agent_id, model, workspace, base_url=url, api_key=key)
    else:
        resolved = write_agent_models_json(agent_id, base_url=url, api_key=key, model=model)
        slug = slugify_provider_from_base_url(url)
        paste_api_key(agent_id, slug, key)
        sync_openclaw_json_model(agent_id, resolved)

    return agent_id


def ensure_main_agent_openai_auth(api_key: Optional[str] = None) -> None:
    """
    Silence gateway ProviderAuthError on the default `main` agent when it uses openai/*.
    Uses the same chat API key from secrets — does not change main's configured model.
    """
    key = (api_key or os.environ.get('OPENAI_API_KEY') or os.environ.get('SkillEvolve_API_KEY') or '').strip()
    if not key:
        return
    paste_api_key('main', 'openai', key)


def prepare_openclaw_for_model(
    model: str,
    *,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    fix_main_auth: bool = True,
) -> str:
    """Call before evolution / PinchBench live runs."""
    agent_id = ensure_bench_agent_auth(model, api_key=api_key, base_url=base_url)
    if fix_main_auth:
        ensure_main_agent_openai_auth(api_key=api_key)
    return agent_id
