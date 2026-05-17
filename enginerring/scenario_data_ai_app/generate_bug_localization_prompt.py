#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
from editor_util import get_multiline_input_via_editor

#AI will modify codes

# ==========================================
# 1. Define Prompt Templates
# ==========================================
# Full template with concurrency analysis
FULL_PROMPT_TEMPLATE = """# Code Bug Localization and Root Cause Analysis Task

You are a senior software architect and debugging expert. Based on the provided zero-noise runtime trace data and synchronization dependencies, please help me perform deterministic factual backtracking to locate the root cause of a bug.

---

## 📋 Bug Symptom & Context

**🐞 Observable Symptom / Anomaly**: 
{requirement}

**💬 Additional Notes (Suspected variables, specific thread IDs, etc.)**: 
{additional_info}

---

## 🔍 Zero-Noise Scenario Runtime Data

The following data comes from real system runtime trace logs. It is a "zero-noise" factual record of the specific execution scenario that triggered the bug. It contains:
1. **Call Tree**: The exact sequence of executed basic blocks, pruned source code, and method signatures. Unexecuted branches are entirely removed.
2. **Happens-Before & Data Races (If applicable)**: Explicit synchronization edges and unsynchronized concurrent accesses between threads.
3. **Important Premise**: Please reason entirely based on this factual data. **Do not guess or fabricate** execution paths. If a piece of code is not in the data, it did not execute.

### ✅ [Runtime Evidence] Complete Execution Data
=========================================
{trace_data}
=========================================

---

## 🎯 Diagnostic Requirements

Please act as a factual detective. **Adhere strictly to the following analysis priority**:

1. **Call‑Tree‑First Principle**: Always begin your backtracking using the **Call Tree** evidence.
   - Trace the exact sequence of executed basic blocks backward from the symptom anchor.
   - Only if the call tree alone fails to explain the observed anomaly (e.g., the executed path appears logically correct but still produces wrong output), **then** consult the `Happens‑Before` and `Data Races` sections.
   - **Never assume a concurrency issue unless the trace data explicitly shows a missing synchronization edge or a stale read from a data race.**

2. **Symptom Anchor**: 
   - Locate the exact block or method in the trace data where the symptom manifested (e.g., the exception point or the final incorrect read).

3. **Factual Backtracking**: 
   - Trace the data flow and execution path backward from the symptom anchor.
   - If multithreading is involved, strictly check the `Happens-Before` and `Data Races` sections. Did a thread read stale data because a synchronization edge was missing? Was there an unexpected interleaving?

4. **Root Cause Identification**:
   - Pinpoint the exact file, function, and logical flaw that caused the execution state to diverge from expectations.

---

## ⚠️ Important Constraints

- **Fact-based only**: Your analysis must be strictly bounded by the provided runtime trace and synchronization data.
- **Complete code**: When providing the fix, you **must provide the complete class or complete method code**. Using `...` to omit original logic is strictly forbidden, ensuring the code can be copied and run directly.
- **Code precision**: Clearly specify the **file name** and **function name** where the fix is applied.

---

## 📋 Output Format Requirements

Please strictly follow the template below when providing your diagnostic report:

# Bug Localization and Fix Plan

## 1. Factual Backtracking Path
[Step-by-step trace from the symptom backward to the root cause, citing specific Thread IDs, Block IDs, or Synchronization Edges from the data]

## 2. Root Cause Analysis
- **File**: [specific file name]
- **Function**: [specific function name]
- **The Flaw**: [Explain exactly what went wrong based on the runtime facts, e.g., missing lock, incorrect branch condition, data race]

## 3. Code Fix Implementation
[Provide the complete modified code using Markdown code blocks. Add prominent comments such as `// [Bug Fix]` at the changed parts]

## 4. Verification Logic
[Briefly explain why this fix resolves the issue and how it corrects the execution flow or synchronization graph]

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

The following data comes from real system runtime trace logs. It is a "zero-noise" factual record of the specific execution scenario that triggered the bug. It contains:
- **Call Tree**: The exact sequence of executed basic blocks, pruned source code, and method signatures. Unexecuted branches are entirely removed.
- **Important Premise**: Please reason entirely based on this factual data. **Do not guess or fabricate** execution paths. If a piece of code is not in the data, it did not execute.

### ✅ [Runtime Evidence] Complete Execution Data
=========================================
{trace_data}
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
    print("#AI will modify codes")
    """
    Phase 1: Interactive prompt preparation.
    Collects user inputs before long-running tasks.
    """
    print("="*50)
    print("🕵️  AI Bug Localization Prompt Auto Generator")
    print("="*50)
    print("Please enter the required information as prompted (press Enter directly to skip optional items)\n")

    # [Modified] 0. Select analysis mode (Hardcoded to Call-Tree First)
    mode = "1"
    print("✅ [Auto-Config] Analysis Mode automatically set to: [1] Call-Tree First (concurrency sections omitted).\n")

    # 1. Collect bug symptom
    requirement = input(
        "🐞 1. Please describe the [Observable Symptom] (e.g., The event-driven aggregation test incorrectly outputs an array of zeros instead of the expected computed values because the program retrieves the results before the background tasks have finished processing them.):\n> ").strip()
    if not requirement:
        requirement = "[No specific symptom provided. Please analyze the trace data for obvious logic errors or exceptions.]"

    # 2. Collect additional notes via Editor
    additional_info = get_multiline_input_via_editor(
        step_title="Please enter [Additional Notes] (optional)",
        prompt_hint="Please provide additional file and data descriptions. For data-sensitive scenarios, it is recommended to provide I/O data examples."
    )

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

    selected_template = SIMPLE_PROMPT_TEMPLATE if mode == "1" else FULL_PROMPT_TEMPLATE

    # 3. Read trace data file
    trace_data = ""

    while True:
        if cli_file_path:
            file_path = cli_file_path
            print(f"\n📁 3. Using Call Tree File from arguments: {file_path}")
            # Reset the variable so if it fails, it will fall back to manual input
            cli_file_path = None
        else:
            # Mode-specific file hint
            if mode == "2":
                file_hint = "Call Tree File With Concurrency (e.g., ../../final-output-combined.md)"
            else:
                file_hint = "Call Tree File (e.g., ../../final-output-calltree.md)"

            file_path = input(
                f"\n📁 3. Please enter the path to the [{file_hint}]:\n> ").strip()
            # Remove possible quotes (common when dragging a file into the terminal)
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
            break
        except Exception as e:
            print(f"❌ Failed to read file: {e}")
            continue

    # 4. Assemble the final prompt
    final_prompt = selected_template.format(
        requirement=requirement,
        additional_info=additional_info,
        trace_data=trace_data
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
