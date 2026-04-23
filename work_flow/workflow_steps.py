# workflow_steps.py
import os
import sys
import subprocess
import re
import platform
import glob
from .utils import Colors, print_color
from .prechecks import setup_windows_proxy

def instrument_code(work_dir):
    print_color("\n>>> Setting up shadow branch and instrumenting code...", Colors.CYAN)

    print()
    print_color("========================================", Colors.YELLOW)
    print_color(" IMPORTANT PATH EXPLANATION", Colors.YELLOW)
    print_color("========================================", Colors.YELLOW)
    print_color(" The path requested here is the Git root directory of the target project.", Colors.YELLOW)
    print_color(" It is NOT the same as the paths listed in target-folders.txt.", Colors.YELLOW)
    print_color(" The paths in target-folders.txt are the specific source folders to instrument.", Colors.YELLOW)
    print_color(" The path entered below must be the top-level Git repository root that contains those folders.", Colors.YELLOW)
    print_color("========================================", Colors.YELLOW)

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
        inst_mode_choice = input("Enter a number (1-3) for the instrumentation mode: ").strip()
        if not re.match(r"^[1-3]$", inst_mode_choice):
            print_color("[!] Invalid input. Please enter 1, 2, or 3.", Colors.RED)

    if inst_mode_choice == "3":
        print_color("[Mode Selection] Skipping instrumentation.", Colors.GREEN)
        return

    mode_arg = "full" if inst_mode_choice == "1" else "incremental"
    print_color(f"[Mode Selection] Selected mode: {mode_arg}", Colors.GREEN)

    setup_script_path = os.path.join(work_dir, "enginerring", "shadow-project-management", "instrument_with_shadow_project.py")

    if os.path.exists(setup_script_path):
        cmd = [sys.executable, setup_script_path, git_root_dir, "--mode", mode_arg]
        if mode_arg == "incremental":
            project_file_path = os.path.join(work_dir, "current_project")
            cmd.extend(["--project-file", project_file_path])

        print_color(f"Executing: {' '.join(cmd)}", Colors.MAGENTA)
        result = subprocess.run(cmd)

        if result.returncode != 0:
            print_color("Error: Failed to setup shadow branch and instrument code. Exiting.", Colors.RED)
            sys.exit(result.returncode)
    else:
        print_color(f"Warning: instrument_with_shadow_project.py not found at {setup_script_path}.", Colors.YELLOW)
        print_color("Please ensure the script is placed in the correct directory. Exiting.", Colors.RED)
        sys.exit(1)

def compile_and_run(instrumentor_test_path):
    print_color("\n>>> Compiling and running instrumentor test...", Colors.CYAN)
    os.chdir(instrumentor_test_path)

    mvn_cmd = "mvn.cmd" if platform.system() == "Windows" else "mvn"
    print_color(f"Executing: {mvn_cmd} clean package -DskipTests", Colors.RESET)
    subprocess.run([mvn_cmd, "clean", "package", "-DskipTests"])

    jar_path = os.path.join("target", "instrumentor-test-1.0-SNAPSHOT.jar")
    print_color(f"Executing: java -jar {jar_path}", Colors.RESET)
    subprocess.run(["java", "-jar", jar_path])

    print_color(
        f"Program execution finished. Please verify that instrumentor-events-*.txt and instrumentor-log-*.txt have been generated in {instrumentor_test_path}",
        Colors.GREEN
    )

def startup_log_manager_server(work_dir):
    print_color("\n>>> Starting Log Manager Server...", Colors.CYAN)
    server_script = os.path.join(work_dir, "enginerring", "log-manager-server", "server.py")
    
    if os.path.exists(server_script):
        print_color(f"Launching {server_script}...", Colors.GREEN)
        # Changed from subprocess.Popen to subprocess.run to prevent stdin collision
        subprocess.run([sys.executable, server_script])
    else:
        print_color(f"server.py not found at: {server_script}", Colors.RED)

def analyze_logs(work_dir, instrumentor_test_path):
    print_color("\n>>> Analyzing logs and extracting denoised data...", Colors.CYAN)
    os.chdir(work_dir)

    log_files = sorted(
        glob.glob(os.path.join(instrumentor_test_path, "instrumentor-log-*.txt")),
        key=os.path.getmtime,
        reverse=True
    )
    events_files = sorted(
        glob.glob(os.path.join(instrumentor_test_path, "instrumentor-events-*.txt")),
        key=os.path.getmtime,
        reverse=True
    )

    if log_files and events_files:
        log_file = log_files[0]
        events_file = events_files[0]
        print(f"Found log file: {log_file}")
        print(f"Found events file: {events_file}")

        ps_exe = "powershell" if platform.system() == "Windows" else "pwsh"
        ps_cmd = [
            ps_exe, "-ExecutionPolicy", "Bypass", "-File", ".\\process-logs-demo.ps1",
            "-TargetFoldersFile", ".\\target-folders.txt",
            "-LogFile", log_file,
            "-CommentMappingFile", ".\\comment-mapping.txt",
            "-EventsFile", events_file
        ]
        subprocess.run(ps_cmd)
    else:
        print_color(
            "Could not find generated log or events file. Please check whether Step 2 executed successfully and generated the logs.",
            Colors.RED
        )

def generate_ai_prompt(work_dir):
    print_color("\n>>> Generating AI Prompt...", Colors.CYAN)
    os.chdir(work_dir)

    ai_app_path = os.path.join(work_dir, "core", "denoised-data-ai-app")
    python_script_path = os.path.join(ai_app_path, "generate_bug_localization_prompt.py")

    if os.path.exists(python_script_path):
        print_color(f"Running Python script from {work_dir} to generate the prompt...", Colors.GREEN)
        subprocess.run([sys.executable, python_script_path])
    else:
        print_color(f"AI prompt generation script not found at: {python_script_path}", Colors.RED)

def ask_llm_for_localization(ask_llm_dir):
    print_color("\n>>> Asking LLM for Bug Localization...", Colors.CYAN)
    setup_windows_proxy()
    
    os.chdir(ask_llm_dir)
    if os.path.exists("run.py"):
        subprocess.run([sys.executable, "run.py"])
    else:
        print_color(f"run.py not found in {ask_llm_dir}", Colors.RED)

def generate_fix_prompt(work_dir):
    print_color("\n>>> Generating Fix Prompt...", Colors.CYAN)

    fix_bug_dir = os.path.join(work_dir, "enginerring", "fix-bug")
    generate_fix_script = os.path.join(fix_bug_dir, "generate_fix_prompt.py")

    if os.path.exists(generate_fix_script):
        subprocess.run([sys.executable, generate_fix_script])
    else:
        print_color(f"generate_fix_prompt.py not found at: {generate_fix_script}", Colors.RED)

def ask_llm_for_code_fix(ask_llm_dir):
    print_color("\n>>> Asking LLM for Code Fix...", Colors.CYAN)
    os.chdir(ask_llm_dir)
    if os.path.exists("run.py"):
        subprocess.run([sys.executable, "run.py"])
    else:
        print_color(f"run.py not found in {ask_llm_dir}", Colors.RED)

def apply_fix(work_dir):
    print_color("\n>>> Applying Fix to Source Code...", Colors.CYAN)

    fix_bug_dir = os.path.join(work_dir, "enginerring", "fix-bug")
    apply_fix_script = os.path.join(fix_bug_dir, "apply_fix.py")

    if os.path.exists(apply_fix_script):
        subprocess.run([sys.executable, apply_fix_script])
    else:
        print_color(f"apply_fix.py not found at: {apply_fix_script}", Colors.RED)