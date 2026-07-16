# Claw-Eval Adapter

Claw-Eval–specific patches and utilities for SkillAdaptor.

## Purpose

Claw-Eval differs from PinchBench mainly in task layout (`tasks/<id>/task.yaml` +
`python -m claw_eval.cli`) and grading. Skill injection, step-level attribution,
and the Localizer / Linker / Qualifier contract match the paper method.

## Paper-aligned runtime path (do not collapse)

`run_skill_adaptor.py --env claw-eval` uses **three layers**:

1. **Harness (OpenClaw default; Claude/Codex/… also supported)** — gateway hygiene +
   `inject_skill_text` into `~/.openclaw/workspace/skills/skill-adaptor-evolved/`
   (same surface as PinchBench).
2. **claw-eval official agent loop** (`python -m claw_eval.cli run`) — starts mock
   HTTP services and writes JSONL with `tool_dispatch`. Official graders **require**
   this; a bare OpenClaw npm chat alone cannot score Claw-Eval tasks.
3. **Official judge** — `google/gemini-3-flash-preview` from claw-eval
   `config_general.yaml` via `official_config.py`. **Never** silently set
   `judge.model_id` to the chat/agent model.

Plus: `ClawEvalConfig` / `ClawEvalGenerator` / task context / shared
`configure_pinchbench_skill_injection`.

### Why not “OpenClaw CLI only”?

Claw-Eval tasks bind tools to local mock servers. Graders look for
`tool_dispatch` / Anthropic-style tool events. The claw-eval runner is the
OpenClaw-compatible evaluation harness shipped by the benchmark (its system
prompt literally says the assistant runs inside OpenClaw). SkillAdaptor keeps
OpenClaw as the **skill/harness base** and uses claw-eval for **execute+grade**.

### Skill visibility

Before each task run, the executor:

1. Calls harness `prepare_runtime` + `inject_skill_text` (required; failure aborts)
2. Mirrors SKILL.md under `skills/skill-adaptor-evolved/` and `.skill/`
3. Emits `.skill-adaptor-configs/<task>_run.yaml` with:
   - agent = SkillAdaptor chat credentials / model
   - judge = official `google/gemini-3-flash-preview` (+ `CLAW_EVAL_JUDGE_*` or OpenRouter)
   - `prompt.skills.default` + `system_prompt_prefix` so the claw-eval loop sees skills

### Step-level attribution (`skills_at_fault`)

1. Claw-Eval JSONL (+ optional OpenClaw session merge) → step list
2. `set_skill_bank` installs `StepSkillRetriever`
3. Each step gets Top-k `skills_used` via embedding over (task, obs, action)
4. Localizer picks `t*`; `skills_at_fault = steps[t*].skills_used`

Task-level injection IDs are only the fallback when per-step retrieval is empty.

### Scoring / judge

**Submitted path (default):** grader on, judge model locked to
`google/gemini-3-flash-preview` (`judge_official.yaml` / claw-eval
`config_general.yaml`). Credentials are URL + key only:

```text
CLAW_EVAL_JUDGE_API_KEY=...
CLAW_EVAL_JUDGE_BASE_URL=https://openrouter.ai/api/v1
# or OPENROUTER_API_KEY=...
```

`CLAW_EVAL_JUDGE_MODEL` overrides are **ignored** unless
`CLAW_EVAL_ALLOW_NONOFFICIAL_JUDGE=1` (set only by the local wiring helper).

**Local wiring when Gemini is unreachable** (scripts are **gitignored / not shipped**;
keep only on your machine — never for paper claims):

```powershell
# Local-only helpers (not in public upload): wiring_judge, micro_live_smoke, evolution_chain_smoke
$env:CLAW_EVAL_ALLOW_NONOFFICIAL_JUDGE=1   # opt-in; scores NOT paper-comparable
```

`CLAW_EVAL_STRICT_JUDGE=1` (default) probes the judge before run.
Debug-only: `CLAW_EVAL_STRICT_JUDGE=0` or `CLAW_EVAL_NO_JUDGE=1`.
OpenClaw opt-out (debug): `CLAW_EVAL_SKIP_OPENCLAW=1`.

### Intermediate artifacts

Under `artifact_dir/trajectories/`:

- `{task_id}_raw_steps.json` — merge label, official score, raw steps
- `{task_id}_annotated.json` — Localizer-ready step list with `skills_used`

## Files

| File | Purpose |
|------|---------|
| `executor.py` | OpenClaw inject + claw-eval run + step attribution |
| `official_config.py` | Official judge lock + probe (submitted path) |
| `judge_official.yaml` | Documented official judge model_id / base_url |
| `task_io.py` | Nested `task.yaml` prompt / category / markdown context |
| `task_context.py` | Localizer/Generator task brief provider |
| `constraint_provider.py` | Container / verifier-shaped reviser constraints |
| `action_extractor.py` | Filter thinking JSON from actions |
| `generator_patch.py` | Titles from `improvement_principle` |
| `config_patch.py` | Claw-Eval thresholds (cosine floor **0.45**) |
| `hints.py` | Localizer / Generator supplements |
| `paper_split.py` | Local builder for 66/133 manifests (IDs stay in `secrets/local/`) |
| `pass_at_k.py` | Pass@k estimator (use with `CLAW_EVAL_TRIALS=3`) |
| `PAPER_EVAL.md` | Paper protocol notes (no task IDs) |

Local-only (gitignored / deleted, not shipped): `wiring_judge.py`, `*_smoke.py`,
`local_comm_batch.py`, `fixtures/`, deprecated `skill_injecting_executor.py`.

## Required env

```text
CLAW_EVAL_PATH=/path/to/claw-eval
CLAW_EVAL_TASKS_DIR=tasks
CLAW_EVAL_PYTHON=...                 # optional
CLAW_EVAL_JUDGE_API_KEY=...          # or OPENROUTER_API_KEY
CLAW_EVAL_JUDGE_BASE_URL=https://openrouter.ai/api/v1
# CLAW_EVAL_TRIALS=3                 # paper Pass@3
SkillAdaptor_API_KEY=...             # agent / chat
SkillAdaptor_BASE_URL=...
SkillAdaptor_EMBEDDING_API_KEY=...
SkillAdaptor_EMBEDDING_BASE_URL=...
SkillAdaptor_EMBEDDING_MODEL=Qwen3-Embedding-8B
```

Legacy `SkillEvolve_*` / `OPENAI_*` names are still read as aliases.

## Paper path check

```powershell
cd skill-adaptor
$env:PYTHONPATH = (Get-Location).Path
# Import / config smoke (no local wiring scripts required):
python -c "from adapters.claw_eval_adapter.official_config import OFFICIAL_JUDGE_MODEL; from core.skill_rerank import llm_rerank_enabled; print(OFFICIAL_JUDGE_MODEL, llm_rerank_enabled())"
```

Materialize 66/133 locally (do not commit): see `PAPER_EVAL.md`.

## History

- **2026-04-25**: Action extraction, title generation, thresholds
- **2026-07-15**: Full PinchBench API parity, nested YAML, OpenClaw inject docs,
  step-level `skills_used`, official judge scores, task context
- **2026-07-16**: Harness-first OpenClaw inject; official judge lock; LLM rerank;
  Pass@3 / paper_split scaffolding; local wiring scripts gitignored
