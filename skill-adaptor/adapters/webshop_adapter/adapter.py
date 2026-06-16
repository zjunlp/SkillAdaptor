"""WebShop Adapter for SkillEvolve"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional
try:
    webshop_path = os.environ.get('WEBSHOP_PATH')
    if webshop_path:
        sys.path.insert(0, webshop_path)
    import gym
    from web_agent_site.envs.web_agent_text_env import WebAgentTextEnv
    WEBSHOP_AVAILABLE = True
except ImportError:
    WEBSHOP_AVAILABLE = False
from core.types import Skill
from .constraint_provider import WebShopConstraintProvider

class WebShopAdapter:

    def __init__(self, num_products: int=1000):
        self.num_products = num_products
        self.env = None
        self.skills = []
        if WEBSHOP_AVAILABLE:
            try:
                self.env = gym.make('WebAgentTextEnv-v0', observation_mode='text', num_products=num_products)
            except Exception as e:
                print(f'Warning: Could not create WebShop env: {e}')

    def is_available(self) -> bool:
        return WEBSHOP_AVAILABLE and self.env is not None

    def run_episode(self, goal_idx: int, skills: List[Skill]=None) -> Dict:
        if not self.is_available():
            return {'goal_idx': goal_idx, 'success': False, 'reward': 0.0, 'error': 'WebShop not available'}
        try:
            obs = self.env.reset(goal_idx=goal_idx)
            done = False
            total_reward = 0.0
            steps = 0
            max_steps = 15
            actions = []
            while not done and steps < max_steps:
                action = self._select_action(obs, skills)
                actions.append(action)
                try:
                    obs, reward, done, info = self.env.step(action)
                    total_reward += reward
                    steps += 1
                except Exception as e:
                    break
            return {'goal_idx': goal_idx, 'success': total_reward >= 1.0, 'reward': total_reward, 'steps': steps, 'actions': actions}
        except Exception as e:
            return {'goal_idx': goal_idx, 'success': False, 'reward': 0.0, 'error': str(e)}

    def _select_action(self, obs: str, skills: List[Skill]=None) -> str:
        if 'search' in obs.lower():
            return 'search[shoes]'
        elif 'buy now' in obs.lower():
            return 'click[buy now]'
        else:
            return 'click[result_0]'

    def get_num_goals(self) -> int:
        if self.is_available():
            return min(100, len(self.env.goals))
        return 0

    def close(self):
        if self.env:
            self.env.close()

    @staticmethod
    def get_revision_constraints() -> str:
        return WebShopConstraintProvider.get_constraints()

    @staticmethod
    def validate_skill(skill_text: str) -> tuple[bool, List[str]]:
        return WebShopConstraintProvider.validate_skill_text(skill_text)

class WebShopSkillBank:
    DEFAULT_SKILLS = [{'id': 'ws_search_strategy', 'title': 'Search Strategy', 'description': 'How to search for products', 'body': '# Search Strategy\n\n1. Use specific keywords\n2. Include price range if needed\n3. Check first 3 results\n'}, {'id': 'ws_comparison', 'title': 'Product Comparison', 'description': 'How to compare products', 'body': '# Product Comparison\n\n1. Check price first\n2. Compare ratings\n3. Look at reviews\n4. Choose best value\n'}]

    @classmethod
    def load_skills(cls) -> List[Skill]:
        skills = []
        for s in cls.DEFAULT_SKILLS:
            skills.append(Skill(id=s['id'], title=s['title'], description=s['description'], body=s['body'], created_from='webshop_default'))
        return skills
