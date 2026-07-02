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

**SkillAdaptor** is a **Python CLI + workspace plugin** that evolves agent **`SKILL.md`** files from failure trajectories. It plugs into **[OpenClaw](https://github.com/openclaw/openclaw)**, **Claude Code**, **Codex CLI**, and **[Hermes Agent](https://github.com/NousResearch/hermes-agent)** via a harness layer (`--harness openclaw|claude-code|codex|hermes`) — same evolution engine, different agent runtime. **Not tied to a fixed task list:** you bring any tasks (markdown briefs, manifest, or benchmark auto-discover); the step-level Localizer→Validator pipeline stays the same.

- **Step-level attribution** — Localizer finds **t★**; Linker attributes skills at that step; Reviser/Generator proposes a targeted fix
- **General workspace plugin** — `run_plugin.py init` + `run_plugin.py`; outputs `skills/<id>/SKILL.md` (harness sync: `.claude/skills/`, `~/.codex/skills/`, `~/.hermes/skills/skill-adaptor/`, or OpenClaw workspace)
- **Flexible task sources** — `input_task/*.md` (default) · `--manifest` · `auto_discover` · OpenClaw bridge `--input-trajectories`
- **Retrieval-gated inject** — category + embedding; no global skill pollution on unrelated tasks

> PinchBench / WebShop / Claw-Eval are **optional executors** (set env paths). Core plugin works on any task briefs you provide.

---

## Key features

| Feature | Description |
|---------|-------------|
| **Step-level adaptation** | Localizer → **t★** fault step · Linker → suspect skills at that step · Reviser/Generator → step-targeted skill edits |
| **Training-free evolution** | Localizer → Linker → Reviser/Generator → Validator (no weight updates) |
| **Agent harness plugin** | Python CLI → OpenClaw gateway, Claude Code `.claude/skills/`, Codex `~/.codex/skills/`, or Hermes `~/.hermes/skills/skill-adaptor/` |
| **General task input** | `input_task/` · `--manifest` · `--mode auto_discover` · bridge trajectories |
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
**Claude Code:** `--harness claude-code` → syncs to `.claude/skills/`.  
**Codex CLI:** `--harness codex` → syncs to `~/.codex/skills/` and `.agents/skills/` ([install guide](plugin/codex/README.md)).  
**Hermes Agent:** `--harness hermes` → syncs to `~/.hermes/skills/skill-adaptor/` ([install guide](plugin/hermes/README.md)).

---

## Quick start

**Python CLI** (works standalone or behind the OpenClaw TS plugin):

```bash
cd skill-adaptor
python run_plugin.py init --workspace ../my-workspace --harness claude-code   # or openclaw / codex / hermes
# Task source A: add your own *.md briefs under my-workspace/input_task/
python run_plugin.py --workspace ../my-workspace --dry-run
python run_plugin.py --workspace ../my-workspace --max-iterations 2
```

**Task sources** (pick one or combine with `--sync-tasks`):

| Source | When to use |
|--------|-------------|
| `input_task/*.md` | **Default** — any custom tasks (EvoSkill-style workspace folders) |
| `--manifest path.json` | Repro/paper splits (local file, optional) |
| `--mode auto_discover` | Auto-split tasks from `PINCHBENCH_PATH` checkout |
| OpenClaw bridge `--input-trajectories` | Seed failures from existing trajectory files |

**Workspace layout:**

| Path | Role |
|------|------|
| `input_task/*.md` | Task briefs — auto-scanned; ~20% held out as validation Q′ |
| `test_task/` | Optional extra held-out task briefs |
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

Optional held-out briefs: `my-workspace/test_task/`.

**Validation split:** auto-derived from `input_task/` (first ~20% → Q′, rest → train). No `validation_task/` folder required.

> **Executor note:** OpenClaw live runs use the PinchBench OpenClaw bridge (`PINCHBENCH_PATH`). WebShop / Claw-Eval are optional when you set `WEBSHOP_PATH` / `CLAW_EVAL_PATH` and `--env webshop|claw-eval`.

---

## OpenClaw plugin (TS UI + Python engine)

Like EvoSkill: **Python CLI is the engine**; OpenClaw adds a TypeScript plugin shell that calls it.

```
OpenClaw TS plugin  →  plugin/python/run_openclaw_evolve.py  →  run_plugin.py  →  PluginHost
```

Configure in `openclaw.json`:

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

## Claude Code (direct install)

Adopted skills sync to `.claude/skills/`. **Exporting skills does not require OpenClaw**; live PinchBench validation (`--env pinchbench`) still runs tasks through the **OpenClaw gateway** and needs `PINCHBENCH_PATH` (same executor as `--harness openclaw`).

```bash
python run_plugin.py init --workspace /path/to/your-project --harness claude-code
# add tasks under /path/to/your-project/input_task/
# load API keys: source scripts/load_secrets.sh  (or secrets/.env on Windows)
python run_plugin.py --workspace /path/to/your-project --harness claude-code
```

---

## Codex CLI (direct install)

No OpenClaw required — adopted skills sync to Codex discovery paths (`~/.codex/skills/` + `.agents/skills/`):

```bash
python run_plugin.py init --workspace /path/to/your-project --harness codex
python run_plugin.py --workspace /path/to/your-project --harness codex
```

Enable skills in `~/.codex/config.toml` (`[features] skills = true`) and restart Codex. See [plugin/codex/README.md](plugin/codex/README.md) for marketplace plugin install.

---

## Hermes Agent (direct install)

No OpenClaw required — adopted skills sync to Hermes category layout (`~/.hermes/skills/skill-adaptor/`):

```bash
python run_plugin.py init --workspace /path/to/your-project --harness hermes
python run_plugin.py --workspace /path/to/your-project --harness hermes
```

See [plugin/hermes/README.md](plugin/hermes/README.md) for `HERMES_HOME`, `skills.external_dirs`, and operator skill install.

---

## Configuration

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` / `OPENAI_API_BASE_URL` | LLM (OpenAI-compatible) |
| `SkillEvolve_API_KEY` / `SkillEvolve_BASE_URL` | Aliases for plugin |
| `SkillEvolve_MODEL` | e.g. `gpt-4.1` |
| `SkillEvolve_EMBEDDING_MODEL` | Default `Qwen3-Embedding-8B` |
| `SkillAdaptor_PROVIDER` | `relay-gpt41` \| `deepseek` \| `openrouter` |
| `SkillAdaptor_HARNESS` | `openclaw` \| `claude-code` \| `codex` \| `hermes` |
| `CODEX_HOME` | Codex home (default `~/.codex`) |
| `HERMES_HOME` | Hermes home (default `~/.hermes`) |
| `PINCHBENCH_PATH` | Required for OpenClaw live execution |
| `OPENCLAW_CLI` | Optional explicit `openclaw` path |

Full template: [`.env.example`](.env.example).

---

## Citation

If you use SkillAdaptor in research, please cite:

```bibtex
@article{skilladaptor2026,
  title={SkillAdaptor: Self-Adapting Skills for LLM Agents from Trajectories},
  author={Zhuoyun Yu, Xin Xie, Wuguannan Yao, Chenxi Wang, Lei Liang, Xiang Qi, Shumin Deng},
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
