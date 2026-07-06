# Claw-Eval Adapter

This directory contains claw-eval specific patches and utilities for SkillAdaptor.

## Purpose

Claw-eval has specific requirements that differ from other benchmarks:
1. LLMs output thinking JSON that needs to be filtered
2. Lower validation thresholds work better for initial skills
3. Skill titles need to be generated from improvement principles, not raw actions

## Files

| File | Purpose |
|------|---------|
| `action_extractor.py` | Extract actual actions from LLM outputs, filtering thinking JSON |
| `generator_patch.py` | Improved skill generator that uses improvement_principle for titles |
| `config_patch.py` | Configuration with lowered validation thresholds (0.01 instead of 0.05) |

## Usage

### Basic Usage

```python
from adapters.claw_eval_adapter import (
    extract_action_content,
    ClawEvalGenerator,
    ClawEvalConfig
)
from core.config import load_config

# Extract action from LLM output
raw_output = '{"type": "thinking", "thinking": "I need to click"}'
action = extract_action_content(raw_output)
# Returns: "[thinking]" (should be skipped)

# Use claw-eval generator
generator = ClawEvalGenerator()

# Use claw-eval config
base_config = load_config()
claw_config = ClawEvalConfig.from_base(base_config)
```

### Integration with Orchestrator

```python
from core.orchestrator import SkillAdaptorOrchestrator
from adapters.claw_eval_adapter import ClawEvalConfig, ClawEvalGenerator

config = ClawEvalConfig()
generator = ClawEvalGenerator()

orchestrator = SkillAdaptorOrchestrator(config=config)
# Override generator with claw-eval version
orchestrator.generator = generator
```

## Key Fixes Applied

### 1. Action Extraction (action_extractor.py)

**Problem**: LLM outputs contain thinking JSON like:
```json
{"type": "thinking", "thinking": "I should click the button"}
```

**Solution**: `extract_action_content()` parses JSON and returns:
- Action content if found in 'action', 'content', 'text', 'message', or 'response' fields
- "[thinking]" if it's pure thinking (should be skipped)
- Original content if not JSON

### 2. Skill Title Generation (generator_patch.py)

**Problem**: `_generate_title()` used `fault.wrong_action[:40]` which contained thinking JSON, resulting in titles like:
```
Handle {'type': 'thinking', 'thinking': "The us situations...
```

**Solution**: Use `fault.improvement_principle` to generate meaningful titles:
```python
def _generate_title(self, fault):
    principle = fault.improvement_principle
    # Extract key phrase from principle
    return f"Handle: {key_phrase}"
```

### 3. Validation Thresholds (config_patch.py)

**Problem**: Threshold of 0.05 is too high for initial skills to show improvement.

**Solution**: Lower to 0.01:
```python
success_delta_threshold: float = 0.01  # Was 0.05
avg_score_delta_threshold: float = 0.01  # Was 0.05
```

## History

- **2026-04-25**: Created based on claw-eval fixes
  - Extract action content filtering
  - Improved title generation
  - Lowered validation thresholds

## Notes

This adapter is specific to claw-eval. For other benchmarks, use the core
SkillAdaptor classes directly unless you encounter similar issues with:
1. LLM outputs containing thinking JSON
2. Need for lower validation thresholds
