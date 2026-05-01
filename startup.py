#!/usr/bin/env python3
"""
Instrumentor Test Bug Fix Workflow Quickstart Script
This script guides you through the full process of code instrumentation,
log denoising and analysis, AI prompt generation, and automated bug fixing.
"""

import os
import sys
import json
import subprocess

from print_utils.utils import Colors, print_color, pause_for_next_step
from enginerring.work_flow.prechecks import (
    print_disclaimer,
    check_java_version,
    check_llm_env,
    auto_select_llm_provider
)
from enginerring.work_flow.workflow_steps import (
    instrument_code,
    handle_instrumentation_dependencies,
    startup_log_manager_server,
    analyze_logs,
    generate_ai_prompt,
    ask_llm_for_localization,
    generate_fix_prompt,
    ask_llm_for_code_fix,
    apply_fix
)
# Import the delayed commit function
from enginerring.shadow_project_management.full_instrumentation import commit_instrumentation
from enginerring.project_manager.project_manager import create_or_select_project


def switch_to_source_branch(proj_path):
    """
    Read the project config.json and checkout the original_git_root
    repository to its configured source_branch.
    
    Args:
        proj_path: Path to the project directory containing config.json
    """
    config_path = os.path.join(proj_path, 'config.json')
    if not os.path.exists(config_path):
        print_color('[Branch Switch] config.json not found, skipping branch switch.', Colors.YELLOW)
        return

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    git_root = config.get('original_git_root', '')
    source_branch = config.get('source_branch', 'master')  # fallback to 'master'

    if not git_root:
        print_color('[Branch Switch] original_git_root is empty, skipping branch switch.', Colors.YELLOW)
        return

    print_color(
        f'[Branch Switch] Switching {git_root} to branch "{source_branch}" ...',
        Colors.CYAN
    )
    try:
        result = subprocess.run(
            ['git', '-C', git_root, 'checkout', source_branch],
            check=True,
            capture_output=True,
            text=True
        )
        print_color(
            f'[Branch Switch] Successfully switched to {source_branch}.',
            Colors.GREEN
        )
    except subprocess.CalledProcessError as e:
        print_color(
            f'[Branch Switch] Failed to switch branch: {e.stderr.strip()}',
            Colors.RED
        )
        print_color(
            '[Branch Switch] You may have uncommitted changes or the branch does not exist.',
            Colors.RED
        )
        # Do not abort the whole workflow; the user may manually inspect and continue.
        print_color(
            '[Branch Switch] Continuing with the workflow despite the branch switch failure.',
            Colors.YELLOW
        )


def main():
    work_dir = os.path.abspath(os.getcwd())
    instrumentor_test_path = os.path.join(work_dir, "core", "instrumentor-test")
    ask_llm_dir = os.path.join(work_dir, "enginerring", "ask_llm")

    print_color("=======================================================", Colors.CYAN)
    print_color("      Enjoy the Convenience of LLMs.     ", Colors.CYAN)
    print_color("=======================================================", Colors.CYAN)
    print(f"Current working directory: {work_dir}")
    print(f"Source and runtime path: {instrumentor_test_path}")
    print_color("=======================================================\n", Colors.CYAN)

    # Pre-checks
    print_disclaimer()
    check_java_version()
    env_file = check_llm_env(ask_llm_dir)
    auto_select_llm_provider(env_file)

    # Step: Create or select a project
    proj_path, root_path = create_or_select_project(work_dir)

    pause_for_next_step("Project and Environment Setup", "Setup Shadow Branch")

    # Workflow Execution: Instrumentation
    instrument_mode = instrument_code(work_dir, proj_path=proj_path, git_root=root_path)

    # Handle dependency injection and commit for full mode
    if instrument_mode == "incremental":
        print_color("\n=======================================================", Colors.YELLOW)
        print_color("  Incremental instrumentation completed.", Colors.YELLOW)
        print_color("  Dependency injection step skipped (not needed for incremental mode).", Colors.YELLOW)
        print_color("=======================================================\n", Colors.YELLOW)
    elif instrument_mode == "full":
        handle_instrumentation_dependencies(work_dir, proj_path, root_path, ask_llm_dir)
        # Commit only after dependencies have been processed
        commit_instrumentation(root_path)
        print_color("\n=======================================================", Colors.YELLOW)
        print_color("  *** ATTENTION ***", Colors.YELLOW)
        print_color("  Instrumentation and Dependency Injection have been completed!", Colors.YELLOW)
        print_color("  Please recompile (if necessary) and execute the target project.", Colors.YELLOW)
        print_color("=======================================================\n", Colors.YELLOW)
    else:  # "skip" or any other value
        print_color("\n=======================================================", Colors.YELLOW)
        print_color("  Instrumentation skipped.", Colors.YELLOW)
        print_color("  Dependency injection step also skipped.", Colors.YELLOW)
        print_color("=======================================================\n", Colors.YELLOW)

    pause_for_next_step("Setup Shadow Branch & Instrumentation", "Startup Log Manager Server")

    # Pass proj_path so that uploaded files are saved under the project
    startup_log_manager_server(work_dir, proj_path=proj_path)

    pause_for_next_step("Startup Log Manager Server", "Analyze Logs and Extract Denoised Data")

    # --- NEW: Switch back to the source branch before log analysis ---
    switch_to_source_branch(proj_path)

    analyze_logs(work_dir, instrumentor_test_path, proj_path=proj_path)
    pause_for_next_step("Log Analysis", "Generate AI Prompt")

    generate_ai_prompt(work_dir)
    pause_for_next_step("Generate AI Prompt", "Ask LLM for Bug Localization")

    ask_llm_for_localization(ask_llm_dir)
    pause_for_next_step("Ask LLM for Bug Localization", "Generate Fix Prompt")

    generate_fix_prompt(work_dir)
    pause_for_next_step("Generate Fix Prompt", "Ask LLM for Code Fix")

    ask_llm_for_code_fix(ask_llm_dir)
    pause_for_next_step("Ask LLM for Code Fix", "Apply Fix to Source Code")

    apply_fix(work_dir)

    print_color("\n=======================================================", Colors.MAGENTA)
    print_color("  Workflow execution completed successfully. The bug has been fixed.", Colors.GREEN)
    print_color("  You can now re-run the tests to verify the fix.", Colors.GREEN)
    print_color("=======================================================", Colors.MAGENTA)

    os.chdir(work_dir)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[!] Process interrupted by user (Ctrl+C). Exiting safely...")
        sys.exit(0)