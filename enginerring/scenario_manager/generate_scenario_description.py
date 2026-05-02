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
        scenario_id = desc.get('scenario_id')
        if not scenario_id:
            print_color(
                '[Scenario Schema] scenario_id field missing, cannot rename directory.',
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
    final_dir = os.path.join(proj_path, scenario_id)
    if os.path.exists(final_dir):
        shutil.rmtree(final_dir)  # overwrite if already exists
    os.rename(target_dir, final_dir)

    print_color(
        f'[Scenario Schema] Outputs moved and directory renamed to: {final_dir}',
        Colors.GREEN
    )


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
        work_dir, 'enginerring', 'scenario_manager', 'scenario_ schema.json')

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

    # Build prompt with strict JSON output constraint
    prompt = f"""You are a concurrency analysis expert. Based on the provided thread call tree (from final-output-calltree.md), fill in the **scenario_schema.json** structure with a summary of the multi-threaded execution.

**Constraints**:
- Output ONLY the completed JSON object, without any additional text, comments, or markdown formatting.
- Follow the exact field names and types defined in the schema.
- Infer sub-processes, threads, components, interactions, and concurrency models from the call tree.
- The output must be valid JSON and pass schema validation.

**Schema Template**:
{schema_template}

**Call Tree Data (Markdown)**:
{calltree_content}

Now generate the completed JSON:"""

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

        # Optional JSON validation
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                json.loads(f.read())
            print('[Scenario Schema] JSON validation passed.')
        except Exception as val_err:
            print(
                f'[Scenario Schema] Warning: output is not valid JSON - {val_err}')

        # If everything succeeded, move the outputs
        if move_outputs and proj_path:
            _move_scenario_outputs(work_dir, proj_path)

    except Exception as e:
        print(f'[Scenario Schema] LLM call failed: {e}')
    finally:
        # Clean up temporary prompt file
        if os.path.exists(temp_prompt_file):
            os.remove(temp_prompt_file)