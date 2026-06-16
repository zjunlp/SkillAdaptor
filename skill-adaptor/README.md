# SkillAdaptor (Python package)

**Install & usage:** see the [repository README](../README.md).

```bash
pip install -r requirements.txt
python run_plugin.py init --workspace ../my-workspace --mode folders --harness openclaw
python run_plugin.py --workspace ../my-workspace --max-iterations 2
```

Secrets: copy `../.env.example` → `../secrets/.env` (gitignored).
