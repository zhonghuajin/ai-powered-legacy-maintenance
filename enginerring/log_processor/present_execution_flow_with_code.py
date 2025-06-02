import os
import re
import argparse

__all__ = ['generate_flow_report']

def parse_calltree(filepath):
    code_map = {}
    detected_lang = "php"

    if not os.path.exists(filepath):
        print(f"[-] Error: Cannot find calltree file: {filepath}")
        return code_map, detected_lang

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    lang_detect_match = re.search(r'```([a-zA-Z0-9_-]+)\n', content)
    if lang_detect_match:
        detected_lang = lang_detect_match.group(1).strip()
        print(f"[+] Detected programming language in calltree: {detected_lang}")

    method_header_re = re.compile(r'-\s+\*\*Method:\*\*\s+`([^`]+)`')

    pos = 0
    while True:
        match = method_header_re.search(content, pos)
        if not match:
            break

        sig = match.group(1).strip()
        start_idx = match.end()

        next_match = method_header_re.search(content, start_idx)
        limit = next_match.start() if next_match else len(content)

        code_block_re = re.compile(rf'```{detected_lang}\s*\n(.*?)\n\s*```', re.DOTALL)
        code_match = code_block_re.search(content, start_idx, limit)

        if code_match:
            code_text = code_match.group(1).strip()
            code_map[sig] = code_text
            pos = code_match.end()
        else:
            pos = start_idx

    return code_map, detected_lang

def find_best_code_match(signature, code_map):
    if signature in code_map:
        return code_map[signature]

    for key, code in code_map.items():
        clean_key = key.replace("global::", "")
        if clean_key == signature:
            return code

    return None

def generate_flow_report(signature_file, calltree_file, output_file):
    """
    Exposed API to generate final report based on execution order and source code mapping
    """
    if not os.path.exists(signature_file):
        print(f"[-] Error: Cannot find signature order file: {signature_file}")
        return

    print("[+] Start parsing calltree source code...")
    code_map, detected_lang = parse_calltree(calltree_file)
    print(f"[+] Successfully extracted source code for {len(code_map)} methods.")

    print("[+] Start matching execution order and generating report...")

    markdown_lines = [
        "# Thread Execution Flow with Source Code\n",
        "This document shows the sequential execution of methods with their respective source code.\n",
        "---\n"
    ]

    with open(signature_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    step = 1
    for line in lines:
        line = line.strip()
        if not line or '|' not in line:
            continue

        parts = line.split('|')
        signature = parts[0].strip()
        file_path = parts[1].strip()

        markdown_lines.append(f"## Step {step}: `{signature}`")
        markdown_lines.append(f"- **File Path:** `{file_path}`\n")

        code = find_best_code_match(signature, code_map)

        if code:
            markdown_lines.append(f"```{detected_lang}")
            markdown_lines.append(code)
            markdown_lines.append("```\n")
        else:
            markdown_lines.append(f"```{detected_lang}")
            markdown_lines.append(f"// Source code not found in calltree (e.g., default constructor or external call)")
            markdown_lines.append("```\n")

        markdown_lines.append("---\n")
        step += 1

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("\n".join(markdown_lines))

    print(f"[+] Report generated successfully! Output file: {os.path.abspath(output_file)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge signature order and calltree source code into a sequential flow report.")
    parser.add_argument("-s", "--signature", default="signature_order.txt", help="Path to signature_order.txt (default: signature_order.txt)")
    parser.add_argument("-c", "--calltree", default="final-output-calltree.md", help="Path to final-output-calltree.md (default: final-output-calltree.md)")

    args = parser.parse_args()
    generate_flow_report(args.signature, args.calltree, "execution_flow_with_code.md")