import os
import sys
import json
import platform
import builtins
import importlib
import subprocess
import webbrowser  # Import built-in module for opening browser
from print_utils.utils import Colors, print_color
from . import common

def get_single_char_fallback():
    """
    Cross-platform single character reader function as a fallback.
    Used if get_single_char is not provided in the common module.
    """
    import sys
    if os.name == 'nt':
        import msvcrt
        # msvcrt.getch() returns bytes
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
                print_color(f"[Git Record] Saved current commit '{commit_id}' to config.json", Colors.GREEN)
            except Exception as e:
                print_color(f"[Git Warning] Failed to record git commit: {e}", Colors.YELLOW)

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
                print_color(f"[Git Warning] Failed to check git status: {e}", Colors.YELLOW)

        if has_changes:
            print_color("\n========================================", Colors.YELLOW)
            print_color(" Verification Required (Changes Detected) ", Colors.YELLOW)
            print_color("========================================", Colors.YELLOW)

            # Let user choose verification method
            print_color("Select verification method:", Colors.CYAN)
            print_color("[1] Run a project startup command in a new terminal", Colors.CYAN)
            print_color("[2] Open a URL in the browser (e.g., for Tomcat/Apache hot-reload)", Colors.CYAN)
            print_color("Press [1] or [2] to choose instantly...", Colors.YELLOW)

            # Prefer the single-character read function from common module, otherwise use fallback
            get_char_func = getattr(common, 'get_single_char', None) or getattr(common, '_original_get_single_char', None) or get_single_char_fallback

            choice = ""
            while choice not in ["1", "2"]:
                try:
                    choice = get_char_func()
                    if isinstance(choice, bytes):
                        choice = choice.decode('utf-8', errors='ignore')
                    choice = choice.strip()
                except Exception:
                    # Fallback to standard input() if single-character read fails
                    choice = input("Enter choice (1 or 2): ").strip()

            print_color(f"\n[Selected Option {choice}] Proceeding...", Colors.GREEN)

            run_verification = True
            process_to_wait = None

            if choice == "1":
                # Force user to enter startup command, empty values are not allowed
                cmd = ""
                while not cmd:
                    cmd = input("Enter the project startup command to verify changes: ").strip()
                    if not cmd:
                        print_color("[Warning] Startup command cannot be empty. Verification is mandatory.", Colors.YELLOW)

                print_color(f"[Info] Opening a new terminal window to execute: {cmd}", Colors.GREEN)
                current_os = platform.system()
                try:
                    if current_os == 'Windows':
                        process_to_wait = subprocess.Popen(f'start cmd /k "{cmd}"', shell=True, cwd=git_root)
                    elif current_os == 'Darwin':
                        applescript = f'tell application "Terminal" to do script "cd {git_root} && {cmd}"'
                        process_to_wait = subprocess.Popen(['osascript', '-e', applescript])
                    else:
                        process_to_wait = subprocess.Popen(['x-terminal-emulator', '-e', f'sh -c "cd {git_root} && {cmd}; exec sh"'])
                except Exception as e:
                    print_color(f"[Error] Failed to launch terminal window: {e}", Colors.RED)

            elif choice == "2":
                # Force user to enter the URL
                url = ""
                while not url:
                    url = input("Enter the URL to open in browser (e.g., http://localhost:8080): ").strip()
                    if not url:
                        print_color("[Warning] URL cannot be empty.", Colors.YELLOW)
                
                # Prepend protocol header if missing
                if not url.startswith(("http://", "https://")):
                    url = "http://" + url

                print_color(f"[Info] Opening browser to: {url}", Colors.GREEN)
                try:
                    webbrowser.open(url)
                except Exception as e:
                    print_color(f"[Error] Failed to open browser: {e}", Colors.RED)

            if run_verification:
                if choice == "1" and process_to_wait:
                    print_color("[Info] Waiting for the terminal window to close...", Colors.YELLOW)
                    process_to_wait.wait()
                else:
                    # If opening a browser, or if terminal process cannot be awaited, let user press Enter manually
                    input("Press Enter once you have finished verification in your browser/terminal...")

                satisfied = input("\nDid the code fix meet your expectations? (yes/no): ").strip().lower()
                if satisfied in ['yes', 'y']:
                    print_color("[Success] Verification passed! Proceeding to next step.", Colors.GREEN)
                    
                    # Reset the state so that the workflow runs normally
                    if config_path and os.path.exists(config_path):
                        try:
                            with open(config_path, "r", encoding="utf-8") as f:
                                config_data = json.load(f)
                            config_data["skip_log_and_manager"] = False
                            with open(config_path, "w", encoding="utf-8") as f:
                                json.dump(config_data, f, indent=4)
                        except Exception as e:
                            print_color(f"[Error] Failed to update config.json: {e}", Colors.RED)
                else:
                    # Set the state to True to skip Manager Server and Log Analysis on subsequent iterations
                    if config_path and os.path.exists(config_path):
                        try:
                            with open(config_path, "r", encoding="utf-8") as f:
                                config_data = json.load(f)
                            config_data["skip_log_and_manager"] = True
                            with open(config_path, "w", encoding="utf-8") as f:
                                json.dump(config_data, f, indent=4)
                        except Exception as e:
                            print_color(f"[Error] Failed to update config.json: {e}", Colors.RED)

                    if saved_commit and git_root:
                        print_color(f"\n[Rollback] Reverting changes to commit: {saved_commit}...", Colors.RED)
                        try:
                            subprocess.run(['git', 'reset', '--hard', saved_commit], cwd=git_root, check=True)
                            subprocess.run(['git', 'clean', '-fd'], cwd=git_root, check=True)
                            print_color("[Rollback] Successfully reverted local workspace.", Colors.GREEN)
                        except Exception as e:
                            print_color(f"[Error] Rollback failed: {e}", Colors.RED)

                    original_input = builtins.input

                    def simulated_input(prompt=""):
                        prompt_str = str(prompt)
                        if "choose action" in prompt_str.lower() or "scenario" in prompt_str.lower():
                            print(prompt_str + "1 (auto-selected due to failed verification)")

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

                    print_color("[Info] Verification failed. Automated rollback complete. Returning to prompt generator selection...", Colors.YELLOW)

        os.chdir(original_cwd)
    except ImportError as e:
        print_color(
            f"[!] Failed to import apply_fix from {fix_bug_dir}: {e}", Colors.RED)
    except Exception as e:
        print_color(f"[!] Error applying fix: {e}", Colors.RED)
        if 'original_cwd' in locals():
            os.chdir(original_cwd)