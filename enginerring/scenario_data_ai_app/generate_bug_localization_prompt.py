#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from editor_util import get_multiline_input

from prompt_common import RUNTIME_DATA_DESC, load_trace_and_flow_data, save_prompt_to_file

"""
AI will modify codes
"""

# ==========================================
# 1. Define Prompt Templates
# ==========================================
SIMPLE_PROMPT_TEMPLATE = f"""# Code Bug Localization and Root Cause Analysis Task

You are a senior software architect and debugging expert. Based on the provided zero-noise runtime trace data, please help me perform deterministic factual backtracking to locate the root cause of a bug.

---

## 📋 Bug Symptom & Context

**🐞 Observable Symptom / Anomaly**: 
{{requirement}}

**💬 Additional Notes**: 
{{additional_info}}

---

{RUNTIME_DATA_DESC}

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


def prepare_prompt():
    print("# AI will modify codes")
    print("="*50)
    print("🕵️  AI Bug Localization Prompt Auto Generator")
    print("="*50)
    print("Please enter the required information as prompted.\n")

    mode = "1"
    print("✅ [Auto-Config] Analysis Mode automatically set to: [1] Call-Tree First (concurrency sections omitted).\n")

    requirement = get_multiline_input(
        "🐞 1. Please describe the [Observable Symptom] (e.g., The event-driven aggregation test...):",
        default_val="[No specific symptom provided. Please analyze the trace data for obvious logic errors or exceptions.]"
    )
    additional_info = "[No additional notes provided.]"

    return {
        "requirement": requirement,
        "additional_info": additional_info,
        "mode": mode
    }


def generate_prompt_with_context(cli_file_path, context):
    if not context:
        context = prepare_prompt()

    requirement = context.get("requirement", "")
    additional_info = context.get("additional_info", "")

    trace_data, execution_flow_data = load_trace_and_flow_data(cli_file_path)

    final_prompt = SIMPLE_PROMPT_TEMPLATE.format(
        requirement=requirement,
        additional_info=additional_info,
        trace_data=trace_data,
        execution_flow_data=execution_flow_data
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
