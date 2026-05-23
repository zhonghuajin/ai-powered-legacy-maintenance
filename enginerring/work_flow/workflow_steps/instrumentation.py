import os
import sys
import re
import shutil
import json
import subprocess
from print_utils.utils import Colors, print_color

from enginerring.shadow_project_management.instrument_with_shadow_project import run_instrumentation_mode
from enginerring.dependency_handler.scan_deps import find_project_files
from enginerring.dependency_handler.prompt_organizer import generate_prompt
from enginerring.dependency_handler.dependency_injector import run_injection

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
        original_cwd=work_dir,
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
    Handle dependency addition after instrumentation
    """
    print_color("\n>>> Handling Instrumentation Dependencies...", Colors.CYAN)

    files_input = find_project_files(git_root)

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
                                    r'namespace\s+[a-zA-Z0-9_]+\s*;', content, re.IGNORECASE)
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

    config_path = os.path.join(proj_path, "config.json")
    whitelist_input = []
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)
            whitelist_input = config_data.get("original-target-folders", [])

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

    prompt = generate_prompt(files_input, whitelist_input, dependency_input)

    prompt_file = os.path.join(ask_llm_dir, "dependency_prompt.txt")
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(prompt)

    print_color(
        f"[+] Dependency prompt generated at {prompt_file}", Colors.GREEN)

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

    print_color(
        "\n>>> Parsing LLM response and injecting dependencies...", Colors.CYAN)

    run_injection(llm_response_file, snippets_json_path, work_dir)