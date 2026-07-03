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

- Set **`SkillAdaptor_PROVIDER=auto`** in `secrets/.env` (default).
- Configure **`OPENAI_API_BASE_URL`** + **`OPENAI_API_KEY`** for chat (all models).
- Configure **`SkillEvolve_EMBEDDING_*`** for embeddings.
- Switch models with **`--model`** only — no env change per model.

Details: [LLM configuration](../README.md#llm-configuration-url--api-key--model) in the root README.

## Secrets

Copy `../.env.example` → `../secrets/.env` (gitignored). Never commit real keys.
