#!/usr/bin/env python3
"""
Instrumentor Test Bug Fix Workflow Quickstart Script
This script guides you through the full process of code instrumentation,
log denoising and analysis, AI prompt generation, and automated bug fixing.
"""

import os
import sys
import json
import subprocess
import argparse
import platform
import webbrowser
import signal

from print_utils.utils import Colors, print_color, pause_for_next_step
from enginerring.work_flow.prechecks import (
    print_disclaimer,
    check_java_version,
    check_llm_env,
    auto_select_llm_provider
)
from enginerring.work_flow.workflow_steps import (
    ensure_language_selected,
    instrument_code,
    handle_instrumentation_dependencies,
    startup_log_manager_server,
    analyze_logs,
    select_ai_prompt_script,
    prepare_ai_prompt_interactive,
    execute_ai_prompt,
    ask_llm_for_localization,
    generate_fix_prompt,
    ask_llm_for_code_fix,
    apply_fix,
    get_single_char
)

from enginerring.shadow_project_management.full_instrumentation import commit_instrumentation
from enginerring.project_manager.project_manager import create_or_select_project
from enginerring.scenario_manager.generate_scenario_description import generate_scenario_description


# Global variable to track the active terminal process for non-Windows platforms
_active_startup_process = None
# Unique window title used to identify and close the verification window on Windows
_win_title = "Instrumentor_Verification_Console"


def get_single_char_fallback():
    """
    Cross-platform single character reader function as a fallback.
    """
    if os.name == 'nt':
        import msvcrt
        ch = msvcrt.getch()
        try:
            return ch.decode('utf-8')
        except Exception:
            return str(ch)
    else:
        import tty
        import termios
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch


def close_previous_startup_window():
    """
    Closes the previously opened terminal window and all its child processes.
    """
    global _active_startup_process
    current_os = platform.system()
    
    if current_os == 'Windows':
        try:
            # Added /T to forcefully terminate the window AND all child processes spawned inside it
            subprocess.run(
                f'taskkill /F /T /FI "WINDOWTITLE eq {_win_title}*"',
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception:
            pass
    else:
        if _active_startup_process is not None:
            try:
                # Get process group ID and kill the entire process group (including all active servers/subprocesses)
                pgid = os.getpgid(_active_startup_process.pid)
                os.killpg(pgid, signal.SIGKILL)
            except Exception:
                try:
                    _active_startup_process.terminate()
                except Exception:
                    pass
            finally:
                try:
                    _active_startup_process.wait(timeout=1)
                except Exception:
                    pass
                _active_startup_process = None


def switch_to_source_branch(proj_path):
    """
    Read the project config.json and checkout the original_git_root
    repository to its configured source_branch.
    """
    config_path = os.path.join(proj_path, 'config.json')
    if not os.path.exists(config_path):
        print_color('[Branch Switch] config.json not found, skipping branch switch.', Colors.YELLOW)
        return

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    git_root = config.get('original_git_root', '')
    source_branch = config.get('source_branch', 'master')

    if not git_root:
        print_color('[Branch Switch] original_git_root is empty, skipping branch switch.', Colors.YELLOW)
        return

    try:
        status_result = subprocess.run(
            ['git', '-C', git_root, 'status', '--porcelain'],
            check=True,
            capture_output=True,
            text=True
        )
        if status_result.stdout.strip():
            print_color(
                '[Branch Switch] Detected uncommitted changes. Adding and amending last commit...',
                Colors.CYAN
            )
            subprocess.run(
                ['git', '-C', git_root, 'add', '.'],
                check=True,
                capture_output=True,
                text=True
            )
            subprocess.run(
                ['git', '-C', git_root, 'commit', '--amend', '--no-edit'],
                check=True,
                capture_output=True,
                text=True
            )
            print_color('[Branch Switch] Changes committed via amend.', Colors.GREEN)
    except subprocess.CalledProcessError as e:
        print_color(f'[Branch Switch] Failed to handle uncommitted changes: {e.stderr.strip()}', Colors.RED)
        print_color('[Branch Switch] Continuing with the workflow despite the error.', Colors.YELLOW)

    print_color(f'[Branch Switch] Switching {git_root} to branch "{source_branch}" ...', Colors.CYAN)
    try:
        result = subprocess.run(
            ['git', '-C', git_root, 'checkout', source_branch],
            check=True,
            capture_output=True,
            text=True
        )
        print_color(f'[Branch Switch] Successfully switched to {source_branch}.', Colors.GREEN)
    except subprocess.CalledProcessError as e:
        print_color(f'[Branch Switch] Failed to switch branch: {e.stderr.strip()}', Colors.RED)
        print_color('[Branch Switch] You may have uncommitted changes or the branch does not exist.', Colors.RED)
        print_color('[Branch Switch] Continuing with the workflow despite the branch switch failure.', Colors.YELLOW)


def run_initial_startup_verification(work_dir, proj_path):
    global _active_startup_process

    if proj_path:
        config_path = os.path.join(proj_path, 'config.json')
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                if config.get('skip_log_and_manager') is True:
                    print_color("[Skip] Verification failed previously. Skipping Initial Startup Verification.", Colors.YELLOW)
                    return False
            except Exception as e:
                print_color(f"[Warning] Failed to read config.json: {e}", Colors.YELLOW)

    close_previous_startup_window()

    print_color("\n=======================================================", Colors.CYAN)
    print_color("      Running Initial Startup Verification...          ", Colors.CYAN)
    print_color("=======================================================", Colors.CYAN)

    config_path = os.path.join(proj_path, 'config.json') if proj_path else None
    config_data = {}
    git_root = work_dir

    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                git_root = config_data.get('original_git_root', work_dir)
        except Exception as e:
            print_color(f"[WARN] Failed to load config.json: {e}", Colors.YELLOW)

    config_key = "startup_command_initial"
    startup_config = config_data.get(config_key)
    choice = ""
    value = ""

    if startup_config and isinstance(startup_config, dict):
        choice = startup_config.get("type", "")
        value = startup_config.get("value", "")
        print_color(f"\n[Auto Verification] Found saved configuration for '{config_key}' (Type {choice}): {value}", Colors.GREEN)
    else:
        print_color("\n========================================", Colors.YELLOW)
        print_color(f" Verification / Startup Configuration Required ({config_key}) ", Colors.YELLOW)
        print_color("========================================", Colors.YELLOW)
        print_color("Please enter your project startup command OR URL directly:", Colors.CYAN)
        print_color("  - If it starts with http://, https://, localhost, or 127.0.0.1, it will open in the browser.", Colors.CYAN)
        print_color("  - Otherwise, it will run as a terminal command.", Colors.CYAN)

        while not value:
            value = input("\nEnter command or URL: ").strip()
            if not value:
                print_color("[Warning] Input cannot be empty.", Colors.YELLOW)

        # Automatically determine the type based on input
        lower_val = value.lower()
        if (
            lower_val.startswith(("http://", "https://")) or 
            lower_val.startswith("localhost") or 
            lower_val.startswith("127.0.0.1") or
            lower_val.startswith("www.")
        ):
            choice = "2"
            print_color(f"\n[Auto-Detected] Input recognized as URL.", Colors.GREEN)
        else:
            choice = "1"
            print_color(f"\n[Auto-Detected] Input recognized as Terminal Command.", Colors.GREEN)

        config_data[config_key] = {
            "type": choice,
            "value": value
        }
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(config_data, f, indent=4, ensure_ascii=False)
                print_color(f"[Config] Successfully saved {config_key} to config.json", Colors.GREEN)
            except Exception as e:
                print_color(f"[Error] Failed to save {config_key} to config.json: {e}", Colors.RED)

    process_to_wait = None
    if choice == "1":
        print_color(f"[Info] Opening a new terminal window to execute: {value}", Colors.GREEN)
        current_os = platform.system()
        try:
            if current_os == 'Windows':
                cmd_str = f'start "{_win_title}" cmd /k "{value}"'
                subprocess.Popen(cmd_str, shell=True, cwd=git_root)
            elif current_os == 'Darwin':
                # Run the AppleScript inside a tracked process group to allow termination
                _active_startup_process = subprocess.Popen(
                    ['osascript', '-e', f'tell application "Terminal" to do script "cd {git_root} && {value}"'],
                    preexec_fn=os.setsid if hasattr(os, 'setsid') else None
                )
                process_to_wait = _active_startup_process
            else:
                _active_startup_process = subprocess.Popen(
                    ['x-terminal-emulator', '-e', f'sh -c "cd {git_root} && {value}; exec sh"'],
                    preexec_fn=os.setsid if hasattr(os, 'setsid') else None
                )
                process_to_wait = _active_startup_process
        except Exception as e:
            print_color(f"[Error] Failed to launch terminal window: {e}", Colors.RED)

    elif choice == "2":
        if not value.startswith(("http://", "https://")):
            value = "http://" + value
        print_color(f"[Info] Opening browser to: {value}", Colors.GREEN)
        try:
            webbrowser.open(value)
        except Exception as e:
            print_color(f"[Error] Failed to open browser: {e}", Colors.RED)

    print_color("\n[Verification] Startup command triggered successfully.", Colors.GREEN)
    input("Press Enter once your project has successfully started to proceed to Log Manager Server...")
    return True


def check_if_ai_will_modify(work_dir, script_name):
    """
    Check if the selected script contains the magic comment '#AI will modify codes'.
    Reads only the first 50 lines to optimize performance.
    """
    if not script_name:
        return False

    script_path = os.path.join(work_dir, 'enginerring', 'scenario_data_ai_app', script_name)
    if not os.path.exists(script_path):
        return False

    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            for _ in range(50):
                line = f.readline()
                if not line:
                    break
                if "AI will modify codes" in line:
                    return True
    except Exception as e:
        print_color(f'[WARN] Failed to read script {script_name}: {e}', Colors.YELLOW)

    return False


def main():
    parser = argparse.ArgumentParser(description="Instrumentor Test Bug Fix Workflow Quickstart Script")
    parser.add_argument(
        '--pause',
        action='store_true',
        help="Pause between workflow steps."
    )
    parser.add_argument(
        '--interactive-ip',
        action='store_true',
        help="Prompt interactively for target IPs. If not specified, will auto-simulate Enter."
    )
    parser.add_argument(
        '--script-index',
        type=int,
        default=None,
        help="Pre-selected index for Select Prompt Generator Script (1-based)."
    )
    args = parser.parse_args()

    if args.interactive_ip:
        os.environ['INTERACTIVE_IP'] = 'true'
    else:
        os.environ['INTERACTIVE_IP'] = 'false'

    def maybe_pause(completed_step, next_step):
        if args.pause:
            pause_for_next_step(completed_step, next_step)

    work_dir = os.path.abspath(os.getcwd())
    ask_llm_dir = os.path.join(work_dir, "enginerring", "ask_llm")

    print_color("=======================================================", Colors.CYAN)
    print_color("      Enjoy the Convenience of LLMs.     ", Colors.CYAN)
    print_color("=======================================================", Colors.CYAN)
    print(f"Current working directory: {work_dir}")
    print_color("=======================================================\n", Colors.CYAN)

    print_disclaimer()
    check_java_version()
    env_file = check_llm_env(ask_llm_dir)
    auto_select_llm_provider(env_file)

    while True:
        print_color("\n=======================================================", Colors.CYAN)
        print_color("      Starting / Restarting Project Workflow      ", Colors.CYAN)
        print_color("=======================================================\n", Colors.CYAN)

        proj_path, root_path, is_new_project = create_or_select_project(work_dir)
        target_language = ensure_language_selected(proj_path)

        while True:
            selected_script = select_ai_prompt_script(work_dir, target_language, preselected_index=args.script_index)
            has_ai_marker = check_if_ai_will_modify(work_dir, selected_script)
            prompt_context = prepare_ai_prompt_interactive(work_dir, selected_script, proj_path=proj_path, save_context=has_ai_marker)

            maybe_pause("Project and Environment Setup", "Setup Shadow Branch")

            instrument_mode, is_skipped = instrument_code(
                work_dir, proj_path=proj_path, git_root=root_path, is_new_project=is_new_project)

            if is_skipped:
                pass
            else:
                if instrument_mode == "incremental":
                    print_color("\n=======================================================", Colors.YELLOW)
                    print_color("  *** ATTENTION ***", Colors.YELLOW)
                    print_color("  Incremental instrumentation completed!", Colors.YELLOW)
                    print_color("  Please RECOMPILE (if necessary), RESTART the target project, and PERFORM operations to trigger logs.", Colors.YELLOW)
                    print_color("=======================================================\n", Colors.YELLOW)
                elif instrument_mode == "full":
                    handle_instrumentation_dependencies(
                        work_dir, proj_path, root_path, ask_llm_dir, target_language)
                    commit_instrumentation(root_path)
                    print_color("\n=======================================================", Colors.YELLOW)
                    print_color("  *** ATTENTION ***", Colors.YELLOW)
                    print_color("  Instrumentation and Dependency Injection have been completed!", Colors.YELLOW)
                    print_color("  Please RECOMPILE (if necessary), RESTART the target project, and PERFORM operations to trigger logs.", Colors.YELLOW)
                    print_color("=======================================================\n", Colors.YELLOW)

            maybe_pause("Setup Shadow Branch & Instrumentation", "Startup Log Manager Server")

            run_initial_startup_verification(work_dir, proj_path=proj_path)

            is_flushed = startup_log_manager_server(work_dir, proj_path=proj_path)

            maybe_pause("Startup Log Manager Server", "Analyze Logs and Extract Denoised Data")

            switch_to_source_branch(proj_path)
            analyze_logs(work_dir, proj_path=proj_path, auto_analyze=is_flushed)

            maybe_pause("Log Analysis", "Generate AI Prompt")

            execute_ai_prompt(work_dir, selected_script, prompt_context)

            if has_ai_marker:
                maybe_pause("Generate AI Prompt", "Ask LLM for Task Analysis")
                ask_llm_for_localization(ask_llm_dir)

                maybe_pause("Ask LLM for Task Analysis", "Generate Fix/Dev Prompt")
                generate_fix_prompt(work_dir, proj_path)

                maybe_pause("Generate Fix/Dev Prompt", "Ask LLM for Code Modification")
                ask_llm_for_code_fix(ask_llm_dir)

                maybe_pause("Ask LLM for Code Modification", "Apply Changes to Source Code")
                apply_fix(work_dir, proj_path, prompt_context)

                print_color("\n=======================================================", Colors.MAGENTA)
                print_color("  Workflow execution completed successfully. The code has been updated.", Colors.GREEN)
                print_color("=======================================================", Colors.MAGENTA)

            elif selected_script:
                maybe_pause("Generate AI Prompt", "Execute General LLM Task")
                print_color(f"\n>>> Executing general LLM task for {selected_script}...", Colors.CYAN)

                if ask_llm_dir not in sys.path:
                    sys.path.insert(0, ask_llm_dir)

                try:
                    import run as ask_llm_run

                    original_cwd = os.getcwd()
                    os.chdir(ask_llm_dir)

                    prompt_file_path = os.path.join(original_cwd, "AI_Task_Prompt.md")
                    output_file_path = os.path.join(original_cwd, "output.md")

                    if not os.path.exists(prompt_file_path):
                        print_color(f"[WARN] Expected prompt file not found: {prompt_file_path}", Colors.YELLOW)
                        print_color("[WARN] Please ensure your script generates this file, or update the filename in startup.py.", Colors.YELLOW)
                    else:
                        ask_llm_run.run_api(file_path=prompt_file_path, output_path=output_file_path)
                        print_color(f"[+] LLM response saved to {output_file_path}", Colors.GREEN)

                    os.chdir(original_cwd)

                    print_color("\n=======================================================", Colors.MAGENTA)
                    print_color("  General LLM task execution completed successfully.", Colors.GREEN)
                    print_color("=======================================================", Colors.MAGENTA)

                except ImportError as e:
                    print_color(f"[!] Failed to import run.py from {ask_llm_dir}: {e}", Colors.RED)
                except Exception as e:
                    print_color(f"[!] Error during LLM API call: {e}", Colors.RED)
                    if 'original_cwd' in locals():
                        os.chdir(original_cwd)
            else:
                print_color("\n[!] Prompt generation was skipped or failed. No further actions taken.", Colors.YELLOW)

            # Automatically switch to the project's source branch once entering the Choose action stage
            if proj_path:
                print_color("\n[System] Entering Choose action stage. Enforcing branch switch...", Colors.YELLOW)
                try:
                    switch_to_source_branch(proj_path)
                except Exception as e:
                    print_color(f"[WARN] Failed to switch branch: {e}", Colors.RED)

            print_color('\n[Scenario Schema] Choose action:', Colors.CYAN)
            print('  1. Skip generate_scenario_description (Default)')
            print('  2. Execute generate_scenario_description')

            prompt_msg = 'Enter your choice [1]: '
            print(prompt_msg, end='', flush=True)

            choice_char = get_single_char()

            if choice_char in ['\r', '\n']:
                print('1')
                choice = '1'
            elif choice_char == '\x03':
                raise KeyboardInterrupt
            else:
                print(choice_char)
                choice = choice_char.strip() or '1'

            if choice == '2':
                generate_scenario_description(work_dir, proj_path)
            else:
                print_color('[Scenario Schema] Skipped by user.', Colors.YELLOW)

            print_color("\n[System] Re-initializing existing project state for the next run...", Colors.CYAN)
            proj_path, root_path, is_new_project = create_or_select_project(
                work_dir,
                preselected_proj_path=proj_path
            )

            os.chdir(work_dir)
            print_color("\n[!] Workflow finished. Returning to Select Prompt Generator Script... (Press Ctrl+C to exit)\n", Colors.CYAN)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[!] Process interrupted by user (Ctrl+C). Exiting safely...")
        sys.exit(0)