# Hermes Agent

SkillAdaptor exports evolved skills into Hermes’s category layout under `skill-adaptor/`.

## Install Hermes

```bash
pip install hermes-agent
```

Docs: https://hermes-agent.nousresearch.com/docs/getting-started/installation

Optional extra skill roots in `~/.hermes/config.yaml`:

```yaml
skills:
  external_dirs:
    - ~/.agents/skills
```

## Run SkillAdaptor

```bash
cd skill-adaptor
python run_plugin.py init --workspace ../my-workspace --harness hermes
# Add task briefs under ../my-workspace/input_task/
python run_plugin.py --workspace ../my-workspace --harness hermes --dry-run
python run_plugin.py --workspace ../my-workspace --harness hermes --max-iterations 2
```

Load API keys first: `source scripts/load_secrets.sh` or `. scripts\load_secrets.ps1`.

## Where skills land

| Path | Role |
|------|------|
| `~/.hermes/skills/skill-adaptor/<id>/SKILL.md` | Global Hermes discovery |
| `<workspace>/.hermes/skills/skill-adaptor/<id>/SKILL.md` | Workspace mirror |

During validation, the active candidate is also written as `skill-adaptor-evolved/SKILL.md` under the same category.

## Operator skill (optional)

Install the in-agent operator skill:

```bash
mkdir -p ~/.hermes/skills/skill-adaptor/skill-adaptor
cp -R plugin/skillnet/skills/skill-adaptor/* ~/.hermes/skills/skill-adaptor/skill-adaptor/
```

Restart Hermes after installing or updating skills.

## Environment

| Variable | Purpose |
|----------|---------|
| `SkillAdaptor_HARNESS` | `hermes` |
| `HERMES_HOME` | Default `~/.hermes` (profile-specific with `hermes -p`) |
| `PINCHBENCH_PATH` | PinchBench executor when using `--env pinchbench` |
