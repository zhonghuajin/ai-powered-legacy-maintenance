#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys

from editor_util import get_multiline_input

"""
AI will modify codes
"""

# ==========================================
# 1. Define Prompt Templates
# ==========================================
# Simplified template (Call-Tree only, concurrency sections removed)
SIMPLE_PROMPT_TEMPLATE = """# Code Bug Localization and Root Cause Analysis Task

You are a senior software architect and debugging expert. Based on the provided zero-noise runtime trace data, please help me perform deterministic factual backtracking to locate the root cause of a bug.

---

## 📋 Bug Symptom & Context

**🐞 Observable Symptom / Anomaly**: 
{requirement}

**💬 Additional Notes**: 
{additional_info}

---

## 🔍 Zero-Noise Scenario Runtime Data

The following data comes from real system runtime trace logs. It is a "zero-noise" factual record of the specific execution scenario that triggered the bug. 

⚠️ **Core Concept**:
The **[Call Tree]** and the **[Execution Flow with Source Code]** provided below are **two different representations of the exact same execution run**. They are completely equivalent and complementary in terms of timeline, thread allocation, and execution logic:
- **Call Tree**: Reflects the runtime appearance order of files, sorted by thread within the current scenario, along with their intra-file function call relationships. Within each thread, files are sorted by their runtime appearance order.
- **Execution Flow with Source Code**: Reflects the runtime appearance order of functions, sorted and presented by thread within the current scenario, along with their source code.
Please analyze them in tandem to reconstruct the complete execution context.

⚠️ **Important Premise**:
- Please reason entirely based on this factual data. **Do not guess, extrapolate, or fabricate** execution paths. 
- If a piece of code, branch, or function is not present in the data below, **it did not execute** in this specific scenario.


### ✅ Call Tree
> *Note: Reflects file-level call hierarchies grouped by thread. Within each thread, files are sorted by their runtime appearance order.*
=========================================
{trace_data}
=========================================

### 📝 Execution Flow with Source Code
> *Note: Reflects step-by-step function execution details and actual source code context.*
=========================================
{execution_flow_data}
=========================================

---

## 🎯 Diagnostic Requirements

Please act as a factual detective. **Focus exclusively on the Call Tree evidence**:

1. **Symptom Anchor**: 
   - Locate the exact block or method in the call tree where the symptom manifested (e.g., the exception point or the final incorrect read).

2. **Factual Backtracking**: 
   - Trace the data flow and execution path backward along the call tree from the symptom anchor.
   - Identify where the execution state diverged from expected behavior.

3. **Root Cause Identification**:
   - Pinpoint the exact file, function, and logical flaw that caused the issue.

---

## ⚠️ Important Constraints

- **Fact-based only**: Your analysis must be strictly bounded by the provided call tree.
- **Complete code**: When providing the fix, you **must provide the complete class or complete method code**. Using `...` to omit original logic is strictly forbidden.
- **Code precision**: Clearly specify the **file name** and **function name** where the fix is applied.

---

## 📋 Output Format Requirements

# Bug Localization and Fix Plan

## 1. Factual Backtracking Path
[Step-by-step trace from the symptom backward to the root cause, citing specific Block IDs from the call tree]

## 2. Root Cause Analysis
- **File**: [specific file name]
- **Function**: [specific function name]
- **The Flaw**: [Explain exactly what went wrong based on the call tree execution]

## 3. Code Fix Implementation
[Provide the complete modified code using Markdown code blocks. Add prominent comments such as `// [Bug Fix]` at the changed parts]

## 4. Verification Logic
[Briefly explain why this fix resolves the issue]

## 5. Files To Modify (Machine-Readable Summary)

Summarize **all** files that must be modified based on the Root Cause Analysis above. This section is intended for automated parsing, so it MUST strictly follow these rules:

- Enclose the list between the two exact marker lines shown below.
- One file path per line, nothing else on that line.
- Output the **raw file path only**. Do NOT add bullets (`-`, `*`), numbering (`1.`), backticks, quotes, comments, descriptions, or trailing punctuation.
- Use the exact path as it appears in the Root Cause Analysis (prefer the most complete relative path available in the trace data).
- Do NOT include duplicates. Do NOT include any file that is only referenced but not modified.
- If no file modification is required, output a single line containing exactly: `NONE`

Output format (do not alter the marker lines):

<!-- FILES_TO_MODIFY_START -->
path/to/first/file.ext
path/to/second/file.ext
<!-- FILES_TO_MODIFY_END -->
"""

# ==========================================
# 2. Interactive Guidance Logic
# ==========================================

def prepare_prompt():
    print("# AI will modify codes")
    """
    Phase 1: Interactive prompt preparation.
    Collects user inputs before long-running tasks.
    """
    print("="*50)
    print("🕵️  AI Bug Localization Prompt Auto Generator")
    print("="*50)
    print("Please enter the required information as prompted.\n")

    # [Auto-Config] Analysis Mode automatically set to: Call-Tree First
    mode = "1"
    print("✅ [Auto-Config] Analysis Mode automatically set to: [1] Call-Tree First (concurrency sections omitted).\n")

    # 1. Collect bug symptom (using multiline input function)
    requirement = get_multiline_input(
        "🐞 1. Please describe the [Observable Symptom] (e.g., The event-driven aggregation test...):",
        default_val="[No specific symptom provided. Please analyze the trace data for obvious logic errors or exceptions.]"
    )

    # 2. Additional notes step is skipped now. Defaulting to an empty string.
    additional_info = "[No additional notes provided.]"

    return {
        "requirement": requirement,
        "additional_info": additional_info,
        "mode": mode
    }

def generate_prompt_with_context(cli_file_path, context):
    """
    Phase 2: Generate the final prompt using the collected context and trace data.
    """
    if not context:
        context = prepare_prompt()

    requirement = context.get("requirement", "")
    additional_info = context.get("additional_info", "")
    mode = context.get("mode", "1")

    # 3. Read trace data file
    trace_data = ""
    execution_flow_data = ""

    while True:
        if cli_file_path:
            file_path = cli_file_path
            print(f"\n📁 2. Using Call Tree File from arguments: {file_path}")
            cli_file_path = None
        else:
            file_hint = "Call Tree File (e.g., ../../final-output-calltree.md)"
            file_path = input(
                f"\n📁 2. Please enter the path to the [{file_hint}]:\n> ").strip()
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
            print("✅ Successfully loaded the runtime trace data!")

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

    # 4. Assemble the final prompt
    final_prompt = SIMPLE_PROMPT_TEMPLATE.format(
        requirement=requirement,
        additional_info=additional_info,
        trace_data=trace_data,
        execution_flow_data=execution_flow_data
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