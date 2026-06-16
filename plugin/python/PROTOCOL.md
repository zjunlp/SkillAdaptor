# TS ↔ Python bridge protocol

Used by `SkillEvolve-openclaw` `python-bridge.ts` and `plugin/python/run_openclaw_evolve.py`.

## Invocation

```text
python run_openclaw_evolve.py
  --workspace-dir <abs>
  --state-dir <abs>
  --skill-adaptor-root <abs>    # directory containing run_plugin.py
  --env pinchbench|claw-eval|webshop|auto
  --max-iterations <int>
  --all-as-test true|false
  [--input-skills <abs.json>]
  [--input-trajectories <abs.jsonl>]
  [--provider ...] [--model ...]
```

## Response

- Exit code `0` on successful plugin run (note: `final_skill_count=0` is still exit 0 if pipeline completed)
- Stdout line: `EVOLVE_OUTPUT_FILE=<abs-path>`

Result JSON (`plugin_evolution_result.json`) includes:

- `result.final_skill_count`, `result.adopted_skill_ids`
- `final_skill_bank_path`
- `held_out_test` (from run record)
- `run_record` path

## Evolution path (paper-aligned)

Bridge **must not** inline a second orchestrator. It delegates to:

`run_plugin.py` → `PluginHost` → `run_pinchbench` → Validator on full `validation_tasks`.

See smoke5_v02 in `docs/EXPERIMENT_LOG.md`.
