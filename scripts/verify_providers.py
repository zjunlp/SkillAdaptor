#!/usr/bin/env python3
"""Real (non-mocked) API connectivity checks for configured providers."""

from __future__ import annotations
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1] / 'skill-adaptor'
sys.path.insert(0, str(ROOT))
from core.provider_config import ProviderProfile, resolve_provider, validate_profile

def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        key, value = (key.strip(), value.strip())
        if key and key not in os.environ:
            os.environ[key] = value

def _chat_probe(profile: ProviderProfile, timeout: float=30.0) -> dict:
    url = profile.base_url.rstrip('/') + '/chat/completions'
    payload = {'model': profile.model, 'messages': [{'role': 'user', 'content': 'Reply with exactly: ok'}], 'max_tokens': 8, 'temperature': 0}
    headers = {'Authorization': f'Bearer {profile.api_key}', 'Content-Type': 'application/json'}
    if profile.name == 'openrouter':
        headers['HTTP-Referer'] = 'https://github.com/skill-adaptor/skill-adaptor'
        headers['X-Title'] = 'SkillAdaptor verify_providers'
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode('utf-8'))
        content = body.get('choices', [{}])[0].get('message', {}).get('content', '')
        return {'ok': True, 'sample': str(content)[:80]}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')[:300]
        return {'ok': False, 'error': f'HTTP {exc.code}', 'detail': detail}
    except Exception as exc:
        return {'ok': False, 'error': str(exc)}

def _balance_probe_deepseek(api_key: str) -> dict:
    req = urllib.request.Request('https://api.deepseek.com/user/balance', headers={'Authorization': f'Bearer {api_key}'}, method='GET')
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return {'ok': True, 'body': json.loads(resp.read().decode('utf-8'))}
    except urllib.error.HTTPError as exc:
        return {'ok': False, 'error': exc.code, 'detail': exc.read().decode('utf-8', errors='replace')[:200]}
    except Exception as exc:
        return {'ok': False, 'error': str(exc)}

def main() -> int:
    secrets = ROOT.parent / 'secrets' / '.env'
    _load_dotenv(secrets)
    _load_dotenv(ROOT / 'secrets' / '.env')
    providers = ['relay-gpt41', 'deepseek']
    if os.environ.get('OPENROUTER_API_KEY', '').strip():
        providers.append('openrouter')
    failed = 0
    print('=== SkillAdaptor provider verification (live) ===\n')
    for name in providers:
        try:
            profile = resolve_provider(name)
        except ValueError as exc:
            print(f'[SKIP] {name}: {exc}')
            failed += 1
            continue
        issues = validate_profile(profile)
        if issues:
            print(f"[FAIL] {name}: {'; '.join(issues)}")
            failed += 1
            continue
        print(f'--- {name} ---')
        print(f'  base_url: {profile.base_url}')
        print(f'  model:    {profile.model}')
        if name == 'deepseek':
            bal = _balance_probe_deepseek(profile.api_key)
            print(f'  balance:  {json.dumps(bal, ensure_ascii=False)}')
            for model_id in ('deepseek-v4-flash', 'deepseek-chat'):
                probe = ProviderProfile(name='deepseek', api_key=profile.api_key, base_url=profile.base_url, model=model_id)
                result = _chat_probe(probe)
                label = 'OK' if result.get('ok') else f'FAIL {result}'
                print(f'  chat[{model_id}]: {label}')
                if model_id == profile.model and (not result.get('ok')):
                    failed += 1
            print()
            continue
        result = _chat_probe(profile)
        if result.get('ok'):
            print(f"  chat:     OK ({result.get('sample', '')!r})")
        else:
            print(f'  chat:     FAIL {result}')
            failed += 1
        print()
    if 'openrouter' not in providers:
        print('[INFO] OPENROUTER_API_KEY not set — openrouter slot reserved in configs/.env.example\n')
    return 1 if failed else 0
if __name__ == '__main__':
    raise SystemExit(main())
