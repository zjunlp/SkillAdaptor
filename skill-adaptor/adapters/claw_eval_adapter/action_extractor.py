"""Action Content Extractor for Claw-Eval"""

import json
from typing import Any, List, Dict

def extract_action_content(content: Any) -> str:
    if isinstance(content, list):
        content = ' '.join((str(c) for c in content))
    content = str(content).strip()
    if content.startswith('{'):
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                for key in ['action', 'content', 'text', 'message', 'response']:
                    if key in data and data[key]:
                        return str(data[key])
                if 'thinking' in data and len(data) == 1:
                    return '[thinking]'
        except json.JSONDecodeError:
            pass
    if '{"type":' in content or "{'type':" in content:
        try:
            start = content.find('{')
            end = content.rfind('}')
            if start >= 0 and end > start:
                data = json.loads(content[start:end + 1])
                if isinstance(data, dict):
                    if data.get('type') == 'thinking':
                        return '[thinking]'
                    for key in ['action', 'content', 'text', 'message', 'response']:
                        if key in data and data[key]:
                            return str(data[key])
        except (json.JSONDecodeError, ValueError):
            pass
    return content

def extract_action_from_trajectory(trajectory: List[Dict]) -> List[Dict]:
    processed = []
    for entry in trajectory:
        if entry.get('type') == 'message':
            msg = entry.get('message', {})
            role = msg.get('role', '')
            content = msg.get('content', '')
            if role == 'assistant':
                extracted = extract_action_content(content)
                if extracted == '[thinking]':
                    continue
                new_entry = entry.copy()
                new_msg = msg.copy()
                new_msg['content'] = extracted
                new_entry['message'] = new_msg
                processed.append(new_entry)
            else:
                processed.append(entry)
        else:
            processed.append(entry)
    return processed

def should_skip_thinking_step(content: Any) -> bool:
    extracted = extract_action_content(content)
    return extracted == '[thinking]'
