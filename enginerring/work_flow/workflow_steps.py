import importlib
import os
import sys
import subprocess
import socket
import re
import platform
import glob
import shutil
import json
from print_utils.utils import Colors, print_color
from .prechecks import setup_windows_proxy
from enginerring.shadow_project_management.instrument_with_shadow_project import run_instrumentation_mode

# Import dependency handling modules
from enginerring.dependency_handler.scan_deps import find_project_files
from enginerring.dependency_handler.prompt_organizer import generate_prompt
from enginerring.dependency_handler.dependency_injector import run_injection


def ensure_language_selected(proj_path):
    """
    Ensure the target programming language is selected and saved in config.json.
    Returns the selected language.
    """
    target_language = 'java'
    if proj_path:
        config_file = os.path.join(proj_path, 'config.json')
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)

                target_language = config.get('language')
                if not target_language:
                    print_color(
                        "\n========================================", Colors.CYAN)
                    print_color(
                        "       Select Programming Language      ", Colors.CYAN)
                    print_color(
                        "========================================", Colors.CYAN)
                    print("  1. Java\n  2. PHP\n  3. Python")
                    print_color(
                        "========================================", Colors.CYAN)
                    lang_choice = input(
                        "Enter your choice [1]: ").strip() or "1"
                    lang_map = {'1': 'java', '2': 'php', '3': 'python'}
                    target_language = lang_map.get(lang_choice, 'java')

                    config['language'] = target_language
                    with open(config_file, 'w', encoding='utf-8') as f:
                        json.dump(config, f, indent=4)
                    print_color(
                        f"[Info] Language set to {target_language.upper()} and saved to config.", Colors.GREEN)
                else:
                    print_color(
                        f"[Info] Using configured language: {target_language.upper()}", Colors.GREEN)
            except Exception as e:
                print_color(
                    f"[WARN] Could not read config for language selection: {e}", Colors.YELLOW)
    return target_language


def instrument_code(work_dir, proj_path=None, git_root=None, is_new_project=False):
    print_color(
        "\n>>> Setting up shadow branch and instrumenting code...", Colors.CYAN)

    if git_root:
        git_root_dir = git_root
    else:
        git_root_dir = ""
        while not git_root_dir:
            git_root_dir = input(
                "Please enter the Git repository root directory of the project that contains the folders listed in target-folders.txt: "
            ).strip()
            if not git_root_dir:
                print_color("[!] Path cannot be empty.", Colors.RED)

    print()
    print_color("========================================", Colors.CYAN)
    print_color("       Select Instrumentation Mode      ", Colors.CYAN)
    print_color("========================================", Colors.CYAN)
    print("  1. Full Instrumentation\n  2. Incremental Instrumentation")
    print_color("========================================", Colors.CYAN)

    inst_mode_choice = ""

    if is_new_project:
        print_color(
            "[Auto Selection] New project detected, automatically selecting Full Instrumentation (Mode 1).", Colors.GREEN)
        inst_mode_choice = "1"
    else:
        print_color(
            "[Auto Selection] Existing project detected, automatically selecting Incremental Instrumentation (Mode 2).", Colors.GREEN)
        inst_mode_choice = "2"

    mode_arg = "full" if inst_mode_choice == "1" else "incremental"
    print_color(f"[Mode Selection] Selected mode: {mode_arg}", Colors.GREEN)

    if proj_path:
        config_file = os.path.join(proj_path, 'config.json')
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)

                original_git_root = config.get('original_git_root')
                source_branch = config.get('source_branch')

                if original_git_root and source_branch and os.path.isdir(original_git_root):
                    print_color(
                        f"[Git Checkout] Restoring branch to '{source_branch}' in {original_git_root}...", Colors.CYAN)
                    subprocess.run(
                        ['git', 'checkout', source_branch],
                        cwd=original_git_root,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        check=True,
                        text=True
                    )
                    print_color(
                        f"[Git Checkout] Successfully switched to '{source_branch}'.", Colors.GREEN)
            except subprocess.CalledProcessError as e:
                print_color(
                    f"[WARN] Failed to checkout branch '{source_branch}'. Error: {e.stderr.strip()}", Colors.YELLOW)
            except Exception as e:
                print_color(
                    f"[WARN] Could not read config or switch branch: {e}", Colors.YELLOW)

    success = run_instrumentation_mode(
        git_root=git_root_dir,
        mode=mode_arg,
        original_cwd=os.getcwd(),
        proj_path=proj_path
    )

    if not success:
        print_color(
            "Error: Failed to setup shadow branch and instrument code. Exiting.", Colors.RED)
        sys.exit(1)

    is_skipped = (success == "NO_MODIFIED_FILES")

    if proj_path and not is_skipped:
        _move_instrumentation_outputs_to_project(work_dir, proj_path)
    elif is_skipped:
        print_color(
            "[Skip] No modified files found, skipped moving instrumentation outputs.", Colors.YELLOW)
        print_color(
            "[Info] Forcing git switch to shadow-project-for-instrumention branch...", Colors.CYAN)
        try:
            subprocess.run(
                ["git", "switch", "shadow-project-for-instrumention"],
                cwd=git_root_dir,
                check=True,
                capture_output=True,
                text=True
            )
            print_color(
                "[Success] Switched to shadow-project-for-instrumention branch.", Colors.GREEN)
        except subprocess.CalledProcessError as e:
            print_color(
                f"[WARN] Failed to switch to shadow branch: {e.stderr.strip()}", Colors.YELLOW)

    return mode_arg, is_skipped


def _move_instrumentation_outputs_to_project(work_dir, proj_path):
    """Move event_dictionary.txt and comment-mapping.txt from work_dir to proj_path."""
    files_to_move = ["event_dictionary.txt", "comment-mapping.txt"]
    for filename in files_to_move:
        src = os.path.join(work_dir, filename)
        dst = os.path.join(proj_path, filename)
        if os.path.isfile(src):
            shutil.move(src, dst)
            print_color(f"[Move] {filename} -> {proj_path}", Colors.GREEN)
        else:
            print_color(
                f"[WARN] {filename} not found in working directory, skip.", Colors.YELLOW)


def handle_instrumentation_dependencies(work_dir, proj_path, git_root, ask_llm_dir, target_language=None):
    """
    Handle dependency addition after instrumentation:
    1. Scan dependency files
    2. Get whitelist
    3. Generate prompt and request LLM
    4. Parse LLM response and inject dependencies
    """
    print_color("\n>>> Handling Instrumentation Dependencies...", Colors.CYAN)

    # 1. Get files_input
    files_input = find_project_files(git_root)

    # Check for PHP project without composer.json
    if target_language == 'php':
        has_composer = any(f.endswith('composer.json')
                           for f in (files_input or []))
        if not has_composer:
            print_color(
                "[-] PHP project without composer.json detected.", Colors.YELLOW)

            log_recorder_path = os.path.join(work_dir, "MULTILINGUAL", "PHP", "INSTRUMENTOR-LOG-RECORDER",
                                             "src", "Instrumentation", "InstrumentLog.php").replace('\\', '/')
            print_color(
                f"[Info] Injecting require_once for {log_recorder_path} into PHP files...", Colors.CYAN)

            config_path = os.path.join(proj_path, "config.json")
            target_folders = []
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
                    target_folders = config_data.get(
                        "original-target-folders", [])

            injected_count = 0
            require_stmt = f"\nrequire_once '{log_recorder_path}';\n"

            for folder in target_folders:
                for root, _, files in os.walk(folder):
                    for file in files:
                        if file.endswith('.php'):
                            filepath = os.path.join(root, file)
                            try:
                                with open(filepath, 'r', encoding='utf-8') as f:
                                    content = f.read()

                                if "require_once" in content and "InstrumentLog.php" in content:
                                    continue

                                match_namespace = re.search(
                                    r'namespace\s+[a-zA-Z0-9_\\]+\s*;', content, re.IGNORECASE)
                                match_declare = re.search(
                                    r'declare\s*\([^)]+\)\s*;', content, re.IGNORECASE)
                                match_php = re.search(
                                    r'<\?php', content, re.IGNORECASE)

                                insert_idx = 0
                                if match_namespace:
                                    insert_idx = match_namespace.end()
                                elif match_declare:
                                    insert_idx = match_declare.end()
                                elif match_php:
                                    insert_idx = match_php.end()

                                if insert_idx > 0:
                                    new_content = content[:insert_idx] + \
                                        require_stmt + content[insert_idx:]
                                    with open(filepath, 'w', encoding='utf-8') as f:
                                        f.write(new_content)
                                    injected_count += 1
                            except Exception as e:
                                print_color(
                                    f"[WARN] Failed to process {filepath}: {e}", Colors.YELLOW)

            print_color(
                f"[Success] Injected require_once into {injected_count} PHP files.", Colors.GREEN)
            print_color(
                "[Info] Skipping standard dependency injection for non-composer PHP project.", Colors.YELLOW)
            return

    if not files_input:
        print_color("[-] No dependency management files found.", Colors.YELLOW)
        return

    # 2. Get whitelist_input
    config_path = os.path.join(proj_path, "config.json")
    whitelist_input = []
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)
            whitelist_input = config_data.get("original-target-folders", [])

    # 3. Get dependency_input
    snippets_json_path = os.path.join(
        work_dir, "enginerring", "dependency_handler", "dependency_snippets.json")
    dependency_input = ""

    if os.path.exists(snippets_json_path):
        with open(snippets_json_path, "r", encoding="utf-8") as f:
            snippets = json.load(f)

            normalized_work_dir = work_dir.replace('\\', '/')

            for file_path in files_input:
                fname = os.path.basename(file_path)
                if fname in snippets:
                    dependency_input = snippets[fname].replace(
                        '{{WORK_DIR}}', normalized_work_dir)
                    break

            if not dependency_input:
                dependency_input = snippets.get(
                    "pom.xml", "<dependency>...</dependency>")

    # 4. Generate Prompt
    prompt = generate_prompt(files_input, whitelist_input, dependency_input)

    # Write prompt for LLM
    prompt_file = os.path.join(ask_llm_dir, "dependency_prompt.txt")
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(prompt)

    print_color(
        f"[+] Dependency prompt generated at {prompt_file}", Colors.GREEN)

    # 5. Invoke LLM
    llm_response_file = os.path.join(
        ask_llm_dir, "dependency_llm_response.txt")

    print_color(
        ">>> Asking LLM to identify target dependency files...", Colors.CYAN)

    if ask_llm_dir not in sys.path:
        sys.path.insert(0, ask_llm_dir)

    try:
        import run as ask_llm_run

        original_cwd = os.getcwd()
        os.chdir(ask_llm_dir)

        ask_llm_run.run_api(
            file_path="dependency_prompt.txt",
            output_path="dependency_llm_response.txt"
        )

        os.chdir(original_cwd)

    except ImportError as e:
        print_color(
            f"[!] Failed to import run.py from {ask_llm_dir}: {e}", Colors.RED)
        return

    os.chdir(original_cwd)

    # 6. Inject dependencies
    print_color(
        "\n>>> Parsing LLM response and injecting dependencies...", Colors.CYAN)

    run_injection(llm_response_file, snippets_json_path, work_dir)


def startup_log_manager_server(work_dir, proj_path=None):
    print_color("\n>>> Starting Log Manager Server...", Colors.CYAN)
    if proj_path:
        config_file = os.path.join(proj_path, 'config.json')
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)

            if config.get('language') == 'php':
                is_running = False
                for port in range(19898, 19999):
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.settimeout(0.05)
                        if s.connect_ex(('127.0.0.1', port)) == 0:
                            is_running = True
                            break

                if is_running:
                    print_color(
                        '[PHP Monitor] Detected existing service on ports 19898-19998. Skipping startup.', Colors.GREEN)
                else:
                    jar_path = os.path.join(
                        work_dir, 'multilingual', 'php', 'instrumentor-log-monitor', 'target', 'redis-log-monitor-1.0-SNAPSHOT.jar')
                    if os.path.exists(jar_path):
                        print_color(
                            '[PHP Monitor] No running service found. Auto-starting monitor in background...', Colors.GREEN)
                        log_file_path = os.path.join(
                            proj_path, 'php_monitor_startup.log')
                        log_file = open(log_file_path, 'w')
                        subprocess.Popen(
                            ['java', '-jar', jar_path],
                            cwd=work_dir,
                            stdout=log_file,
                            stderr=subprocess.STDOUT
                        )
                    else:
                        print_color(
                            f'[Warning] PHP log monitor jar not found at: {jar_path}', Colors.YELLOW)

    server_dir = os.path.join(work_dir, "enginerring", "log_manager_server")

    if server_dir not in sys.path:
        sys.path.insert(0, server_dir)

    try:
        if 'log_manager' in sys.modules:
            del sys.modules['log_manager']

        import log_manager as log_server

        log_server.SCENARIO_SAVE_ROOT = proj_path if proj_path else os.getcwd()

        print_color(f"Launching log manager server interface...", Colors.GREEN)
        return log_server.run_manager()
    except ImportError as e:
        print_color(
            f"Failed to import log_manager module from {server_dir}: {e}", Colors.RED)
        return False


def analyze_logs(work_dir, proj_path=None, auto_analyze=False):
    print_color(
        "\n>>> Analyzing logs and extracting denoised data...", Colors.CYAN)

    if auto_analyze:
        print_color(
            "[Auto] Flush command detected. Automatically executing Log Analysis...", Colors.GREEN)
        choice = "2"
    else:
        print()
        print_color("========================================", Colors.CYAN)
        print_color("       Analyze Logs Options             ", Colors.CYAN)
        print_color("========================================", Colors.CYAN)
        print("  1. Skip (Default)\n  2. Execute Log Analysis")
        print_color("========================================", Colors.CYAN)

        choice = input(
            "Enter a number (1-2) or press Enter to skip [1]: ").strip() or "1"

    if choice == "1":
        print_color(
            "[Log Analysis] Skipping log analysis and denoising.", Colors.GREEN)
        return

    os.chdir(work_dir)

    pruned_dir = os.path.join(work_dir, 'pruned')
    if os.path.exists(pruned_dir):
        shutil.rmtree(pruned_dir)
        print_color(
            f"[CLEAN] Removed existing pruned directory: {pruned_dir}", Colors.GREEN)
    os.makedirs(pruned_dir, exist_ok=True)
    print_color(
        f"[CLEAN] Ensured fresh pruned directory: {pruned_dir}", Colors.GREEN)

    if proj_path and os.path.isdir(proj_path):
        search_dir = os.path.join(proj_path, 'scenario_data')
    else:
        search_dir = os.path.join(work_dir, 'scenario_data')
        print_color(
            "[WARNING] proj_path not provided, falling back to global scenario_data directory.",
            Colors.YELLOW
        )

    project_lang = "java"
    if proj_path:
        config_path = os.path.join(proj_path, 'config.json')
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                    project_lang = config_data.get('language', 'java').lower()
            except Exception as e:
                print_color(
                    f"[WARN] Failed to read language from config.json: {e}", Colors.YELLOW)

    if not os.path.isdir(search_dir):
        print_color(
            f"[WARNING] scenario_data directory not found at {search_dir}.",
            Colors.YELLOW
        )

    log_files = sorted(
        glob.glob(os.path.join(search_dir, "instrumentor-log-*.txt")),
        key=os.path.getmtime,
        reverse=True
    )
    events_files = sorted(
        glob.glob(os.path.join(search_dir, "instrumentor-events-*.txt")),
        key=os.path.getmtime,
        reverse=True
    )

    if not events_files:
        print_color(
            f"[Auto-Fix] Could not find events file in: {search_dir}. Automatically creating a fake empty event file.",
            Colors.YELLOW
        )
        os.makedirs(search_dir, exist_ok=True)
        fake_events_file = os.path.join(
            search_dir, "instrumentor-events-fake.txt")
        with open(fake_events_file, "w", encoding="utf-8") as f:
            pass
        events_files = [fake_events_file]

    if not log_files:
        print_color(
            f"Could not find generated log file in: {search_dir}. "
            "Please check whether Step 2 executed successfully and generated the logs.",
            Colors.RED
        )
        return

    log_file = log_files[0]
    events_file = events_files[0]
    print(f"Found log file: {log_file}")
    print(f"Found events file: {events_file}")

    target_folders_file = os.path.join(
        proj_path, "target-folders.txt") if proj_path else ".\\target-folders.txt"

    if proj_path:
        comment_mapping_file = os.path.join(proj_path, "comment-mapping.txt")
        event_dict_file = os.path.join(proj_path, "event_dictionary.txt")
    else:
        comment_mapping_file = ".\\comment-mapping.txt"
        event_dict_file = ".\\event_dictionary.txt"

    if not os.path.exists(comment_mapping_file):
        print_color(
            f"[WARN] comment-mapping.txt not found at {comment_mapping_file}", Colors.YELLOW)
    if not os.path.exists(event_dict_file):
        print_color(
            f"[WARN] event_dictionary.txt not found at {event_dict_file}", Colors.YELLOW)

    if work_dir not in sys.path:
        sys.path.insert(0, work_dir)
    try:
        from enginerring import process_logs
    except ImportError as e:
        print_color(f"Failed to import process_logs: {e}", Colors.RED)
        return

    try:
        process_logs.process_logs(
            language=project_lang,
            target_folders_file=target_folders_file,
            log_file=log_file,
            comment_mapping_file=comment_mapping_file,
            events_file=events_file,
            event_dictionary_file=event_dict_file,
        )
    except Exception as e:
        print_color(f"Log processing failed: {e}", Colors.RED)


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
    while True:
        choice = input(f"Enter your choice (1-{len(scripts)}): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(scripts):
            break
        print_color("[!] Invalid choice, please try again.", Colors.RED)

    selected_script = scripts[int(choice) - 1]
    print_color(f"\n[Info] Selected script: {selected_script}", Colors.GREEN)
    return selected_script

def execute_ai_prompt(work_dir, selected_script):
    if not selected_script:
        return None

    print_color("\n>>> Generating AI Prompt...", Colors.CYAN)
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

        if hasattr(module, 'generate_prompt'):
            module.generate_prompt(selected_calltree_path)
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


def ask_llm_for_localization(ask_llm_dir):
    print_color("\n>>> Asking LLM for Task Analysis...", Colors.CYAN)
    setup_windows_proxy()

    if ask_llm_dir not in sys.path:
        sys.path.insert(0, ask_llm_dir)

    try:
        import run as ask_llm_run

        original_cwd = os.getcwd()

        # [Modified] Read unified AI_Task_Prompt.md instead of AI_Task_Prompt.md
        file_path = os.path.join(original_cwd, "AI_Task_Prompt.md")
        output_path = os.path.join(original_cwd, "output.md")

        os.chdir(ask_llm_dir)

        ask_llm_run.run_api(
            file_path=file_path,
            output_path=output_path
        )

        os.chdir(original_cwd)
        print_color(f"[+] LLM response saved to {output_path}", Colors.GREEN)

    except ImportError as e:
        print_color(
            f"[!] Failed to import run.py from {ask_llm_dir}: {e}", Colors.RED)
    except Exception as e:
        print_color(f"[!] Error during LLM API call: {e}", Colors.RED)
        if 'original_cwd' in locals():
            os.chdir(original_cwd)


def generate_fix_prompt(work_dir, proj_path=None):
    print_color("\n>>> Generating Fix Prompt...", Colors.CYAN)

    fix_bug_dir = os.path.join(work_dir, "enginerring", "fix_bug")

    if fix_bug_dir not in sys.path:
        sys.path.insert(0, fix_bug_dir)

    try:
        import generate_fix_prompt as fix_prompt_gen

        importlib.reload(fix_prompt_gen)

        original_cwd = os.getcwd()
        os.chdir(work_dir)

        report_path = os.path.join(work_dir, "output.md")

        fix_prompt_gen.generate_prompt(
            proj_path=proj_path, report_path=report_path)

        os.chdir(original_cwd)
    except ImportError as e:
        print_color(
            f"[!] Failed to import generate_fix_prompt from {fix_bug_dir}: {e}", Colors.RED)
    except Exception as e:
        print_color(f"[!] Error generating fix prompt: {e}", Colors.RED)
        if 'original_cwd' in locals():
            os.chdir(original_cwd)


def ask_llm_for_code_fix(ask_llm_dir):
    print_color("\n>>> Asking LLM for Code Fix...", Colors.CYAN)

    if ask_llm_dir not in sys.path:
        sys.path.insert(0, ask_llm_dir)

    try:
        import run as ask_llm_run

        original_cwd = os.getcwd()

        file_path = os.path.join(original_cwd, "AI_Apply_Fix_Prompt.md")
        output_path = os.path.join(original_cwd, "output.md")

        os.chdir(ask_llm_dir)

        print_color(f"[+] Using prompt file: {file_path}", Colors.GREEN)

        ask_llm_run.run_api(
            file_path=file_path,
            output_path=output_path
        )

        os.chdir(original_cwd)
        print_color(f"[+] LLM response saved to {output_path}", Colors.GREEN)

    except ImportError as e:
        print_color(
            f"[!] Failed to import run.py from {ask_llm_dir}: {e}", Colors.RED)
    except Exception as e:
        print_color(f"[!] Error during LLM API call: {e}", Colors.RED)
        if 'original_cwd' in locals():
            os.chdir(original_cwd)


def apply_fix(work_dir, proj_path=None):
    print_color("\n>>> Applying Fix to Source Code...", Colors.CYAN)

    fix_bug_dir = os.path.join(work_dir, "enginerring", "fix_bug")

    if fix_bug_dir not in sys.path:
        sys.path.insert(0, fix_bug_dir)

    try:
        import apply_fix as fix_applier

        importlib.reload(fix_applier)

        original_cwd = os.getcwd()
        os.chdir(work_dir)

        fixed_code_path = os.path.join(work_dir, "output.md")

        base_dirs = []
        if proj_path:
            config_path = os.path.join(proj_path, "config.json")
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
                    base_dirs = config_data.get("original-target-folders", [])

        if not base_dirs:
            base_dirs = ["."]
            print_color(
                "[Warning] No original-target-folders found in config.json, using current directory.", Colors.YELLOW)

        fix_applier.run_apply_fix(
            fixed_code_path=fixed_code_path, base_dirs=base_dirs)

        os.chdir(original_cwd)
    except ImportError as e:
        print_color(
            f"[!] Failed to import apply_fix from {fix_bug_dir}: {e}", Colors.RED)
    except Exception as e:
        print_color(f"[!] Error applying fix: {e}", Colors.RED)
        if 'original_cwd' in locals():
            os.chdir(original_cwd)
