import os
import sys
import argparse
from .full_instrumentation import run_full_instrumentation
from .sync_modified_files import sync_files


def run_instrumentation_mode(git_root, mode="full", project_file="current_project",
                             original_cwd=None):
    """
    Execute instrumentation task (full or incremental).

    Parameters
    ----------
    git_root : str
        Root directory of the target Git repository.
    mode : str
        "full" or "incremental".
    project_file : str
        Path to the project info JSON file.
    original_cwd : str, optional
        Original working directory, needed for incremental mode.
    """
    git_root_dir = os.path.abspath(git_root)
    project_file_path = os.path.abspath(project_file)
    if original_cwd is None:
        original_cwd = os.getcwd()

    if not os.path.isdir(git_root_dir):
        print(f"Error: Directory '{git_root_dir}' does not exist.")
        return False

    success = False
    try:
        print(f"\n>>> Starting code instrumentation in '{mode}' mode...")

        if mode == "full":
            success = run_full_instrumentation(git_root_dir, project_file_path, original_cwd)
            if not success:
                print("Error: Full instrumentation flow failed.")
        elif mode == "incremental":
            print("Notice: Incremental instrumentation is selected.")
            try:
                success = sync_files(project_file_path=project_file_path,
                                     original_cwd=original_cwd)
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
    parser.add_argument("git_root", help="Path to the root directory of the target Git project")
    parser.add_argument("--mode", choices=["full", "incremental"], default="full",
                        help="Instrumentation mode: full or incremental")
    parser.add_argument("--project-file", default="current_project",
                        help="Path to the project info JSON file (default: current_project)")

    args = parser.parse_args()
    run_instrumentation_mode(args.git_root, args.mode, args.project_file)


if __name__ == "__main__":
    main()