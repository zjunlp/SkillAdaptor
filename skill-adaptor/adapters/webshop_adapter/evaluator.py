"""WebShop Evaluator"""

from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from core.types import Skill
from .env_wrapper import WebShopEnvWrapper
from .llm_policy import SkillAugmentedLLMPolicy

class WebShopEvaluator:

    def __init__(self, env: WebShopEnvWrapper, llm_config: Dict[str, Any], output_dir: Optional[Path]=None, embedding_api_key: Optional[str]=None, embedding_base_url: Optional[str]=None):
        self.env = env
        self.llm_config = llm_config
        self.output_dir = Path(output_dir) if output_dir else None
        self.embedding_api_key = embedding_api_key
        self.embedding_base_url = embedding_base_url
        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)

    def evaluate(self, goal_indices: List[int], skill_bank: Optional[Dict[str, Skill]]=None, max_steps: int=50, verbose: bool=False) -> Dict[str, Any]:
        policy = SkillAugmentedLLMPolicy(self.llm_config, skill_bank=skill_bank, top_k_skills=3, embedding_api_key=self.embedding_api_key, embedding_base_url=self.embedding_base_url)
        results = []
        for i, goal_idx in enumerate(goal_indices):
            if verbose:
                print(f'[{i + 1}/{len(goal_indices)}] Goal {goal_idx}...')
            episode = self.env.run_episode(goal_idx=goal_idx, policy=policy, max_steps=max_steps, verbose=verbose)
            results.append(episode)
        metrics = self._compute_metrics(results)
        if self.output_dir:
            self._save_results(results, metrics)
        return metrics

    def _compute_metrics(self, results: List[Dict]) -> Dict[str, Any]:
        if not results:
            return {'success_rate': 0.0, 'avg_score': 0.0, 'avg_steps': 0.0, 'sample_size': 0}
        success_count = sum((1 for r in results if r['success']))
        total_reward = sum((r['total_reward'] for r in results))
        total_steps = sum((r['num_steps'] for r in results))
        avg_score = total_reward / len(results)
        return {'success_rate': success_count / len(results), 'avg_score': avg_score, 'avg_score_percent': avg_score * 100.0, 'avg_steps': total_steps / len(results), 'sample_size': len(results), 'successful_episodes': success_count, 'harsh_success_rate': sum((1 for r in results if r['total_reward'] >= 0.999)) / len(results)}

    def _save_results(self, results: List[Dict], metrics: Dict[str, Any]) -> None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        model = self.llm_config.get('model', 'unknown')
        output = {'timestamp': datetime.now().isoformat(), 'model': model, 'metrics': metrics, 'episodes': results}
        path = self.output_dir / f'eval_{model}_{timestamp}.json'
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f'Results saved to {path}')

    def evaluate_skill_bank(self, skill_bank: Dict[str, Skill], num_goals: int=100, start_idx: int=0) -> Dict[str, Any]:
        max_goals = self.env.get_goal_count()
        end_idx = min(start_idx + num_goals, max_goals)
        actual_goals = end_idx - start_idx
        if actual_goals <= 0:
            return {'success_rate': 0.0, 'avg_score': 0.0, 'sample_size': 0}
        goal_indices = list(range(start_idx, end_idx))
        return self.evaluate(goal_indices=goal_indices, skill_bank=skill_bank, verbose=False)
