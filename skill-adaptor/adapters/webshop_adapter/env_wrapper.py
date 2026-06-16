"""WebShop Environment Wrapper"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

class WebShopEnvWrapper:

    def __init__(self, num_products: int=1000, observation_mode: str='text', webshop_path: Optional[Path | str]=None):
        self.num_products = num_products
        self.observation_mode = observation_mode
        self.webshop_path = Path(webshop_path) if webshop_path else None
        self.env = None
        self._setup_environment()

    def _setup_environment(self) -> None:
        try:
            import gym
            if self.webshop_path:
                import sys
                sys.path.insert(0, str(self.webshop_path))
            from web_agent_site.envs import WebAgentTextEnv
            self.env = gym.make('WebAgentTextEnv-v0', observation_mode=self.observation_mode, num_products=self.num_products)
        except ImportError as e:
            print(f'Failed to import WebShop: {e}')
            raise

    def reset(self, goal_idx: int=0) -> Tuple[str, Dict]:
        if self.env is None:
            raise RuntimeError('Environment not initialized')
        obs, info = self.env.reset(session=goal_idx)
        return (obs, info)

    def step(self, action: str) -> Tuple[str, float, bool, Dict]:
        if self.env is None:
            raise RuntimeError('Environment not initialized')
        return self.env.step(action)

    def get_available_actions(self) -> Dict[str, Any]:
        if self.env is None:
            return {}
        return self.env.get_available_actions()

    def close(self) -> None:
        if self.env:
            self.env.close()

    def get_goal_count(self) -> int:
        if self.env is None or not hasattr(self.env, 'server'):
            return 0
        return len(self.env.server.goals)

    @staticmethod
    def get_revision_constraints() -> str:
        from .constraint_provider import WebShopConstraintProvider
        return WebShopConstraintProvider.get_constraints()

    def _build_valid_actions_list(self, available: Dict[str, Any]) -> List[str]:
        valid_actions = []
        has_search = available.get('has_search_bar', False)
        if has_search:
            valid_actions.append('search[product]')
        clickables = available.get('clickables', [])
        for clickable in clickables[:15]:
            valid_actions.append(f'click[{clickable}]')
        return valid_actions if valid_actions else ['search[product]']

    def run_episode(self, goal_idx: int, policy, max_steps: int=50, verbose: bool=False, use_strict_valid: bool=False) -> Dict[str, Any]:
        obs, info = self.reset(goal_idx)
        if hasattr(policy, 'begin_episode'):
            policy.begin_episode(obs)
        steps = []
        total_reward = 0.0
        done = False
        recent_actions = []
        for step in range(max_steps):
            available = self.get_available_actions()
            valid_actions = None
            if use_strict_valid and hasattr(policy, 'forward_from_valid'):
                valid_actions = self._build_valid_actions_list(available)
            if valid_actions and hasattr(policy, 'forward_from_valid'):
                action = policy.forward_from_valid(obs, available, valid_actions, recent_actions=recent_actions)
            else:
                action = policy.forward(obs, available, recent_actions=recent_actions)
            obs, reward, done, info = self.step(action)
            step_data = {'step': step, 'action': action, 'observation': obs[:500], 'reward': reward, 'done': done}
            steps.append(step_data)
            recent_actions = (recent_actions + [action])[-10:]
            total_reward += reward
            if verbose:
                print(f'  Step {step + 1}: {action} -> r={reward:.3f}')
            if done:
                break
        return {'goal_idx': goal_idx, 'steps': steps, 'total_reward': total_reward, 'success': total_reward > 0, 'num_steps': len(steps)}
