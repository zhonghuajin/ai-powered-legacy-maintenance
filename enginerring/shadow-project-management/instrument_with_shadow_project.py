import os
import sys
import argparse
from full_instrumentation import run_full_instrumentation
from sync_modified_files import sync_files

def main():
    parser = argparse.ArgumentParser(description="Create instrumentation branch, perform code instrumentation, and stash changes.")
    parser.add_argument("git_root", help="Path to the root directory of the target Git project")
    parser.add_argument("--mode", choices=["full", "incremental"], default="full", help="Instrumentation mode: full or incremental")
    parser.add_argument("--project-file", default="current_project", help="Path to the project info JSON file (default: current_project)")
    
    args = parser.parse_args()

    git_root_dir = os.path.abspath(args.git_root)
    inst_mode = args.mode
    project_file_path = os.path.abspath(args.project_file)
    original_cwd = os.getcwd()

    if not os.path.isdir(git_root_dir):
        print(f"Error: Directory '{git_root_dir}' does not exist.")
        sys.exit(1)

    try:
        print(f"\n>>> Starting code instrumentation in '{inst_mode}' mode...")
        
        if inst_mode == "full":
            success = run_full_instrumentation(git_root_dir, project_file_path, original_cwd)
            if not success:
                print("Error: Full instrumentation flow failed.")
                sys.exit(1)
                
        elif inst_mode == "incremental":
            print("Notice: Incremental instrumentation is selected.")
            try:
                success = sync_files(project_file_path=project_file_path)
            except Exception as e:
                print(f"Error: Incremental sync failed with exception: {e}")
                success = False
            
            if not success:
                print("Error: Incremental instrumentation flow failed.")
                sys.exit(1)
            
        print("Instrumentation completed.")

    finally:
        os.chdir(original_cwd)
        print(f"\n>>> Returned to original working directory: {original_cwd}")

if __name__ == "__main__":
    main()