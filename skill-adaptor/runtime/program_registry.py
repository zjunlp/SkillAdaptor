"""Program snapshots — optional git branches for adopted skill banks (EvoSkill-inspired form)."""

from __future__ import annotations
import json
import os
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

@dataclass
class ProgramSnapshot:
    name: str
    iteration: int
    parent: Optional[str] = None
    adopted_skill_ids: List[str] = field(default_factory=list)
    skill_count: int = 0
    delta_success: Optional[float] = None
    delta_avg_score: Optional[float] = None
    benchmark: str = ''
    harness: str = 'openclaw'
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class ProgramRegistry:
    BRANCH_PREFIX = 'skill-adaptor/program/'
    STATE_DIR_NAME = 'programs'

    def __init__(self, workspace: Path, *, git_branches: Optional[bool]=None):
        self.workspace = Path(workspace)
        self.state_dir = self.workspace / '.skill-adaptor' / self.STATE_DIR_NAME
        self.state_dir.mkdir(parents=True, exist_ok=True)
        if git_branches is None:
            git_branches = os.environ.get('SkillAdaptor_PROGRAM_GIT', '').lower() in ('1', 'true', 'yes')
        self.git_branches = git_branches
        self._git_root = self._find_git_root()

    @staticmethod
    def _find_git_root() -> Optional[Path]:
        current = Path.cwd()
        for parent in [current, *current.parents]:
            if (parent / '.git').exists():
                return parent
        return None

    def save_snapshot(self, snapshot: ProgramSnapshot) -> Path:
        path = self.state_dir / f'{snapshot.name}.json'
        path.write_text(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2), encoding='utf-8')
        latest = self.state_dir / 'current.json'
        latest.write_text(path.read_text(encoding='utf-8'), encoding='utf-8')
        if self.git_branches and self._git_root:
            self._maybe_git_commit(snapshot)
        return path

    def _maybe_git_commit(self, snapshot: ProgramSnapshot) -> None:
        branch = f'{self.BRANCH_PREFIX}{snapshot.name}'
        paths_to_add: List[str] = []
        try:
            rel_state = self.state_dir.relative_to(self._git_root)
            paths_to_add.append(str(rel_state))
        except ValueError:
            pass
        skills_dir = self.workspace / 'skills'
        try:
            paths_to_add.append(str(skills_dir.relative_to(self._git_root)))
        except ValueError:
            pass
        if not paths_to_add:
            return
        try:
            subprocess.run(['git', 'checkout', '-B', branch], cwd=self._git_root, capture_output=True, text=True, check=False)
            for rel in paths_to_add:
                subprocess.run(['git', 'add', rel], cwd=self._git_root, capture_output=True, check=False)
            msg = f'SkillAdaptor program {snapshot.name}: skills={snapshot.skill_count} Δ={snapshot.delta_success}'
            subprocess.run(['git', 'commit', '-m', msg], cwd=self._git_root, capture_output=True, check=False)
        except OSError:
            pass

    def list_snapshots(self) -> List[str]:
        return sorted((p.stem for p in self.state_dir.glob('*.json') if p.name != 'current.json'))
