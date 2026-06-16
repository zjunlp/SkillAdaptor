<div align="center">

# SkillAdaptor: Self-Adapting Skills for LLM Agents from Trajectories

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Paper](https://img.shields.io/badge/📄_Paper-ARXIV_2026-lightgrey)](https://arxiv.org/abs/2606.01311)

<img src="paper/overview.png" alt="SkillAdaptor overview" width="900"/>

[Installation](#installation) ·
[Quick Start](#quick-start) ·
[OpenClaw](#openclaw-typescript-plugin) ·
[Citation](#citation)

**⭐ If you like our project, please give us a star on GitHub for the latest updates!**

</div>

---

**SkillAdaptor** is a **training-free** harness plugin for [OpenClaw](https://github.com/openclaw/openclaw) and **Claude Code**. It evolves agent skills from **real failure trajectories**, and exports adopted skills into your workspace.

- **Step-level attribution** — Localizer finds the accountable failure step **t★** in each trajectory; Linker attributes skills active at that step, then Reviser/Generator proposes a targeted fix
- **Plugin-first** — `run_plugin.py init` + `run_plugin.py`; skills land in `skills/<id>/SKILL.md`
- **`input_task/` auto-parse** — drop task briefs under `workspace/input_task/`; train/val split is inferred (no manifest required)
- **Retrieval-gated inject** — category + embedding matching; no global skill pollution on unrelated tasks

> Optional: `--manifest` / `--template smoke5` for bundled benchmark splits (local repro only).

---

## Key features

| Feature | Description |
|---------|-------------|
| **Step-level adaptation** | Localizer → **t★** fault step · Linker → suspect skills at that step · Reviser/Generator → step-targeted skill edits |
| **Training-free evolution** | Localizer → Linker → Reviser/Generator → Validator (no weight updates) |
| **Dual harness** | `--harness openclaw` (default) or `--harness claude-code` |
| **Workspace plugin** | `run_plugin.py init` + `run_plugin.py` — skills land in `skills/<id>/SKILL.md` |
| **Retrieval-gated inject** | Category + embedding; no global skill pollution on unrelated tasks |

---

## Installation

### 1. Clone & Python deps

```bash
git clone https://github.com/zjunlp/SkillAdaptor.git
cd SkillAdaptor/skill-adaptor
pip install -r requirements.txt
```

### 2. Secrets (never commit)

```bash
cd ..   # repo root (SkillAdaptor/)
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

## Quick start

Install-only path: init workspace → add tasks under `input_task/` → run (no manifest file).

```bash
cd skill-adaptor
python run_plugin.py init --workspace ../my-workspace
# copy or author briefs, e.g. benchmarks/generic_stubs/task_generic_shell_safe.md → my-workspace/input_task/
python run_plugin.py --workspace ../my-workspace --dry-run   # wiring check, no API
python run_plugin.py --workspace ../my-workspace \
  --harness openclaw --provider relay-gpt41 --model gpt-4.1 --max-iterations 2
```

**Workspace layout** (same idea as EvoSkill-style task folders):

| Path | Role |
|------|------|
| `input_task/*.md` | Task briefs — auto-scanned; ~20% held out as validation Q′ |
| `test_task/` | Optional extra held-out stubs |
| `skills/<id>/SKILL.md` | Adopted skills after Validator passes |

Use **`--sync-tasks`** after editing task files. Live OpenClaw runs need `PINCHBENCH_PATH` in `secrets/.env`.

---

## Task brief format

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

> **Executor note:** OpenClaw live runs use the PinchBench OpenClaw bridge (`PINCHBENCH_PATH`). WebShop / Claw-Eval are optional when you set `WEBSHOP_PATH` / `CLAW_EVAL_PATH` and `--env webshop|claw-eval`.

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

## Citation

If you use SkillAdaptor in research, please cite:

```bibtex
@article{skilladaptor2026,
  title={SkillAdaptor: Self-Adapting Skills for LLM Agents from Trajectories},
  author={...},
  year={2026},
  url={https://arxiv.org/abs/2606.01311}
}
```

---

## License

This project is released under the [MIT License](https://opensource.org/licenses/MIT).

---

## Acknowledgement

Structure inspired by open-source agent tooling from [ZJUNLP](https://github.com/zjunlp/) (e.g. [EasyEdit](https://github.com/zjunlp/EasyEdit), [LightMem](https://github.com/zjunlp/LightMem), [SkillNet](https://github.com/zjunlp/SkillNet)).
