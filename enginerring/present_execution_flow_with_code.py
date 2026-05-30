import os
import re
import argparse

def parse_calltree(filepath):
    """
    Parse final-output-calltree.md to extract method signatures and their corresponding source code
    """
    code_map = {}
    if not os.path.exists(filepath):
        print(f"[-] Error: Cannot find calltree file: {filepath}")
        return code_map

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    method_header_re = re.compile(r'-\s+\*\*Method:\*\*\s+`([^`]+)`')

    pos = 0
    while True:
        match = method_header_re.search(content, pos)
        if not match:
            break

        sig = match.group(1).strip()
        start_idx = match.end()

        code_start = content.find("```php", start_idx)
        next_match = method_header_re.search(content, start_idx)

        if next_match and (code_start == -1 or next_match.start() < code_start):
            pos = start_idx
            continue

        if code_start != -1:
            code_end = content.find("```", code_start + 6)
            if code_end != -1:
                code_text = content[code_start + 6:code_end].strip()
                code_map[sig] = code_text
                pos = code_end + 3
            else:
                pos = start_idx
        else:
            pos = start_idx

    return code_map

def generate_flow_report(signature_file, calltree_file, output_file):
    """
    Generate final report based on execution order and source code mapping
    """
    if not os.path.exists(signature_file):
        print(f"[-] Error: Cannot find signature order file: {signature_file}")
        return

    print("[+] Start parsing calltree source code...")
    code_map = parse_calltree(calltree_file)
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

        if signature in code_map:
            code = code_map[signature]
            markdown_lines.append("```php")
            markdown_lines.append(code)
            markdown_lines.append("```\n")
        else:
            markdown_lines.append("```php")
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
    parser.add_argument("-o", "--output", default="execution_flow_with_code.md", help="Path to output markdown file (default: execution_flow_with_code.md)")

    args = parser.parse_args()
    generate_flow_report(args.signature, args.calltree, args.output)