<div align="center">

# SkillAdaptor

**Self-Adapting Skills for LLM Agents from Trajectories**

*Training-free · Plugin-first · OpenClaw & Claude Code*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](skill-adaptor/requirements.txt)

📄 [**Paper (PDF)**](paper/skilladaptor.pdf)

<img src="paper/overview.png" alt="SkillAdaptor overview" width="900"/>

</div>

---

## Overview

**SkillAdaptor** evolves agent **`SKILL.md`** files from **real failure trajectories**, validates each candidate with **A/B testing** on a held-out validation set **Q′**, and exports adopted skills into your workspace. It is a **harness plugin** for [OpenClaw](https://github.com/openclaw/openclaw) and **Claude Code**: you define a **task set**, the agent runs on those tasks, failures drive skill generation, and the **Validator** decides adopt vs reject.

> **Not limited to three benchmarks.** Bundled manifests (PinchBench / WebShop / Claw-Eval) are optional. For **your own tasks**, use **`init --mode folders`**, drop task briefs under `input_task/`, and evolve on the **same task group** with retrieval-gated injection and triple validation gates.

---

## Key features

| Feature | Description |
|---------|-------------|
| **Training-free evolution** | Localizer → Linker → Reviser/Generator → Validator (no weight updates) |
| **Dual harness** | `--harness openclaw` (default) or `--harness claude-code` |
| **Workspace plugin** | `run_plugin.py init` + `run_plugin.py` — skills land in `skills/<id>/SKILL.md` |
| **Retrieval-gated inject** | Category + embedding; no global skill pollution on unrelated tasks |
| **Triple adopt gates** | Source task Δ>0 · category HOLD_BASELINE · full Q′ HOLD_BASELINE |
| **Anti-leak** | Disjoint manifests enforced; embedding text excludes task IDs |
| **Fail-fast** | No silent LLM/embedding fallback |
| **Evolution audit** | `evolution_output/evolution_audit.jsonl` — per-candidate adopt/reject record |

---

## Installation

### 1. Clone & Python deps

```bash
git clone https://github.com/zjunlp/SkillAdaptor.git
cd skill-adaptor/skill-adaptor
pip install -r requirements.txt
```

### 2. Secrets (never commit)

```bash
cd ..   # repo root
mkdir -p secrets
cp .env.example secrets/.env
# Edit secrets/.env — API keys & paths (placeholders only in .env.example)
```

```bash
# Linux / macOS
source scripts/load_secrets.sh

# Windows PowerShell
. scripts\load_secrets.ps1
```

### 3. Agent harness

**OpenClaw (recommended for live runs)**

```bash
npm install -g openclaw
openclaw gateway start
openclaw gateway status   # Connectivity probe: ok
```

Set `PINCHBENCH_PATH` in `secrets/.env` to your PinchBench checkout (OpenClaw task runner).  
**Claude Code:** use `--harness claude-code`; adopted skills sync to `.claude/skills/`.

---

## Quick start (bundled smoke — wiring check)

```bash
cd skill-adaptor
python run_plugin.py init --workspace ../my-workspace --template smoke5
python run_plugin.py \
  --workspace ../my-workspace \
  --manifest ../benchmarks/manifests/pinchbench_smoke_5.json \
  --harness openclaw \
  --provider relay-gpt41 --model gpt-4.1 \
  --max-iterations 2 --env pinchbench
```

**Success:** log `-> ADOPTED` and `my-workspace/skills/<skill_id>/SKILL.md`.

---

## Generic tasks (any task set — core plugin path)

Use this when you are **not** tied to a bundled benchmark manifest.

### 1. Initialize empty workspace

```bash
cd skill-adaptor
python run_plugin.py init \
  --workspace ../my-workspace \
  --mode folders \
  --harness openclaw \
  --benchmark pinchbench
```

### 2. Add your tasks

Copy or author markdown briefs under `my-workspace/input_task/` (see [generic stubs](benchmarks/generic_stubs/) for format):

```markdown
---
id: my_task_fix_deploy
category: devops
---

# Fix broken deploy script

## Prompt
...

## Grading Criteria
...
```

Optional held-out stubs: `my-workspace/test_task/`.

**Validation split:** auto-derived from `input_task/` (first ~20% → Q′, rest → train). No `validation_task/` folder required.

### 3. Run evolution on the same task group

```bash
python run_plugin.py \
  --workspace ../my-workspace \
  --harness openclaw \
  --provider relay-gpt41 --model gpt-4.1 \
  --max-iterations 3
```

Manifest is resolved from workspace folders + `project.json`. Use **`--sync-tasks`** after editing task files.

> **Executor note:** OpenClaw live runs use the PinchBench OpenClaw bridge (`PINCHBENCH_PATH`). WebShop / Claw-Eval are optional adapters when you set `WEBSHOP_PATH` / `CLAW_EVAL_PATH` and `--env webshop|claw-eval`.

---

## OpenClaw TypeScript plugin

Python engine (this repo):

```
plugin/python/run_openclaw_evolve.py  →  skill-adaptor/run_plugin.py  →  PluginHost
```

Configure in your OpenClaw plugin (`openclaw.json`):

```json
{
  "skillAdaptorRoot": "/absolute/path/to/skill-adaptor/skill-adaptor",
  "pythonCommand": "python",
  "benchmarkEnv": "pinchbench",
  "maxIterations": 2
}
```

See [plugin/openclaw/README.md](plugin/openclaw/README.md). TS UI lives in a separate repo (e.g. SkillEvolve-openclaw).

---

## Claude Code

```bash
python run_plugin.py init --workspace ../my-workspace --mode folders --harness claude-code
python run_plugin.py --workspace ../my-workspace --harness claude-code ...
```

Adopted skills are exported to `skills/<id>/SKILL.md` and synced to `.claude/skills/`.

---

## Configuration

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` / `OPENAI_API_BASE_URL` | LLM (OpenAI-compatible) |
| `SkillEvolve_API_KEY` / `SkillEvolve_BASE_URL` | Aliases for plugin |
| `SkillEvolve_MODEL` | e.g. `gpt-4.1` |
| `SkillEvolve_EMBEDDING_MODEL` | Default `Qwen3-Embedding-8B` |
| `SkillAdaptor_PROVIDER` | `relay-gpt41` \| `deepseek` \| `openrouter` |
| `SkillAdaptor_HARNESS` | `openclaw` \| `claude-code` |
| `PINCHBENCH_PATH` | Required for OpenClaw live execution |
| `OPENCLAW_CLI` | Optional explicit `openclaw` path |

Full template: [`.env.example`](.env.example).

---

## Repository layout (what we ship)

```
skill-adaptor/              # Python plugin core + tests
plugin/python/              # OpenClaw bridge
plugin/openclaw/            # TS wiring notes
benchmarks/manifests/       # Optional bundled task splits
benchmarks/generic_stubs/   # Portable task brief examples
paper/skilladaptor.pdf      # Method paper
scripts/                    # load_secrets, init_workspace, verify_env
README.md                   # This file
```

**Not in git:** `secrets/`, any `plugin/workspace*` run dirs, trajectories, logs (`see .gitignore`).

---

## Validation gates (adoption)

| Gate | Scope | Rule |
|------|-------|------|
| Source | `created_from` task | **Δ > 0** (success or avg score) |
| Category | Same `domain_category` on Q′ | HOLD_BASELINE (no regression) |
| Full Q′ | All validation tasks | HOLD_BASELINE; unrelated tasks frozen at baseline on revised eval |

---

## Security before `git push`

```powershell
.\scripts\verify_before_push.ps1
```

Never commit `secrets/.env`. Rotate keys if they were ever staged.

---

## Tests & CI

```bash
cd skill-adaptor
python -m pytest tests/ -q --ignore=tests/integration
```

GitHub Actions: import checks + `run_plugin.py --dry-run` (no API keys).

---

## Citation

If you use SkillAdaptor in research, please cite:

```bibtex
@article{skilladaptor2026,
  title={SkillAdaptor: Self-Adapting Skills for LLM Agents from Trajectories},
  author={...},
  year={2026},
  note={Paper: paper/skilladaptor.pdf}
}
```

---

## License

This project is released under the [MIT License](LICENSE).

---

## Acknowledgement

Structure inspired by open-source agent tooling from [ZJUNLP](https://github.com/zjunlp/) (e.g. [EasyEdit](https://github.com/zjunlp/EasyEdit), [LightMem](https://github.com/zjunlp/LightMem), [SkillNet](https://github.com/zjunlp/SkillNet)).
