"""PinchBench Step-by-Step Skill Tracker"""

from __future__ import annotations
import json
import re
from typing import Any, Dict, List, Optional
from core.types import Skill
from core.llm_params import chat_temperature

class StepSkillTracker:

    def __init__(self, skills: Dict[str, Skill], llm_client: Optional[Any]=None, api_key: Optional[str]=None, base_url: Optional[str]=None, model: Optional[str]=None):
        if llm_client is None:
            raise RuntimeError('LLM client is REQUIRED for step-by-step skill tracking. Please provide a valid OpenAI-compatible client.')
        self.skills = skills
        self.llm_client = llm_client
        self.api_key = api_key
        self.base_url = base_url
        self.model = model or 'gpt-4o'

    def analyze_step_skills(self, step_observation: str, step_action: str, step_thinking: str='', previous_steps: Optional[List[Dict]]=None) -> List[str]:
        if not self.skills:
            return []
        prompt = self._build_analysis_prompt(step_observation, step_action, step_thinking, previous_steps)
        response = self._call_llm(prompt)
        return self._parse_skill_usage(response)

    def _build_analysis_prompt(self, observation: str, action: str, thinking: str, previous_steps: Optional[List[Dict]]) -> str:
        skill_descriptions = []
        for skill_id, skill in self.skills.items():
            desc = f"- {skill_id}:\n  Title: {skill.title}\n  Purpose: {skill.description[:150]}\n  When to use: {(skill.when_to_apply[:100] if skill.when_to_apply else 'N/A')}"
            skill_descriptions.append(desc)
        skills_text = '\n'.join(skill_descriptions)
        context_text = ''
        if previous_steps:
            context_parts = []
            for i, step in enumerate(previous_steps[-3:], 1):
                ctx_action = step.get('action', '')[:80]
                ctx_thinking = step.get('thinking', '')[:60]
                context_parts.append(f'  Step -{len(previous_steps) - i + 1}: {ctx_action}')
                if ctx_thinking:
                    context_parts.append(f'    Thought: {ctx_thinking}')
            context_text = 'Previous Steps:\n' + '\n'.join(context_parts)
        observation = observation[:500] if observation else ''
        action = action[:200] if action else ''
        thinking = thinking[:300] if thinking else ''
        return f"""# Skill Usage Analysis\n\nYou are analyzing which skills an AI agent used to complete a task.\n\n## Available Skills\n\n{skills_text}\n\n## Current Step to Analyze\n\n{context_text}\n\n**Current Observation**:\n```\n{observation}\n```\n\n**Action Taken**:\n```\n{action}\n```\n\n**Agent's Thinking** (if available):\n```\n{thinking}\n```\n\n## Analysis Guidelines\n\nDetermine which skills from the list above were actually USED or FOLLOWED in this step:\n\n1. **Direct Application** (strong signal): Action clearly follows skill instructions\n2. **Pattern Match** (medium signal): Behavior aligns with skill's "When to use" condition\n3. **Conceptual Influence** (weak signal): Thinking references skill concepts\n4. **No Usage**: Action is generic or unrelated to any skill\n\n## Output Format\n\nReturn a JSON object with skill IDs that were used:\n\n```json\n{{\n  "skills_used": ["skill_001", "skill_003"],\n  "reasoning": "Brief explanation of why these skills were used",\n  "confidence": "high|medium|low"\n}}\n```\n\nIf no skills were clearly used, return empty: `{{"skills_used": [], "reasoning": "Generic action", "confidence": "high"}}`\n"""

    def _call_llm(self, prompt: str) -> str:
        if self.llm_client is None:
            raise RuntimeError('LLM client not available for skill tracking')
        try:
            response = self.llm_client.chat.completions.create(model=self.model, messages=[{'role': 'system', 'content': 'You are a precise skill attribution analyzer. Return only valid JSON.'}, {'role': 'user', 'content': prompt}], temperature=chat_temperature(self.model, 0.1), max_tokens=256)
            return response.choices[0].message.content
        except Exception as e:
            raise RuntimeError(f'LLM call failed for skill tracking: {e}') from e

    def _parse_skill_usage(self, content: str) -> List[str]:
        data = self._extract_json_object(content)
        if isinstance(data, dict):
            skills = data.get('skills_used', [])
            return [s for s in skills if s in self.skills]
        used_skills = []
        for skill_id in self.skills.keys():
            if skill_id in content:
                used_skills.append(skill_id)
        if used_skills:
            return used_skills
        return []

    @staticmethod
    def _extract_json_object(content: str):
        import json
        fenced = re.search('```(?:json)?\\s*(.*?)\\s*```', content, re.DOTALL)
        if fenced:
            try:
                return json.loads(fenced.group(1).strip())
            except json.JSONDecodeError:
                pass
        try:
            return json.loads(content.strip())
        except json.JSONDecodeError:
            pass
        start = content.find('{')
        if start >= 0:
            depth = 0
            for idx in range(start, len(content)):
                ch = content[idx]
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(content[start:idx + 1])
                        except json.JSONDecodeError:
                            break
        return None

    def track_trajectory_skills(self, trajectory: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        enriched_steps = []
        previous_steps = []
        for step in trajectory:
            step_copy = step.copy()
            if step.get('type') == 'metadata':
                enriched_steps.append(step_copy)
                continue
            thinking = ''
            obs = step.get('observation', '')
            thinking_match = re.search('\\[Thinking\\]\\s*(.+?)(?:\\n|$)', obs, re.DOTALL)
            if thinking_match:
                thinking = thinking_match.group(1).strip()
            skills_used = self.analyze_step_skills(step_observation=obs, step_action=step.get('action', ''), step_thinking=thinking, previous_steps=previous_steps)
            step_copy['skills_used'] = skills_used
            enriched_steps.append(step_copy)
            previous_steps.append({'observation': obs, 'action': step.get('action', ''), 'thinking': thinking, 'skills_used': skills_used})
        return enriched_steps

def create_step_tracker(skills: Dict[str, Skill], llm_client: Any, api_key: Optional[str]=None, base_url: Optional[str]=None, model: Optional[str]=None) -> StepSkillTracker:
    if llm_client is None:
        raise RuntimeError('llm_client is REQUIRED for step-by-step skill tracking. Rule-based fallback has been removed.')
    return StepSkillTracker(skills=skills, llm_client=llm_client, api_key=api_key, base_url=base_url, model=model)
