import os
import sys
import json
import importlib
import inspect
from print_utils.utils import Colors, print_color
from .common import get_single_char

# Global variable to cache the selected script during the application's runtime
_cached_selected_script = None

def select_ai_prompt_script(work_dir, target_language=None, preselected_index=None):
    global _cached_selected_script

    print_color("\n>>> Pre-selecting AI Prompt Generator...", Colors.CYAN)

    # If a script has already been selected in a previous iteration, reuse it
    if _cached_selected_script:
        print_color(f"[Info] Using previously selected script (Cached): {_cached_selected_script}", Colors.GREEN)
        return _cached_selected_script

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
    
    # Check if a valid pre-selected index was passed via command line
    if preselected_index is not None:
        if 1 <= preselected_index <= len(scripts):
            choice = str(preselected_index)
            print_color(f"[Info] Automatically selected script index from arguments: {choice}", Colors.GREEN)
        else:
            print_color(
                f"[Warning] Pre-selected index {preselected_index} is out of bounds (1-{len(scripts)}). Falling back to manual selection.",
                Colors.YELLOW
            )

    if not choice:
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
    
    # Save the choice to the cache
    _cached_selected_script = selected_script
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
            prepare_func = getattr(module, 'prepare_prompt')
            sig = inspect.signature(prepare_func)

            # Dynamically detect if prepare_prompt supports proj_path parameter
            if 'proj_path' in sig.parameters:
                print_color(f"[Info] Passing proj_path to {selected_script}'s prepare_prompt.", Colors.GREEN)
                prompt_context = prepare_func(proj_path=proj_path)
            else:
                print_color(f"[Info] {selected_script}'s prepare_prompt does not accept proj_path. Calling without it.", Colors.GREEN)
                prompt_context = prepare_func()

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
    # Kept empty or as compatibility fallback for legacy scripts.
    # Scripts that have been moved to the prepare_prompt phase will no longer trigger interaction here.
    pass

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
            # Removed _post_process_other_trace_data(work_dir, selected_script) to avoid duplicate interactive prompts
            return selected_script
        elif hasattr(module, 'generate_prompt'):
            module.generate_prompt(selected_calltree_path)
            # For legacy scripts that don't support context, keep the original post-processing as fallback
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