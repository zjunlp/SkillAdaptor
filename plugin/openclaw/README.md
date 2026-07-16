# OpenClaw plugin

OpenClaw is the **default harness** for SkillAdaptor (workspace / PinchBench / Claw-Eval).
This repo ships the Python evolution engine; the TypeScript UI plugin lives in a sibling package.

## Prerequisites (live runs)

```powershell
npm install -g openclaw
openclaw gateway start
openclaw gateway status
```

Windows: if `openclaw` is not on PATH, set in `secrets/.env`:

```text
OPENCLAW_CLI=C:\Users\you\AppData\Roaming\npm\openclaw.cmd
```

Load secrets from repo root:

```powershell
. .\scripts\load_secrets.ps1
```

Required for live evolve: chat + embedding keys. Claw-Eval also needs official judge credentials
(`CLAW_EVAL_JUDGE_*` or `OPENROUTER_API_KEY` serving `google/gemini-3-flash-preview`).

Skill inject surface (written by harness):

```text
~/.openclaw/workspace/skills/skill-adaptor-evolved/SKILL.md
```

## Install (UI plugin)

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
| `benchmarkEnv` | `pinchbench`, `claw-eval`, `workspace`, or `webshop` |
| `allAsTest` | `false` for train/val split; `true` for quick probes only |
| `maxIterations` | Evolution loop cap |

CLI (no TS UI required):

```powershell
cd skill-adaptor
python run_plugin.py init --workspace ../my-workspace --harness openclaw
python run_plugin.py --workspace ../my-workspace --harness openclaw --dry-run
python run_plugin.py --workspace ../my-workspace --harness openclaw --max-iterations 2
```

## Benchmarks via OpenClaw harness

| Env | Extra env | Notes |
|-----|-----------|--------|
| `workspace` | none | Tasks in `input_task/*.md` |
| `pinchbench` | `PINCHBENCH_PATH` | Gateway required |
| `claw-eval` | `CLAW_EVAL_PATH` + judge keys + `--task-manifest` | OpenClaw inject + claw-eval CLI grade |

Do not collapse Claw-Eval to “OpenClaw chat only” — graders need `claw_eval.cli run` + official judge.

## Secrets

See root `.env.example`. Never commit `secrets/.env` or local task-ID manifests.
