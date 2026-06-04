#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from editor_util import get_multiline_input

from prompt_common import RUNTIME_DATA_DESC, load_trace_and_flow_data, save_prompt_to_file

"""
AI will modify codes
"""

# ==========================================
# 1. Define Prompt Template
# ==========================================
PROMPT_TEMPLATE = f"""# Code Secondary Development and Feature Extension Guidance Task

You are a senior software architect and code development expert. Based on the existing code execution trace data, please guide me and help me implement new feature requirements.

---

## 📋 Requirement Definition

**🎯 Target New Feature**: 
{{requirement}}

**💬 Additional Notes (Optional)**: 
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
- **Code precision**: You must clearly specify the **file name** and **function name** being modified.

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


def prepare_prompt():
    print("#AI will modify codes")
    print("="*50)
    print("🚀 AI Secondary Development Prompt Auto Generator")
    print("="*50)
    print("Please enter the required information as prompted.\n")

    requirement = get_multiline_input(
        "🎯 1. Please enter the [Target New Feature] (e.g., add a Semaphore-based test scenario):",
        default_val="[No specific requirement provided, please let the AI analyze possible extension points in the current scenario]"
    )
    additional_info = "[No additional notes provided.]"

    return {
        "requirement": requirement,
        "additional_info": additional_info
    }


def generate_prompt_with_context(cli_file_path, context):
    if not context:
        context = prepare_prompt()

    requirement = context.get("requirement", "")
    additional_info = context.get("additional_info", "")

    trace_data, execution_flow_data = load_trace_and_flow_data(cli_file_path)

    final_prompt = PROMPT_TEMPLATE.format(
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
