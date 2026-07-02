# SkillNet ecosystem integration

SkillAdaptor can be used **alongside** [zjunlp/SkillNet](https://github.com/zjunlp/SkillNet) as a portable Agent Skill (this folder) plus optional Python hooks (`runtime/skillnet_bridge.py`).

## Install as Agent Skill (like `skills/skillnet`)

Copy into your agent skills directory:

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

Install **both** `skillnet` and `skill-adaptor` skills for the recommended workflow: search → execute → evolve on failure → evaluate.

Point `skillAdaptorRoot` at the `skill-adaptor/` directory containing `run_plugin.py`.

## Optional: post-adopt SkillNet evaluate

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
| `SKILLNET_POST_EVAL` | `0` | `skillnet evaluate` each adopted skill |
| `SKILLNET_POST_ANALYZE` | `0` | `skillnet analyze` on workspace `skills/` |

## Upstream PR to SkillNet

See [UPSTREAM_PR.md](../UPSTREAM_PR.md) for copying `skills/skill-adaptor/` into [zjunlp/SkillNet](https://github.com/zjunlp/SkillNet).

Validate package before install:

```bash
python plugin/skillnet/skills/skill-adaptor/scripts/skill_adaptor_validate.py --strict
```
