"""
generate_scenario_schema.py
Step: Analyze final-output-calltree.md -> build prompt -> call LLM -> output scenario_schema.json
"""

import os
import sys
import json


def generate_scenario_schema(work_dir: str):
    """
    After log denoising, utilize final-output-calltree.md and the scenario_schema.json
    template to generate a structured scenario description JSON via LLM.
    """
    # Paths
    pruned_dir = os.path.join(work_dir, 'pruned')
    calltree_file = os.path.join(work_dir, 'final-output-calltree.md')
    # Template file location
    schema_template_file = os.path.join(work_dir, 'enginerring', 'scenario_manager', 'scenario_ schema.json')

    if not os.path.exists(calltree_file):
        print('[Scenario Schema] Call tree file not found, skipping.')
        return
    if not os.path.exists(schema_template_file):
        print(f'[Scenario Schema] Schema template not found: {schema_template_file}, skipping.')
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
    output_file = os.path.join(work_dir, 'scenario_schema_output.json')

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
            print(f'[Scenario Schema] Warning: output is not valid JSON - {val_err}')

    except Exception as e:
        print(f'[Scenario Schema] LLM call failed: {e}')
    finally:
        # Clean up temporary prompt file
        if os.path.exists(temp_prompt_file):
            os.remove(temp_prompt_file)