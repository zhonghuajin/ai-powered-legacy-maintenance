# project_manager.py
"""Project creation and selection logic, including target folder management."""

import os
import sys
import re
import json
import subprocess
import shutil
from print_utils.utils import Colors, print_color


def create_or_select_project(work_dir):
    """
    Step: Create or select an existing project.
    After selection/creation, prompt the user to specify target folders/files.
    Returns the project directory (proj_path) and git repository root directory (root_path).
    """
    projects_dir = os.path.join(work_dir, "projects")
    os.makedirs(projects_dir, exist_ok=True)

    # Gather existing projects (subdirectories with valid config.json)
    existing_projects = []
    if os.path.isdir(projects_dir):
        for entry in os.listdir(projects_dir):
            proj_path = os.path.join(projects_dir, entry)
            if os.path.isdir(proj_path):
                config_file = os.path.join(proj_path, "config.json")
                if os.path.isfile(config_file):
                    try:
                        with open(config_file, "r", encoding="utf-8") as f:
                            cfg = json.load(f)
                        root_path = cfg.get("original_git_root", "")
                        existing_projects.append((entry, root_path, proj_path))
                    except Exception:
                        # Ignore invalid config files
                        pass

    # If no projects exist, force creation of a new one
    if not existing_projects:
        print_color(
            "No existing projects found. Let's create a new one.", Colors.CYAN)
        proj_path, root_path = _create_new_project(work_dir, projects_dir)
    else:
        proj_path, root_path = _select_or_create_project(
            work_dir, projects_dir, existing_projects
        )

    # Manage target folders for the selected/created project
    _manage_target_folders(proj_path)

    return proj_path, root_path


def _select_or_create_project(work_dir, projects_dir, existing_projects):
    """
    Display existing projects and let the user pick one or create a new project.
    Returns (proj_path, root_path).
    """
    print_color("\n=== Existing Projects ===", Colors.CYAN)
    for idx, (name, root, _) in enumerate(existing_projects, start=1):
        print(f"  {idx}. {name}  ->  {root}")
    print(f"  {len(existing_projects) + 1}. Create a new project")

    while True:
        try:
            choice = input(
                "Select a project number or choose to create a new one: ").strip()
            if choice.isdigit():
                num = int(choice)
                if 1 <= num <= len(existing_projects):
                    selected_name, selected_root, selected_proj_path = existing_projects[num - 1]
                    print_color(
                        f"Selected project: {selected_name} (root: {selected_root})",
                        Colors.GREEN,
                    )
                    return selected_proj_path, selected_root
                elif num == len(existing_projects) + 1:
                    return _create_new_project(work_dir, projects_dir)
                else:
                    print_color("Invalid choice. Try again.", Colors.RED)
            else:
                print_color("Please enter a number.", Colors.RED)
        except KeyboardInterrupt:
            print("\nOperation cancelled.")
            sys.exit(1)


def _create_new_project(work_dir, projects_dir):
    """
    Helper to create a new project.
    Returns (proj_path, root_path).
    """
    print_color("\n--- Create a New Project ---", Colors.CYAN)
    # Validate project name
    while True:
        name = input(
            "Enter a project name (English letters, digits, hyphens, underscores allowed): "
        ).strip()
        if not name:
            print_color("Project name cannot be empty.", Colors.RED)
            continue
        # Check for Unicode range - rejected with English message
        if re.search(r'[\u4e00-\u9fff]', name):
            print_color(
                "Non-English characters are not allowed. Please use English.", Colors.RED)
            continue
        if not re.match(r'^[a-zA-Z0-9_\-\.]+$', name):
            print_color(
                "Only letters, digits, hyphens, underscores and dots are allowed.", Colors.RED
            )
            continue
        # Check if project already exists
        proj_path = os.path.join(projects_dir, name)
        if os.path.exists(proj_path):
            print_color(
                f"Project '{name}' already exists. Please choose a different name.", Colors.RED
            )
            continue
        break

    git_root = ""
    while not git_root:
        git_root = input(
            "Please enter the Git repository root directory of the project: ").strip()
        if not git_root:
            print_color("Path cannot be empty.", Colors.RED)
        elif not os.path.isdir(git_root):
            print_color(
                "The specified directory does not exist. Please enter a valid path.", Colors.RED
            )
            git_root = ""
        else:
            git_root = os.path.abspath(git_root)

    # Create project folder and config.json
    proj_path = os.path.join(projects_dir, name)
    os.makedirs(proj_path, exist_ok=True)
    config = {"original_git_root": git_root}
    config_path = os.path.join(proj_path, "config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

    print_color(
        f"Project '{name}' created successfully with root: {git_root}", Colors.GREEN)
    return proj_path, git_root


# ---------------------------------------------------------------------------
# Target folder management
# ---------------------------------------------------------------------------

def _sync_config_original_targets(proj_path, paths):
    """
    Synchronize the target paths to the config.json file under 'original-target-folders'.
    """
    config_path = os.path.join(proj_path, "config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)

            config_data["original-target-folders"] = paths

            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=4)
        except Exception as e:
            print_color(
                f"Failed to update config.json with original-target-folders: {e}", Colors.RED)


def _manage_target_folders(proj_path):
    """
    Prompt the user to specify target folders/files for the project.
    Saves results to target-folders.txt in the project directory.
    If the file already has entries, the user can keep, replace, or edit them.
    """
    target_file = os.path.join(proj_path, "target-folders.txt")
    existing_paths = _read_target_folders(target_file)

    # If entries already exist, ask the user what to do
    if existing_paths:
        print_color(
            f"\nCurrent target paths ({len(existing_paths)} entries):", Colors.CYAN
        )
        for p in existing_paths:
            print(f"  - {p}")
        print()
        print("  k - Keep current targets and continue")
        print("  r - Replace with new targets")
        print("  a - Append more targets")
        choice = input("Choose an action [k]: ").strip().lower() or "k"
        if choice == "k":
            print_color("Keeping existing target paths.", Colors.GREEN)
            _sync_config_original_targets(proj_path, existing_paths)
            return
        elif choice == "a":
            new_paths = _prompt_target_input(target_file)
            if new_paths:
                combined = existing_paths + new_paths
                _write_target_folders(target_file, combined)
                _sync_config_original_targets(proj_path, combined)
                print_color(
                    f"Saved {len(combined)} target path(s) to: {target_file}", Colors.GREEN
                )
            else:
                print_color(
                    "No new paths added. Keeping existing targets.", Colors.YELLOW)
                _sync_config_original_targets(proj_path, existing_paths)
            return
        # choice == "r" falls through to fresh input below

    # Fresh input (no existing entries, or user chose to replace)
    paths = _prompt_target_input(target_file)
    if paths:
        _write_target_folders(target_file, paths)
        _sync_config_original_targets(proj_path, paths)
        print_color(
            f"Saved {len(paths)} target path(s) to: {target_file}", Colors.GREEN)
    else:
        print_color(
            "No target paths specified. You can edit the file later:", Colors.YELLOW)
        print_color(f"  {target_file}", Colors.YELLOW)


def _prompt_target_input(target_file):
    """
    Let the user choose between interactive input or opening an editor,
    then collect and return a list of paths.
    """
    print_color(
        "\nHow would you like to specify target folders/files?", Colors.CYAN)
    print("  1. Type or drag-and-drop paths in terminal (recommended)")
    print("  2. Open in a text editor")
    method = input("Choose method [1]: ").strip() or "1"

    if method == "2":
        return _collect_paths_editor(target_file)
    else:
        return _collect_paths_multiline()


def _collect_paths_multiline():
    """
    Collect file/folder paths interactively, one per line.
    The user can drag files from a file manager into the terminal.
    An empty line signals the end of input.
    Returns a list of validated absolute paths.
    """
    print_color("\nEnter target file/folder paths, one per line.", Colors.CYAN)
    print_color(
        "  Tip: You can drag files/folders from your file manager into the terminal.", Colors.YELLOW)
    print_color(
        "  Press Enter on an empty line to finish. Type 'q' to cancel.\n", Colors.YELLOW)

    paths = []
    while True:
        try:
            line = input(f"  [{len(paths) + 1}] > ").strip()
        except KeyboardInterrupt:
            print("\nInput cancelled.")
            return paths

        # Strip surrounding quotes that drag-and-drop may produce
        line = line.strip("'\"")

        if not line:
            if paths:
                break
            print_color(
                "  Please enter at least one path (or 'q' to cancel).", Colors.RED)
            continue

        if line.lower() == "q":
            return paths

        if not os.path.exists(line):
            print_color(f"  WARNING: Path does not exist: {line}", Colors.RED)
            confirm = input("  Add it anyway? [y/N]: ").strip().lower()
            if confirm not in ("y", "yes"):
                continue

        abs_path = os.path.abspath(line)
        if abs_path in paths:
            print_color(f"  Duplicate skipped: {abs_path}", Colors.YELLOW)
            continue

        paths.append(abs_path)
        print_color(f"  Added: {abs_path}", Colors.GREEN)

    return paths


def _collect_paths_editor(target_file):
    """
    Open target-folders.txt in the user's preferred editor.
    After the editor closes, read back the paths from the file.
    Returns a list of paths.
    """
    template = (
        "# Enter target file or folder paths, one per line.\n"
        "# Lines starting with '#' are treated as comments and ignored.\n"
        "# Blank lines are ignored.\n"
        "#\n"
        "# Examples:\n"
        "#   /home/user/project/src/main/java\n"
        "#   /home/user/project/src/main/java/com/example/App.java\n"
        "#   C:\\Users\\user\\project\\src\n"
        "\n"
    )

    # Write template only if the file does not already exist or is empty
    if not os.path.isfile(target_file) or os.path.getsize(target_file) == 0:
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(template)

    editor = _detect_editor()

    # Important instructions before opening the editor
    print_color(
        "\n*****************************************************************", Colors.YELLOW)
    print_color("  IMPORTANT: Please read before editing!", Colors.RED)
    print_color(
        "*****************************************************************", Colors.YELLOW)
    print_color("  - Enter one file or folder path per line.", Colors.CYAN)
    print_color(
        "  - Lines starting with '#' are comments and will be IGNORED.", Colors.CYAN)
    print_color("  - Blank lines will also be ignored.", Colors.CYAN)
    print_color(
        "  - Only plain path lines will be saved as targets.", Colors.CYAN)
    print_color(
        "*****************************************************************", Colors.YELLOW)
    print_color(f"  Editor : {editor}", Colors.GREEN)
    print_color(f"  File   : {target_file}", Colors.GREEN)
    print_color(
        "*****************************************************************", Colors.YELLOW)
    print_color(
        "  Save the file and close the editor to continue.", Colors.YELLOW)
    print_color(
        "*****************************************************************\n", Colors.YELLOW)

    try:
        subprocess.call(f'{editor} "{target_file}"', shell=True)
    except Exception as e:
        print_color(f"Failed to open editor: {e}", Colors.RED)
        print_color(
            f"Please edit the file manually and re-run:\n  {target_file}", Colors.YELLOW)
        return []

    return _read_target_folders(target_file)


def _detect_editor():
    """
    Detect the best available text editor.
    Priority: $EDITOR env var > system default (macOS/Windows) > nano > vim > vi.
    """
    env_editor = os.environ.get("EDITOR")
    if env_editor:
        return env_editor

    # macOS: open with default text editor, -W blocks until closed
    if sys.platform == "darwin":
        return "open -W -t"

    # Windows: notepad is always available and blocks until closed
    if os.name == "nt":
        return "notepad"

    # Unix-like: prefer terminal editors that block naturally
    for candidate in ("nano", "vim", "vi"):
        if shutil.which(candidate):
            return candidate

    return "vi"


def _read_target_folders(target_file):
    """
    Read target-folders.txt and return a list of non-empty, non-comment lines.
    """
    if not os.path.isfile(target_file):
        return []
    with open(target_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    paths = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            paths.append(stripped)
    return paths


def _write_target_folders(target_file, paths):
    """
    Write the given list of paths to target-folders.txt.
    Only writes actual paths, no comment headers.
    """
    with open(target_file, "w", encoding="utf-8") as f:
        for p in paths:
            f.write(p + "\n")
