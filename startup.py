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
import argparse

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
# New import for scenario schema generation
from enginerring.scenario_manager.generate_scenario_description import generate_scenario_description


def switch_to_source_branch(proj_path):
    """
    Read the project config.json and checkout the original_git_root
    repository to its configured source_branch.
    Before switching, if there are any uncommitted changes, add them
    and amend the last commit (git add . && git commit --amend --no-edit).

    Args:
        proj_path: Path to the project directory containing config.json
    """
    config_path = os.path.join(proj_path, 'config.json')
    if not os.path.exists(config_path):
        print_color(
            '[Branch Switch] config.json not found, skipping branch switch.', Colors.YELLOW)
        return

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    git_root = config.get('original_git_root', '')
    source_branch = config.get('source_branch', 'master')

    if not git_root:
        print_color(
            '[Branch Switch] original_git_root is empty, skipping branch switch.', Colors.YELLOW)
        return

    # --- Check for uncommitted changes before switching ---
    try:
        status_result = subprocess.run(
            ['git', '-C', git_root, 'status', '--porcelain'],
            check=True,
            capture_output=True,
            text=True
        )
        if status_result.stdout.strip():
            print_color(
                '[Branch Switch] Detected uncommitted changes. Adding and amending last commit...',
                Colors.CYAN
            )
            subprocess.run(
                ['git', '-C', git_root, 'add', '.'],
                check=True,
                capture_output=True,
                text=True
            )
            subprocess.run(
                ['git', '-C', git_root, 'commit', '--amend', '--no-edit'],
                check=True,
                capture_output=True,
                text=True
            )
            print_color(
                '[Branch Switch] Changes committed via amend.',
                Colors.GREEN
            )
    except subprocess.CalledProcessError as e:
        print_color(
            f'[Branch Switch] Failed to handle uncommitted changes: {e.stderr.strip()}',
            Colors.RED
        )
        print_color(
            '[Branch Switch] Continuing with the workflow despite the error.',
            Colors.YELLOW
        )
    # -----------------------------------------------------------

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
        print_color(
            '[Branch Switch] Continuing with the workflow despite the branch switch failure.',
            Colors.YELLOW
        )


def main():
    parser = argparse.ArgumentParser(description="Instrumentor Test Bug Fix Workflow Quickstart Script")
    parser.add_argument(
        '--no-pause', 
        action='store_true', 
        help="Skip pausing between workflow steps."
    )
    args = parser.parse_args()

    def maybe_pause(completed_step, next_step):
        if not args.no_pause:
            pause_for_next_step(completed_step, next_step)

    work_dir = os.path.abspath(os.getcwd())
    ask_llm_dir = os.path.join(work_dir, "enginerring", "ask_llm")

    print_color(
        "=======================================================", Colors.CYAN)
    print_color("      Enjoy the Convenience of LLMs.     ", Colors.CYAN)
    print_color(
        "=======================================================", Colors.CYAN)
    print(f"Current working directory: {work_dir}")
    print_color(
        "=======================================================\n", Colors.CYAN)

    # Pre-checks
    print_disclaimer()
    check_java_version()
    env_file = check_llm_env(ask_llm_dir)
    auto_select_llm_provider(env_file)

    # Step: Create or select a project
    proj_path, root_path, is_new_project = create_or_select_project(work_dir)

    maybe_pause("Project and Environment Setup", "Setup Shadow Branch")

    # Workflow Execution: Instrumentation
    instrument_mode = instrument_code(
        work_dir, proj_path=proj_path, git_root=root_path, is_new_project=is_new_project)

    # Handle dependency injection and commit for full mode
    if instrument_mode == "incremental":
        print_color(
            "\n=======================================================", Colors.YELLOW)
        print_color("  Incremental instrumentation completed.", Colors.YELLOW)
        print_color(
            "  Dependency injection step skipped (not needed for incremental mode).", Colors.YELLOW)
        print_color(
            "=======================================================\n", Colors.YELLOW)
    elif instrument_mode == "full":
        handle_instrumentation_dependencies(
            work_dir, proj_path, root_path, ask_llm_dir)
        commit_instrumentation(root_path)
        print_color(
            "\n=======================================================", Colors.YELLOW)
        print_color("  *** ATTENTION ***", Colors.YELLOW)
        print_color(
            "  Instrumentation and Dependency Injection have been completed!", Colors.YELLOW)
        print_color(
            "  Please recompile (if necessary) and execute the target project.", Colors.YELLOW)
        print_color(
            "=======================================================\n", Colors.YELLOW)

    maybe_pause("Setup Shadow Branch & Instrumentation",
                "Startup Log Manager Server")

    # Pass proj_path so that uploaded files are saved under the project
    # Capture the flush state returned by the log manager
    is_flushed = startup_log_manager_server(work_dir, proj_path=proj_path)

    maybe_pause("Startup Log Manager Server",
                "Analyze Logs and Extract Denoised Data")

    # --- Switch back to the source branch before log analysis ---
    switch_to_source_branch(proj_path)

    # Pass the flush state to automatically trigger log analysis if applicable
    analyze_logs(work_dir, proj_path=proj_path, auto_analyze=is_flushed)

    # ---------------------------------------------------------------
    # Scenario description generation (with automatic output move)
    # ---------------------------------------------------------------
    print_color('\n[Scenario Schema] Temporarily skipped (Supporting code not implemented).', Colors.YELLOW)

    maybe_pause("Log Analysis", "Generate AI Prompt")

    # Capture the selected script to determine the next workflow steps
    selected_script = generate_ai_prompt(work_dir)

    if selected_script == "generate_bug_localization_prompt.py":
        # Execute the original Bug Fix Workflow
        maybe_pause("Generate AI Prompt", "Ask LLM for Bug Localization")
        ask_llm_for_localization(ask_llm_dir)
        
        maybe_pause("Ask LLM for Bug Localization", "Generate Fix Prompt")
        generate_fix_prompt(work_dir, proj_path)
        
        maybe_pause("Generate Fix Prompt", "Ask LLM for Code Fix")
        ask_llm_for_code_fix(ask_llm_dir)
        
        maybe_pause("Ask LLM for Code Fix", "Apply Fix to Source Code")
        apply_fix(work_dir, proj_path)
        
        print_color(
            "\n=======================================================", Colors.MAGENTA)
        print_color(
            "  Workflow execution completed successfully. The bug has been fixed.", Colors.GREEN)
        print_color(
            "  You can now re-run the tests to verify the fix.", Colors.GREEN)
        print_color(
            "=======================================================", Colors.MAGENTA)
            
    elif selected_script:
        # Execute the General LLM Task Workflow
        maybe_pause("Generate AI Prompt", "Execute General LLM Task")
        print_color(f"\n>>> Executing general LLM task for {selected_script}...", Colors.CYAN)
        
        if ask_llm_dir not in sys.path:
            sys.path.insert(0, ask_llm_dir)
            
        try:
            import run as ask_llm_run
            
            original_cwd = os.getcwd()
            os.chdir(ask_llm_dir)
            
            # Assuming the generic prompt is saved as AI_General_Prompt.md
            # You may need to adjust this filename based on your actual script output
            prompt_file_path = os.path.join(original_cwd, "AI_General_Prompt.md") 
            output_file_path = os.path.join(original_cwd, "output.md")
            
            if not os.path.exists(prompt_file_path):
                print_color(f"[WARN] Expected prompt file not found: {prompt_file_path}", Colors.YELLOW)
                print_color("[WARN] Please ensure your script generates this file, or update the filename in startup.py.", Colors.YELLOW)
            else:
                ask_llm_run.run_api(file_path=prompt_file_path, output_path=output_file_path)
                print_color(f"[+] LLM response saved to {output_file_path}", Colors.GREEN)
                
            os.chdir(original_cwd)
            
            print_color(
                "\n=======================================================", Colors.MAGENTA)
            print_color(
                "  General LLM task execution completed successfully.", Colors.GREEN)
            print_color(
                "=======================================================", Colors.MAGENTA)
                
        except ImportError as e:
            print_color(f"[!] Failed to import run.py from {ask_llm_dir}: {e}", Colors.RED)
        except Exception as e:
            print_color(f"[!] Error during LLM API call: {e}", Colors.RED)
            if 'original_cwd' in locals():
                os.chdir(original_cwd)
    else:
        print_color("\n[!] Prompt generation was skipped or failed. No further actions taken.", Colors.YELLOW)

    os.chdir(work_dir)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[!] Process interrupted by user (Ctrl+C). Exiting safely...")
        sys.exit(0)