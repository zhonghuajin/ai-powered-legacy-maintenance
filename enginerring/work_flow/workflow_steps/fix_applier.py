import os
import sys
import json
import platform
import builtins
import importlib
import subprocess
import webbrowser
from print_utils.utils import Colors, print_color
from . import common


# Global variable to track the active terminal process for non-Windows platforms
_active_fix_process = None
# Unique window title used to identify and close the verification window on Windows
_win_title = "Instrumentor_Verification_Console"


def get_single_char_fallback():
    """
    Cross-platform single character reader function as a fallback.
    Used if get_single_char is not provided in the common module.
    """
    import sys
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


def close_previous_fix_window():
    """
    Closes the previously opened terminal window.
    """
    global _active_fix_process
    current_os = platform.system()
    
    if current_os == 'Windows':
        try:
            # Forcefully close any window matching our unique title
            subprocess.run(
                f'taskkill /F /FI "WINDOWTITLE eq {_win_title}*"',
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception:
            pass
    else:
        if _active_fix_process is not None:
            try:
                if _active_fix_process.poll() is None:
                    try:
                        os.killpg(os.getpgid(_active_fix_process.pid), 15)
                    except Exception:
                        _active_fix_process.terminate()
                    _active_fix_process.wait(timeout=2)
            except Exception:
                pass
            _active_fix_process = None


def execute_startup_verification(config_data, config_path, git_root, config_key="startup_command_fix"):
    global _active_fix_process

    close_previous_fix_window()

    shared_key = "startup_command_initial"
    startup_config = config_data.get(shared_key) or config_data.get(config_key)

    choice = ""
    value = ""

    if startup_config and isinstance(startup_config, dict):
        choice = startup_config.get("type", "")
        value = startup_config.get("value", "")
        print_color(
            f"\n[Auto Verification] Reusing saved startup configuration (Type {choice}): {value}", Colors.GREEN)
    else:
        print_color("\n========================================",
                    Colors.YELLOW)
        print_color(
            f" Verification / Startup Configuration Required ", Colors.YELLOW)
        print_color("========================================", Colors.YELLOW)
        print_color("Select verification/startup method:", Colors.CYAN)
        print_color(
            "[1] Run a project startup command in a new terminal", Colors.CYAN)
        print_color(
            "[2] Open a URL in the browser (e.g., for hot-reload)", Colors.CYAN)
        print_color("Press [1] or [2] to choose instantly...", Colors.YELLOW)

        get_char_func = getattr(common, 'get_single_char', None) or getattr(
            common, '_original_get_single_char', None) or get_single_char_fallback

        while choice not in ["1", "2"]:
            try:
                choice = get_char_func()
                if isinstance(choice, bytes):
                    choice = choice.decode('utf-8', errors='ignore')
                choice = choice.strip()
            except Exception:
                choice = input("Enter choice (1 or 2): ").strip()

        print_color(
            f"\n[Selected Option {choice}] Proceeding...", Colors.GREEN)

        if choice == "1":
            while not value:
                value = input("Enter the project startup command: ").strip()
                if not value:
                    print_color(
                        "[Warning] Startup command cannot be empty.", Colors.YELLOW)
        elif choice == "2":
            while not value:
                value = input(
                    "Enter the URL to open in browser (e.g., http://localhost:8080): ").strip()
                if not value:
                    print_color("[Warning] URL cannot be empty.",
                                Colors.YELLOW)

        config_payload = {
            "type": choice,
            "value": value
        }
        config_data[config_key] = config_payload
        config_data[shared_key] = config_payload

        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(config_data, f, indent=4, ensure_ascii=False)
                print_color(
                    f"[Config] Successfully saved startup configuration to config.json", Colors.GREEN)
            except Exception as e:
                print_color(
                    f"[Error] Failed to save configuration to config.json: {e}", Colors.RED)

    process_to_wait = None
    if choice == "1":
        print_color(
            f"[Info] Opening a new terminal window to execute: {value}", Colors.GREEN)
        current_os = platform.system()
        try:
            if current_os == 'Windows':
                # Using start command with explicit title to ensure visibility and clean termination
                cmd_str = f'start "{_win_title}" cmd /k "{value}"'
                subprocess.Popen(cmd_str, shell=True, cwd=git_root)
            elif current_os == 'Darwin':
                applescript = f'tell application "Terminal" to do script "cd {git_root} && {value}"'
                _active_fix_process = subprocess.Popen(
                    ['osascript', '-e', applescript])
                process_to_wait = _active_fix_process
            else:
                _active_fix_process = subprocess.Popen(
                    ['x-terminal-emulator', '-e', f'sh -c "cd {git_root} && {value}; exec sh"'],
                    preexec_fn=os.setsid if hasattr(os, 'setsid') else None
                )
                process_to_wait = _active_fix_process
        except Exception as e:
            print_color(
                f"[Error] Failed to launch terminal window: {e}", Colors.RED)

    elif choice == "2":
        if not value.startswith(("http://", "https://")):
            value = "http://" + value
        print_color(f"[Info] Opening browser to: {value}", Colors.GREEN)
        try:
            webbrowser.open(value)
        except Exception as e:
            print_color(f"[Error] Failed to open browser: {e}", Colors.RED)

    return choice, process_to_wait


def apply_fix(work_dir, proj_path=None, prompt_context=None):
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
        config_data = {}
        config_path = ""
        git_root = ""

        if proj_path:
            config_path = os.path.join(proj_path, "config.json")
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
                    base_dirs = config_data.get("original-target-folders", [])
                    git_root = config_data.get("original_git_root", "")

        if not base_dirs:
            base_dirs = ["."]
            print_color(
                "[Warning] No original-target-folders found in config.json, using current directory.", Colors.YELLOW)

        saved_commit = None
        if git_root and os.path.exists(git_root):
            try:
                commit_id = subprocess.check_output(
                    ['git', 'rev-parse', 'HEAD'],
                    cwd=git_root,
                    stderr=subprocess.DEVNULL
                ).decode('utf-8').strip()

                config_data['current_commit'] = commit_id
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(config_data, f, indent=4)
                saved_commit = commit_id
                print_color(
                    f"[Git Record] Saved current commit '{commit_id}' to config.json", Colors.GREEN)
            except Exception as e:
                print_color(
                    f"[Git Warning] Failed to record git commit: {e}", Colors.YELLOW)

        fix_applier.run_apply_fix(
            fixed_code_path=fixed_code_path,
            base_dirs=base_dirs,
            prompt_context=prompt_context,
            proj_path=proj_path
        )

        has_changes = False
        if git_root and os.path.exists(git_root):
            try:
                status_out = subprocess.check_output(
                    ['git', 'status', '--porcelain'],
                    cwd=git_root
                ).decode('utf-8').strip()
                if status_out:
                    has_changes = True
            except Exception as e:
                print_color(
                    f"[Git Warning] Failed to check git status: {e}", Colors.YELLOW)

        if has_changes:

            choice, process_to_wait = execute_startup_verification(
                config_data, config_path, git_root, config_key="startup_command_fix"
            )

            if choice == "1" and process_to_wait:
                print_color(
                    "[Info] Waiting for the terminal window to close...", Colors.YELLOW)
                process_to_wait.wait()
            else:
                input(
                    "Press Enter once you have finished verification in your browser/terminal...")

            satisfied = input(
                "\nDid the code fix meet your expectations? (yes/no): ").strip().lower()
            
            # Close the verification window immediately after getting user input
            close_previous_fix_window()

            if satisfied in ['yes', 'y']:
                print_color(
                    "[Success] Verification passed! Proceeding to next step.", Colors.GREEN)

                if config_path and os.path.exists(config_path):
                    try:
                        with open(config_path, "r", encoding="utf-8") as f:
                            config_data = json.load(f)
                        config_data["skip_log_and_manager"] = False
                        with open(config_path, "w", encoding="utf-8") as f:
                            json.dump(config_data, f, indent=4)
                    except Exception as e:
                        print_color(
                            f"[Error] Failed to update config.json: {e}", Colors.RED)
            else:
                if config_path and os.path.exists(config_path):
                    try:
                        with open(config_path, "r", encoding="utf-8") as f:
                            config_data = json.load(f)
                        config_data["skip_log_and_manager"] = True
                        with open(config_path, "w", encoding="utf-8") as f:
                            json.dump(config_data, f, indent=4)
                    except Exception as e:
                        print_color(
                            f"[Error] Failed to update config.json: {e}", Colors.RED)

                if saved_commit and git_root:
                    print_color(
                        f"\n[Rollback] Reverting changes to commit: {saved_commit}...", Colors.RED)
                    try:
                        subprocess.run(
                            ['git', 'reset', '--hard', saved_commit], cwd=git_root, check=True)
                        subprocess.run(['git', 'clean', '-fd'],
                                       cwd=git_root, check=True)
                        print_color(
                            "[Rollback] Successfully reverted local workspace.", Colors.GREEN)
                    except Exception as e:
                        print_color(
                            f"[Error] Rollback failed: {e}", Colors.RED)

                original_input = builtins.input

                def simulated_input(prompt=""):
                    prompt_str = str(prompt)
                    if "choose action" in prompt_str.lower() or "scenario" in prompt_str.lower():
                        print(prompt_str +
                              "1 (auto-selected due to failed verification)")

                        builtins.input = original_input
                        common._original_get_single_char = None
                        return "1"
                    return original_input(prompt)

                def simulated_get_single_char():
                    print("1 (auto-selected due to failed verification)")

                    builtins.input = original_input
                    common._original_get_single_char = None
                    return "1"

                builtins.input = simulated_input
                common._original_get_single_char = simulated_get_single_char

                print_color(
                    "[Info] Verification failed. Automated rollback complete. Returning to prompt generator selection...", Colors.YELLOW)

        os.chdir(original_cwd)
    except ImportError as e:
        print_color(
            f"[!] Failed to import apply_fix from {fix_bug_dir}: {e}", Colors.RED)
    except Exception as e:
        print_color(f"[!] Error applying fix: {e}", Colors.RED)
        if 'original_cwd' in locals():
            os.chdir(original_cwd)