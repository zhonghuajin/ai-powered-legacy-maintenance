import os

RUNTIME_DATA_DESC = """## 🔍 Scenario Runtime Data Description

The following data comes from real system runtime trace logs. It is a "zero-noise" factual record of the specific execution scenario that triggered the bug.

⚠️ **Core Concept**:
The **[Call Tree]** and the **[Execution Flow with Source Code]** provided below are **two different representations of the exact same execution run**. They are completely equivalent and complementary in terms of timeline, thread allocation, and execution logic:
- **Call Tree**: Reflects the runtime appearance order of files, sorted by thread within the current scenario, along with their intra-file function call relationships. Within each thread, files are sorted by their runtime appearance order.
- **Execution Flow with Source Code**: Reflects the runtime appearance order of functions, sorted and presented by thread within the current scenario, along with their source code.
Please analyze them in tandem to reconstruct the complete execution context.

⚠️ **Important Premise**:
- Please reason entirely based on this factual data. **Do not guess, extrapolate, or fabricate** execution paths.
- If a piece of code, branch, or function is not present in the data below, **it did not execute** in this specific scenario."""

def load_trace_and_flow_data(cli_file_path):
    trace_data = ""
    execution_flow_data = ""

    while True:
        if cli_file_path:
            file_path = cli_file_path
            print(f"\n📁 2. Using Call Chain Data File from arguments: {file_path}")
            cli_file_path = None
        else:
            file_path = input(
                "\n📁 2. Please enter the path to the [Call Chain Data File] (e.g., final-output-calltree.md):\n> "
            ).strip()
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

            dir_name = os.path.dirname(os.path.abspath(file_path))
            flow_path = os.path.join(dir_name, "execution_flow_with_code.md")

            if os.path.exists(flow_path):
                print(f"📁 Auto-detected execution flow file in the same directory: {flow_path}")
                with open(flow_path, 'r', encoding='utf-8') as f_flow:
                    execution_flow_data = f_flow.read()
                print("✅ Successfully loaded the execution flow with code data!")
            else:
                print(f"⚠️ Warning: 'execution_flow_with_code.md' not found in {dir_name}.")
                manual_flow_path = input(
                    "👉 Please enter the path to [execution_flow_with_code.md] manually (or press Enter to skip):\n> "
                ).strip().strip('\'"')
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

    return trace_data, execution_flow_data

def save_prompt_to_file(final_prompt, output_filename="AI_Task_Prompt.md"):
    try:
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(final_prompt)
        print("\n" + "="*50)
        print(f"🎉 Success! The complete prompt has been generated and saved in the current directory as: {output_filename}")
        print("👉 You can now open this file directly, copy all its contents, and send them to the AI!")
        print("="*50)
    except Exception as e:
        print(f"\n❌ Failed to save file: {e}")