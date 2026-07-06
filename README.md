<div align="center">

# SkillAdaptor: Self-Adapting Skills for LLM Agents from Trajectories

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![arXiv](https://img.shields.io/badge/arXiv-2606.01311-b5212f.svg?logo=arxiv)](https://arxiv.org/abs/2606.01311)

<img src="paper/overview.png" alt="SkillAdaptor overview" width="900"/>

[Installation](#installation) ·
[Quick Start](#quick-start) ·
[Step-level trajectories](#step-level-trajectory-extraction) ·
[Paper](#paper) ·
[OpenClaw](#openclaw-typescript-plugin) ·
[Citation](#citation)


</div>

---

**SkillAdaptor** is a **Python CLI + workspace plugin** that evolves agent **`SKILL.md`** files from failure trajectories. It plugs into **[OpenClaw](https://github.com/openclaw/openclaw)**, **Claude Code**, **Codex CLI**, and **[Hermes Agent](https://github.com/NousResearch/hermes-agent)** via a harness layer (`--harness openclaw|claude-code|codex|hermes`) — same evolution engine, different agent runtime. **Not tied to a fixed task list:** you bring any tasks (markdown briefs, manifest, or benchmark auto-discover); the step-level Localizer→Validator pipeline stays the same.

- **Step-level attribution** — On a failed agent run, SkillAdaptor reads the step-by-step trace: the **Localizer** marks the earliest bad step **t★** (e.g. wrong tool call or deliverable); the **Linker** scores which injected `SKILL.md` is responsible at that step; **Reviser** patches that skill or **Generator** writes a new one; **Validator** re-runs held-out tasks and adopts only if metrics beat the baseline.
- **General workspace plugin** — `run_plugin.py init` + `run_plugin.py`; outputs `skills/<id>/SKILL.md` (harness sync: `.claude/skills/`, `~/.codex/skills/`, `~/.hermes/skills/skill-adaptor/`, or OpenClaw workspace)
- **Flexible task sources** — `input_task/*.md` (default) · `--manifest` · `auto_discover` · OpenClaw bridge `--input-trajectories`
- **Retrieval-gated inject** — no global skill pollution on unrelated tasks

> PinchBench / WebShop / Claw-Eval are **optional executors** (set env paths). Core plugin works on any task briefs you provide.

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

Set `PINCHBENCH_PATH` in `secrets/.env` only when using the PinchBench benchmark executor.
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

Use **`--sync-tasks`** after editing task files. For **workspace-only** runs (`--env workspace`, default when no benchmark path is set), tasks live in `input_task/` and do **not** need `PINCHBENCH_PATH`. Set `PINCHBENCH_PATH` only for PinchBench / Claw-Eval benchmark executors.

---

## Step-level trajectory extraction

SkillAdaptor **extracts steps automatically** from agent run artifacts — you do not hand-label trajectories for the evolution loop.

| Source | Typical executor | What gets parsed |
|--------|------------------|------------------|
| OpenClaw session JSONL | `workspace`, PinchBench | `toolCall` / `tool_use` → one step per tool call |
| Claw-Eval trace JSONL | `claw-eval` | `tool_use` events in trace files |
| PinchBench transcript | `pinchbench` | Native transcript + OpenClaw extract (merged) |
| Pre-seeded files | `--input-trajectories` | Copied into `.skill-adaptor/artifacts/trajectories/` |

Merged steps are written to `{task_id}_annotated.json` with `metadata.step_provenance` (e.g. `native_primary_enriched`, `extracted_primary`) and per-step `action` / `observation`.

### Tool actions required

Step-level Localizer → Linker → Reviser/Generator **only runs on real tool steps**. Each usable step must have a **tool-level `action`**, e.g.:

```text
shell({"command": "grep ERROR app.log"})
write({"path": "report.txt", "content": "..."})
```

The following **do not** count as evolution-grade steps:

- `(assistant response)` — text-only turns with no tool call  
- Empty / placeholder actions (`(no action)`, `(end)`, …)  
- Runs with score but **no** parseable tool trace  

If a live run produces no qualifying steps, SkillAdaptor **fails fast** (`TaskExecutionError`) instead of silently inventing a trajectory.

### Exceptions (probes only)

| Mode | Behavior |
|------|----------|
| Default | No trace → **error**; evolution stops for that task |
| `probe_mode=true` in manifest | Sets `ALLOW_SYNTHETIC_TRAJECTORY=1`; may synthesize a **1-step** minimal trajectory when only score/text is available |
| `--input-trajectories` | Seed real traces before evolution (still must contain tool actions to be useful) |

Check `steps[].metadata.step_provenance` and `steps[].action` in `{task_id}_annotated.json` to confirm a run is real, not synthetic.

---

## LLM configuration (URL / API key / model)

Configure **one chat API** + **one embedding API** in `secrets/.env`. Switch models with **`--model` only** — no env edits per model.

### Recommended setup

```bash
# secrets/.env
SkillAdaptor_PROVIDER=auto
OPENAI_API_BASE_URL=https://your-api.example.com/v1
OPENAI_API_KEY=sk-...
SkillEvolve_MODEL=gpt-4.1

SkillEvolve_EMBEDDING_API_KEY=sk-...
SkillEvolve_EMBEDDING_BASE_URL=https://your-embedding-api.example.com/v1
SkillEvolve_EMBEDDING_MODEL=text-embedding-3-small
```

```bash
. scripts/load_secrets.ps1   # or source scripts/load_secrets.sh
cd skill-adaptor

# Same .env — only change --model:
python run_plugin.py --workspace ../my-workspace --model gpt-4.1
python run_plugin.py --workspace ../my-workspace --model kimi-k2.5
python run_plugin.py --workspace ../my-workspace --model glm-5
```

At runtime the plugin writes **one canonical env set** for the whole pipeline:

`SkillEvolve_*`, `OPENAI_*`, `MODEL`, `SkillAdaptor_ACTIVE_PROVIDER`.

### Optional alternate chat providers

Set `SkillAdaptor_PROVIDER` only when you need a different chat backend entirely:

| `SkillAdaptor_PROVIDER` | Env vars |
|-------------------------|----------|
| `auto` (default) | `OPENAI_API_KEY` + `OPENAI_API_BASE_URL` |
| `deepseek` | `DEEPSEEK_API_*` |
| `openrouter` | `OPENROUTER_API_*` |

Legacy names (`relay-gpt41`, `relay-kimi`, `gpt`, `glm`) map to `auto`.

### Embeddings

Skill–task matching always uses `SkillEvolve_EMBEDDING_*` (independent from chat URL/key).



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
| `SkillAdaptor_PROVIDER` | `auto` (default) \| `deepseek` \| `openrouter` |
| `OPENAI_API_KEY` / `OPENAI_API_BASE_URL` | Chat LLM (all models via `--model`) |
| `SkillEvolve_MODEL` | Default model when `--model` omitted |
| `SkillEvolve_EMBEDDING_*` | Embedding API (skill retrieval) |
| `DEEPSEEK_API_*` | Only when `SkillAdaptor_PROVIDER=deepseek` |
| `OPENROUTER_API_*` | Only when `SkillAdaptor_PROVIDER=openrouter` |
| `SkillAdaptor_HARNESS` | `openclaw` \| `claude-code` \| `codex` \| `hermes` |
| `CODEX_HOME` | Codex home (default `~/.codex`) |
| `HERMES_HOME` | Hermes home (default `~/.hermes`) |
| `PINCHBENCH_PATH` | PinchBench executor only (`--env pinchbench`) |
| `CLAW_EVAL_PATH` | Claw-Eval executor only (`--env claw-eval`) |
| `ALLOW_SYNTHETIC_TRAJECTORY` | `1` to allow 1-step fallback when no tool trace (probes; not for paper eval) |
| `OPENCLAW_CLI` | Optional explicit `openclaw` path |

Full template: [`.env.example`](.env.example).

---

## Paper

**[SkillAdaptor: Self-Adapting Skills for LLM Agents from Trajectories](https://arxiv.org/abs/2606.01311)** ([arXiv:2606.01311](https://arxiv.org/abs/2606.01311))

Method overview figure: [`paper/overview.png`](paper/overview.png) (also shown above).

---

## Citation

If you use SkillAdaptor in research, please cite:

```bibtex
@misc{yu2026skilladaptor,
  title={SkillAdaptor: Self-Adapting Skills for LLM Agents from Trajectories},
  author={Zhuoyun Yu and Xin Xie and Wuguannan Yao and Chenxi Wang and Lei Liang and Xiang Qi and Shumin Deng},
  year={2026},
  eprint={2606.01311},
  archivePrefix={arXiv},
  primaryClass={cs.AI},
  url={https://arxiv.org/abs/2606.01311}
}
```

---

## License

This project is released under the [MIT License](https://opensource.org/licenses/MIT).

---

## Acknowledgement

Structure inspired by open-source agent tooling from [ZJUNLP](https://github.com/zjunlp/) (e.g. [EasyEdit](https://github.com/zjunlp/EasyEdit), [LightMem](https://github.com/zjunlp/LightMem), [SkillNet](https://github.com/zjunlp/SkillNet)).
