import os
import json
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
from .run_instrumentation_flow import run_instrumentation_flow


def run_cmd(cmd, check=True):
    """Run shell command and return output"""
    print(f"Executing command: {' '.join(cmd)}")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if check and result.returncode != 0:
        print(f"Command failed: {result.stderr}")
        result.check_returncode()
    return result.stdout.strip()


def _finalize_incremental_run(proj_path):
    """
    After incremental instrumentation succeeds, append the content of
    target-folders.txt to incremental-instrument-history.log, then restore
    target-folders.txt from the 'target-folders' field in config.json.
    """
    target_file = os.path.join(proj_path, "target-folders.txt")
    history_file = os.path.join(proj_path, "incremental-instrument-history.log")
    config_file = os.path.join(proj_path, "config.json")

    # Step 1: Append current target list to history log
    if os.path.isfile(target_file):
        with open(target_file, 'r', encoding='utf-8') as f:
            current_content = f.read().strip()
        if current_content:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            with open(history_file, 'a', encoding='utf-8') as f:
                f.write(f"\n{'='*40}\n")
                f.write(f"{timestamp} Incremental instrumentation target files:\n")
                f.write(current_content + '\n')
            print(f"[Post-process] Appended target file list to {history_file}")
    else:
        print("[Post-process] target-folders.txt not found, skip history append.")

    # Step 2: Restore target-folders.txt from config.json
    if os.path.isfile(config_file):
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        original_targets = config.get('original-target-folders', [])
        if isinstance(original_targets, list):
            with open(target_file, 'w', encoding='utf-8') as f:
                for folder in original_targets:
                    f.write(folder + '\n')
            print(f"[Post-process] Restored target-folders.txt from config.json")
        else:
            print("[Post-process] Warning: 'original-target-folders' in config.json is not a list, skip restore.")
    else:
        print("[Post-process] Warning: config.json not found, cannot restore target-folders.txt.")


def sync_files(project_file_path, original_cwd, proj_path=None):
    """
    Synchronize modified files based on the project configuration.

    Parameters
    ----------
    project_file_path : str
        Path to the current_project JSON file.
    original_cwd : str
        Original working directory before changing to git root.
    proj_path : str, optional
        Path to the isolated project directory. If provided,
        target-folders.txt will be written there instead of original_cwd.
    """
    if project_file_path is None:
        print("Error: project_file_path cannot be None.")
        return False

    current_project_file = Path(project_file_path)
    if not current_project_file.exists():
        print(f"Error: File not found: {current_project_file}")
        return False

    with open(current_project_file, 'r', encoding='utf-8') as f:
        config = json.load(f)

    original_git_root = config.get("original_git_root")
    source_branch = config.get("source_branch")

    if not original_git_root or not source_branch:
        print("Error: Missing original_git_root or source_branch in current_project file")
        return False

    print(f"Retrieved Git root: {original_git_root}")
    print(f"Retrieved source branch: {source_branch}")

    os.chdir(original_git_root)
    print(f"Working directory changed to: {os.getcwd()}")

    # 1. Check if current branch is source_branch
    current_branch = run_cmd(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
    if current_branch != source_branch:
        print(f"Error: Current branch is '{current_branch}', but expected '{source_branch}'. Incremental sync aborted.")
        return False

    target_branch = "shadow-project-for-instrumention"

    # 2. Check for uncommitted changes and commit if any
    status_output = run_cmd(['git', 'status', '--porcelain'])
    has_uncommitted_changes = bool(status_output.strip())
    
    if has_uncommitted_changes:
        print("\n" + "!" * 70)
        print("\033[1;31m" + "[ WARNING: UNCOMMITTED CHANGES DETECTED ]".center(64) + "\033[0m")
        print(f"\033[1;33mUncommitted changes found in branch '{source_branch}'. Executing 'git commit'...\033[0m")
        run_cmd(['git', 'add', '.'])
        run_cmd(['git', 'commit', '-m', 'Auto-commit before incremental instrumentation'])
        print("\033[1;31m" + f"YOUR CHANGES IN '{source_branch}' HAVE BEEN COMMITTED!".center(64) + "\033[0m")
        print("!" * 70 + "\n")

    # 3. Get truly user-modified files
    print("Calculating merge base to find actual modified files...")
    merge_base = run_cmd(['git', 'merge-base', 'HEAD', target_branch])
    diff_output = run_cmd(['git', 'diff', '--name-only', f'{merge_base}..HEAD'])

    modified_files = set()
    for line in diff_output.splitlines():
        filepath = line.strip()
        if filepath:
            if filepath.startswith('"') and filepath.endswith('"'):
                filepath = filepath[1:-1]
            modified_files.add(filepath)

    if not modified_files:
        print("No modified files found compared to the base commit.")
        return True

    print(f"Found {len(modified_files)} modified file(s).")

    # 4. Backup modified files to ~/modified
    user_home = Path.home()
    modified_dir = user_home / "modified"
    if not modified_dir.exists():
        modified_dir.mkdir(parents=True)

    for file_rel_path in modified_files:
        src_file = Path(original_git_root) / file_rel_path
        if not src_file.is_file():
            continue
        dst_file = modified_dir / file_rel_path
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dst_file)
        print(f"Backed up: {file_rel_path} -> {dst_file}")

    # 5. Switch to shadow-project-for-instrumention branch
    run_cmd(['git', 'checkout', target_branch])

    # 6. Restore files to current shadow branch
    print("Starting to overwrite files in shadow branch...")
    synced_absolute_paths = []
    for file_rel_path in modified_files:
        src_file = modified_dir / file_rel_path
        if not src_file.is_file():
            continue
        dst_file = Path(original_git_root) / file_rel_path
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dst_file)
        synced_absolute_paths.append(str(dst_file.resolve()))
        print(f"Restored: {src_file} -> {dst_file}")

    # 7. Save absolute paths to target-folders.txt
    # Modified: use proj_path if provided, matching full instrumentation behavior
    if proj_path:
        target_folders_file = os.path.join(proj_path, "target-folders.txt")
    else:
        target_folders_file = os.path.join(original_cwd, "target-folders.txt")
    with open(target_folders_file, 'w', encoding='utf-8') as f:
        for path in synced_absolute_paths:
            f.write(path + '\n')
    print(f"Saved {len(synced_absolute_paths)} absolute path(s) to {target_folders_file}.")

    # Switch back to original working directory to locate instrumentation jar
    os.chdir(original_cwd)
    print(f"Working directory changed back to: {os.getcwd()}")

    # 8. Execute incremental instrumentation
    print("Running instrumentation flow for synchronized files...")
    success = run_instrumentation_flow(target_folders_file=target_folders_file)
    
    if success:
        print("\nCommitting incremental instrumentation changes to the shadow branch...")
        os.chdir(original_git_root)
        run_cmd(['git', 'add', '.'])
        print(f"Soft resetting shadow branch to match '{source_branch}'...")
        run_cmd(['git', 'reset', '--soft', source_branch])
        run_cmd(['git', 'commit', '-m', 'Auto-commit: Code instrumentation'])
        
        # NEW: Post-processing after successful incremental instrumentation
        if proj_path:
            _finalize_incremental_run(proj_path)

        print("\n" + "*" * 70)
        print("\033[1;32m" + "[ SUCCESS ]".center(64) + "\033[0m")
        print(f"\033[1;32mShadow branch is now exactly 1 commit ahead of '{source_branch}'.\033[0m")
        print("*" * 70 + "\n")
        print("All operations completed successfully!")
    else:
        print("Instrumentation flow failed during incremental sync.")

    return success