import os
import sys
import subprocess
import json
import argparse
from .full_instrumentation import run_full_instrumentation
from .sync_modified_files import sync_files
from print_utils.utils import Colors, print_color


def run_block_wrapper_tool(work_dir, proj_path, git_root):
    """
    Check for modified files in the current git branch.
    Run the BlockWrapperTool for the respective language.
    If the tool modifies files and there were no prior modifications, commit the changes.
    """
    if not proj_path or not git_root:
        return

    config_file = os.path.join(proj_path, 'config.json')
    target_file = os.path.join(proj_path, 'target-folders.txt')
    language = 'java'

    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                language = json.load(f).get('language', 'java').lower()
        except Exception as e:
            print_color(
                f"[WARN] Could not read config for language: {e}", Colors.YELLOW)

    targets = []
    if os.path.exists(target_file):
        try:
            with open(target_file, 'r', encoding='utf-8') as f:
                targets = [line.strip() for line in f if line.strip()
                           and not line.startswith('#')]
        except Exception as e:
            print_color(
                f"[WARN] Could not read target folders: {e}", Colors.YELLOW)

    if not targets:
        return

    try:
        status_cmd = ['git', '-C', git_root, 'status', '--porcelain']
        pre_status = subprocess.run(
            status_cmd, capture_output=True, text=True, check=True).stdout.strip()
        has_modified_before = bool(pre_status)
    except subprocess.CalledProcessError as e:
        print_color(f"[WARN] Failed to get git status: {e}", Colors.YELLOW)
        return

    for target in targets:
        cmd = []
        if language == 'php':
            script_path = os.path.join(
                work_dir, 'multilingual', 'php', 'block-wrapper', 'BlockWrapperTool.php')
            cmd = ['php', script_path, target]
        elif language in ['javascript', 'js']:
            script_path = os.path.join(
                work_dir, 'multilingual', 'javascript', 'block-wrapper', 'BlockWrapperTool.js')
            cmd = ['node', script_path, target]
        elif language == 'java':
            jar_path = os.path.join(work_dir, 'multilingual', 'java', 'block-wrapper',
                                    'target', 'javaparser-block-wrapper-1.0-SNAPSHOT.jar')
            cmd = ['java', '-jar', jar_path, target]
        else:
            continue

        print_color(
            f">>> Running BlockWrapperTool for {language}: {' '.join(cmd)}", Colors.CYAN)
        try:
            subprocess.run(cmd, check=False)
        except Exception as e:
            print_color(
                f"[WARN] Failed to execute BlockWrapperTool: {e}", Colors.YELLOW)

    if not has_modified_before:
        try:
            post_status = subprocess.run(
                status_cmd, capture_output=True, text=True, check=True).stdout.strip()
            if post_status:
                print_color(
                    ">>> BlockWrapperTool modified files. Committing changes...", Colors.YELLOW)
                subprocess.run(['git', '-C', git_root, 'commit', '-a', '-m',
                               'Auto-commit: BlockWrapperTool modifications'], check=True)
        except subprocess.CalledProcessError as e:
            print_color(
                f"[WARN] Failed to commit BlockWrapperTool changes: {e}", Colors.YELLOW)


def run_instrumentation_mode(git_root, mode="full", original_cwd=None, proj_path=None):
    """
    Execute instrumentation task (full or incremental).

    Parameters
    ----------
    git_root : str
        Root directory of the target Git repository.
    mode : str
        "full" or "incremental".
    original_cwd : str, optional
        Original working directory, needed for incremental mode.
    proj_path : str, optional
        Path to the isolated project directory containing target-folders.txt and config.json.
    """
    git_root_dir = os.path.abspath(git_root)
    if original_cwd is None:
        original_cwd = os.getcwd()

    if not os.path.isdir(git_root_dir):
        print(f"Error: Directory '{git_root_dir}' does not exist.")
        return False

    success = False
    try:
        print(f"\n>>> Starting code instrumentation in '{mode}' mode...")

        # Prepare common path for mapping file (may be used by both modes)
        mapping_file = os.path.join(
            proj_path, "block-line-mapping.txt") if proj_path else None

        if mode == "full":
            # Execute BlockWrapperTool before instrumentation
            if proj_path and git_root_dir:
                run_block_wrapper_tool(original_cwd, proj_path, git_root_dir)

            success = run_full_instrumentation(
                git_root_dir, original_cwd, proj_path)
            if not success:
                print("Error: Full instrumentation flow failed.")
        elif mode == "incremental":
            print("Notice: Incremental instrumentation is selected.")
            try:
                # The sync_files function now handles incremental mode and mapping file
                # internally (see its updated implementation). No extra args needed here.
                success = sync_files(
                    original_cwd=original_cwd, proj_path=proj_path)
            except Exception as e:
                print(f"Error: Incremental sync failed with exception: {e}")
                success = False
            if not success:
                print("Error: Incremental instrumentation flow failed.")
        else:
            print(f"Unknown mode: {mode}")
            return False

        if success:
            print("Instrumentation completed.")
        return success
    finally:
        os.chdir(original_cwd)


def main():
    # Command-line entry point (optional, for manual invocation)
    parser = argparse.ArgumentParser(
        description="Create instrumentation branch, perform code instrumentation, and stash changes."
    )
    parser.add_argument(
        "git_root", help="Path to the root directory of the target Git project")
    parser.add_argument("--mode", choices=["full", "incremental"], default="full",
                        help="Instrumentation mode: full or incremental")
    # The --project-file argument has been removed because project info is now stored in config.json

    args = parser.parse_args()
    run_instrumentation_mode(args.git_root, args.mode)


if __name__ == "__main__":
    main()
