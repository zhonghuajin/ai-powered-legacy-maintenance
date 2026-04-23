#!/usr/bin/env python3
"""
Instrumentor Test Bug Fix Workflow Quickstart Script
This script guides you through the full process of code instrumentation, log denoising and analysis, AI prompt generation, and automated bug fixing.
"""

import os
import sys

from work_flow.utils import Colors, print_color, pause_for_next_step
from work_flow.prechecks import (
    check_target_folders,
    print_disclaimer,
    check_java_version,
    check_llm_env,
    auto_select_llm_provider
)
from work_flow.workflow_steps import (
    instrument_code,
    startup_log_manager_server,
    analyze_logs,
    generate_ai_prompt,
    ask_llm_for_localization,
    generate_fix_prompt,
    ask_llm_for_code_fix,
    apply_fix
)

def main():
    work_dir = os.path.abspath(os.getcwd())
    instrumentor_test_path = os.path.join(work_dir, "core", "instrumentor-test")
    ask_llm_dir = os.path.join(work_dir, "enginerring", "ask-llm")

    print_color("=======================================================", Colors.CYAN)
    print_color("      Enjoy the Convenience of LLMs.     ", Colors.CYAN)
    print_color("=======================================================", Colors.CYAN)
    print(f"Current working directory: {work_dir}")
    print(f"Source and runtime path: {instrumentor_test_path}")
    print_color("=======================================================\n", Colors.CYAN)

    # Pre-checks
    check_target_folders(work_dir)
    print_disclaimer()
    check_java_version()
    env_file = check_llm_env(ask_llm_dir)
    auto_select_llm_provider(env_file)

    pause_for_next_step("Environment Setup", "Setup Shadow Branch")

    # Workflow Execution
    instrument_code(work_dir)

    print_color("\n=======================================================", Colors.YELLOW)
    print_color("  *** ATTENTION ***", Colors.YELLOW)
    print_color("  Instrumentation has been completed!", Colors.YELLOW)
    print_color("  Please recompile (if necessary) and execute the target project.", Colors.YELLOW)
    print_color("=======================================================\n", Colors.YELLOW)

    pause_for_next_step("Setup Shadow Branch & Instrumentation", "Startup Log Manager Server")

    startup_log_manager_server(work_dir)

    pause_for_next_step("Startup Log Manager Server", "Analyze Logs and Extract Denoised Data")

    analyze_logs(work_dir, instrumentor_test_path)
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