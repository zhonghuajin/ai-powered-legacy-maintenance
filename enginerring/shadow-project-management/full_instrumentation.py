import os
import sys
import json
import subprocess
from run_instrumentation_flow import run_instrumentation_flow

def run_git_command(command):
    try:
        result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return True, result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return False, e.stderr.strip()

def run_full_instrumentation(git_root_dir, project_file_path, original_cwd):
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

    # 记录 project info
    os.chdir(original_cwd)
    os.makedirs(os.path.dirname(project_file_path), exist_ok=True)
    project_info = {
        "original_git_root": git_root_dir,
        "source_branch": source_branch
    }
    with open(project_file_path, "w", encoding="utf-8") as f:
        json.dump(project_info, f, indent=4, ensure_ascii=False)
    
    print(f"\nSuccessfully wrote project information to file: {project_file_path}")

    # 执行全量插桩
    target_folders_file = os.path.join(original_cwd, "target-folders.txt")
    success = run_instrumentation_flow(target_folders_file=target_folders_file)
    
    if success:
        # 插桩完成后，在影子分支进行 commit
        os.chdir(git_root_dir)
        print("\nCommitting instrumentation changes to the shadow branch...")
        run_git_command(["git", "add", "."])
        
        # 检查最后一次 commit 是否是我们的插桩 commit
        _, last_commit_msg = run_git_command(["git", "log", "-1", "--pretty=%B"])
        if "Auto-commit: Code instrumentation" in last_commit_msg:
            print("Amending previous instrumentation commit...")
            run_git_command(["git", "commit", "--amend", "--no-edit"])
        else:
            print("Creating new instrumentation commit...")
            run_git_command(["git", "commit", "-m", "Auto-commit: Code instrumentation"])

        print("\n" + "*" * 70)
        print("\033[1;31m" + "【 IMPORTANT NOTICE 】".center(64) + "\033[0m")
        print(f"\033[1;33mFor the Git project at: {git_root_dir}\033[0m")
        print(f"\033[1;33mYou are currently on branch: {branch_name}\033[0m")
        print(f"\033[1;32mAll instrumentation changes have been committed to this shadow branch.\033[0m")
        print(f"\033[1;32mYou can safely switch back to ({source_branch}) anytime.\033[0m")
        print("*" * 70 + "\n")
        
    return success