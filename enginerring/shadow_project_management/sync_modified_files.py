import os
import sys
import json
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
from .run_instrumentation_flow import run_instrumentation_flow


def run_cmd(cmd, check=True):
    """Run shell command and return output"""
    print(f"Executing command: {' '.join(cmd)}")
    result = subprocess.run(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
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
    history_file = os.path.join(
        proj_path, "incremental-instrument-history.log")
    config_file = os.path.join(proj_path, "config.json")

    # Step 1: Append current target list to history log
    if os.path.isfile(target_file):
        with open(target_file, 'r', encoding='utf-8') as f:
            current_content = f.read().strip()
        if current_content:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            with open(history_file, 'a', encoding='utf-8') as f:
                f.write(f"\n{'='*40}\n")
                f.write(
                    f"{timestamp} Incremental instrumentation target files:\n")
                f.write(current_content + '\n')
            print(
                f"[Post-process] Appended target file list to {history_file}")
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
            print(
                "[Post-process] Warning: 'original-target-folders' in config.json is not a list, skip restore.")
    else:
        print(
            "[Post-process] Warning: config.json not found, cannot restore target-folders.txt.")


def get_llm_commit_message(proj_path, status_output, work_dir):
    """Generate a commit message using LLM based on the previous prompt context and git status."""
    default_msg = 'Auto-commit before incremental instrumentation'
    if not proj_path:
        return default_msg

    mapping_file = os.path.join(work_dir, 'last_prompt_context.json')
    if not os.path.exists(mapping_file):
        return default_msg

    try:
        with open(mapping_file, 'r', encoding='utf-8') as f:
            mapping_data = json.load(f)

        requirement = mapping_data.get("requirement", "")

        llm_prompt = f"""
        You are a senior developer. Please generate a concise and professional Git Commit Comment based on the following information (return only plain text, no quotes or extra explanations):
        1. Previous modification requirement: {requirement}
        2. Current Git status (modified files):
        {status_output}
        """

        ask_llm_dir = os.path.join(work_dir, 'enginerring', 'ask_llm')
        if ask_llm_dir not in sys.path:
            sys.path.insert(0, ask_llm_dir)
        from llm_chat import LLMClient

        provider = os.environ.get('AUTO_SELECTED_LLM_PROVIDER', 'deepseek')
        client = LLMClient(provider=provider)
        comment = client.chat(llm_prompt, stream=False).strip()

        if comment:
            return comment.strip('"').strip("'")
        return default_msg
    except Exception as e:
        print(f"[WARN] Failed to generate AI commit message: {e}")
        return default_msg


def sync_files(original_cwd, proj_path=None):
    """
    Synchronize modified files based on the project configuration.

    Parameters
    ----------
    original_cwd : str
        Original working directory before changing to git root.
    proj_path : str, optional
        Path to the isolated project directory. If provided,
        the configuration file (config.json) and target-folders.txt
        will be read/written there; otherwise original_cwd is used.
    """
    # Determine location of config.json
    base_dir = proj_path if proj_path else original_cwd
    config_file = Path(base_dir) / "config.json"

    if not config_file.exists():
        print(f"Error: Configuration file not found: {config_file}")
        return False

    with open(config_file, 'r', encoding='utf-8') as f:
        config = json.load(f)

    original_git_root = config.get("original_git_root")
    source_branch = config.get("source_branch")
    language = config.get("language", "java")  # Retrieve language

    if not original_git_root or not source_branch:
        print("Error: Missing original_git_root or source_branch in config.json")
        return False

    print(f"Retrieved Git root: {original_git_root}")
    print(f"Retrieved source branch: {source_branch}")

    os.chdir(original_git_root)
    print(f"Working directory changed to: {os.getcwd()}")

    # 1. Check if current branch is source_branch
    current_branch = run_cmd(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
    if current_branch != source_branch:
        print(
            f"Error: Current branch is '{current_branch}', but expected '{source_branch}'. Incremental sync aborted.")
        return False

    target_branch = "shadow-project-for-instrumention"

    # 2. Check for uncommitted changes and commit if any
    status_output = run_cmd(['git', 'status', '--porcelain'])
    has_uncommitted_changes = bool(status_output.strip())

    if has_uncommitted_changes:
        print("\n" + "!" * 70)
        print(
            "\033[1;31m" + "[ WARNING: UNCOMMITTED CHANGES DETECTED ]".center(64) + "\033[0m")
        print(
            f"\033[1;33mUncommitted changes found in branch '{source_branch}'. Executing 'git commit'...\033[0m")
        run_cmd(['git', 'add', '.'])

        # Use AI to generate commit message
        ai_commit_msg = get_llm_commit_message(
            proj_path, status_output, original_cwd)
        run_cmd(['git', 'commit', '-m', ai_commit_msg])

        print(
            "\033[1;31m" + f"YOUR CHANGES IN '{source_branch}' HAVE BEEN COMMITTED!".center(64) + "\033[0m")
        print("!" * 70 + "\n")

    # 3. Get truly user-modified files
    print("Calculating merge base to find actual modified files...")
    merge_base = run_cmd(['git', 'merge-base', 'HEAD', target_branch])
    diff_output = run_cmd(
        ['git', 'diff', '--name-only', f'{merge_base}..HEAD'])

    modified_files = set()
    for line in diff_output.splitlines():
        filepath = line.strip()
        if filepath:
            if filepath.startswith('"') and filepath.endswith('"'):
                filepath = filepath[1:-1]
            modified_files.add(filepath)

    if not modified_files:
        print("No modified files found compared to the base commit.")
        return "NO_MODIFIED_FILES"

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
    if proj_path:
        target_folders_file = os.path.join(proj_path, "target-folders.txt")
    else:
        target_folders_file = os.path.join(original_cwd, "target-folders.txt")
    with open(target_folders_file, 'w', encoding='utf-8') as f:
        for path in synced_absolute_paths:
            f.write(path + '\n')
    print(
        f"Saved {len(synced_absolute_paths)} absolute path(s) to {target_folders_file}.")

    # Switch back to original working directory to locate instrumentation jar
    os.chdir(original_cwd)
    print(f"Working directory changed back to: {os.getcwd()}")

    # 8. Execute incremental instrumentation
    print("Running instrumentation flow for synchronized files...")

    mapping_file = os.path.join(
        proj_path, "comment-mapping.txt") if proj_path else None
    if mapping_file and not os.path.isfile(mapping_file):
        print(
            f"Warning: Mapping file not found at {mapping_file}, continuing without it.")
        mapping_file = None

    # Pass the language parameter to the instrumentation flow
    success = run_instrumentation_flow(
        target_folders_file=target_folders_file,
        incremental=True,
        mapping_file=mapping_file,
        language=language
    )

    if success:
        print("\nCommitting incremental instrumentation changes to the shadow branch...")
        os.chdir(original_git_root)
        run_cmd(['git', 'add', '.'])
        print(f"Soft resetting shadow branch to match '{source_branch}'...")
        run_cmd(['git', 'reset', '--soft', source_branch])
        run_cmd(['git', 'commit', '-m', 'Auto-commit: Code instrumentation'])

        # Post-processing after successful incremental instrumentation
        if proj_path:
            _finalize_incremental_run(proj_path)

        print("\n" + "*" * 70)
        print("\033[1;32m" + "[ SUCCESS ]".center(64) + "\033[0m")
        print(
            f"\033[1;32mShadow branch is now exactly 1 commit ahead of '{source_branch}'.\033[0m")
        print("*" * 70 + "\n")
        print("All operations completed successfully!")
    else:
        print("Instrumentation flow failed during incremental sync.")

    return success
