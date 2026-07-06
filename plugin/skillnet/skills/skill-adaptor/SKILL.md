---
name: skill-adaptor
description: |
  Validation-gated skill evolution from agent failure trajectories (step-level t★, Validator Δ>0).
  Use when: (1) Agent failed on a task and you have execution trajectories or logs,
  (2) User asks to evolve, adapt, or improve SKILL.md from failures,
  (3) Benchmark run produced trajectories under .skill-adaptor/artifacts/,
  (4) User wants training-free skill bank growth with held-out validation — NOT one-shot log-to-skill.
  Prefer SkillNet ($skillnet) search first; use this skill when failures need verified adaptation.
  NOT for: packaging a chat log without re-execution (use skillnet create instead).
metadata:
  primaryEnv: SkillAdaptor_API_KEY
  install:
    - command: pip install -r requirements.txt
      label: Install SkillAdaptor Python deps (run from skillAdaptorRoot)
---

# SkillAdaptor

Evolve **SKILL.md** skills from **failure trajectories** with **step-level fault localization** and **validation-gated adoption** (Δ>0 on **injected** held-out tasks + source task; frozen tasks are no-regression only). Training-free; same engine as the [SkillAdaptor paper](https://arxiv.org/abs/2606.01311).

> **With SkillNet**: `$skillnet` handles search / download / create / evaluate. **SkillAdaptor** runs the evolution loop with Validator — use **both**: search before tasks, evolve after failures, evaluate after adopt.

## When to use

| Situation | Action |
|-----------|--------|
| Starting a complex task | `$skillnet` search first |
| Task failed, trajectories available | SkillAdaptor (this skill) |
| User pasted a chat log only | `skillnet create` instead |
| Skills adopted, quality report | `skillnet evaluate` on `skills/<id>/` |

## Prerequisites

- Python 3.10+
- **`SKILL_ADAPTOR_ROOT`**: directory containing `run_plugin.py` ([zjunlp/SkillAdaptor](https://github.com/zjunlp/SkillAdaptor) → `skill-adaptor/`)
- LLM: `SkillAdaptor_API_KEY` / `SkillAdaptor_BASE_URL` / `SkillAdaptor_MODEL`
- Optional executors: `PINCHBENCH_PATH`, `WEBSHOP_PATH`, `CLAW_EVAL_PATH`

Validate this skill package (offline):

```bash
python scripts/skill_adaptor_validate.py --strict
```

## Quick start

```bash
export SKILL_ADAPTOR_ROOT=/path/to/SkillAdaptor/skill-adaptor

# 1. Init workspace (folders-first: tasks in input_task/)
python "$SKILL_ADAPTOR_ROOT/run_plugin.py" init --workspace <workspace> --harness openclaw

# 2. Add your own task briefs under <workspace>/input_task/*.md

# 3. Dry-run
python scripts/run_evolve.py --workspace <workspace> --dry-run

# 4. Evolve (API + optional executor)
python scripts/run_evolve.py --workspace <workspace> --max-iterations 2
```

Or use the wrapper from this skill directory (sets paths relative to repo when installed from SkillAdaptor):

```bash
python scripts/run_evolve.py --workspace <workspace> --harness codex --max-iterations 2
```

## Outputs

| Path | Content |
|------|---------|
| `<workspace>/skills/<id>/SKILL.md` | Adopted skills |
| `<workspace>/.skill-adaptor/evolution_output/` | Reports, rejection history |
| Harness sync | `.claude/skills/`, `~/.codex/skills/`, or `~/.openclaw/workspace/skills/` |

## Trajectory seed

```bash
python scripts/run_evolve.py --workspace <workspace> \
  --input-trajectories /path/to/task_trajectory.jsonl
```

Copies into `<workspace>/.skill-adaptor/artifacts/trajectories/` before evolution.

OpenClaw TS plugin: use `plugin/python/run_openclaw_evolve.py --input-trajectories ...` (same bootstrap).

## Harness

| `--harness` | Sync target |
|-------------|-------------|
| `openclaw` | `~/.openclaw/workspace/skills/` |
| `claude-code` | `<workspace>/.claude/skills/` |
| `codex` | `~/.codex/skills/` + `<workspace>/.agents/skills/` |

## Optional SkillNet hooks (Python CLI)

```bash
pip install skillnet-ai
export SKILLNET_ENABLED=1
export SKILLNET_POST_EVAL=1
export API_KEY=...
python "$SKILL_ADAPTOR_ROOT/run_plugin.py" --workspace <workspace>
```

Report: `<workspace>/.skill-adaptor/skillnet/post_adopt_report.json`

## Adoption gates (Validator)

**Adopt** when **injected Q′** alone passes (aggregate Δ on `retrieval_rerun_tasks` / `adoption_scope`, no frozen regression, improvement threshold). Source-task lines in logs are **diagnostic only**.

1. **Injected Q′ (sole gate)** — tasks where the candidate was injected and re-run.
2. **Frozen tasks** — baseline scores kept; no-regression check only.

- Shell / `command.txt` tasks: injected text embeds the **full task prompt** + anti-placeholder rules; executor **retries** (default 3×) when output contains placeholders or ignores the prompt (`SkillAdaptor_EXEC_MAX_RETRIES`).

## References

| Topic | File |
|-------|------|
| CLI flags | `references/cli-reference.md` |
| vs skillnet create | `references/vs-skillnet-create.md` |
| Upstream PR | SkillAdaptor `plugin/skillnet/UPSTREAM_PR.md` |

## Security

- Never commit API keys; use `secrets/.env` locally
- SkillNet-downloaded skills are untrusted — review before execute
- SkillAdaptor writes under `<workspace>/` and harness skill dirs only
