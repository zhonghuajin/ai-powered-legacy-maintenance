#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys

# AI will modify codes

# ==========================================
# 0. Define Global Descriptions (To Avoid Redundancy)
# ==========================================
CALL_TREE_DESC = "Reflects the runtime appearance order of files, sorted by thread within the current scenario, along with their intra-file function call relationships."
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

## 🔍 Scenario Call Chain Data Description

The following data comes from real system runtime trace logs and contains the following core information:
1. **Trace Sequence**: A linear sequence of basic blocks executed by the thread.
2. **Call Tree (`final-output-calltree.md`)**: {call_tree_desc}
3. **Execution Flow with Code (`execution_flow_with_code.md`)**: {exec_flow_desc}
4. **Important Premise**: The data only contains code that was **actually executed**. If a piece of code does not appear in the data, it means it was not executed in this scenario. Please reason entirely based on this factual data and **never fabricate** nonexistent code structures.

### ✅ [Reference Scenario] Complete Call Chain Data (Call Tree)
=========================================
{{trace_data}}
=========================================

### 📝 [Reference Scenario] Detailed Execution Flow with Source Code
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

## 4. Potential Risks and Notes
[List side effects, concurrency hazards, or performance issues to watch out for during development]

## 5. Files To Modify (Machine-Readable Summary)

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


def get_multiline_input(prompt_title, default_val=""):
    """
    Generic function to get multiline inputs from the console.
    """
    print(f"\n{prompt_title}")
    print("👉 Instruction: You can press [Enter] to start a new line.")
    print(
        "   To finish, press [Enter] twice consecutively, or type ':q' on a new line.")
    print("-" * 60)

    lines = []
    empty_count = 0

    while True:
        try:
            line = input()
            if line.strip() == ':q':
                break
            if line == '':
                empty_count += 1
                if empty_count >= 2:
                    break
            else:
                empty_count = 0
            lines.append(line)
        except EOFError:
            break

    while lines and lines[-1] == '':
        lines.pop()

    result = "\n".join(lines).strip()
    print("-" * 60 + "\n✅ Input saved successfully!\n")

    if not result:
        return default_val
    return result


def prepare_prompt(proj_path=None): # ✨ [Added] Added optional parameter proj_path to support precise scan scenario
    print("# AI will modify codes")
    """
    Phase 1: Interactive prompt preparation.
    Collects user inputs before long-running tasks.
    """
    print("="*50)
    print("🚀 AI Secondary Development Prompt Auto Generator")
    print("="*50)
    print("Please enter the required information as prompted.\n")

    # 1. Collect target feature (supporting multiline input)
    requirement = get_multiline_input(
        "🎯 1. Please enter the [Target New Feature] (e.g., add a Semaphore-based test scenario):",
        default_val="[No specific requirement provided, please let the AI analyze possible extension points in the current scenario]"
    )

    # 2. Skip additional notes step
    additional_info = "[No additional notes provided.]"

    # ✨ [Added] Advance interaction for Select Another Scenario for Trace Data
    other_trace_data_content = ""
    if proj_path:
        # proj_path usually follows the structure: work_dir/projects/project_name
        # we can locate the projects directory via its parent directory
        projects_dir = os.path.dirname(proj_path)
        scenarios = []
        if os.path.exists(projects_dir):
            for root, dirs, files in os.walk(projects_dir):
                if 'final-output-calltree.md' in files:
                    # Exclude the currently running scenario directory itself
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

            choice = input(f'Enter your choice to inject reference trace (1-{len(scenarios)}, or press Enter to skip): ').strip()
            if choice.isdigit() and 1 <= int(choice) <= len(scenarios):
                selected_scenario_dir = scenarios[int(choice) - 1]
                trace_file_path = os.path.join(selected_scenario_dir, 'final-output-calltree.md')
                flow_file_path = os.path.join(selected_scenario_dir, 'execution_flow_with_code.md')

                try:
                    # 1. Read call tree data
                    with open(trace_file_path, 'r', encoding='utf-8') as tf:
                        trace_data = tf.read()

                    # 2. Read execution flow data (if exists)
                    flow_data = ""
                    if os.path.exists(flow_file_path):
                        try:
                            with open(flow_file_path, 'r', encoding='utf-8') as ff:
                                flow_data = ff.read()
                        except Exception as fe:
                            print(f"[!] Failed to read execution flow from reference scenario: {fe}")

                    other_trace_data_header = f"\n\n=========================================\n### Trace Data from Other Scenario: {os.path.basename(selected_scenario_dir)}\n> **Note**: This is runtime data from another scenario and may be helpful as a reference for the current implementation requirements.\n=========================================\n"
                    
                    # Append call tree data (using global constant CALL_TREE_DESC)
                    other_trace_data_content = other_trace_data_header + f"#### Call Tree. {CALL_TREE_DESC}:\n" + trace_data
                    
                    # ✨ [Modified] Inject execution_flow_with_code.md data from the same directory (using global constant EXEC_FLOW_DESC)
                    if flow_data:
                        other_trace_data_content += f"\n\n#### Execution Flow with Code. {EXEC_FLOW_DESC}:\n" + flow_data
                    else:
                        other_trace_data_content += "\n\n#### Execution Flow with Code:\n[No execution flow with code data found in this scenario.]"

                    reference_note = "\n=========================================\n"
                    other_trace_data_content += reference_note
                    
                    print(f"[+] Successfully scheduled reference trace data and execution flow from {os.path.basename(selected_scenario_dir)} for injection.")
                except Exception as e:
                    print(f"[!] Failed to read trace data from reference scenario: {e}")
            else:
                print('[!] Skipping reference trace data injection.')
        else:
            print('[Info] No other reference scenarios found in projects directory.')

    return {
        "requirement": requirement,
        "additional_info": additional_info,
        "other_trace_data": other_trace_data_content # ✨ [Added] Store in context and pass to Phase 2
    }


def generate_prompt_with_context(cli_file_path, context):
    """
    Phase 2: Generate the final prompt using the collected context and trace data.
    """
    if not context:
        context = prepare_prompt()

    requirement = context.get("requirement", "")
    additional_info = context.get("additional_info", "")
    # ✨ [Added] Extract reference trace data pre-selected in Phase 1 from context
    other_trace_data = context.get("other_trace_data", "")

    # Fallback to empty string if context does not contain it
    if not other_trace_data:
        other_trace_data = ""

    # 3. Read trace data file
    trace_data = ""
    execution_flow_data = ""

    while True:
        if cli_file_path:
            file_path = cli_file_path
            print(
                f"\n📁 2. Using Call Chain Data File from arguments: {file_path}")
            cli_file_path = None
        else:
            file_path = input(
                "\n📁 2. Please enter the path to the [Call Chain Data File] (e.g., final-output-calltree.md):\n> ").strip()
            # Remove possible quotes
            file_path = file_path.strip('\'"')

        if not file_path:
            print("❌ File path cannot be empty. Please enter it again!")
            continue

        if not os.path.exists(file_path):
            print(
                f"❌ File not found: {file_path}. Please check whether the path is correct!")
            continue

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                trace_data = f.read()
            print("✅ Successfully loaded the call chain data!")

            # Auto-detect execution_flow_with_code.md in the same directory
            dir_name = os.path.dirname(os.path.abspath(file_path))
            flow_path = os.path.join(dir_name, "execution_flow_with_code.md")

            if os.path.exists(flow_path):
                print(
                    f"📁 Auto-detected execution flow file in the same directory: {flow_path}")
                with open(flow_path, 'r', encoding='utf-8') as f_flow:
                    execution_flow_data = f_flow.read()
                print("✅ Successfully loaded the execution flow with code data!")
            else:
                print(
                    f"⚠️ Warning: 'execution_flow_with_code.md' not found in {dir_name}.")
                manual_flow_path = input(
                    "👉 Please enter the path to [execution_flow_with_code.md] manually (or press Enter to skip):\n> ").strip().strip('\'"')
                if manual_flow_path and os.path.exists(manual_flow_path):
                    with open(manual_flow_path, 'r', encoding='utf-8') as f_flow:
                        execution_flow_data = f_flow.read()
                    print("✅ Successfully loaded the execution flow with code data!")
                else:
                    print("⚠️ Skipped loading execution flow data.")
                    execution_flow_data = "[No execution flow with code data provided.]"
            break
        except Exception as e:
            print(f"❌ Failed to read file: {e}")
            continue

    # 4. Assemble the final prompt (formatting global descriptions dynamically)
    formatted_template = PROMPT_TEMPLATE.format(
        call_tree_desc=CALL_TREE_DESC,
        exec_flow_desc=EXEC_FLOW_DESC
    )
    
    final_prompt = formatted_template.format(
        requirement=requirement,
        additional_info=additional_info,
        trace_data=trace_data,
        execution_flow_data=execution_flow_data,
        other_trace_data=other_trace_data # Fill in reference trace data
    )

    # 5. Write to file
    output_filename = "AI_Task_Prompt.md"
    try:
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(final_prompt)
        print("\n" + "="*50)
        print(
            f"🎉 Success! The complete prompt has been generated and saved in the current directory as: {output_filename}")
        print("👉 You can now open this file directly, copy all its contents, and send them to the AI!")
        print("="*50)
    except Exception as e:
        print(f"\n❌ Failed to save file: {e}")


def generate_prompt(cli_file_path=None):
    """
    Legacy wrapper for backward compatibility.
    Executes both phases sequentially.
    """
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