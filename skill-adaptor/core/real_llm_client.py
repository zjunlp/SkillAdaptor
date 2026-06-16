"""Real LLM Client - No Fallback, Fail Hard on Error"""

from __future__ import annotations
import json
import os
import time
import re
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable

class LLMError(Exception):
    pass

class LLMConfigError(LLMError):
    pass

class LLMAPIError(LLMError):
    pass

class LLMResponseError(LLMError):
    pass

class RealLLMClient:

    def __init__(self, model: str, api_key: Optional[str]=None, base_url: Optional[str]=None, max_retries: int=5, timeout: int=120):
        self.model = model
        self.api_key = api_key or os.getenv('LLM_API_KEY')
        self.base_url = (base_url or os.getenv('LLM_BASE_URL', '')).rstrip('/')
        self.max_retries = max_retries
        self.timeout = timeout
        if not self.api_key:
            raise LLMConfigError('API key not provided. Set via api_key parameter or LLM_API_KEY env var.')
        if not self.base_url:
            raise LLMConfigError('Base URL not provided. Set via base_url parameter or LLM_BASE_URL env var.')
        if self.api_key in ['YOUR_API_KEY', 'API-KEY', '', 'placeholder']:
            raise LLMConfigError(f"Invalid API key: '{self.api_key}'. Please provide a real API key.")
        self.stats = {'total_calls': 0, 'successful_calls': 0, 'failed_calls': 0, 'total_tokens': 0, 'start_time': datetime.now().isoformat()}
        try:
            import requests
            self._requests = requests
        except ImportError:
            raise LLMConfigError('requests library is required. Install with: pip install requests')

    def call(self, prompt: str, temperature: float=0.7, max_tokens: int=2048, system_message: Optional[str]=None) -> str:
        self.stats['total_calls'] += 1
        messages = []
        if system_message:
            messages.append({'role': 'system', 'content': system_message})
        messages.append({'role': 'user', 'content': prompt})
        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = self._make_request(messages, temperature, max_tokens)
                self.stats['successful_calls'] += 1
                return response
            except (self._requests.exceptions.Timeout, self._requests.exceptions.ConnectionError) as e:
                last_error = f'Network error (attempt {attempt + 1}): {e}'
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt
                    time.sleep(wait_time)
                    continue
            except self._requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if hasattr(e.response, 'status_code') else 0
                if status_code in [429, 500, 502, 503, 504]:
                    last_error = f'HTTP {status_code} (attempt {attempt + 1}): {e}'
                    if attempt < self.max_retries - 1:
                        wait_time = 2 ** attempt
                        time.sleep(wait_time)
                        continue
                else:
                    self.stats['failed_calls'] += 1
                    raise LLMAPIError(f'LLM API HTTP error {status_code}: {e}. Check your API key and base URL.') from e
            except Exception as e:
                self.stats['failed_calls'] += 1
                raise LLMAPIError(f'Unexpected error calling LLM: {e}') from e
        self.stats['failed_calls'] += 1
        raise LLMAPIError(f'LLM API call failed after {self.max_retries} attempts. Last error: {last_error}')

    def _make_request(self, messages: List[Dict[str, str]], temperature: float, max_tokens: int) -> str:
        headers = {'Authorization': f'Bearer {self.api_key}', 'Content-Type': 'application/json'}
        data = {'model': self.model, 'messages': messages, 'temperature': temperature, 'max_tokens': max_tokens}
        try:
            response = self._requests.post(f'{self.base_url}/chat/completions', headers=headers, json=data, timeout=self.timeout)
            response.raise_for_status()
            result = response.json()
            if 'choices' not in result or not result['choices']:
                raise LLMResponseError(f'Invalid API response format: {result}')
            content = result['choices'][0].get('message', {}).get('content', '')
            if not content or not content.strip():
                raise LLMResponseError('LLM returned empty response')
            if 'usage' in result and 'total_tokens' in result['usage']:
                self.stats['total_tokens'] += result['usage']['total_tokens']
            return content.strip()
        except self._requests.exceptions.JSONDecodeError as e:
            raise LLMResponseError(f'Failed to parse LLM response as JSON: {e}') from e

    def get_stats(self) -> Dict[str, Any]:
        return self.stats.copy()

    def reset_stats(self) -> None:
        self.stats = {'total_calls': 0, 'successful_calls': 0, 'failed_calls': 0, 'total_tokens': 0, 'start_time': datetime.now().isoformat()}

class LLMClientFactory:

    @staticmethod
    def from_env() -> RealLLMClient:
        return RealLLMClient(model=os.getenv('LLM_MODEL', 'kimi-k2.5'), api_key=os.getenv('LLM_API_KEY'), base_url=os.getenv('LLM_BASE_URL'))

    @staticmethod
    def for_benchmark(benchmark: str) -> RealLLMClient:
        configs = {'claweval': {'model': 'kimi-k2.5', 'base_url': os.getenv('LLM_BASE_URL', '')}, 'webshop': {'model': 'kimi-k2.5', 'base_url': os.getenv('LLM_BASE_URL', '')}, 'pinchbench': {'model': 'kimi-k2.5', 'base_url': os.getenv('LLM_BASE_URL', '')}}
        if benchmark not in configs:
            raise LLMConfigError(f'Unknown benchmark: {benchmark}')
        config = configs[benchmark]
        return RealLLMClient(model=config['model'], base_url=config['base_url'])
