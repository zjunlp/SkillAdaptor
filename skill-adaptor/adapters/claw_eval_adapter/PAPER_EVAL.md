# Paper-facing Claw-Eval eval protocol (no task IDs shipped)

## Official defaults (uploaded code)

| Knob | Value |
|------|--------|
| Embedding | `Qwen3-Embedding-8B` (`core/embedding_config.PRIMARY_EMBEDDING_MODEL`) |
| Cosine floor | `0.45` (ClawEvalConfig) |
| Skill inject | embed top-10 (≥ floor) → **LLM rerank** → top-k |
| Judge | `google/gemini-3-flash-preview` |
| Split | 66 adaptation + 133 test (Appendix C.2) |
| Metric | Avg Score + **Pass@3%** |

Local overrides (gitignored `secrets/.env` only):

```text
SkillAdaptor_EMBEDDING_MODEL=text-embedding-3-small   # local backup; never change code default
# SkillAdaptor_LLM_RERANK=0   # only to A/B disable rerank
```

## Materialize 66/133 locally (do not commit)

```powershell
cd skill-adaptor
$env:PYTHONPATH = (Get-Location).Path
python -c "
from pathlib import Path
import os
from adapters.claw_eval_adapter.paper_split import build_paper_style_split, write_split_manifest
claw = Path(os.environ['CLAW_EVAL_PATH']) / os.environ.get('CLAW_EVAL_TASKS_DIR','tasks')
payload = build_paper_style_split(claw, n_adapt=66, n_test=133, seed=42)
write_split_manifest(payload, Path('../secrets/local/claw_eval_paper_66_133.json'))
print(len(payload['input_tasks']), len(payload['test_tasks']))
"
```

## Pass@3

```python
from adapters.claw_eval_adapter.pass_at_k import pass_at_k_from_trials, aggregate_pass_at_k
# per task: 3 independent trials → [True, False, True]
pass_at_k_from_trials([True, False, True], k=3)
```

Set `CLAW_EVAL_TRIALS=3` so `ClawEvalExecutor` passes `--trials 3` to claw-eval CLI.
Aggregate with `pass_at_k` / `aggregate_pass_at_k`. Micro local runs leave trials unset (=1).

## Local micro (same category)

`secrets/local/claw_eval_micro_communication.json` — communication-only train/val/test.
