# Codex CLI plugin (SkillAdaptor)

**Python evolution engine** lives in `skill-adaptor/` (same as OpenClaw / Claude Code). The Codex harness syncs adopted skills into paths Codex discovers at runtime.

## Architecture

```text
Codex CLI (or OpenClaw codex harness)
  → reads ~/.codex/skills/**/SKILL.md
  → reads <workspace>/.agents/skills/**/SKILL.md   # EvoSkill-compatible repo-local path

SkillAdaptor CLI
  → run_plugin.py --harness codex
  → export skills/<id>/SKILL.md
  → sync to ~/.codex/skills/ + workspace/.agents/skills/
```

This mirrors [EvoSkill](https://github.com/sentient-agi/EvoSkill): Codex discovers skills via **`~/.codex/skills/`** and repo-local **`.agents/skills/`** (no OpenClaw gateway required).

## Install Codex CLI

```bash
# macOS
brew install --cask codex

# Or see https://developers.openai.com/codex
```

Enable skills in `~/.codex/config.toml` (if not already on):

```toml
[features]
skills = true
```

Restart Codex after installing skills.

## Use SkillAdaptor with Codex

```bash
cd skill-adaptor
python run_plugin.py init --workspace ../my-workspace --harness codex
# add your own task brief under ../my-workspace/input_task/
python run_plugin.py --workspace ../my-workspace --harness codex --dry-run
python run_plugin.py --workspace ../my-workspace --harness codex --max-iterations 2
```

Adopted skills land in:

| Path | Purpose |
|------|---------|
| `<workspace>/skills/<id>/SKILL.md` | Canonical SkillAdaptor export |
| `~/.codex/skills/<id>/SKILL.md` | Codex global skill discovery |
| `<workspace>/.agents/skills/<id>/SKILL.md` | Repo-local discovery (EvoSkill-style) |

During validation runs, the active candidate is also injected as `skill-adaptor-evolved/SKILL.md` in those trees.

## Optional: native Codex plugin (marketplace)

To register SkillAdaptor as a **Codex curated plugin** (skills bundled with a marketplace entry):

1. Copy `plugin/codex/skill-adaptor-plugin/` to `~/.codex/plugins/skill-adaptor/`
2. Merge `plugin/codex/marketplace.fragment.json` into `~/.agents/plugins/marketplace.json`
3. Restart Codex and verify with `/codex skills` (OpenClaw) or Codex desktop skills list

The bundled meta-skill `skills/skill-adaptor/SKILL.md` documents how to invoke `run_plugin.py` from a Codex session.

## OpenClaw + Codex harness

If you run OpenClaw with the bundled **codex** plugin (`plugins.entries.codex.enabled`), OpenClaw routes OpenAI model turns through Codex app-server. SkillAdaptor still evolves skills via Python CLI; point `--harness codex` so exports land in `~/.codex/skills/`. Use `openclaw migrate codex` to inventory personal Codex skills into OpenClaw when needed.

## Environment

| Variable | Purpose |
|----------|---------|
| `SkillAdaptor_HARNESS` | Set to `codex` |
| `CODEX_HOME` | Default `~/.codex` |
| `OPENAI_API_KEY` | Codex + SkillAdaptor LLM calls |

Same secrets loading as CLI: `scripts/load_secrets.ps1` / `load_secrets.sh`.
