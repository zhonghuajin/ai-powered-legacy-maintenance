# -*- coding: utf-8 -*-
import os
import subprocess
from pathlib import Path

# Dynamically resolve the project root (two levels up from log_processors folder)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def run_java_pruner(target_folders_list, log_file, comment_mapping_file, pruned_folder, block_pruner_jar=None, base_reference_dir=None):
    """Specific logic for executing Java Block Pruner."""
    if not block_pruner_jar:
        block_pruner_jar = str(PROJECT_ROOT / "multilingual" / "java" /
                               "block-pruner" / "target" / "block-pruner-1.0-SNAPSHOT.jar")

    print("Checking Java environment variables...")
    java_home = os.environ.get("JAVA_HOME")
    if not java_home:
        raise EnvironmentError(
            "JAVA_HOME environment variable not configured. Please set JAVA_HOME."
        )
    env = os.environ.copy()
    env["PATH"] = os.path.join(java_home, "bin") + os.pathsep + env.get("PATH", "")

    print("Executing Java Block Pruner...")
    source_dirs_arg = ";".join(target_folders_list)
    block_pruner_cmd = [
        "java", "-jar", block_pruner_jar,
        source_dirs_arg,
        comment_mapping_file,
        log_file,
        pruned_folder
    ]
    if base_reference_dir:
        block_pruner_cmd.append(base_reference_dir)

    try:
        subprocess.run(block_pruner_cmd, env=env, check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Error executing Block Pruner: {e}")


def run_python_pruner(target_folders_list, log_file, comment_mapping_file, pruned_folder, base_reference_dir=None):
    """Specific logic for executing Python Block Pruner."""
    print("Executing Python Block Pruner...")
    print("[INFO] Python block pruner is currently a stub.")


def run_php_pruner(target_folders_list, log_file, comment_mapping_file, pruned_folder, base_reference_dir=None):
    """Specific logic for executing PHP Block Pruner."""
    print("Executing PHP Block Pruner...")
    php_pruner_script_path = str(
        PROJECT_ROOT / "multilingual" / "php" / "block-pruner" / "BlockPruner.php")
    source_dirs_arg = ";".join(target_folders_list)

    php_pruner_cmd = [
        "php",
        php_pruner_script_path,
        source_dirs_arg,
        comment_mapping_file,
        log_file,
        pruned_folder
    ]
    if base_reference_dir:
        php_pruner_cmd.append(base_reference_dir)

    try:
        subprocess.run(php_pruner_cmd, check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Error executing PHP Block Pruner: {e}")


def run_javascript_pruner(target_folders_list, log_file, comment_mapping_file, pruned_folder, base_reference_dir=None):
    """Specific logic for executing JavaScript Block Pruner."""
    print("Executing JavaScript Block Pruner...")
    js_pruner_script_path = str(
        PROJECT_ROOT / "multilingual" / "javascript" / "block-pruner" / "BlockPruner.js")
    source_dirs_arg = ";".join(target_folders_list)

    js_pruner_cmd = [
        "node",
        js_pruner_script_path,
        source_dirs_arg,
        comment_mapping_file,
        log_file,
        pruned_folder
    ]
    if base_reference_dir:
        js_pruner_cmd.append(base_reference_dir)

    try:
        subprocess.run(js_pruner_cmd, check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Error executing JavaScript Block Pruner: {e}")