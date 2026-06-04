#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from editor_util import get_multiline_input

from prompt_common import RUNTIME_DATA_DESC, load_trace_and_flow_data, save_prompt_to_file

# ==========================================
# 1. Define Prompt Template
# ==========================================
PROMPT_TEMPLATE = f"""# Scenario Requirement Inclusion Analysis Task

You are an expert system analyst. Your task is to analyze whether the user's specific requirement is covered or executed within the provided scenario runtime trace data.

---

## 📋 Requirement Definition

**🎯 Target Requirement to Analyze**: 
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

## 🎯 Analysis Requirements

Please deeply analyze the complete execution chain of the above scenario and answer the following questions:

1. **Inclusion & Match Analysis**:
   - Does the provided scenario trace (Call Tree / Execution Flow) contain or execute the logic requested in the **Target Requirement**?
   - Identify any specific classes, methods, or execution steps in the trace that directly relate to the requirement.
2. **Execution Gap Identification**:
   - If the requirement is NOT fully covered, what parts of the execution flow are missing from this scenario?
   - Which branch or condition in the source code prevented the target requirement logic from being executed?
3. **Evidence Extraction**:
   - Provide concrete code snippets or call tree paths from the trace data above to support your conclusion.

---

## ⚠️ Important Constraints

- **Fact-based only**: Analysis must be based only on the provided call chain data. Do not assume or extrapolate.
- **No code modification**: This task is purely analytical. Do not provide code modifications or implementation plans.

---

## 📋 Output Format Requirements

Please strictly follow the template below when providing the analysis report:

# Scenario Requirement Inclusion Analysis Report

## 1. Executive Summary
[State clearly whether the requirement is fully included, partially included, or completely absent from the scenario]

## 2. Detailed Matching Analysis
- **Matched Components**: [List specific files, functions, or lines of code that match the requirement]
- **Execution Path Evidence**: [Explain how the execution flow reaches or bypasses the requirement logic]

## 3. Missing Elements & Gaps
[Explain what is missing from the current trace to satisfy the requirement, if applicable]

"""


def prepare_prompt():
    print("#AI will modify codes")
    print("="*50)
    print("🔍 Scenario Requirement Inclusion Analyzer")
    print("="*50)
    print("Please enter the required information as prompted.\n")

    requirement = get_multiline_input(
        "🎯 1. Please enter the [Target Requirement to Analyze]:",
        default_val="[No specific requirement provided, please analyze the general flow of the scenario]"
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
