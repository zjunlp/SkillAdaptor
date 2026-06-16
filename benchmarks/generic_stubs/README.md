# Generic task stubs (harness-agnostic briefs)

These markdown files describe **portable** agent tasks (CSV, shell, API health, doc extract).
Use them as:

1. **Documentation** for what “universal” plugin tasks look like
2. **Workspace stubs** — copy into `plugin/workspace/input_task/` for `folders` mode init
3. **Future mock benchmark** — wire a local grader without PinchBench/WebShop/Claw

Real evolution still needs a benchmark executor (PinchBench / WebShop / Claw-Eval).
For tri-benchmark smoke, use `benchmarks/manifests/*_micro_*.json` instead.
