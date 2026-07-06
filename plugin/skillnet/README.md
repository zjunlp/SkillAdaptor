# SkillNet integration

Portable Agent Skill in `plugin/skillnet/skills/skill-adaptor/`, plus optional Python hooks in `runtime/skillnet_bridge.py`.

## Install the skill

```bash
# OpenClaw
cp -R plugin/skillnet/skills/skill-adaptor ~/.openclaw/workspace/skills/skill-adaptor

# Claude Code
mkdir -p ~/.claude/skills
cp -R plugin/skillnet/skills/skill-adaptor ~/.claude/skills/skill-adaptor

# Codex
mkdir -p ~/.codex/skills
cp -R plugin/skillnet/skills/skill-adaptor ~/.codex/skills/skill-adaptor
```

Point `skillAdaptorRoot` at the `skill-adaptor/` directory that contains `run_plugin.py`.

## Post-adopt evaluation (optional)

```bash
pip install skillnet-ai
export SKILLNET_ENABLED=1
export SKILLNET_POST_EVAL=1
export API_KEY=...
python run_plugin.py --workspace <ws> --max-iterations 2
```

| Variable | Default | Meaning |
|----------|---------|---------|
| `SKILLNET_ENABLED` | `0` | Master switch |
| `SKILLNET_POST_EVAL` | `0` | Run `skillnet evaluate` on each adopted skill |
| `SKILLNET_POST_ANALYZE` | `0` | Run `skillnet analyze` on workspace `skills/` |

## Validate before install

```bash
python plugin/skillnet/skills/skill-adaptor/scripts/skill_adaptor_validate.py --strict
```

Upstream packaging notes: [UPSTREAM_PR.md](../UPSTREAM_PR.md).
