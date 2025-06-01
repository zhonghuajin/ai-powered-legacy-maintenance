#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
generate_scenario_description.py
Step: Analyze final-output-calltree.md & execution_flow_with_code.md -> build prompt -> call LLM -> output scenario_description.json
Also responsible for moving and organizing the generated outputs into the project directory.
"""

import os
import sys
import json
import shutil
import glob
import re

from print_utils.utils import Colors, print_color


def _move_scenario_outputs(work_dir: str, proj_path: str):
    """
    Move final-*.json, final-*.md, execution_flow_with_code.md and scenario_description.json
    to <proj_path>/scenario_data and rename that directory
    using the scenario_id field from scenario_description.json.
    """
    scenario_desc_path = os.path.join(work_dir, 'scenario_description.json')
    if not os.path.exists(scenario_desc_path):
        print_color(
            '[Scenario Schema] scenario_description.json not found, skipping move.',
            Colors.YELLOW
        )
        return

    # Read scenario_id
    try:
        with open(scenario_desc_path, 'r', encoding='utf-8') as f:
            desc = json.load(f)

        # Handle cases where LLM outputs a schema-like structure instead of a pure instance
        if 'properties' in desc and isinstance(desc['properties'], dict) and 'scenario_id' in desc['properties']:
            scenario_id = desc['properties'].get('scenario_id')
            if isinstance(scenario_id, dict) and 'type' in scenario_id:
                scenario_id = None
        else:
            scenario_id = desc.get('scenario_id')

        if not scenario_id:
            print_color(
                '[Scenario Schema] scenario_id field missing, cannot rename directory.',
                Colors.RED
            )
            return

        if isinstance(scenario_id, dict):
            print_color(
                '[Scenario Schema] scenario_id is a schema definition, not a value. LLM failed to generate proper instance.',
                Colors.RED
            )
            return

    except Exception as e:
        print_color(
            f'[Scenario Schema] Failed to read scenario_description.json: {e}',
            Colors.RED
        )
        return

    # Prepare temporary target directory
    target_dir = os.path.join(proj_path, 'scenario_data')
    if os.path.exists(target_dir):
        shutil.rmtree(target_dir)
    os.makedirs(target_dir, exist_ok=True)

    # Move final-*.json and final-*.md
    for pattern in ('final-*.json', 'final-*.md'):
        for file_path in glob.glob(os.path.join(work_dir, pattern)):
            shutil.move(file_path, os.path.join(
                target_dir, os.path.basename(file_path)))

    # Move execution_flow_with_code.md
    execution_flow_file = os.path.join(work_dir, 'execution_flow_with_code.md')
    if os.path.exists(execution_flow_file):
        shutil.move(execution_flow_file, os.path.join(
            target_dir, 'execution_flow_with_code.md'))

    # Move scenario_description.json
    shutil.move(scenario_desc_path, os.path.join(
        target_dir, 'scenario_description.json'))

    # Rename scenario_data directory to scenario_id
    final_dir = os.path.join(proj_path, str(scenario_id))
    if os.path.exists(final_dir):
        shutil.rmtree(final_dir)  # overwrite if already exists
    os.rename(target_dir, final_dir)

    print_color(
        f'[Scenario Schema] Outputs moved and directory renamed to: {final_dir}',
        Colors.GREEN
    )


def clean_llm_json_output(raw_content: str) -> str:
    """
    Strips markdown code blocks and extracts the JSON string from the LLM output.
    """
    raw_content = raw_content.strip()

    # Use regex to find the first JSON object block
    match = re.search(r'(\{.*\})', raw_content, re.DOTALL)
    if match:
        extracted = match.group(1).strip()
        return extracted

    # Fallback cleanup if regex fails but markdown blocks are present
    if raw_content.startswith('```'):
        raw_content = raw_content.split('\n', 1)[-1]
        if raw_content.rfind('```') != -1:
            raw_content = raw_content[:raw_content.rfind('```')]

    return raw_content.strip()


def generate_scenario_description(work_dir: str, proj_path: str = None, move_outputs: bool = True):
    """
    After log denoising, utilize final-output-calltree.md, execution_flow_with_code.md,
    and the scenario_schema.json template to generate a structured scenario description JSON via LLM.
    If proj_path is provided and move_outputs is True, the generated files are moved
    into the project's scenario data directory automatically.
    """
    # Paths
    pruned_dir = os.path.join(work_dir, 'pruned')
    calltree_file = os.path.join(work_dir, 'final-output-calltree.md')
    execution_flow_file = os.path.join(work_dir, 'execution_flow_with_code.md')

    # Template file location
    schema_template_file = os.path.join(
        work_dir, 'enginerring', 'scenario_manager', 'scenario_schema.json')

    if not os.path.exists(calltree_file):
        print('[Scenario Schema] Call tree file not found, skipping.')
        return
    if not os.path.exists(schema_template_file):
        print(
            f'[Scenario Schema] Schema template not found: {schema_template_file}, skipping.')
        return

    # Read input data
    with open(calltree_file, 'r', encoding='utf-8') as f:
        calltree_content = f.read()

    # Read execution flow with code if available
    execution_flow_content = ""
    if os.path.exists(execution_flow_file):
        print(
            f'[Scenario Schema] Auto-detected execution flow file: {execution_flow_file}')
        with open(execution_flow_file, 'r', encoding='utf-8') as f:
            execution_flow_content = f.read()
    else:
        print(
            f'[Scenario Schema] Warning: execution_flow_with_code.md not found in {work_dir}. Proceeding with call tree only.')
        execution_flow_content = "[No execution flow with code data available for this scenario.]"

    with open(schema_template_file, 'r', encoding='utf-8') as f:
        schema_template = f.read()

    # Build prompt with strict JSON output constraint and explicit instance instruction.
    # The prompt incorporates a deep-dive analysis template focusing on single-threaded execution,
    # state transitions, pipelines, and error chains (excluding concurrency).
    prompt = f"""You are an expert Software Architect and Runtime Behavior Analyst. Your task is to analyze a program's runtime execution data and generate a structured JSON DATA INSTANCE that conforms to the provided `scenario_schema.json` template.

To achieve maximum accuracy, you must perform a deep-dive analysis of the provided data sources, paying special attention to the actual source code and sequential execution flow.

### ANALYSIS METHODOLOGY (How to analyze the runtime):
1. **Control Flow & Execution Path (`final-output-calltree.md` & `execution_flow_with_code.md`)**:
   - Trace the exact runtime sequence of function/method invocations.
   - Understand the logical stages of execution from initialization to termination.
2. **State & Lifecycle Transitions**:
   - Trace any state machines or stateful components. Identify the exact state trajectory (e.g., `idle -> running -> paused -> done`) and the guard conditions or events that triggered the transitions by analyzing the source code closures.
3. **Data Pipelines & Stream Processing**:
   - Analyze how data flows through the system. Identify functional pipelines (`compose`, `pipeline`, `pipe`), reactive streams (`Observable` chains), and data transformations (filter predicates, map closures).
4. **Error Handling & Exception Chains**:
   - Map out the exception propagation path. Trace any nested try-catch blocks and reconstruct the causal chain of exceptions (e.g., root cause -> validation failure -> application error).
5. **Design Patterns & Meta-programming**:
   - Detect active design patterns (e.g., Dynamic Proxy, Metadata Registry, Observer, Soft Delete). Explain how they interact during this runtime using the provided source code.

**Constraints**:
- Output ONLY the completed JSON data object, without any additional text, comments, or markdown formatting blocks.
- DO NOT output a JSON Schema definition. You must output the actual populated data instance.
- The root of your JSON must directly contain the fields: "scenario_id", "scenario_name", "summary", "tags", and "sub_scenarios". Do NOT nest them inside a "properties" object.
- Ensure all descriptions and summaries inside the JSON are written in professional **Chinese**.
- The output must be valid, well-formed JSON.

### EXPECTED JSON STRUCTURE & TEMPLATE:
Your output JSON must populate the fields of the schema. Ensure the "summary" and "sub_scenarios" fields capture the following structured details in Chinese:
- **Scenario Overview**: Professional name, ID, tech stack, and core purpose.
- **Execution Path Analysis**: Step-by-step stage analysis with source code behavior breakdown.
- **Deep-Dive into Key Mechanisms**:
  - State machine transitions and guard conditions.
  - Data pipelines, stream transformations, and final outputs.
  - Exception propagation and causal chains.
  - Meta-programming proxies and WeakMap metadata associations.
- **Execution Characteristics**: Performance, design patterns, and architectural evaluation.

**Schema Template to Follow**:
{schema_template}

**Call Tree Data (Markdown)**:
{calltree_content}

**Execution Flow with Source Code (Markdown)**:
{execution_flow_content}

Now, perform the deep-dive analysis of the execution flow and source code, and generate the completed JSON DATA INSTANCE:"""

    # Temporary prompt file and output file
    temp_prompt_file = os.path.join(pruned_dir, 'temp_scenario_prompt.md')
    output_file = os.path.join(work_dir, 'scenario_description.json')

    # Ensure pruned directory exists
    os.makedirs(pruned_dir, exist_ok=True)

    with open(temp_prompt_file, 'w', encoding='utf-8') as f:
        f.write(prompt)

    try:
        # Add ask_llm directory to sys.path to import run.py
        ask_llm_dir = os.path.join(work_dir, 'enginerring', 'ask_llm')
        if ask_llm_dir not in sys.path:
            sys.path.insert(0, ask_llm_dir)

        import run as ask_llm_run
        ask_llm_run.run_api(
            file_path=temp_prompt_file,
            output_path=output_file
        )
        print(f'[Scenario Schema] Successfully generated: {output_file}')

        # Read, clean, and validate the JSON output
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                raw_output = f.read()

            cleaned_json_str = clean_llm_json_output(raw_output)
            parsed_json = json.loads(cleaned_json_str)

            # If LLM still nested it in properties, extract it out to fix the file
            if 'properties' in parsed_json and 'scenario_id' in parsed_json['properties']:
                if isinstance(parsed_json['properties']['scenario_id'], str):
                    parsed_json = parsed_json['properties']

            # Overwrite the file with the clean, validated JSON
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(parsed_json, f, indent=2)

            print('[Scenario Schema] JSON validation and sanitization passed.')
        except Exception as val_err:
            print(
                f'[Scenario Schema] Warning: output is not valid JSON - {val_err}')
            print(
                '[Scenario Schema] The raw output will be kept, but downstream tasks might fail.')

        # If everything succeeded, move the outputs
        if move_outputs and proj_path:
            _move_scenario_outputs(work_dir, proj_path)

    except Exception as e:
        print(f'[Scenario Schema] LLM call failed: {e}')
    finally:
        # Clean up temporary prompt file
        if os.path.exists(temp_prompt_file):
            os.remove(temp_prompt_file)