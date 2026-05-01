import os
import sys
import argparse
from .full_instrumentation import run_full_instrumentation
from .sync_modified_files import sync_files


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
        mapping_file = os.path.join(proj_path, "comment-mapping.txt") if proj_path else None

        if mode == "full":
            success = run_full_instrumentation(git_root_dir, original_cwd, proj_path)
            if not success:
                print("Error: Full instrumentation flow failed.")
        elif mode == "incremental":
            print("Notice: Incremental instrumentation is selected.")
            try:
                # The sync_files function now handles incremental mode and mapping file
                # internally (see its updated implementation). No extra args needed here.
                success = sync_files(original_cwd=original_cwd, proj_path=proj_path)
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
    # The --project-file argument has been removed because project info is now stored in config.json

    args = parser.parse_args()
    run_instrumentation_mode(args.git_root, args.mode)


if __name__ == "__main__":
    main()