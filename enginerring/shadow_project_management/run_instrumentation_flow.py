import os
import sys
import subprocess
import shutil

from print_utils.utils import print_color, Colors


def _run_java_instrumentation(target_folders, incremental, mapping_file):
    """
    Executes the Java-specific instrumentation logic.
    """
    # 3. Check Java environment variables
    print("\nChecking Java environment variables...")
    java_home = os.environ.get("JAVA_HOME")
    if not java_home:
        print_color("Error: JAVA_HOME Environment variable not configured. "
                     "Please set JAVA_HOME to point to your JDK installation directory.", Colors.RED)
        return False

    print(f"Using JAVA_HOME: {java_home}")

    java_bin = os.path.join(java_home, "bin")
    os.environ["PATH"] = f"{java_bin}{os.pathsep}{os.environ.get('PATH', '')}"

    java_exe = shutil.which("java")
    if not java_exe:
        print_color("Error: Java (java) not found in PATH.", Colors.RED)
        return False

    # 4. Execute Instrumentor related Java commands
    print("\nExecuting code instrumentation (Instrumentor)...")

    instrumentor_jar = os.path.join(".", "core", "instrumentor", "target",
                                    "instrumentor-1.0-SNAPSHOT.jar")
    encoding_jar = os.path.join(".", "core", "instrumentor-with-encoding", "target",
                                "instrumentor-with-encoding-1.0-SNAPSHOT.jar")
    activator_jar = os.path.join(".", "core", "instrumentor-activator", "target",
                                 "instrumentor-activator-1.0-SNAPSHOT.jar")

    # Step 1: Main instrumentation (same for full & incremental)
    print("Running Main instrumentation...")
    java_cmd = [java_exe, "-jar", instrumentor_jar] + target_folders
    if subprocess.run(java_cmd).returncode != 0:
        print_color("Warning: Main instrumentation step returned non-zero exit code.", Colors.YELLOW)

    # Step 2: Encoding mapping (incremental mode adds -m flag)
    print("Running Encoding mapping...")
    java_cmd = [java_exe, "-jar", encoding_jar]
    if incremental:
        java_cmd += ["-m", mapping_file]
    java_cmd += target_folders
    if subprocess.run(java_cmd).returncode != 0:
        print_color("Warning: Encoding mapping step returned non-zero exit code.", Colors.YELLOW)

    # Step 3: Activator (same for full & incremental)
    print("Running Activator...")
    java_cmd = [java_exe, "-jar", activator_jar] + target_folders
    if subprocess.run(java_cmd).returncode != 0:
        print_color("Warning: Activator step returned non-zero exit code.", Colors.YELLOW)

    return True


def _run_python_instrumentation(target_folders, incremental, mapping_file):
    """
    Executes the Python-specific instrumentation logic.
    (Placeholder for future implementation)
    """
    print("\nChecking Python environment and dependencies...")
    print_color("[Info] Python instrumentation logic goes here.", Colors.CYAN)
    # TODO: Implement Python AST parsing or instrumentation tool execution
    # python_cmd = [sys.executable, "-m", "python_instrumentor"] + target_folders
    # subprocess.run(python_cmd)
    return True


def run_instrumentation_flow(target_folders_file=None, target_folders_list=None,
                             incremental=False, mapping_file=None, language='java'):
    """
    Pure Python implementation of the instrumentation flow.
    Ensures cross-platform compatibility without relying on PowerShell.

    Args:
        target_folders_file: Path to a text file listing target folders (one per line).
        target_folders_list: A list of target folder paths (takes priority over file).
        incremental:        If True, performs incremental instrumentation by merging
                            with an existing mapping file. Only the specified targets
                            are re-instrumented; entries for other files are retained.
        mapping_file:       Path to the existing comment-mapping.txt for incremental mode.
                            Defaults to ./comment-mapping.txt if not specified.
        language:           Target programming language for instrumentation (default: 'java').
    """
    mode_label = "Incremental" if incremental else "Full"
    print(f"\n--- Starting Instrumentation Flow ({mode_label}) for {language.upper()} ---")

    target_folders = []

    # 1. Read and validate target folders
    if target_folders_list:
        target_folders = target_folders_list
    else:
        if not target_folders_file:
            target_folders_file = os.path.join(".", "target-folders.txt")

        if not os.path.exists(target_folders_file):
            print_color(f"Error: Target folders file does not exist: {target_folders_file}", Colors.RED)
            return False

        with open(target_folders_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    target_folders.append(line)

        if not target_folders:
            print()
            print_color("=================================================================", Colors.RED)
            print_color(f"ERROR: No target folders found in file: {target_folders_file}", Colors.RED)
            print_color("      Please add at least one valid folder path to the file.", Colors.RED)
            print_color("=================================================================", Colors.RED)
            print()
            return False

        print(f"Loaded {len(target_folders)} target folder(s) from file: {target_folders_file}")

    for folder in target_folders:
        if not os.path.exists(folder):
            print_color(f"Error: Target folder does not exist: {folder}", Colors.RED)
            return False

    print(f"Target folders: {', '.join(target_folders)}")

    # 2. Resolve mapping file for incremental mode
    if mapping_file is None:
        mapping_file = os.path.join(".", "comment-mapping.txt")

    mapping_file = os.path.abspath(mapping_file)

    if incremental:
        if not os.path.exists(mapping_file):
            print_color(f"Warning: Mapping file not found: {mapping_file}", Colors.YELLOW)
            print_color("Falling back to full instrumentation mode.", Colors.YELLOW)
            incremental = False
        else:
            print(f"Incremental mode: merging with existing mapping: {mapping_file}")

    # 3. Dispatch instrumentation based on language
    success = False
    lang_lower = language.lower()
    
    if lang_lower == 'java':
        success = _run_java_instrumentation(target_folders, incremental, mapping_file)
    elif lang_lower == 'python':
        success = _run_python_instrumentation(target_folders, incremental, mapping_file)
    else:
        print_color(f"Error: Unsupported language for instrumentation: {language}", Colors.RED)
        return False

    if success:
        print("\nInstrumentation phase completed. "
              "Please check the generated log file timestamp and use process-logs-demo.py for subsequent processing.")
        
    return success