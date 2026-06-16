"""Unified LLM Client for SkillEvolve."""

from __future__ import annotations
import json
import os
import re
import urllib.request
from typing import Optional

class SkillEvolveLLMClient:

    def __init__(self, api_key: Optional[str]=None, base_url: Optional[str]=None, model: Optional[str]=None, provider: Optional[str]=None):
        self.model = model or os.environ.get('SkillEvolve_MODEL', '')
        if not self.model:
            raise ValueError('Model name must be provided via argument or SkillEvolve_MODEL environment variable')
        self._model_lower = self.model.lower()
        if provider is None:
            if 'gpt' in self._model_lower:
                provider = 'openai'
            else:
                provider = 'generic'
        provider_prefix = f'SkillEvolve_{provider.upper()}_'
        self.api_key = api_key or os.environ.get(f'{provider_prefix}API_KEY', '') or os.environ.get('SkillEvolve_API_KEY', '')
        self.base_url = base_url or os.environ.get(f'{provider_prefix}BASE_URL', '') or os.environ.get('SkillEvolve_BASE_URL', '')
        if not self.api_key:
            raise ValueError('API key must be provided via argument or environment variable')
        if not self.base_url:
            raise ValueError('Base URL must be provided via argument or environment variable')
        self.base_url = self.base_url.rstrip('/')
        self.uses_reasoning_content = any((x in self._model_lower for x in ['kimi', 'glm']))
        self.uses_max_completion_tokens = 'max_completion_tokens' in self.model.lower()

    def call(self, prompt: str, system: Optional[str]=None, max_tokens: int=500, temperature: float=0.3) -> str:
        messages = []
        if system:
            messages.append({'role': 'system', 'content': system})
        messages.append({'role': 'user', 'content': prompt})
        payload = {'model': self.model, 'messages': messages, 'temperature': temperature}
        if self.uses_max_completion_tokens:
            payload['max_completion_tokens'] = max_tokens
        else:
            payload['max_tokens'] = max_tokens
        headers = {'Authorization': f'Bearer {self.api_key}', 'Content-Type': 'application/json'}
        req = urllib.request.Request(f'{self.base_url}/chat/completions', data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
            msg = data['choices'][0]['message']
            content = msg.get('content') or ''
            if not content and 'reasoning_content' in msg:
                reasoning = msg['reasoning_content'] or ''
                content = self._extract_from_reasoning(reasoning)
            return content

    def _extract_from_reasoning(self, reasoning: str) -> str:
        if not reasoning:
            return ''
        code_block_match = re.search('```(?:json)?\\s*\\n?(.*?)```', reasoning, re.DOTALL)
        if code_block_match:
            json_text = code_block_match.group(1).strip()
            try:
                json.loads(json_text)
                return json_text
            except json.JSONDecodeError:
                pass
        json_candidates = []
        brace_depth = 0
        in_string = False
        escape_next = False
        start_pos = None
        for i, char in enumerate(reasoning):
            if escape_next:
                escape_next = False
                continue
            if char == '\\' and in_string:
                escape_next = True
                continue
            if char == '"' and (not in_string):
                in_string = True
                if brace_depth > 0 and start_pos is not None:
                    try:
                        candidate = reasoning[start_pos:i + 1]
                        if re.search('"[^"]+"\\s*:', candidate):
                            json.loads(candidate)
                            json_candidates.append(candidate)
                    except json.JSONDecodeError:
                        pass
            elif char == '"' and in_string:
                in_string = False
            elif not in_string:
                if char == '{':
                    if brace_depth == 0:
                        start_pos = i
                    brace_depth += 1
                elif char == '}':
                    brace_depth -= 1
                    if brace_depth == 0 and start_pos is not None:
                        try:
                            candidate = reasoning[start_pos:i + 1]
                            parsed = json.loads(candidate)
                            if isinstance(parsed, dict) and len(parsed) > 0:
                                json_candidates.append(candidate)
                        except json.JSONDecodeError:
                            pass
                        start_pos = None
        if json_candidates:
            return max(json_candidates, key=len)
        simple_json = re.search('\\{[^{}]*"[^"]+"\\s*:\\s*[^\\{\\}]*\\}', reasoning)
        if simple_json:
            return simple_json.group()
        for pattern in ['\\{[^\\}]*\\}', '\\[[^\\]]*\\]']:
            match = re.search(pattern, reasoning)
            if match:
                try:
                    json.loads(match.group())
                    return match.group()
                except json.JSONDecodeError:
                    continue
        sentences = [s.strip() for s in reasoning.split('.') if s.strip()]
        if sentences:
            return sentences[-1]
        return reasoning

    def call_json(self, prompt: str, system: Optional[str]=None, max_tokens: int=500, temperature: float=0.3) -> dict:
        if 'json' not in prompt.lower():
            prompt += '\n\nReturn your response as valid JSON.'
        content = self.call(prompt, system, max_tokens, temperature)
        return self._extract_json(content)

    def _extract_json(self, content: str) -> dict:
        code_block_match = re.search('```(?:json)?\\s*\\n?(.*?)```', content, re.DOTALL)
        if code_block_match:
            json_text = code_block_match.group(1).strip()
            try:
                return json.loads(json_text)
            except json.JSONDecodeError:
                pass
        start = content.find('{')
        if start >= 0:
            brace_count = 0
            for i, char in enumerate(content[start:]):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        try:
                            return json.loads(content[start:start + i + 1])
                        except json.JSONDecodeError:
                            break
        start = content.find('[')
        end = content.rfind(']')
        if start >= 0 and end > start:
            try:
                return json.loads(content[start:end + 1])
            except json.JSONDecodeError:
                pass
        json_match = re.search('\\{[^{}]*"[^"]+"[^{}]*\\}', content)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        raise ValueError(f'No valid JSON found in response: {content[:200]}...')

def create_llm_client_from_config(config) -> SkillEvolveLLMClient:
    model = getattr(config, 'model', None) or ''
    model_lower = model.lower()
    if 'kimi' in model_lower or 'glm' in model_lower:
        provider = 'glm'
    elif 'gpt' in model_lower:
        provider = 'gpt'
    else:
        provider = 'glm'
    provider_prefix = f'SkillEvolve_{provider.upper()}_'
    api_key = os.environ.get(f'{provider_prefix}API_KEY') or getattr(config, 'api_key', None) or ''
    base_url = os.environ.get(f'{provider_prefix}BASE_URL') or getattr(config, 'base_url', None) or ''
    return SkillEvolveLLMClient(api_key=api_key, base_url=base_url, model=model, provider=provider)
