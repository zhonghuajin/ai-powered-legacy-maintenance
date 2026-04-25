import os
import sys
import subprocess
import shutil

from print_utils.utils import print_color, Colors


def run_instrumentation_flow(target_folders_file=None, target_folders_list=None):
    """
    Pure Python implementation of the instrumentation flow.
    Ensures cross-platform compatibility without relying on PowerShell.
    """
    print("\n--- Starting Instrumentation Flow ---")
    
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

    # 2. Check Java environment variables
    print("\nChecking Java environment variables...")
    java_home = os.environ.get("JAVA_HOME")
    if not java_home:
        print_color("Error: JAVA_HOME Environment variable not configured. Please set JAVA_HOME to point to your JDK installation directory.", Colors.RED)
        return False
        
    print(f"Using JAVA_HOME: {java_home}")
    
    java_bin = os.path.join(java_home, "bin")
    os.environ["PATH"] = f"{java_bin}{os.pathsep}{os.environ.get('PATH', '')}"

    java_exe = shutil.which("java")
    if not java_exe:
        print_color("Error: Java (java) not found in PATH.", Colors.RED)
        return False

    # 3. Execute Instrumentor related Java commands
    print("\nExecuting code instrumentation (Instrumentor)...")
    
    jars_to_run = [
        ("Main instrumentation", os.path.join(".", "core", "instrumentor", "target", "instrumentor-1.0-SNAPSHOT.jar")),
        ("Encoding mapping", os.path.join(".", "core", "instrumentor-with-encoding", "target", "instrumentor-with-encoding-1.0-SNAPSHOT.jar")),
        ("Activator", os.path.join(".", "core", "instrumentor-activator", "target", "instrumentor-activator-1.0-SNAPSHOT.jar"))
    ]
    
    for step_name, jar_path in jars_to_run:
        print(f"Running {step_name}...")
        java_cmd = [java_exe, "-jar", jar_path] + target_folders
        if subprocess.run(java_cmd).returncode != 0:
            print_color(f"Warning: {step_name} step returned non-zero exit code.", Colors.YELLOW)

    print("\nInstrumentation phase completed. Please check the generated log file timestamp and use process-logs-demo.py for subsequent processing.")
    return True