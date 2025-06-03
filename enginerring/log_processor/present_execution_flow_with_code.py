import os
import re
import argparse

__all__ = ['generate_flow_report']

def parse_calltree(filepath):
    """
    Parse the calltree markdown.

    Returns:
        code_map:  { (file_path_or_None, signature): code_text }
        detected_lang: str

    The key is a tuple of (file_path, signature). When the calltree does not
    expose a file path for a given method, file_path is None and the entry can
    still be matched by signature alone.
    """
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
    file_header_re = re.compile(r'-\s+\*\*File(?:\s*Path)?:\*\*\s+`([^`]+)`')

    pos = 0
    while True:
        match = method_header_re.search(content, pos)
        if not match:
            break

        sig = match.group(1).strip()
        start_idx = match.end()

        next_match = method_header_re.search(content, start_idx)
        limit = next_match.start() if next_match else len(content)

        # Try to find an associated file path within this method's section.
        file_path = None
        file_match = file_header_re.search(content, start_idx, limit)
        if file_match:
            file_path = file_match.group(1).strip()

        code_block_re = re.compile(rf'```{detected_lang}\s*\n(.*?)\n\s*```', re.DOTALL)
        code_match = code_block_re.search(content, start_idx, limit)

        if code_match:
            code_text = code_match.group(1).strip()
            code_map[(file_path, sig)] = code_text
            pos = code_match.end()
        else:
            pos = start_idx

    return code_map, detected_lang

def find_best_code_match(signature, file_path, code_map):
    """
    Resolve the source code for a given (signature, file_path).

    Priority:
        1. Exact (file_path, signature) match.
        2. Exact (file_path, signature-without-'global::') match.
        3. Signature-only match (file_path None), if unambiguous.
    """
    # 1. Exact file + signature
    if (file_path, signature) in code_map:
        return code_map[(file_path, signature)]

    # 2. Tolerate the 'global::' prefix on the calltree side
    for (key_file, key_sig), code in code_map.items():
        if key_file == file_path and key_sig.replace("global::", "") == signature:
            return code

    # 3. Fall back to signature-only matching (used when the calltree has no
    #    file path). Only return it if exactly one signature matches, to avoid
    #    silently pasting the wrong 'anonymous' body.
    signature_only_hits = [
        code for (key_file, key_sig), code in code_map.items()
        if key_sig.replace("global::", "") == signature
    ]
    if len(signature_only_hits) == 1:
        return signature_only_hits[0]

    return None

def parse_signature_order_line(line):
    """
    Parse one line of signature_order.txt.

    Supports both formats:
        - "signature | file_path"               (legacy, 2 fields)
        - "signature | file_path | line_number"  (current, 3 fields)

    Returns (signature, file_path, line) or None if the line is unusable.
    """
    if '|' not in line:
        return None

    parts = [p.strip() for p in line.split('|')]
    signature = parts[0]
    file_path = parts[1] if len(parts) > 1 else ""
    line_no = parts[2] if len(parts) > 2 else ""
    return signature, file_path, line_no

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
        if not line:
            continue

        parsed = parse_signature_order_line(line)
        if not parsed:
            continue

        signature, file_path, line_no = parsed

        markdown_lines.append(f"## Step {step}: `{signature}`")
        markdown_lines.append(f"- **File Path:** `{file_path}`")
        if line_no:
            markdown_lines.append(f"- **Line:** `{line_no}`")
        markdown_lines.append("")

        code = find_best_code_match(signature, file_path, code_map)

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