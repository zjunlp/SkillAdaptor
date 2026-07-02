# Hermes Agent plugin (SkillAdaptor)

**Python evolution engine** lives in `skill-adaptor/` (same as OpenClaw / Claude Code / Codex). The Hermes harness syncs adopted skills into paths [Hermes Agent](https://github.com/NousResearch/hermes-agent) discovers at runtime.

## Architecture

```text
Hermes Agent CLI
  → reads ~/.hermes/skills/<category>/<skill_id>/SKILL.md
  → optional skills.external_dirs in ~/.hermes/config.yaml

SkillAdaptor CLI
  → run_plugin.py --harness hermes
  → export skills/<id>/SKILL.md
  → sync to ~/.hermes/skills/skill-adaptor/ + workspace/.hermes/skills/skill-adaptor/
```

Hermes organizes skills by **category** (for example `mlops/axolotl/SKILL.md`). SkillAdaptor uses category **`skill-adaptor`** so evolved skills stay grouped and do not collide with bundled Hermes skills.

## Install Hermes Agent

```bash
# See https://hermes-agent.nousresearch.com/docs/getting-started/installation
pip install hermes-agent
```

Optional: point Hermes at additional skill roots in `~/.hermes/config.yaml`:

```yaml
skills:
  external_dirs:
    - ~/.agents/skills
```

## Use SkillAdaptor with Hermes

```bash
cd skill-adaptor
python run_plugin.py init --workspace ../my-workspace --harness hermes
# add your own task brief under ../my-workspace/input_task/
python run_plugin.py --workspace ../my-workspace --harness hermes --dry-run
python run_plugin.py --workspace ../my-workspace --harness hermes --max-iterations 2
```

Adopted skills land in:

| Path | Purpose |
|------|---------|
| `~/.hermes/skills/skill-adaptor/<id>/SKILL.md` | Hermes global skill discovery |
| `<workspace>/.hermes/skills/skill-adaptor/<id>/SKILL.md` | Workspace-local mirror for version control |

During evolution, the active candidate skill is also written to `skill-adaptor-evolved/SKILL.md` under the same category (same pattern as Codex `skill-adaptor-evolved`).

## Environment

| Variable | Purpose |
|----------|---------|
| `SkillAdaptor_HARNESS` | Set to `hermes` |
| `HERMES_HOME` | Default `~/.hermes` (profile-specific when using `hermes -p`) |
| `PINCHBENCH_PATH` | Live PinchBench executor when running `--env pinchbench` |

## Bundled operator skill

Copy the SkillAdaptor operator skill into Hermes (optional, for in-agent `/skill-adaptor` usage):

```bash
mkdir -p ~/.hermes/skills/skill-adaptor/skill-adaptor
cp -R plugin/skillnet/skills/skill-adaptor/* ~/.hermes/skills/skill-adaptor/skill-adaptor/
```

Restart Hermes after installing or updating skills.
