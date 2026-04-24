# project_manager.py
"""Project creation and selection logic."""

import os
import sys
import re
import json
from .utils import Colors, print_color


def create_or_select_project(work_dir):
    """
    Step: Create or select an existing project.
    Returns the git repository root directory (root_path) for the selected project.
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
                        root_path = cfg.get("root_path", "")
                        existing_projects.append((entry, root_path))
                    except Exception:
                        # Ignore invalid config files
                        pass

    # If no projects exist, force creation of a new one
    if not existing_projects:
        print_color("No existing projects found. Let's create a new one.", Colors.CYAN)
        return _create_new_project(work_dir, projects_dir)

    # Display existing projects and an option to create a new one
    print_color("\n=== Existing Projects ===", Colors.CYAN)
    for idx, (name, root) in enumerate(existing_projects, start=1):
        print(f"  {idx}. {name}  ->  {root}")
    print(f"  {len(existing_projects) + 1}. Create a new project")

    choice = ""
    while True:
        try:
            choice = input("Select a project number or choose to create a new one: ").strip()
            if choice.isdigit():
                num = int(choice)
                if 1 <= num <= len(existing_projects):
                    selected_name, selected_root = existing_projects[num - 1]
                    print_color(f"Selected project: {selected_name} (root: {selected_root})", Colors.GREEN)
                    return selected_root
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
    """Helper to create a new project and return its root_path."""
    print_color("\n--- Create a New Project ---", Colors.CYAN)
    # Validate project name (no Chinese characters)
    while True:
        name = input("Enter a project name (English letters, digits, hyphens, underscores allowed): ").strip()
        if not name:
            print_color("Project name cannot be empty.", Colors.RED)
            continue
        # Check for Chinese characters (Unicode range)
        if re.search(r'[\u4e00-\u9fff]', name):
            print_color("Chinese characters are not allowed. Please use English.", Colors.RED)
            continue
        if not re.match(r'^[a-zA-Z0-9_\-\.]+$', name):
            print_color("Only letters, digits, hyphens, underscores and dots are allowed.", Colors.RED)
            continue
        # Check if project already exists
        proj_path = os.path.join(projects_dir, name)
        if os.path.exists(proj_path):
            print_color(f"Project '{name}' already exists. Please choose a different name.", Colors.RED)
            continue
        break

    git_root = ""
    while not git_root:
        git_root = input("Please enter the Git repository root directory of the project: ").strip()
        if not git_root:
            print_color("Path cannot be empty.", Colors.RED)
        # Basic existence check
        elif not os.path.isdir(git_root):
            print_color("The specified directory does not exist. Please enter a valid path.", Colors.RED)
            git_root = ""
        else:
            git_root = os.path.abspath(git_root)

    # Create project folder and config.json
    proj_path = os.path.join(projects_dir, name)
    os.makedirs(proj_path, exist_ok=True)
    config = {"root_path": git_root}
    config_path = os.path.join(proj_path, "config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

    print_color(f"Project '{name}' created successfully with root: {git_root}", Colors.GREEN)
    return git_root