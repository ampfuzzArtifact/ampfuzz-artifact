# AMPFuzz: LLM-Enhanced Smart Contract Fuzzing

This repository contains implementation artifacts for our LLM-enhanced smart contract fuzzing approach. Following reviewer feedback on reproducibility, we provide the exact prompts, model configurations, and triggering policies used in our experiments.

## Reproducibility Artifacts

**Exact Prompts** (`prompts/current/`):
- `cot_prompt.txt` - Chain-of-thought prompt for initial seed generation
- `basic_prompt.txt` - Simplified prompt for fallback cases

**Model Configuration** (`config/llm_settings.yaml`):
- DeepSeek-chat API settings
- Temperature parameters: 0.8 (exploration), 0.5 (focused mutation)  
- Token limits and budget constraints

**LLM Triggering Policy** (`config/triggering_policy.yaml`):
- Initial generation: Always (5 test cases per new contract)
- Mutation enhancement: 30% probability during evolution
- Context-aware triggers: new coverage, bug detection, fitness improvement

## Implementation Overview

Our approach integrates LLM guidance into the ConFuzzius baseline fuzzer at two key phases:

1. **Seed Generation**: Generate initial test cases using systematic vulnerability analysis instead of pure randomization
2. **Mutation Enhancement**: Apply LLM-guided mutations when baseline fuzzer discovers promising cases ("amplify-and-deepen" strategy)

Key technical details:
- Uses different temperature settings for exploration vs exploitation
- Implements comprehensive filtering (98.7% success rate)
- Context capture from successful execution traces
- Budget-controlled API usage (~$0.035 per contract)

## Code Structure

```
ampfuzz-artifact/
├── config/                      
│   ├── llm_settings.yaml       # Model parameters and API configuration
│   ├── triggering_policy.yaml  # LLM call triggering conditions
│   └── env_example.txt         # Environment setup template
├── prompts/                     
│   ├── current/                # Exact prompts used in experiments
│   └── all_versions/           # Prompt evolution history
├── src/                        
│   ├── llm_generator.py       # LLM integration and response filtering
│   ├── mutation.py            # Enhanced mutation operators 
│   ├── llm_mutator.py         # Context-aware strategy generation
│   └── integration_points.md  # Technical integration details
└── scripts/                    
    ├── analyze_filter_stats.py  # LLM response quality analysis
    ├── analyze_variance.py      # Multi-run statistical analysis
    └── data_process/            # Experimental data processing
```

## Key Implementation Notes

**LLM Integration Points:**
- Seed generation: `src/llm_generator.generate_with_llm()`
- Mutation enhancement: `src/mutation.py` (line ~58)
- Response filtering: `src/llm_generator._parse_and_validate_response()`

**Triggering Logic:**
- Mode detection: Check `args.exp_mode` for 'llm' variants
- Context capture: Successful cases stored in `llm_amplifier_context`
- Probability-based: 30% of mutations use LLM guidance

**Quality Control:**
- JSON validation and ABI compatibility checking
- Type sanitization for argument conversion
- Success rate: 98.7% of LLM responses pass filters

This artifact provides the technical specifications needed for independent validation while preserving the core implementation approach described in our paper.