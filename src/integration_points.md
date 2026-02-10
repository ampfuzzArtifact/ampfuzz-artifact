# LLM Integration Points

This document outlines where LLM calls are integrated into the ConFuzzius baseline fuzzer.

## Core Integration Points

### 1. Seed Generation
**Location**: Population initialization phase  
**Trigger**: When mode includes 'llm'  
**Implementation**: `llm_generator.generate_with_llm(mode, num_cases=5, phase="init")`  
**Settings**: Temperature 0.8, CoT prompt

### 2. Mutation Enhancement  
**Location**: Mutation operator (~line 58 in mutation.py)  
**Trigger**: 30% probability + context availability  
**Implementation**: Context-aware strategy generation using execution traces  
**Settings**: Temperature 0.5, focused mutation

### 3. Context Capture
**Mechanism**: Store successful case information in `llm_amplifier_context`  
**Data**: Execution logs, test case parameters, coverage information  
**Usage**: Feed to LLM for guided mutation generation

## Configuration Integration

- Mode detection via `args.exp_mode` 
- Settings loaded from `config/llm_settings.yaml`
- Triggering rules from `config/triggering_policy.yaml`
- Prompts loaded from `prompts/current/`

## Performance Notes

- API latency: 2-3 seconds per call
- Token usage: ~50k per contract
- Filter success rate: 98.7%
- Context overhead: ~1KB per case
              hero_info.get("test_case_str", ""),
              hero_info.get("order", "")
          )
  
  # Apply mutation
  if use_llm_mutation and self._llm_mutation_strategy:
      return self.llm_guided_mutation(individual, self._llm_mutation_strategy)
  ```

### 3. Filtering and Validation (Critical for Quality)
- **File**: `fuzzer/engine/components/llm_generator.py`  
- **Purpose**: Ensure LLM outputs are valid and executable
- **Filter Steps**:
  1. JSON format validation
  2. ABI function matching
  3. Argument type sanitization  
  4. Argument count verification
  
```python
def _parse_and_validate_response(self, text):
    # Filter statistics tracking
    self.filter_stats["total_generated"] += len(cases)
    
    for case in cases:
        # 1. Basic format check
        if not isinstance(case.get("arguments", []), list):
            self.filter_stats["rejection_reasons"]["invalid_format"] += 1
            continue
            
        # 2. Function name/hash resolution
        function_identifier = case["arguments"][0]
        if function_identifier in self.function_name_to_hash:
            function_hash = self.function_name_to_hash[function_identifier]
        elif function_identifier not in self.interface:
            self.filter_stats["rejection_reasons"]["abi_mismatch"] += 1
            continue
            
        # 3. Type sanitization
        try:
            self._sanitize_argument_types(case)
        except ValueError:
            self.filter_stats["rejection_reasons"]["type_sanitize_fail"] += 1
            continue
            
    # Success rate: ~98.7% in our experiments
```

## Core Classes and Files

### LLMGenerator (`src/llm_generator.py`)
- **Main LLM interface**: Handles API calls, prompt construction, response parsing
- **Key methods**: `generate_with_llm()`, `_parse_and_validate_response()`, `_sanitize_argument_types()`

### Mutation (`src/mutation.py`)  
- **LLM-guided mutation**: Integrates LLM into evolution process
- **Amplify-and-deepen**: Uses successful test cases to guide further mutation
- **Filter integration**: Ensures mutated cases pass validation

### LLMMutator (`src/llm_mutator.py`)
- **Strategy generator**: Creates mutation strategies based on successful test cases
- **Context-aware**: Uses execution logs and coverage info to guide mutations

## The Amplify-and-Deepen Process

This is the key innovation - when baseline fuzzer finds interesting test cases:

1. **Detection**: Execution analyzer detects new coverage/bugs
2. **Context Capture**: Store execution logs, test case, and analysis context  
3. **Strategy Generation**: LLM analyzes successful case to create mutation strategy
4. **Guided Mutation**: Apply LLM-generated strategy to similar test cases
5. **Filtering**: Validate all mutated cases before adding to population

```python
# When new coverage detected
if new_coverage_found:
    env.llm_amplifier_context = {
        "logs": execution_logs,
        "test_case_str": str(successful_case),
        "order": execution_order
    }
    
# In mutation operator  
if hasattr(env, 'llm_amplifier_context'):
    strategy = llm_mutator.get_mutation_strategy(context)
    return llm_guided_mutation(individual, strategy)
```

This amplify-and-deepen approach is what makes our method effective - instead of random LLM calls, we focus LLM effort on areas where baseline already found something interesting.