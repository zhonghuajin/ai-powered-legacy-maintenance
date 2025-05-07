import os
import json
import subprocess
from .run_instrumentation_flow import run_instrumentation_flow


def run_git_command(command):
    try:
        result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return True, result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return False, e.stderr.strip()


def _remove_gitignore_if_exists(repo_root: str):
    """
    Remove .gitignore from the repository root if it exists.
    This is only called inside the shadow branch context to ensure
    instrumentation is not blocked by ignore rules.
    """
    gitignore_path = os.path.join(repo_root, '.gitignore')
    if os.path.isfile(gitignore_path):
        try:
            os.remove(gitignore_path)
            print(f'[Shadow Branch] Removed .gitignore: {gitignore_path}')
        except OSError as e:
            print(f'[Shadow Branch] Failed to remove .gitignore: {e}')
    else:
        print('[Shadow Branch] .gitignore not found, no action needed.')


def run_full_instrumentation(git_root_dir, original_cwd, proj_path=None):
    branch_name = "shadow-project-for-instrumention"
    print(f"Entering directory: {git_root_dir}")
    os.chdir(git_root_dir)

    is_git_repo, _ = run_git_command(["git", "rev-parse", "--is-inside-work-tree"])
    if not is_git_repo:
        print(f"Error: '{git_root_dir}' is not a valid Git repository.")
        return False

    success, source_branch = run_git_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if not success:
        return False
    print(f"Current branch: {source_branch}")

    print(f"Checking if branch '{branch_name}' exists...")
    branch_exists, _ = run_git_command(["git", "rev-parse", "--verify", branch_name])

    if source_branch == branch_name:
        print(f"Already on branch '{branch_name}', no need to switch.")
    elif branch_exists:
        print(f"Branch '{branch_name}' already exists, switching...")
        success, msg = run_git_command(["git", "checkout", branch_name])
        if not success:
            print(f"Failed to switch branch: {msg}")
            return False
    else:
        print(f"Branch '{branch_name}' does not exist, creating and switching...")
        success, msg = run_git_command(["git", "checkout", "-b", branch_name])
        if not success:
            print(f"Failed to create branch: {msg}")
            return False

    # At this point we are inside the shadow branch. Remove .gitignore if present.
    _remove_gitignore_if_exists(git_root_dir)

    # Record project info into config.json and retrieve language
    os.chdir(original_cwd)
    language = 'java'  # Default fallback
    if proj_path:
        config_path = os.path.join(proj_path, "config.json")
        config = {}
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                try:
                    config = json.load(f)
                    language = config.get("language", "java")  # Retrieve language
                except json.JSONDecodeError:
                    print(f"Warning: failed to parse {config_path}, overwriting.")
        config["original_git_root"] = git_root_dir
        config["source_branch"] = source_branch
        os.makedirs(proj_path, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
        print(f"Project info updated in: {config_path}")
    else:
        print("Warning: proj_path not provided, unable to save project info.")

    # Execute full instrumentation
    if proj_path:
        target_folders_file = os.path.join(proj_path, "target-folders.txt")
    else:
        target_folders_file = os.path.join(original_cwd, "target-folders.txt")

    # Pass the language parameter to the instrumentation flow
    success = run_instrumentation_flow(
        target_folders_file=target_folders_file, 
        language=language
    )

    if success:
        # Commit is delayed until dependencies are injected.
        # Display branch status without committing.
        print("\n" + "*" * 70)
        print("\033[1;31m" + "[ IMPORTANT NOTICE ]".center(64) + "\033[0m")
        print(f"\033[1;33mFor the Git project at: {git_root_dir}\033[0m")
        print(f"\033[1;33mYou are currently on branch: {branch_name}\033[0m")
        print("*" * 70 + "\n")

    return success


def commit_instrumentation(git_root_dir):
    """
    Commit all staged changes (instrumentation + dependency injection) on the shadow branch.
    If the previous commit is an auto-commit, amend it; otherwise create a new commit.
    """
    original_dir = os.getcwd()
    try:
        os.chdir(git_root_dir)
        print("\n>>> Committing instrumentation and dependency changes to shadow branch...")
        run_git_command(["git", "add", "."])

        _, last_commit_msg = run_git_command(["git", "log", "-1", "--pretty=%B"])
        if "Auto-commit: Code instrumentation" in last_commit_msg:
            print("Amending previous instrumentation commit...")
            run_git_command(["git", "commit", "--amend", "--no-edit"])
        else:
            print("Creating new unified instrumentation commit...")
            run_git_command(["git", "commit", "-m", "Auto-commit: Code instrumentation (incl. dependencies)"])

        print("[+] Commit completed.")
    finally:
        os.chdir(original_dir)