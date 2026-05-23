import os
import sys
import json
import platform
import builtins
import importlib
import subprocess
from print_utils.utils import Colors, print_color
from . import common

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
            print_color(" Verification Options (Changes Detected) ", Colors.YELLOW)
            print_color("========================================", Colors.YELLOW)
            print("  1. Enter project startup command and verify")
            print("  2. Skip verification")
            print_color("========================================", Colors.YELLOW)

            # 直接引用 common.get_single_char()，并即时回显用户按下的键
            print("Enter your choice (1-2): ", end="", flush=True)
            choice = common.get_single_char().strip()
            print(choice)  # 打印按下的字符并换行

            run_verification = False
            process_to_wait = None

            if choice == '1':
                cmd = input("Enter the project startup command: ").strip()
                if cmd:
                    run_verification = True
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

            if run_verification:
                if process_to_wait:
                    print_color("[Info] Waiting for the terminal window to close...", Colors.YELLOW)
                    process_to_wait.wait()
                else:
                    input("Press Enter once you have finished verification...")

                satisfied = input("\nDid the code fix meet your expectations? (yes/no): ").strip().lower()
                if satisfied in ['yes', 'y']:
                    print_color("[Success] Verification passed! Proceeding to next step.", Colors.GREEN)
                else:
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