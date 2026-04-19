import os
import sys
import argparse
import subprocess
import json

# Import the instrumentation flow from the renamed standalone module
from run_instrumentation_flow import run_instrumentation_flow


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


def main():
    # Set up command line argument parsing
    parser = argparse.ArgumentParser(description="Create instrumentation branch, perform code instrumentation, and stash changes.")
    parser.add_argument("git_root", help="Path to the root directory of the target Git project")
    # Add --mode argument to support full and incremental instrumentation
    parser.add_argument("--mode", choices=["full", "incremental"], default="full", help="Instrumentation mode: full or incremental")
    args = parser.parse_args()

    git_root_dir = os.path.abspath(args.git_root)
    inst_mode = args.mode
    branch_name = "shadow-project-for-instrumention"

    # Get the current working directory
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
        # 3. Execute instrumentation (Imported Pure Python function)
        # ==========================================
        print(f"\n>>> Starting code instrumentation in '{inst_mode}' mode...")
        target_folders_file = os.path.join(original_cwd, "target-folders.txt")

        if inst_mode == "full":
            # Call the imported Python function for full instrumentation
            success = run_instrumentation_flow(
                target_folders_file=target_folders_file, 
                skip_build_and_test=True
            )
            
            if not success:
                print("Error: Full instrumentation flow failed.")
                sys.exit(1)
                
        elif inst_mode == "incremental":
            # Placeholder for incremental instrumentation
            print("Notice: Incremental instrumentation is selected.")
            print("TODO: Implement incremental instrumentation logic here.")
            # Assume success to prevent the script from exiting prematurely
            success = True 
            
            if not success:
                print("Error: Incremental instrumentation flow failed.")
                sys.exit(1)
            
        print("Instrumentation completed.")

        # ==========================================
        # Important user notice
        # ==========================================
        print("\n" + "*" * 70)
        print("\033[1;31m" + "【 IMPORTANT NOTICE 】".center(64) + "\033[0m")
        print(f"\033[1;33mFor the Git project at: {git_root_dir}\033[0m")
        print(f"\033[1;33mYou are currently on branch: {branch_name}\033[0m")
        print(f"\033[1;32mIf you need to switch back to the original branch ({source_branch}), "
              f"please run the following command first:\033[0m\033[1;31m git stash\033[0m")
        print("*" * 70 + "\n")

    finally:
        # ==========================================
        # 5. Ensure return to the original working directory
        # ==========================================
        os.chdir(original_cwd)
        print(f"\n>>> Returned to original working directory: {original_cwd}")


if __name__ == "__main__":
    main()