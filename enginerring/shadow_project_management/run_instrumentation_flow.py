import os
import sys
import subprocess
import shutil
from datetime import datetime

try:
    from print_utils.utils import print_color, Colors
except ImportError:
    class Colors:
        RED = '\033[91m'
        GREEN = '\033[92m'
        YELLOW = '\033[93m'
        CYAN = '\033[96m'
        ENDC = '\033[0m'

    def print_color(text, color_code):
        print(f"{color_code}{text}{Colors.ENDC}")

def normalize_path(path):
    return os.path.normcase(os.path.abspath(path))

def write_merged_file(file_path, entries, file_desc, format_desc, sort_by_key=False):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_entries = len(entries)

    comments = [
        "# ================================================",
        f"# {file_desc}",
        f"# Generation Time: {current_time}",
        f"# Total Entries: {total_entries}",
        "# ================================================",
        f"# Format: {format_desc}",
        "# Note: This mapping needs to be regenerated after source code modifications and re-instrumentation.\n"
    ]

    if sort_by_key:
        try:
            keys_to_write = sorted(entries.keys(), key=lambda x: int(x))
        except ValueError:
            keys_to_write = sorted(entries.keys())
    else:
        keys_to_write = list(entries.keys())

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(comments) + "\n")
        for key in keys_to_write:
            f.write(f"{key} = {entries[key]}\n")

def perform_incremental_merge(mapping_file, range_file, signature_file):
    inc_mapping_file = mapping_file.replace(".txt", ".incremental.txt")
    inc_range_file = range_file.replace(".txt", ".incremental.txt")
    inc_signature_file = signature_file.replace(".txt", ".incremental.txt")

    if not (os.path.exists(inc_mapping_file) and os.path.exists(inc_range_file) and os.path.exists(inc_signature_file)):
        print_color("[Merge] Missing one or more incremental files. Skipping merge.", Colors.YELLOW)
        return False

    print_color("\n--- Starting Deep Incremental Data Merge ---", Colors.CYAN)

    modified_files = set()
    inc_mappings = {}

    with open(inc_mapping_file, 'r', encoding='utf-8') as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            if '=' in line:
                block_id, file_and_line = [x.strip() for x in line.split('=', 1)]
                inc_mappings[block_id] = file_and_line
                if ':' in file_and_line:
                    file_path = file_and_line.rsplit(':', 1)[0]
                    modified_files.add(normalize_path(file_path))

    print(f"[Merge] Identified {len(modified_files)} modified file(s) from incremental mapping:")
    for f_path in modified_files:
        print(f"  - {f_path}")

    base_mappings = {}
    obsolete_block_ids = set()

    if os.path.exists(mapping_file):
        with open(mapping_file, 'r', encoding='utf-8') as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith('#'):
                    continue
                if '=' in line:
                    block_id, file_and_line = [x.strip() for x in line.split('=', 1)]
                    base_mappings[block_id] = file_and_line
                    if ':' in file_and_line:
                        file_path = file_and_line.rsplit(':', 1)[0]
                        if normalize_path(file_path) in modified_files:
                            obsolete_block_ids.add(block_id)

    print(f"[Merge] Found {len(obsolete_block_ids)} obsolete Block ID(s) to be removed.")

    cleaned_mappings = {
        bid: val for bid, val in base_mappings.items()
        if bid not in obsolete_block_ids
    }
    cleaned_mappings.update(inc_mappings)
    write_merged_file(
        mapping_file,
        cleaned_mappings,
        "Instrumentation Comment -> Integer ID Mapping Table",
        "Integer ID = File Absolute Path:Code Block Start Line Number",
        sort_by_key=True
    )

    base_signatures = {}
    if os.path.exists(signature_file):
        with open(signature_file, 'r', encoding='utf-8') as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith('#'):
                    continue
                if '=' in line:
                    block_id, sig = [x.strip() for x in line.split('=', 1)]
                    base_signatures[block_id] = sig

    cleaned_signatures = {
        bid: sig for bid, sig in base_signatures.items()
        if bid not in obsolete_block_ids
    }

    with open(inc_signature_file, 'r', encoding='utf-8') as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            if '=' in line:
                block_id, sig = [x.strip() for x in line.split('=', 1)]
                cleaned_signatures[block_id] = sig

    write_merged_file(
        signature_file,
        cleaned_signatures,
        "Block ID -> Method Signature Mapping Table",
        "Block ID = Method Signature",
        sort_by_key=True
    )

    cleaned_ranges = {}

    if os.path.exists(range_file):
        with open(range_file, 'r', encoding='utf-8') as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith('#'):
                    continue
                if '=' in line:
                    key, val = [x.strip() for x in line.split('=', 1)]
                    if '|' in key:
                        file_path = key.split('|', 1)[0].strip()
                        if normalize_path(file_path) in modified_files:
                            continue
                    cleaned_ranges[key] = val

    with open(inc_range_file, 'r', encoding='utf-8') as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            if '=' in line:
                key, val = [x.strip() for x in line.split('=', 1)]
                cleaned_ranges[key] = val

    write_merged_file(
        range_file,
        cleaned_ranges,
        "Method Line Range Mapping Table",
        "File Absolute Path | Method Name = Start Line-End Line",
        sort_by_key=False
    )

    for temp_file in [inc_mapping_file, inc_range_file, inc_signature_file]:
        try:
            os.remove(temp_file)
        except OSError as e:
            print_color(f"[Merge] Warning: Could not remove {os.path.basename(temp_file)}: {e}", Colors.YELLOW)

    print_color("--- Incremental Data Merge Completed Successfully ---\n", Colors.GREEN)
    return True

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

def _run_python_instrumentation(target_folders, incremental, mapping_file, range_file, signature_file, work_dir):
    """Executes the Python-specific instrumentation logic."""
    python_exe = sys.executable or shutil.which("python") or shutil.which("python3")
    if not python_exe:
        print_color("Error: python not found in PATH.", Colors.RED)
        return False

    pipeline_script = os.path.join(
        work_dir, "multilingual", "python", "instrumentor", "InstrumentationPipeline.py")

    if not os.path.exists(pipeline_script):
        print_color(
            f"Error: Python instrumentation script not found at {pipeline_script}", Colors.RED)
        return False

    python_cmd = [python_exe, pipeline_script]
    if incremental:
        python_cmd += [
            "--incremental",
            "--mapping", mapping_file,
            "--range", range_file,
            "--signature", signature_file
        ]

    python_cmd += target_folders

    print(f"Running: {' '.join(python_cmd)}")
    result = subprocess.run(python_cmd)

    if result.returncode != 0:
        print_color(
            "Warning: Python Instrumentation pipeline returned non-zero exit code.", Colors.YELLOW)
        return False

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

    should_merge = incremental

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
            should_merge = False
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
        work_dir = os.path.abspath(os.getcwd())
        success = _run_python_instrumentation(
            target_folders, incremental, mapping_file, range_file, signature_file, work_dir)
    else:
        print_color(
            f"Error: Unsupported language for instrumentation: {language}", Colors.RED)
        return False

    if success:
        if should_merge:
            perform_incremental_merge(mapping_file, range_file, signature_file)

        print("\nInstrumentation phase completed. "
              "Please check the generated log file timestamp and use process-logs-demo.py for subsequent processing.")

    return success