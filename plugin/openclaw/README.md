# OpenClaw plugin

OpenClaw provides the UI; this repo provides the Python evolution engine under `skill-adaptor/`.

## Install

**TypeScript plugin** (UI):

```powershell
openclaw plugins install <ABS_PATH>/SkillAdaptor-openclaw/src/skill-adaptor-ts
openclaw plugins enable skill-adaptor
```

**Python bridge** — copy into the TS package:

```text
skill-adaptor/plugin/python/run_openclaw_evolve.py
  → SkillAdaptor-openclaw/src/skill-adaptor-ts/python/run_openclaw_evolve.py
```

The bridge calls `run_plugin.py` and prints `EVOLVE_OUTPUT_FILE=...` for the UI parser.

## Configure

`openclaw.json` or plugin UI:

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
| `benchmarkEnv` | `pinchbench`, `claw-eval`, or `webshop` |
| `allAsTest` | `false` for train/val split; `true` for quick probes only |
| `maxIterations` | Evolution loop cap |

CLI equivalents: `--harness openclaw`, `--program-git` for optional `skill-adaptor/program/*` branches.

## Secrets

Load `secrets/.env` via `scripts/load_secrets.ps1` or `load_secrets.sh`. Set `PINCHBENCH_PATH` (or `CLAW_EVAL_PATH` / `WEBSHOP_PATH`) for live benchmark runs.
