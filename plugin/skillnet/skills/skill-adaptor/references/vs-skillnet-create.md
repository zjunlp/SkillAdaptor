# SkillAdaptor vs `skillnet create`

| | `skillnet create trajectory.txt` | SkillAdaptor `run_plugin.py` |
|--|----------------------------------|------------------------------|
| Input | Text log / trajectory file | Tasks + executed trajectories |
| Localization | Implicit in one LLM pass | Explicit **t★** step |
| Validation | Optional `evaluate` after | **Required Δ>0** on injected Q′ to adopt; source task advisory |
| Iterations | Manual | Built-in loop |
| Best for | Quick packaging | Multi-task evolution with re-execution adoption |

Use **create** for one-off distill; use **SkillAdaptor** when adoption must be justified by re-execution metrics.
