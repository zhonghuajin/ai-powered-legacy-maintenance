# scan_deps.py

import os
import argparse
from pathlib import Path

# Exact filenames to look for
PROJECT_FILES = {
    # C/C++
    "Makefile",
    "CMakeLists.txt",
    # JavaScript / TypeScript / Node.js
    "package.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    # Java / Kotlin
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    # PHP
    "composer.json",
    # Python
    "requirements.txt",
    "Pipfile",
    "pyproject.toml",
    "setup.py",
    # Go
    "go.mod",
    # Rust
    "Cargo.toml",
    # Ruby
    "Gemfile",
    # Dart / Flutter
    "pubspec.yaml",
    # C# / .NET (exact filenames)
    "packages.config",          # Legacy .NET Framework NuGet dependency file
    "nuget.config",             # NuGet configuration (lowercase)
    "NuGet.Config",             # NuGet configuration (uppercase)
    "global.json",              # .NET SDK version control file
    "Directory.Build.props",    # MSBuild directory-level custom properties
    "Directory.Build.targets",  # MSBuild directory-level custom targets
    "project.json",             # Early .NET Core project file (deprecated but may exist in old projects)
}

# File extensions to look for (for cases where the project name is not fixed)
PROJECT_EXTENSIONS = {
    # C# / .NET / Visual Studio
    ".csproj",   # C# project file
    ".sln",      # Visual Studio solution file
    ".fsproj",   # F# project file
    ".vbproj",   # VB.NET project file
}

def find_project_files(root_dir):
    """
    Walk through a directory and find all project management files, returning their absolute paths.
    """
    root_path = Path(root_dir).resolve()
    
    if not root_path.exists() or not root_path.is_dir():
        print(f"Error: Directory '{root_dir}' does not exist or is not a valid directory.")
        return []

    found_files = []

    # Use os.walk to traverse the directory, this better handles permission issues and
    # easily ignores certain unwanted directories
    for dirpath, dirnames, filenames in os.walk(root_path):
        # Ignore common hidden directories or dependency/build output directories to
        # significantly speed up scanning and reduce noise
        ignored_dirs = {
            '.git', '.svn', 'node_modules', 'venv', '.venv',
            'target', 'build', 'dist',
            'bin', 'obj', 'packages'  # Common C# build output and dependency directories
        }
        dirnames[:] = [d for d in dirnames if d not in ignored_dirs]

        for filename in filenames:
            # 1. Check if it is in the exact match set
            if filename in PROJECT_FILES:
                full_path = os.path.join(dirpath, filename)
                found_files.append(full_path)
                continue
            
            # 2. Check if it matches a specific file extension
            _, ext = os.path.splitext(filename)
            if ext.lower() in PROJECT_EXTENSIONS:
                full_path = os.path.join(dirpath, filename)
                found_files.append(full_path)

    return found_files

def scan_and_display(directory="."):
    """
    Scan the given directory for project files and print the results.
    This function can be safely imported and called from other Python modules.
    """
    abs_dir = Path(directory).resolve()
    print(f"Scanning directory: {abs_dir} ...\n")
    
    project_files = find_project_files(directory)
    
    if not project_files:
        print("No project files found.")
    else:
        print(f"Found {len(project_files)} project files:\n")
        for file_path in project_files:
            print(file_path)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scan a directory and find all project management/dependency files.")
    parser.add_argument("directory", nargs="?", default=".", help="Directory path to scan (defaults to current directory)")
    args = parser.parse_args()
    
    scan_and_display(args.directory)