"""
generate_scenario_description.py
Step: Analyze final-output-calltree.md -> build prompt -> call LLM -> output scenario_schema.json
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
    Move final-*.json, final-*.md and scenario_description.json
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
            # Optionally, if it's nested, we might want to extract just the properties as the real description
            if isinstance(scenario_id, dict) and 'type' in scenario_id:
                # LLM literally just returned the schema without filling it
                scenario_id = None
        else:
            scenario_id = desc.get('scenario_id')
            
        if not scenario_id:
            print_color(
                '[Scenario Schema] scenario_id field missing, cannot rename directory.',
                Colors.RED
            )
            return
            
        # If scenario_id is a dictionary (e.g., LLM left the schema definition intact), fail gracefully
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
            shutil.move(file_path, os.path.join(target_dir, os.path.basename(file_path)))

    # Move scenario_description.json
    shutil.move(scenario_desc_path, os.path.join(target_dir, 'scenario_description.json'))

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
    After log denoising, utilize final-output-calltree.md and the scenario_schema.json
    template to generate a structured scenario description JSON via LLM.
    If proj_path is provided and move_outputs is True, the generated files are moved
    into the project's scenario data directory automatically.
    """
    # Paths
    pruned_dir = os.path.join(work_dir, 'pruned')
    calltree_file = os.path.join(work_dir, 'final-output-calltree.md')
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
    with open(schema_template_file, 'r', encoding='utf-8') as f:
        schema_template = f.read()

    # Build prompt with strict JSON output constraint and explicit instance instruction
    prompt = f"""You are a concurrency analysis expert. Based on the provided thread call tree (from final-output-calltree.md), generate a JSON DATA INSTANCE that conforms to the provided scenario_schema.json.

**Constraints**:
- Output ONLY the completed JSON data object, without any additional text, comments, or markdown formatting.
- DO NOT output a JSON Schema definition. You must output the actual data instance.
- The root of your JSON must directly contain the fields: "scenario_id", "scenario_name", "summary", "tags", and "sub_scenarios". Do NOT nest them inside a "properties" object.
- Infer sub-processes, threads, components, interactions, and concurrency models from the call tree.
- The output must be valid JSON.

**Schema Definition to Follow**:
{schema_template}

**Call Tree Data (Markdown)**:
{calltree_content}

Now generate the completed JSON DATA INSTANCE:"""

    # Temporary prompt file and output file
    temp_prompt_file = os.path.join(pruned_dir, 'temp_scenario_prompt.md')
    output_file = os.path.join(work_dir, 'scenario_description.json')

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
            print(f'[Scenario Schema] Warning: output is not valid JSON - {val_err}')
            print('[Scenario Schema] The raw output will be kept, but downstream tasks might fail.')

        # If everything succeeded, move the outputs
        if move_outputs and proj_path:
            _move_scenario_outputs(work_dir, proj_path)

    except Exception as e:
        print(f'[Scenario Schema] LLM call failed: {e}')
    finally:
        # Clean up temporary prompt file
        if os.path.exists(temp_prompt_file):
            os.remove(temp_prompt_file)