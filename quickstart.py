#!/usr/bin/env python3
"""
Instrumentor Test Bug Fix Workflow Quickstart Script
This script guides you through the full process of code instrumentation, compiling and running the instrumentor test, log denoising and analysis, AI prompt generation, and automated bug fixing.
"""

import os

# 直接从 work_flow 文件夹中导入模块
from work_flow.utils import Colors, print_color, pause_for_next_step
from work_flow.prechecks import (
    check_target_folders, 
    print_disclaimer, 
    check_java_version, 
    check_llm_env, 
    auto_select_llm_provider
)
from work_flow.workflow_steps import (
    step_0_1_instrument_code,
    step_2_compile_and_run,
    step_3_analyze_logs,
    step_4_generate_ai_prompt,
    step_5_ask_llm_for_localization,
    step_6_generate_fix_prompt,
    step_7_ask_llm_for_code_fix,
    step_8_apply_fix
)

def main():
    work_dir = os.path.abspath(os.getcwd())
    instrumentor_test_path = os.path.join(work_dir, "core", "instrumentor-test")
    ask_llm_dir = os.path.join(work_dir, "enginerring", "ask-llm")

    print_color("=======================================================", Colors.CYAN)
    print_color("      Instrumentor Test Workflow Quickstart Script     ", Colors.CYAN)
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

    pause_for_next_step("[Environment Setup]", "[Step 0] Setup Shadow Branch")

    # Workflow Execution
    step_0_1_instrument_code(work_dir)
    pause_for_next_step("[Step 0 & 1] Setup Shadow Branch & Instrumentation", "[Step 2] Compile and Run Instrumentor Test")

    step_2_compile_and_run(instrumentor_test_path)
    pause_for_next_step("[Step 2] Compile and Run", "[Step 3] Analyze Logs and Extract Denoised Data")

    step_3_analyze_logs(work_dir, instrumentor_test_path)
    pause_for_next_step("[Step 3] Log Analysis", "[Step 4] Generate AI Prompt")

    step_4_generate_ai_prompt(work_dir)
    pause_for_next_step("[Step 4] Generate AI Prompt", "[Step 5] Ask LLM for Bug Localization")

    step_5_ask_llm_for_localization(ask_llm_dir)
    pause_for_next_step("[Step 5] Ask LLM for Bug Localization", "[Step 6] Generate Fix Prompt")

    step_6_generate_fix_prompt(work_dir)
    pause_for_next_step("[Step 6] Generate Fix Prompt", "[Step 7] Ask LLM for Code Fix")

    step_7_ask_llm_for_code_fix(ask_llm_dir)
    pause_for_next_step("[Step 7] Ask LLM for Code Fix", "[Step 8] Apply Fix to Source Code")

    step_8_apply_fix(work_dir)

    print_color("\n=======================================================", Colors.MAGENTA)
    print_color("  Workflow execution completed successfully. The bug has been fixed.", Colors.GREEN)
    print_color("  You can now re-run the tests to verify the fix.", Colors.GREEN)
    print_color("=======================================================", Colors.MAGENTA)

    os.chdir(work_dir)

if __name__ == "__main__":
    main()