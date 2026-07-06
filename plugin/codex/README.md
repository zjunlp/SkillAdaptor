# Codex CLI

SkillAdaptor exports evolved skills to the paths Codex reads at runtime.

## Install Codex

```bash
# macOS
brew install --cask codex
```

Docs: https://developers.openai.com/codex

Turn on skills in `~/.codex/config.toml`:

```toml
[features]
skills = true
```

Restart Codex after changing skills.

## Run SkillAdaptor

```bash
cd skill-adaptor
python run_plugin.py init --workspace ../my-workspace --harness codex
# Add task briefs under ../my-workspace/input_task/
python run_plugin.py --workspace ../my-workspace --harness codex --dry-run
python run_plugin.py --workspace ../my-workspace --harness codex --max-iterations 2
```

Load API keys first: `source scripts/load_secrets.sh` or `. scripts\load_secrets.ps1`.

## Where skills land

| Path | Role |
|------|------|
| `<workspace>/skills/<id>/SKILL.md` | Canonical export |
| `~/.codex/skills/<id>/SKILL.md` | Global Codex discovery |
| `<workspace>/.agents/skills/<id>/SKILL.md` | Repo-local discovery |

During validation, the active candidate is also written as `skill-adaptor-evolved/SKILL.md` in those trees.

## Marketplace plugin (optional)

Bundle SkillAdaptor as a Codex curated plugin:

1. Copy `plugin/codex/skill-adaptor-plugin/` → `~/.codex/plugins/skill-adaptor/`
2. Merge `plugin/codex/marketplace.fragment.json` into `~/.agents/plugins/marketplace.json`
3. Restart Codex; check the skills list in the Codex UI

The bundled skill `skills/skill-adaptor/SKILL.md` documents how to call `run_plugin.py` from a Codex session.

## Environment

| Variable | Purpose |
|----------|---------|
| `SkillAdaptor_HARNESS` | `codex` |
| `CODEX_HOME` | Default `~/.codex` |
| `OPENAI_API_KEY` | Chat LLM for SkillAdaptor and Codex |
