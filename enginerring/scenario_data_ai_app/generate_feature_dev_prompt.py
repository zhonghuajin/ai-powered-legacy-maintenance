#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys

# ==========================================
# 1. Define Prompt Template
# ==========================================
PROMPT_TEMPLATE = """# Code Secondary Development and Feature Extension Guidance Task

You are a senior software architect and code development expert. Based on the existing code execution trace data, please guide me and help me implement new feature requirements.

---

## 📋 Requirement Definition

**🎯 Target New Feature**: 
{target_feature}

**💬 Additional Notes (Optional)**: 
{additional_info}

---

## 🔍 Scenario Call Chain Data Description

The following data comes from real system runtime trace logs and contains the following core information:
1. **Trace Sequence**: A linear sequence of basic blocks executed by the thread.
2. **Call Tree**: Includes method signatures, source files, executed Block IDs, and **pruned source code**.
3. **Important Premise**: The data only contains code that was **actually executed**. If a piece of code does not appear in the data, it means it was not executed in this scenario. Please reason entirely based on this factual data and **never fabricate** nonexistent code structures.

### ✅ [Reference Scenario] Complete Call Chain Data
=========================================
{trace_data}
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

## 4. Potential Risks and Notes
[List side effects, concurrency hazards, or performance issues to watch out for during development]

## 5. Files To Modify (Machine-Readable Summary)

Summarize **all** files that must be modified based on the Key Hook Point above. This section is intended for automated parsing, so it MUST strictly follow these rules:

- Enclose the list between the two exact marker lines shown below.
- One file path per line, nothing else on that line.
- Output the **raw file path only**. Do NOT add bullets (`-`, `*`), numbering (`1.`), backticks, quotes, comments, descriptions, or trailing punctuation.
- Use the exact path as it appears in the Key Hook Point (prefer the most complete relative path available in the trace data).
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
def generate_prompt(cli_file_path=None):
    print("="*50)
    print("🚀 AI Secondary Development Prompt Auto Generator")
    print("="*50)
    print("Please enter the required information as prompted (press Enter directly to skip optional items)\n")

    # 1. Collect target feature
    target_feature = input("🎯 1. Please enter the [Target New Feature] (e.g., add a Semaphore-based test scenario):\n> ").strip()
    if not target_feature:
        target_feature = "[No specific requirement provided, please let the AI analyze possible extension points in the current scenario]"

    # 2. Collect additional notes
    additional_info = input("\n💬 2. Please enter [Additional Notes] (optional, e.g., must use JDK 8, no external dependencies allowed):\n> ").strip()
    if not additional_info:
        additional_info = "No special additional notes. Please follow general best practices."

    # 3. Read trace data file
    trace_data = ""
    while True:
        if cli_file_path:
            file_path = cli_file_path
            print(f"\n📁 3. Using Call Chain Data File from arguments: {file_path}")
            cli_file_path = None
        else:
            file_path = input("\n📁 3. Please enter the path to the [Call Chain Data File] (e.g., final-output-calltree.md):\n> ").strip()
            # Remove possible quotes (common when dragging a file into the terminal)
            file_path = file_path.strip('\'"')
        
        if not file_path:
            print("❌ File path cannot be empty. Please enter it again!")
            continue
            
        if not os.path.exists(file_path):
            print(f"❌ File not found: {file_path}. Please check whether the path is correct!")
            continue
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                trace_data = f.read()
            print("✅ Successfully loaded the call chain data!")
            break
        except Exception as e:
            print(f"❌ Failed to read file: {e}")
            continue

    # 4. Assemble the final prompt
    final_prompt = PROMPT_TEMPLATE.format(
        target_feature=target_feature,
        additional_info=additional_info,
        trace_data=trace_data
    )

    # 5. Write to file
    # [Modified] Unified output filename for downstream processing
    output_filename = "AI_Task_Prompt.md"
    try:
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(final_prompt)
        print("\n" + "="*50)
        print(f"🎉 Success! The complete prompt has been generated and saved in the current directory as: {output_filename}")
        print("👉 You can now open this file directly, copy all its contents, and send them to the AI!")
        print("="*50)
    except Exception as e:
        print(f"\n❌ Failed to save file: {e}")

def main():
    cli_file_path = sys.argv[1] if len(sys.argv) > 1 else None
    generate_prompt(cli_file_path)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 Operation cancelled by user.")
        sys.exit(0)