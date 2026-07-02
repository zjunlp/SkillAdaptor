---
name: skill-adaptor
description: Run SkillAdaptor to evolve agent skills from task failures. Use when improving SKILL.md files from trajectories or after benchmark runs.
---

# SkillAdaptor (Codex)

Evolve reusable **SKILL.md** files from failure trajectories. Python CLI in this repo.

## Quick run

From the SkillAdaptor repo (set `skillAdaptorRoot` to the directory containing `run_plugin.py`):

```bash
cd <skillAdaptorRoot>
python run_plugin.py init --workspace <workspace> --harness codex
# add task briefs under <workspace>/input_task/*.md
python run_plugin.py --workspace <workspace> --harness codex --max-iterations 2
```

Outputs: `<workspace>/skills/<id>/SKILL.md` — auto-synced to `~/.codex/skills/` and `<workspace>/.agents/skills/`.

## Harness

Use `--harness codex` (not `openclaw` or `claude-code`) so adopted skills appear in Codex skill discovery paths.

## Docs

See `plugin/codex/README.md` in the SkillAdaptor repository.
