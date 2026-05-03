import importlib
import os
import sys
import subprocess
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


def instrument_code(work_dir, proj_path=None, git_root=None):
    print_color(
        "\n>>> Setting up shadow branch and instrumenting code...", Colors.CYAN)

    print()
    print_color("========================================", Colors.YELLOW)
    print_color(" IMPORTANT PATH EXPLANATION", Colors.YELLOW)
    print_color("========================================", Colors.YELLOW)
    print_color(
        " The path requested here is the Git root directory of the target project.", Colors.YELLOW)
    print_color(
        " It is NOT the same as the paths listed in target-folders.txt.", Colors.YELLOW)
    print_color(
        " The paths in target-folders.txt are the specific source folders to instrument.", Colors.YELLOW)
    print_color(
        " The path entered below must be the top-level Git repository root that contains those folders.", Colors.YELLOW)
    print_color("========================================", Colors.YELLOW)

    if git_root:
        git_root_dir = git_root
        print_color(
            f"Using saved Git repository root directory: {git_root_dir}", Colors.GREEN)
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
    print("  1. Full Instrumentation\n  2. Incremental Instrumentation\n  3. Skip (if project is already instrumented)")
    print_color("========================================", Colors.CYAN)

    inst_mode_choice = ""
    while not re.match(r"^[1-3]$", inst_mode_choice):
        inst_mode_choice = input(
            "Enter a number (1-3) for the instrumentation mode: ").strip()
        if not re.match(r"^[1-3]$", inst_mode_choice):
            print_color(
                "[!] Invalid input. Please enter 1, 2, or 3.", Colors.RED)

    if inst_mode_choice == "3":
        print_color("[Mode Selection] Skipping instrumentation.", Colors.GREEN)
        return "skip"

    mode_arg = "full" if inst_mode_choice == "1" else "incremental"
    print_color(f"[Mode Selection] Selected mode: {mode_arg}", Colors.GREEN)

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

    # Move instrumentation output files to project directory after success
    if proj_path:
        _move_instrumentation_outputs_to_project(work_dir, proj_path)

    return mode_arg


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


def handle_instrumentation_dependencies(work_dir, proj_path, git_root, ask_llm_dir):
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
            # Use pom.xml snippet as an example for the prompt
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

    # 5. Invoke LLM (import module directly for easier debugging)
    llm_response_file = os.path.join(
        ask_llm_dir, "dependency_llm_response.txt")

    print_color(
        ">>> Asking LLM to identify target dependency files...", Colors.CYAN)

    # Add ask_llm directory to sys.path for importing
    if ask_llm_dir not in sys.path:
        sys.path.insert(0, ask_llm_dir)

    try:
        import run as ask_llm_run

        # Switch to ask_llm directory so .env file can be read correctly
        original_cwd = os.getcwd()
        os.chdir(ask_llm_dir)

        # Call the exposed API interface
        ask_llm_run.run_api(
            file_path="dependency_prompt.txt",
            output_path="dependency_llm_response.txt"
        )

        # Return to original working directory
        os.chdir(original_cwd)

    except ImportError as e:
        print_color(
            f"[!] Failed to import run.py from {ask_llm_dir}: {e}", Colors.RED)
        return

    # Return to original working directory
    os.chdir(original_cwd)

    # 6. Inject dependencies
    print_color(
        "\n>>> Parsing LLM response and injecting dependencies...", Colors.CYAN)
    run_injection(llm_response_file, snippets_json_path)


def compile_and_run(instrumentor_test_path):
    print_color("\n>>> Compiling and running instrumentor test...", Colors.CYAN)
    os.chdir(instrumentor_test_path)

    mvn_cmd = "mvn.cmd" if platform.system() == "Windows" else "mvn"
    print_color(
        f"Executing: {mvn_cmd} clean package -DskipTests", Colors.RESET)
    subprocess.run([mvn_cmd, "clean", "package", "-DskipTests"])

    jar_path = os.path.join("target", "instrumentor-test-1.0-SNAPSHOT.jar")
    print_color(f"Executing: java -jar {jar_path}", Colors.RESET)
    subprocess.run(["java", "-jar", jar_path])

    print_color(
        f"Program execution finished. Please verify that instrumentor-events-*.txt and instrumentor-log-*.txt have been generated in {instrumentor_test_path}",
        Colors.GREEN
    )


def startup_log_manager_server(work_dir, proj_path=None):
    print_color("\n>>> Starting Log Manager Server...", Colors.CYAN)
    
    # NEW: Added interactive prompt to skip log manager startup
    print()
    print_color("========================================", Colors.CYAN)
    print_color("       Log Manager Server Options       ", Colors.CYAN)
    print_color("========================================", Colors.CYAN)
    print("  1. Start Server (Default)\n  2. Skip (if logs are already collected)")
    print_color("========================================", Colors.CYAN)
    
    choice = input("Enter a number (1-2) or press Enter to start [1]: ").strip()
    if choice == "2":
        print_color("[Log Manager] Skipping log manager server startup.", Colors.GREEN)
        return
    
    server_dir = os.path.join(work_dir, "enginerring", "log_manager_server")
    
    # Add server directory to sys.path for importing
    if server_dir not in sys.path:
        sys.path.insert(0, server_dir)
        
    try:
        # Clear any cached module to avoid conflicts
        if 'log_manager' in sys.modules:
            del sys.modules['log_manager']
            
        import log_manager as log_server
        
        # Set the save root to the selected project directory
        log_server.SCENARIO_SAVE_ROOT = proj_path if proj_path else os.getcwd()
        
        print_color(f"Launching log manager server interface...", Colors.GREEN)
        log_server.run_manager()
    except ImportError as e:
        print_color(f"Failed to import log_manager module from {server_dir}: {e}", Colors.RED)


def analyze_logs(work_dir, instrumentor_test_path, proj_path=None):
    print_color(
        "\n>>> Analyzing logs and extracting denoised data...", Colors.CYAN)
        
    # ============================================================
    # NEW: Interactive prompt to skip log analysis
    # ============================================================
    print()
    print_color("========================================", Colors.CYAN)
    print_color("       Analyze Logs Options             ", Colors.CYAN)
    print_color("========================================", Colors.CYAN)
    print("  1. Skip (Default)\n  2. Execute Log Analysis")
    print_color("========================================", Colors.CYAN)
    
    choice = input("Enter a number (1-2) or press Enter to skip [1]: ").strip() or "1"
    
    if choice == "1":
        print_color("[Log Analysis] Skipping log analysis and denoising.", Colors.GREEN)
        return
        
    os.chdir(work_dir)

    # ============================================================
    # NEW: Clear the 'pruned' folder under work_dir before analysis
    # ============================================================
    pruned_dir = os.path.join(work_dir, 'pruned')
    if os.path.exists(pruned_dir):
        shutil.rmtree(pruned_dir)
        print_color(f"[CLEAN] Removed existing pruned directory: {pruned_dir}", Colors.GREEN)
    os.makedirs(pruned_dir, exist_ok=True)
    print_color(f"[CLEAN] Ensured fresh pruned directory: {pruned_dir}", Colors.GREEN)

    # Determine the scenario_data directory based on project context
    if proj_path and os.path.isdir(proj_path):
        scenario_dir = os.path.join(proj_path, 'scenario_data')
    else:
        scenario_dir = os.path.join(work_dir, 'scenario_data')
        print_color(
            "[WARNING] proj_path not provided, falling back to global scenario_data directory.",
            Colors.YELLOW
        )

    if os.path.isdir(scenario_dir):
        search_dir = scenario_dir
    else:
        search_dir = instrumentor_test_path
        print_color(
            f"[WARNING] scenario_data not found at {scenario_dir}, trying instrumentor test path.",
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

    if not log_files or not events_files:
        print_color(
            f"Could not find generated log or events file in: {search_dir}. "
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

    # Safety check: ensure required files exist
    if not os.path.exists(comment_mapping_file):
        print_color(
            f"[WARN] comment-mapping.txt not found at {comment_mapping_file}", Colors.YELLOW)
    if not os.path.exists(event_dict_file):
        print_color(
            f"[WARN] event_dictionary.txt not found at {event_dict_file}", Colors.YELLOW)

    # --- Replace subprocess call with direct function invocation ---
    # Add work_dir to path so that we can import process_logs_demo
    if work_dir not in sys.path:
        sys.path.insert(0, work_dir)
    try:
        import process_logs
    except ImportError as e:
        print_color(f"Failed to import process_logs_demo: {e}", Colors.RED)
        return

    try:
        process_logs.process_logs(
            target_folders_file=target_folders_file,
            log_file=log_file,
            comment_mapping_file=comment_mapping_file,
            events_file=events_file,
            event_dictionary_file=event_dict_file,
        )
    except Exception as e:
        print_color(f"Log processing failed: {e}", Colors.RED)


def generate_ai_prompt(work_dir):
    print_color("\n>>> Generating AI Prompt...", Colors.CYAN)
    os.chdir(work_dir)

    ai_app_path = os.path.join(work_dir, "core", "scenario_data_ai_app")
    python_script_path = os.path.join(
        ai_app_path, "generate_bug_localization_prompt.py")

    if not os.path.exists(python_script_path):
        print_color(
            f"AI prompt generation script not found at: {python_script_path}", Colors.RED)
        return

    # Scan for final-output-calltree.md files in the projects directory
    projects_dir = os.path.join(work_dir, "projects")
    search_pattern = os.path.join(projects_dir, "**", "final-output-calltree.md")
    calltree_files = glob.glob(search_pattern, recursive=True)

    selected_calltree_path = None

    if not calltree_files:
        print_color("[Warning] No final-output-calltree.md found in projects directory.", Colors.YELLOW)
    else:
        print_color("\n=== Select Call Tree File ===", Colors.CYAN)
        options = []
        for idx, file_path in enumerate(calltree_files, start=1):
            rel_path = os.path.relpath(file_path, projects_dir)
            project_name = rel_path.split(os.sep)[0] if os.sep in rel_path else rel_path
            options.append((project_name, os.path.abspath(file_path)))
            print(f"  {idx}. {project_name} ({rel_path})")
            
        while True:
            choice = input(f"Select a project number [1-{len(options)}] or press Enter to skip: ").strip()
            if not choice:
                break
            if choice.isdigit():
                num = int(choice)
                if 1 <= num <= len(options):
                    selected_project_name, selected_calltree_path = options[num - 1]
                    print_color(f"Selected project: {selected_project_name}", Colors.GREEN)
                    break
            print_color("Invalid selection, please try again.", Colors.RED)

    print_color(
        f"Running Python script from {work_dir} to generate the prompt...", Colors.GREEN)
    
    # Dynamically import generate_bug_localization_prompt and call exposed interface
    if ai_app_path not in sys.path:
        sys.path.insert(0, ai_app_path)
        
    try:
        import generate_bug_localization_prompt as prompt_gen
        
        importlib.reload(prompt_gen)
        
        prompt_gen.generate_prompt(selected_calltree_path)
    except ImportError as e:
        print_color(f"[!] Failed to import generate_bug_localization_prompt: {e}", Colors.RED)
    except Exception as e:
        print_color(f"[!] Error generating prompt: {e}", Colors.RED)


def ask_llm_for_localization(ask_llm_dir):
    print_color("\n>>> Asking LLM for Bug Localization...", Colors.CYAN)
    setup_windows_proxy()

    if ask_llm_dir not in sys.path:
        sys.path.insert(0, ask_llm_dir)

    try:
        import run as ask_llm_run
        
        original_cwd = os.getcwd()
        
        file_path = os.path.join(original_cwd, "AI_Bug_Localization_Prompt.md")
        output_path = os.path.join(original_cwd, "output.md")
        
        os.chdir(ask_llm_dir)

        ask_llm_run.run_api(
            file_path=file_path,
            output_path=output_path
        )
        
        os.chdir(original_cwd)
        print_color(f"[+] LLM response saved to {output_path}", Colors.GREEN)
        
    except ImportError as e:
        print_color(f"[!] Failed to import run.py from {ask_llm_dir}: {e}", Colors.RED)
    except Exception as e:
        print_color(f"[!] Error during LLM API call: {e}", Colors.RED)
        if 'original_cwd' in locals():
            os.chdir(original_cwd)


def generate_fix_prompt(work_dir, proj_path=None):
    print_color("\n>>> Generating Fix Prompt...", Colors.CYAN)

    fix_bug_dir = os.path.join(work_dir, "enginerring", "fix_bug")
    
    # Dynamically import generate_fix_prompt and call the exposed interface
    if fix_bug_dir not in sys.path:
        sys.path.insert(0, fix_bug_dir)
        
    try:
        import generate_fix_prompt as fix_prompt_gen
        
        # Reload to ensure we have the latest version if modified
        importlib.reload(fix_prompt_gen)
        
        original_cwd = os.getcwd()
        os.chdir(work_dir)
        
        # Automatically determine the report path based on localization output
        report_path = os.path.join(work_dir, "output.md")
        
        # Call the exposed interface with proj_path and report_path
        fix_prompt_gen.generate_prompt(proj_path=proj_path, report_path=report_path)
        
        os.chdir(original_cwd)
    except ImportError as e:
        print_color(f"[!] Failed to import generate_fix_prompt from {fix_bug_dir}: {e}", Colors.RED)
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
        
        # Automatically set paths based on the current working directory
        file_path = os.path.join(original_cwd, "AI_Apply_Fix_Prompt.md")
        output_path = os.path.join(original_cwd, "output.md")
        
        # Change directory to ensure environment variables and context are correct for LLM module
        os.chdir(ask_llm_dir)
        
        print_color(f"[+] Using prompt file: {file_path}", Colors.GREEN)

        ask_llm_run.run_api(
            file_path=file_path,
            output_path=output_path
        )
        
        # Restore the original working directory
        os.chdir(original_cwd)
        print_color(f"[+] LLM response saved to {output_path}", Colors.GREEN)
        
    except ImportError as e:
        print_color(f"[!] Failed to import run.py from {ask_llm_dir}: {e}", Colors.RED)
    except Exception as e:
        print_color(f"[!] Error during LLM API call: {e}", Colors.RED)
        if 'original_cwd' in locals():
            os.chdir(original_cwd)


# MODIFIED: Added proj_path parameter to allow automatic configuration loading
def apply_fix(work_dir, proj_path=None):
    print_color("\n>>> Applying Fix to Source Code...", Colors.CYAN)

    fix_bug_dir = os.path.join(work_dir, "enginerring", "fix_bug")
    
    if fix_bug_dir not in sys.path:
        sys.path.insert(0, fix_bug_dir)
        
    try:
        import apply_fix as fix_applier
        
        # Reload to ensure we have the latest version if modified
        importlib.reload(fix_applier)
        
        original_cwd = os.getcwd()
        os.chdir(work_dir)
        
        # MODIFIED: Automatically determine fixed code path and base directories
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
            print_color("[Warning] No original-target-folders found in config.json, using current directory.", Colors.YELLOW)
        
        # Call the exposed interface with the new parameters
        # Note: Ensure that run_apply_fix in apply_fix.py is updated to accept these parameters
        fix_applier.run_apply_fix(fixed_code_path=fixed_code_path, base_dirs=base_dirs)
        
        os.chdir(original_cwd)
    except ImportError as e:
        print_color(f"[!] Failed to import apply_fix from {fix_bug_dir}: {e}", Colors.RED)
    except Exception as e:
        print_color(f"[!] Error applying fix: {e}", Colors.RED)
        if 'original_cwd' in locals():
            os.chdir(original_cwd)