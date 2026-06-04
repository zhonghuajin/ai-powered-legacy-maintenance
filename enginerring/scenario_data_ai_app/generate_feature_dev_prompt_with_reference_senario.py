#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys

from editor_util import get_multiline_input
# 导入公共模块
from prompt_common import load_trace_and_flow_data, save_prompt_to_file

"""
AI will modify codes
"""

# ==========================================
# 0. Define Global Descriptions (To Avoid Redundancy)
# ==========================================
CALL_TREE_DESC = "Reflects the runtime appearance order of files, sorted by thread within the current scenario, along with their intra-file function call relationships. Within each thread, files are sorted by their runtime appearance order."
EXEC_FLOW_DESC = "Reflects the runtime appearance order of functions, sorted and presented by thread within the current scenario, along with their source code."

# ==========================================
# 1. Define Prompt Template
# ==========================================
PROMPT_TEMPLATE = """# Code Secondary Development and Feature Extension Guidance Task

You are a senior software architect and code development expert. Based on the existing code execution trace data, please guide me and help me implement new feature requirements.

---

## 📋 Requirement Definition

**🎯 Target New Feature**: 
{{requirement}}

**💬 Additional Notes (Optional)**: 
{{additional_info}}

---

## 🔍 Scenario Runtime Data Description

The following data comes from real system runtime trace logs. It is a "zero-noise" factual record of the specific execution scenario that triggered the bug. 

⚠️ **Core Concept**:
The **[Call Tree]** and the **[Execution Flow with Source Code]** provided below are **two different representations of the exact same execution run**. They are completely equivalent and complementary in terms of timeline, thread allocation, and execution logic:
- **Call Tree**: {call_tree_desc}
- **Execution Flow with Source Code**: {exec_flow_desc}
Please analyze them in tandem to reconstruct the complete execution context.

⚠️ **Important Premise**:
- Please reason entirely based on this factual data. **Do not guess, extrapolate, or fabricate** execution paths. 
- If a piece of code, branch, or function is not present in the data below, **it did not execute** in this specific scenario.

### ✅ Call Tree
> *Note: Reflects file-level call hierarchies grouped by thread. Within each thread, files are sorted by their runtime appearance order.*
=========================================
{{trace_data}}
=========================================

### 📝 Execution Flow with Source Code
> *Note: Reflects step-by-step function execution details and actual source code context.*
=========================================
{{execution_flow_data}}
=========================================

{{other_trace_data}}
---

## 🎯 Development Analysis Requirements

Please deeply analyze the complete execution chain of the above scenario and explain how to implement the new feature based on it:

1. **Hook Point Identification**: 
   - According to the new feature requirements, analyze **which exact step** in the existing process should be modified or extended.
   - Precisely specify the file, function name, and insertion point for the code.
2. **Logic Reuse Analysis**: 
   - Which existing functions or modules in the current call chain can be directly reused?
3. **Concurrency Safety**:
   - Evaluate whether adding the new feature could break the current execution logic (such as deadlocks, visibility failures, resource contention, etc.).

---

## ⚠️ Important Constraints

- **Fact-based only**: Analysis must be based only on the provided call chain data.
- **Complete code**: When providing modified code, you **must provide the complete class or complete method code**. Using `...` to omit original logic is strictly forbidden, to ensure the code can be copied and run directly.
- **Code precision**: You must clearly specify the **file name** and **function name being modified.**

---

## 📋 Output Format Requirements

Please strictly follow the template below when providing the guidance plan:

# New Feature Development Guidance Plan

## 1. Core Idea
[Briefly explain how to use the existing architecture to implement the new feature]

## 2. Key Hook Point (Where to modify)
- **File**: [specific file name]
- **Function**: [specific function name]
- **Reasoning**: [explain why this location is chosen]

## 3. Code Implementation (How to modify)
[Provide the complete modified code using Markdown code blocks, and add prominent comments such as `// [Added]` or `// [Modified]` at newly added/changed parts]

## 4. Files To Modify (Machine-Readable Summary)

Summarize **all** files that must be modified or **newly created** based on the Key Hook Point above. This section is intended for automated parsing, so it MUST strictly follow these rules:

- Enclose the list between the two exact marker lines shown below.
- One file path per line, nothing else on that line.
- Output the **raw file path only**. Do NOT add bullets (`-`, `*`), numbering (`1.`), backticks, quotes, comments, descriptions, or trailing punctuation.
- Use the exact path as it appears in the Key Hook Point (prefer the most complete relative path available in the trace data).
- **For NEW files**: Infer the most appropriate relative path based on the existing project structure (e.g., package declarations, existing directories) and output it here.
- Do NOT include duplicates. Do NOT include any file that is only referenced but not modified.
- If no file modification is required, output a single line containing exactly: `NONE`

Output format (do not alter the marker lines):

<!-- FILES_TO_MODIFY_START -->
path/to/existing/file.ext
path/to/new/inferred_file.ext
<!-- FILES_TO_MODIFY_END -->
"""

# ==========================================
# 2. Interactive Guidance Logic
# ==========================================


def prepare_prompt(proj_path=None):
    print("# AI will modify codes")
    print("="*50)
    print("🚀 AI Secondary Development Prompt Auto Generator")
    print("="*50)
    print("Please enter the required information as prompted.\n")

    requirement = get_multiline_input(
        "🎯 1. Please enter the [Target New Feature] (e.g., add a Semaphore-based test scenario):",
        default_val="[No specific requirement provided, please let the AI analyze possible extension points in the current scenario]"
    )
    additional_info = "[No additional notes provided.]"

    other_trace_data_content = ""
    if proj_path:
        projects_dir = os.path.dirname(proj_path)
        scenarios = []
        if os.path.exists(projects_dir):
            for root, dirs, files in os.walk(projects_dir):
                if 'final-output-calltree.md' in files:
                    if os.path.abspath(root) != os.path.abspath(proj_path):
                        scenarios.append(root)

        if scenarios:
            print('\n========================================')
            print(' Select Another Scenario for Trace Data ')
            print('========================================')
            for i, scenario in enumerate(scenarios, 1):
                rel_path = os.path.relpath(scenario, projects_dir)
                print(f"  {i}. {rel_path}")
            print('========================================')

            choice = input(
                f'Enter your choice to inject reference trace (1-{len(scenarios)}, or press Enter to skip): ').strip()
            if choice.isdigit() and 1 <= int(choice) <= len(scenarios):
                selected_scenario_dir = scenarios[int(choice) - 1]
                trace_file_path = os.path.join(
                    selected_scenario_dir, 'final-output-calltree.md')
                flow_file_path = os.path.join(
                    selected_scenario_dir, 'execution_flow_with_code.md')

                try:
                    with open(trace_file_path, 'r', encoding='utf-8') as tf:
                        trace_data = tf.read()

                    flow_data = ""
                    if os.path.exists(flow_file_path):
                        try:
                            with open(flow_file_path, 'r', encoding='utf-8') as ff:
                                flow_data = ff.read()
                        except Exception as fe:
                            print(
                                f"[!] Failed to read execution flow from reference scenario: {fe}")

                    other_trace_data_header = f"\n\n=========================================\n### Trace Data from Other Scenario: {os.path.basename(selected_scenario_dir)}\n> **Note**: This is runtime data from another scenario and may be helpful as a reference for the current implementation requirements.\n=========================================\n"
                    other_trace_data_content = other_trace_data_header + \
                        f"#### Call Tree. {CALL_TREE_DESC}:\n" + trace_data

                    if flow_data:
                        other_trace_data_content += f"\n\n#### Execution Flow with Code. {EXEC_FLOW_DESC}:\n" + flow_data
                    else:
                        other_trace_data_content += "\n\n#### Execution Flow with Code:\n[No execution flow with code data found in this scenario.]"

                    reference_note = "\n=========================================\n"
                    other_trace_data_content += reference_note
                    print(
                        f"[+] Successfully scheduled reference trace data and execution flow from {os.path.basename(selected_scenario_dir)} for injection.")
                except Exception as e:
                    print(
                        f"[!] Failed to read trace data from reference scenario: {e}")
            else:
                print('[!] Skipping reference trace data injection.')
        else:
            print('[Info] No other reference scenarios found in projects directory.')

    return {
        "requirement": requirement,
        "additional_info": additional_info,
        "other_trace_data": other_trace_data_content
    }


def generate_prompt_with_context(cli_file_path, context):
    if not context:
        context = prepare_prompt()

    requirement = context.get("requirement", "")
    additional_info = context.get("additional_info", "")
    other_trace_data = context.get("other_trace_data", "")

    if not other_trace_data:
        other_trace_data = ""

    trace_data, execution_flow_data = load_trace_and_flow_data(cli_file_path)

    formatted_template = PROMPT_TEMPLATE.format(
        call_tree_desc=CALL_TREE_DESC,
        exec_flow_desc=EXEC_FLOW_DESC
    )

    final_prompt = formatted_template.format(
        requirement=requirement,
        additional_info=additional_info,
        trace_data=trace_data,
        execution_flow_data=execution_flow_data,
        other_trace_data=other_trace_data
    )

    save_prompt_to_file(final_prompt)


def generate_prompt(cli_file_path=None):
    context = prepare_prompt()
    generate_prompt_with_context(cli_file_path, context)


def main():
    cli_file_path = sys.argv[1] if len(sys.argv) > 1 else None
    generate_prompt(cli_file_path)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 Operation cancelled by user.")
        sys.exit(0)
