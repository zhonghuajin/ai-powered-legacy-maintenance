import os
import sys
import argparse
import subprocess
import json


def run_git_command(command):
    """Run a Git command and return the result."""
    try:
        result = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return True, result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return False, e.stderr.strip()


def run_script_command(command):
    """Run an external script command and print output directly to console for progress visibility."""
    try:
        subprocess.run(
            command,
            check=True,
            text=True
        )
        return True
    except subprocess.CalledProcessError as e:
        return False


def main():
    # Set up command line argument parsing
    parser = argparse.ArgumentParser(description="Create instrumentation branch, perform code instrumentation, and stash changes.")
    parser.add_argument("git_root", help="Path to the root directory of the target Git project")
    args = parser.parse_args()

    git_root_dir = os.path.abspath(args.git_root)
    branch_name = "shadow-project-for-instrumention"

    # Get the current working directory (the directory where quickstart.ps1 resides)
    original_cwd = os.getcwd()

    if not os.path.isdir(git_root_dir):
        print(f"Error: Directory '{git_root_dir}' does not exist.")
        sys.exit(1)

    source_branch = "unknown"

    try:
        # ==========================================
        # 1. Enter the specified Git root directory and handle branch logic
        # ==========================================
        print(f"Entering directory: {git_root_dir}")
        os.chdir(git_root_dir)

        is_git_repo, _ = run_git_command(
            ["git", "rev-parse", "--is-inside-work-tree"])
        if not is_git_repo:
            print(f"Error: '{git_root_dir}' is not a valid Git repository.")
            sys.exit(1)

        success, branch_out = run_git_command(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"])
        if success:
            source_branch = branch_out
            print(f"Current branch: {source_branch}")

        print(f"Checking if branch '{branch_name}' exists...")
        branch_exists, _ = run_git_command(
            ["git", "rev-parse", "--verify", branch_name])

        if source_branch == branch_name:
            print(f"Already on branch '{branch_name}', no need to switch.")
        elif branch_exists:
            print(f"Branch '{branch_name}' already exists, switching...")
            success, msg = run_git_command(["git", "checkout", branch_name])
            if not success:
                print(f"Failed to switch branch: {msg}")
                sys.exit(1)
        else:
            print(f"Branch '{branch_name}' does not exist, creating and switching...")
            success, msg = run_git_command(
                ["git", "checkout", "-b", branch_name])
            if not success:
                print(f"Failed to create branch: {msg}")
                sys.exit(1)

        # ==========================================
        # 2. Return to original working directory and write current_project
        # ==========================================
        os.chdir(original_cwd)
        output_file = "current_project"
        project_info = {
            "original_git_root": git_root_dir,
            "source_branch": source_branch
        }
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(project_info, f, indent=4, ensure_ascii=False)
        print(f"\nSuccessfully wrote project information to file: {os.path.abspath(output_file)}")

        # ==========================================
        # 3. Execute instrumentation
        # ==========================================
        print("\n>>> Starting code instrumentation...")
        target_folders_file = os.path.join(original_cwd, "target-folders.txt")

        # Construct PowerShell execution command
        ps_command = [
            "powershell.exe",
            "-ExecutionPolicy", "Bypass",
            "-File", ".\\run-instrumentation-demo.ps1",
            "-TargetFoldersFile", target_folders_file,
            "-SkipBuildAndTest"
        ]

        success = run_script_command(ps_command)
        if not success:
            print("Error: Instrumentation script execution failed.")
            sys.exit(1)
        print("Instrumentation completed.")

        # ==========================================
        # 4. Return to Git root directory and execute git stash
        # ==========================================
        print(f"\n>>> Returning to Git root directory to execute git stash: {git_root_dir}")
        os.chdir(git_root_dir)

        # Use -u flag to ensure untracked files generated during instrumentation are also stashed
        success, msg = run_git_command(["git", "stash", "-u"])
        if success:
            print(f"git stash successful:\n{msg}")
        else:
            print(f"git stash failed: {msg}")

    finally:
        # ==========================================
        # 5. Ensure return to the original working directory
        # ==========================================
        os.chdir(original_cwd)
        print(f"\n>>> Returned to original working directory: {original_cwd}")


if __name__ == "__main__":
    main()