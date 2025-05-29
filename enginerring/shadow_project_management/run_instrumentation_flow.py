import os
import sys
import subprocess
import shutil

from print_utils.utils import print_color, Colors

def _run_java_instrumentation(target_folders, incremental, mapping_file, range_file, signature_file):
    """Single JAR call, replaces previous multiple subprocesses"""
    java_home = os.environ.get("JAVA_HOME")
    if not java_home:
        print_color("Error: JAVA_HOME not configured.", Colors.RED)
        return False

    java_exe = shutil.which("java")
    if not java_exe:
        print_color("Error: java not found in PATH.", Colors.RED)
        return False

    pipeline_jar = os.path.join(".", "multilingual", "java", "instrumentor", "target",
                                "instrumentor-1.0-SNAPSHOT.jar")

    java_cmd = [java_exe, "-jar", pipeline_jar]
    if incremental:

        java_cmd += [
            "--incremental",
            "-m", mapping_file,
            "-r", range_file,
            "-s", signature_file
        ]
    java_cmd += target_folders

    print(f"Running: {' '.join(java_cmd)}")
    result = subprocess.run(java_cmd)

    if result.returncode != 0:
        print_color(
            "Warning: Instrumentation pipeline returned non-zero exit code.", Colors.YELLOW)
        return False

    return True

def _run_php_instrumentation(target_folders, incremental, mapping_file, range_file, signature_file, work_dir):
    """Executes the PHP-specific instrumentation logic."""
    php_exe = shutil.which("php")
    if not php_exe:
        print_color("Error: php not found in PATH.", Colors.RED)
        return False

    pipeline_script = os.path.join(
        work_dir, "multilingual", "php", "instrumentor", "InstrumentationPipeline.php")

    if not os.path.exists(pipeline_script):
        print_color(
            f"Error: PHP instrumentation script not found at {pipeline_script}", Colors.RED)
        return False

    php_cmd = [php_exe, pipeline_script]
    if incremental:

        php_cmd += [
            "--incremental",
            "--mapping", mapping_file,
            "--range", range_file,
            "--signature", signature_file
        ]

    php_cmd += target_folders

    print(f"Running: {' '.join(php_cmd)}")
    result = subprocess.run(php_cmd)

    if result.returncode != 0:
        print_color(
            "Warning: PHP Instrumentation pipeline returned non-zero exit code.", Colors.YELLOW)
        return False

    return True

def _run_javascript_instrumentation(target_folders, work_dir):
    """Executes the JavaScript-specific instrumentation logic."""
    node_exe = shutil.which("node")
    if not node_exe:
        print_color("Error: node not found in PATH.", Colors.RED)
        return False

    pipeline_script = os.path.join(
        work_dir, "multilingual", "javascript", "instrumentor", "InstrumentationPipeline.js")

    if not os.path.exists(pipeline_script):
        print_color(
            f"Error: JS instrumentation script not found at {pipeline_script}", Colors.RED)
        return False

    js_cmd = [node_exe, pipeline_script] + target_folders

    print(f"Running: {' '.join(js_cmd)}")
    result = subprocess.run(js_cmd)

    if result.returncode != 0:
        print_color(
            "Warning: JS Instrumentation pipeline returned non-zero exit code.", Colors.YELLOW)
        return False

    return True

def _run_python_instrumentation(target_folders, incremental, mapping_file, range_file, signature_file):
    """
    Executes the Python-specific instrumentation logic.
    (Placeholder for future implementation)
    """
    print("\nChecking Python environment and dependencies...")
    print_color("[Info] Python instrumentation logic goes here.", Colors.CYAN)

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
        mapping_file:       Path to the existing block-line-mapping.txt for incremental mode.
                            Defaults to ./block-line-mapping.txt if not specified.
        language:           Target programming language for instrumentation (default: 'java').
    """
    mode_label = "Incremental" if incremental else "Full"
    print(
        f"\n--- Starting Instrumentation Flow ({mode_label}) for {language.upper()} ---")

    target_folders = []

    if target_folders_list:
        target_folders = target_folders_list
    else:
        if not target_folders_file:
            target_folders_file = os.path.join(".", "target-folders.txt")

        if not os.path.exists(target_folders_file):
            print_color(
                f"Error: Target folders file does not exist: {target_folders_file}", Colors.RED)
            return False

        with open(target_folders_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    target_folders.append(line)

        if not target_folders:
            print()
            print_color(
                "=================================================================", Colors.RED)
            print_color(
                f"ERROR: No target folders found in file: {target_folders_file}", Colors.RED)
            print_color(
                "      Please add at least one valid folder path to the file.", Colors.RED)
            print_color(
                "=================================================================", Colors.RED)
            print()
            return False

        print(
            f"Loaded {len(target_folders)} target folder(s) from file: {target_folders_file}")

    for folder in target_folders:
        if not os.path.exists(folder):
            print_color(
                f"Error: Target folder does not exist: {folder}", Colors.RED)
            return False

    print(f"Target folders: {', '.join(target_folders)}")

    if mapping_file is None:
        mapping_file = os.path.join(".", "block-line-mapping.txt")

    mapping_file = os.path.abspath(mapping_file)

    mapping_dir = os.path.dirname(mapping_file)
    range_file = os.path.abspath(os.path.join(mapping_dir, "method-range.txt"))
    signature_file = os.path.abspath(os.path.join(mapping_dir, "block-signature.txt"))

    if incremental:

        missing_files = []
        if not os.path.exists(mapping_file):
            missing_files.append(mapping_file)
        if not os.path.exists(range_file):
            missing_files.append(range_file)
        if not os.path.exists(signature_file):
            missing_files.append(signature_file)

        if missing_files:
            print_color("Warning: Incremental mode requires all mapping files to exist.", Colors.YELLOW)
            for mf in missing_files:
                print_color(f"  Missing: {mf}", Colors.YELLOW)
            print_color("Falling back to full instrumentation mode.", Colors.YELLOW)
            incremental = False
        else:
            print(f"Incremental mode: merging with existing files:")
            print(f"  Mapping:   {mapping_file}")
            print(f"  Ranges:    {range_file}")
            print(f"  Signature: {signature_file}")

    success = False
    lang_lower = language.lower()

    if lang_lower == 'java':
        success = _run_java_instrumentation(
            target_folders, incremental, mapping_file, range_file, signature_file)
    elif lang_lower == 'php':
        work_dir = os.path.abspath(os.getcwd())
        success = _run_php_instrumentation(
            target_folders, incremental, mapping_file, range_file, signature_file, work_dir)
    elif lang_lower in ['javascript', 'js']:

        work_dir = os.path.abspath(os.getcwd())
        success = _run_javascript_instrumentation(target_folders, work_dir)
    elif lang_lower == 'python':
        success = _run_python_instrumentation(
            target_folders, incremental, mapping_file, range_file, signature_file)
    else:
        print_color(
            f"Error: Unsupported language for instrumentation: {language}", Colors.RED)
        return False

    if success:
        print("\nInstrumentation phase completed. "
              "Please check the generated log file timestamp and use process-logs-demo.py for subsequent processing.")

    return success