# SkillAdaptor CLI reference

## Commands

```bash
python run_plugin.py init --workspace PATH [--harness openclaw|claude-code|codex|hermes]
python run_plugin.py --workspace PATH [--dry-run] [--max-iterations N]
python run_plugin.py --workspace PATH --manifest PATH
python run_plugin.py --workspace PATH --input-trajectories PATH
```

## Task sources

1. **folders** (default): `input_task/*.md`
2. **manifest**: `--manifest path/to/active_manifest.json`
3. **auto_discover**: `init --mode auto_discover` (PinchBench)
4. **trajectory seed**: `--input-trajectories` copies into `.skill-adaptor/artifacts/trajectories/`

## Environment

| Variable | Purpose |
|----------|---------|
| `SKILL_ADAPTOR_ROOT` | Directory with `run_plugin.py` (for `scripts/run_evolve.py`) |
| `SkillEvolve_API_KEY` | LLM |
| `SkillEvolve_MODEL` | e.g. gpt-4.1 |
| `SkillAdaptor_HARNESS` | openclaw / claude-code / codex / hermes |
| `HERMES_HOME` | Hermes home (default `~/.hermes`) |
| `PINCHBENCH_PATH` | Live OpenClaw/PinchBench executor |
| `SKILLNET_ENABLED` | Optional post-adopt SkillNet hooks |
