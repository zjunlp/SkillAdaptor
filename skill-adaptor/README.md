# SkillAdaptor (Python package)

**Install & usage:** see the [repository README](../README.md).

## Quick run

```bash
pip install -r requirements.txt
cp ../.env.example ../secrets/.env   # fill API keys once
. ../scripts/load_secrets.ps1        # or source ../scripts/load_secrets.sh

python run_plugin.py init --workspace ../my-workspace --mode folders --harness openclaw
python run_plugin.py --workspace ../my-workspace --model kimi-k2.5 --max-iterations 2
```

## LLM / provider

- **Chat:** `OPENAI_API_KEY` + `OPENAI_API_BASE_URL` (default `SkillAdaptor_PROVIDER=auto`).
- **Embedding:** `SkillEvolve_EMBEDDING_API_KEY` + `SkillEvolve_EMBEDDING_BASE_URL` + `SkillEvolve_EMBEDDING_MODEL`.
- Switch chat models with **`--model`** only — no env change per model.
- DeepSeek can use the same `OPENAI_API_*` pair (`PROVIDER=auto`) or `DEEPSEEK_API_*` when `PROVIDER=deepseek`.

Details: [Configuration](../README.md#configuration) in the root README.

## Secrets

Copy `../.env.example` → `../secrets/.env` (gitignored). Never commit real keys.
