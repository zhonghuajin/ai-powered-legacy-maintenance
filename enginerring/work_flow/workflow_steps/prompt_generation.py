import os
import sys
import json
import importlib
from print_utils.utils import Colors, print_color
from .common import get_single_char

def select_ai_prompt_script(work_dir, target_language=None):
    print_color("\n>>> Pre-selecting AI Prompt Generator...", Colors.CYAN)
    ai_app_path = os.path.join(work_dir, "enginerring", "scenario_data_ai_app")

    if not os.path.exists(ai_app_path):
        print_color(
            f"[Error] AI app directory not found at: {ai_app_path}", Colors.RED)
        return None

    scripts = []
    for file in os.listdir(ai_app_path):
        if file.endswith(".py") and file not in ["__init__.py", "editor_util.py"]:
            scripts.append(file)

    if not scripts:
        print_color(
            f"[Error] No Python scripts found in {ai_app_path}", Colors.RED)
        return None

    scripts.sort()

    print_color("\n========================================", Colors.CYAN)
    print_color("       Select Prompt Generator Script   ", Colors.CYAN)
    print_color("========================================", Colors.CYAN)
    for i, script in enumerate(scripts, 1):
        print(f"  {i}. {script}")
    print_color("========================================", Colors.CYAN)

    choice = ""
    prompt_msg = f"Enter your choice (1-{len(scripts)}): "

    while True:
        if len(scripts) < 10:
            print(prompt_msg, end='', flush=True)
            choice = get_single_char()

            if choice == '\x03':
                print("\n")
                raise KeyboardInterrupt

            print(choice)
            choice = choice.strip()
        else:
            choice = input(prompt_msg).strip()

        if choice.isdigit() and 1 <= int(choice) <= len(scripts):
            break

        if len(scripts) < 10:
            print()
        print_color("[!] Invalid choice, please try again.", Colors.RED)

    selected_script = scripts[int(choice) - 1]
    print_color(f"\n[Info] Selected script: {selected_script}", Colors.GREEN)
    return selected_script

def prepare_ai_prompt_interactive(work_dir, selected_script, proj_path=None, save_context=True):
    if not selected_script:
        return None

    print_color("\n>>> Preparing AI Prompt (User Interaction)...", Colors.CYAN)
    original_cwd = os.getcwd()
    os.chdir(work_dir)

    ai_app_path = os.path.join(work_dir, "enginerring", "scenario_data_ai_app")
    module_name = selected_script[:-3]

    if ai_app_path not in sys.path:
        sys.path.insert(0, ai_app_path)

    prompt_context = None
    try:
        module = importlib.import_module(module_name)
        importlib.reload(module)

        if hasattr(module, 'prepare_prompt'):
            prompt_context = module.prepare_prompt()

            if prompt_context and save_context:
                target_dir = proj_path if proj_path else work_dir
                context_file_path = os.path.join(target_dir, 'last_prompt_context.json')
                try:
                    with open(context_file_path, 'w', encoding='utf-8') as f:
                        json.dump(prompt_context, f, ensure_ascii=False, indent=4)
                    print_color(f"[Info] Saved prompt context to {context_file_path}", Colors.GREEN)
                except Exception as e:
                    print_color(f"[WARN] Failed to save context: {e}", Colors.YELLOW)
        else:
            print_color(
                f"[Info] 'prepare_prompt' function not found in {selected_script}. Skipping interactive preparation.", Colors.YELLOW)
    except ImportError as e:
        print_color(f"[!] Failed to import {module_name}: {e}", Colors.RED)
    except Exception as e:
        print_color(f"[!] Error during prompt preparation: {e}", Colors.RED)
    finally:
        os.chdir(original_cwd)

    return prompt_context

def _post_process_other_trace_data(work_dir, selected_script):
    if not selected_script:
        return

    script_path = os.path.join(work_dir, "enginerring", "scenario_data_ai_app", selected_script)

    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            script_content = f.read()
    except Exception as e:
        print_color(f'[WARN] Could not read selected script {selected_script}: {e}', Colors.YELLOW)
        return

    if '--OTHER_TRACE_DATA--' in script_content:
        print_color('\n[!] Detected --OTHER_TRACE_DATA-- placeholder in the selected script. Need to inject trace data from another scenario.', Colors.YELLOW)

        projects_dir = os.path.join(work_dir, 'projects')
        scenarios = []
        if os.path.exists(projects_dir):
            for root, dirs, files in os.walk(projects_dir):
                if 'final-output-calltree.md' in files:
                    scenarios.append(root)

        if not scenarios:
            print_color('[WARN] No scenarios found with final-output-calltree.md.', Colors.RED)
            return

        print_color('\n========================================', Colors.CYAN)
        print_color(' Select Another Scenario for Trace Data ', Colors.CYAN)
        print_color('========================================', Colors.CYAN)
        for i, scenario in enumerate(scenarios, 1):
            rel_path = os.path.relpath(scenario, projects_dir)
            print(f"  {i}. {rel_path}")
        print_color('========================================', Colors.CYAN)

        choice = input(f'Enter your choice (1-{len(scenarios)}): ').strip()
        if choice.isdigit() and 1 <= int(choice) <= len(scenarios):
            selected_scenario_dir = scenarios[int(choice) - 1]
            trace_file_path = os.path.join(selected_scenario_dir, 'final-output-calltree.md')

            try:
                with open(trace_file_path, 'r', encoding='utf-8') as tf:
                    trace_data = tf.read()

                other_trace_data_header = f"\n\n=========================================\n### Trace Data from Other Scenario: {os.path.basename(selected_scenario_dir)}\n=========================================\n"
                reference_note = "\n\n> **Note**: This is runtime data from another scenario and may be helpful as a reference for the current implementation requirements.\n=========================================\n"
                replacement = other_trace_data_header + trace_data + reference_note

                prompt_file = os.path.join(work_dir, 'AI_Task_Prompt.md')

                if not os.path.exists(prompt_file):
                    raise FileNotFoundError(f"Expected prompt file not found: {prompt_file}")

                try:
                    with open(prompt_file, 'r', encoding='utf-8') as f:
                        content = f.read()

                    if '--OTHER_TRACE_DATA--' in content:
                        new_content = content.replace('--OTHER_TRACE_DATA--', replacement)
                        with open(prompt_file, 'w', encoding='utf-8') as f:
                            f.write(new_content)
                        print_color(f'[+] Successfully injected trace data from {os.path.basename(selected_scenario_dir)} into {os.path.basename(prompt_file)}', Colors.GREEN)
                except Exception as e:
                    print_color(f'[!] Failed to process {os.path.basename(prompt_file)}: {e}', Colors.RED)
            except Exception as e:
                print_color(f'[!] Failed to read trace data or process prompt file: {e}', Colors.RED)
        else:
            print_color('[!] Invalid choice, skipping trace data injection.', Colors.YELLOW)

def execute_ai_prompt(work_dir, selected_script, prompt_context=None):
    if not selected_script:
        return None

    print_color("\n>>> Generating AI Prompt (Auto Filling)...", Colors.CYAN)
    original_cwd = os.getcwd()
    os.chdir(work_dir)

    ai_app_path = os.path.join(work_dir, "enginerring", "scenario_data_ai_app")
    module_name = selected_script[:-3]

    selected_calltree_path = os.path.join(work_dir, "final-output-calltree.md")

    if os.path.exists(selected_calltree_path):
        print_color(
            f"[Info] Found final-output-calltree.md in working directory. Using path: {selected_calltree_path}", Colors.GREEN)
    else:
        print_color(
            f"[Warning] final-output-calltree.md not found in working directory: {work_dir}", Colors.YELLOW)

    print_color(
        f"Running Python script from {work_dir} to generate the prompt...", Colors.GREEN)

    if ai_app_path not in sys.path:
        sys.path.insert(0, ai_app_path)

    try:
        module = importlib.import_module(module_name)
        importlib.reload(module)

        if hasattr(module, 'generate_prompt_with_context'):
            module.generate_prompt_with_context(selected_calltree_path, prompt_context)
            _post_process_other_trace_data(work_dir, selected_script)
            return selected_script
        elif hasattr(module, 'generate_prompt'):
            module.generate_prompt(selected_calltree_path)
            _post_process_other_trace_data(work_dir, selected_script)
            return selected_script
        else:
            print_color(
                f"[!] 'generate_prompt' function not found in {selected_script}. Please ensure the script exposes this interface.", Colors.RED)
            return None

    except ImportError as e:
        print_color(f"[!] Failed to import {module_name}: {e}", Colors.RED)
        return None
    except Exception as e:
        print_color(f"[!] Error generating prompt: {e}", Colors.RED)
        return None
    finally:
        os.chdir(original_cwd)