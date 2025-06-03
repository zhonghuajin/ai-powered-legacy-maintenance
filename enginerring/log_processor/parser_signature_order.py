import re
import os
import argparse

__all__ = ['analyze_thread_flow']

def parse_method_range(file_path):
    """
    Parse method-range.txt
    Returns: { method_signature: (file_path, start_line, end_line) }
    """
    method_map = {}
    if not os.path.exists(file_path):
        print(f"Warning: File not found {file_path}")
        return method_map

    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            try:
                parts = line.split('|')
                file_abs_path = parts[0].strip()
                right_part = parts[1].strip()
                method_name, line_range = right_part.split('=')
                method_name = method_name.strip()
                start_line, end_line = map(int, line_range.strip().split('-'))
                method_map[method_name] = (file_abs_path, start_line, end_line)
            except Exception as e:
                continue
    return method_map

def parse_block_signature(file_path):
    """
    Parse block-signature.txt
    Returns: { block_id: method_signature }
    """
    block_sig_map = {}
    if not os.path.exists(file_path):
        print(f"Warning: File not found {file_path}")
        return block_sig_map

    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            try:
                block_id_str, sig = line.split('=', 1)
                block_id = int(block_id_str.strip())
                block_sig_map[block_id] = sig.strip()
            except Exception as e:
                continue
    return block_sig_map

def parse_block_line_mapping(file_path):
    """
    Parse block-line-mapping.txt
    Returns: { block_id: (file_path, line_number) }
    """
    block_line_map = {}
    if not os.path.exists(file_path):
        print(f"Warning: File not found {file_path}")
        return block_line_map

    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            try:
                block_id_str, path_line = line.split('=', 1)
                block_id = int(block_id_str.strip())
                file_path_abs, line_num_str = path_line.rsplit(':', 1)
                block_line_map[block_id] = (file_path_abs.strip(), int(line_num_str.strip()))
            except Exception as e:
                continue
    return block_line_map

def parse_instrumentor_log(file_path):
    """
    Parse instrumentor-log-*.txt
    Returns: [ (thread_name, [block_id_1, block_id_2, ...]) ]
    """
    threads_data = []
    if not os.path.exists(file_path):
        print(f"Warning: File not found {file_path}")
        return threads_data

    current_thread = None
    current_blocks = []

    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            thread_match = re.match(r'^\[([^\]]+)\]', line)
            if thread_match:
                if current_thread:
                    threads_data.append((current_thread, current_blocks))
                current_thread = thread_match.group(1)
                current_blocks = []
            else:
                blocks = [int(b.strip()) for b in line.split('->') if b.strip().isdigit()]
                current_blocks.extend(blocks)

        if current_thread:
            threads_data.append((current_thread, current_blocks))

    return threads_data

def analyze_thread_flow(log_file, block_signature_file, block_line_mapping_file):
    """
    Exposed API to analyze thread flow and generate signature_order.txt in CWD.
    """
    block_signatures = parse_block_signature(block_signature_file)
    block_lines = parse_block_line_mapping(block_line_mapping_file)

    # Parse execution log
    threads_logs = parse_instrumentor_log(log_file)

    output_lines = []
    for thread_name, blocks in threads_logs:
        flow = []
        for b_id in blocks:
            sig = block_signatures.get(b_id, f"Unknown_Block_{b_id}")
            file, line = block_lines.get(b_id, ("Unknown_File", "Unknown_Line"))
            flow.append((sig, file, line))

        # Merge adjacent duplicate calls.
        # Two consecutive entries are considered the same call only when BOTH
        # the signature AND the file match, so that two different files that
        # happen to share a signature are not collapsed together.
        dedup_flow = []
        for sig, file, line in flow:
            if not dedup_flow or dedup_flow[-1][0] != sig or dedup_flow[-1][1] != file:
                dedup_flow.append((sig, file, line))

        # Output: signature | full file path | start line of the block.
        # The line number lets the downstream report match the exact code block
        # even when many blocks share the signature 'anonymous'.
        for sig, file, line in dedup_flow:
            output_lines.append(f"{sig} | {file} | {line}\n")

    # Write to signature_order.txt in the current working directory
    output_path = os.path.join(os.getcwd(), "signature_order.txt")
    with open(output_path, "w", encoding="utf-8") as out_f:
        out_f.writelines(output_lines)

    print(f"Success: Results have been written to {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze instrumentor thread flow execution")
    parser.add_argument("log_file", help="Path to instrumentor log file")
    parser.add_argument("block_signature_file", help="Path to block signature file")
    parser.add_argument("block_line_mapping_file", help="Path to block line mapping file")

    args = parser.parse_args()

    analyze_thread_flow(args.log_file, args.block_signature_file, args.block_line_mapping_file)