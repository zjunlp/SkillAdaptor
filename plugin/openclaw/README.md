# OpenClaw TypeScript plugin (SkillAdaptor)

The canonical **TypeScript UI** lives in the sibling repo **SkillEvolve-openclaw** (`src/skill-evolve-ts`).

The **Python evolution engine** (paper-aligned, smoke5 verified) lives in **this repo** under `skill-adaptor/`.

## Architecture (two repos, one pipeline)

```text
OpenClaw UI (TS plugin)
  → python/run_openclaw_evolve.py   # bridge
  → skill-adaptor/run_plugin.py     # workspace + manifest
  → PluginHost → run_pinchbench → SkillEvolveOrchestrator
  → export skills/<id>/SKILL.md
```

## Install TS plugin

```powershell
openclaw plugins install <ABS_PATH>/SkillEvolve-openclaw/src/skill-evolve-ts
openclaw plugins enable skill-adaptor
```

## Sync Python bridge

Copy **this file** into the TS package (overwrite upstream inline runner):

```text
skill-adaptor/plugin/python/run_openclaw_evolve.py
  → SkillEvolve-openclaw/src/skill-evolve-ts/python/run_openclaw_evolve.py
```

The reference bridge delegates to `run_plugin.py` (same path as CLI smoke5_v02), and prints `EVOLVE_OUTPUT_FILE=...` for the TS parser.

## Plugin config (`openclaw.json` or UI)

```json
{
  "skillAdaptorRoot": "<ABS_PATH>/skill-adaptor/skill-adaptor",
  "pythonCommand": "python",
  "benchmarkEnv": "pinchbench",
  "allAsTest": false,
  "maxIterations": 2
}
```

| Field | Meaning |
|-------|---------|
| `skillAdaptorRoot` | Directory containing `run_plugin.py` |
| `benchmarkEnv` | `pinchbench` \| `claw-eval` \| `webshop` |
| `allAsTest` | `false` for normal train/val split; `true` only for quick probes |

CLI also supports `--harness openclaw|claude-code` and `--program-git` (optional git branches `skill-adaptor/program/*`).

## Environment

Same as CLI: `PINCHBENCH_PATH`, `SkillEvolve_API_KEY`, embedding vars. Use `scripts/load_secrets.ps1` when developing locally.

## Do not duplicate the TS tree here

Install from SkillEvolve-openclaw and point `skillAdaptorRoot` at this Python package.
