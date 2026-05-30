import re

def parse_mapping(mapping_file_path):
    """
    Parse mapping file, return a dict { block_id (int): file_path (str) }
    """
    mapping = {}

    pattern = re.compile(r'^\s*(\d+)\s*=\s*(.*?):\d+\s*$')

    with open(mapping_file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            match = pattern.match(line)
            if match:
                block_id = int(match.group(1))
                file_path = match.group(2)
                mapping[block_id] = file_path
    return mapping

def parse_log_sequence(log_file_path):
    """
    Parse log file, extract all block number sequence
    """
    sequence = []
    with open(log_file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('['):
                continue

            parts = [int(x.strip()) for x in line.split('->') if x.strip().isdigit()]
            sequence.extend(parts)
    return sequence

def analyze_file_order(log_file, mapping_file):

    mapping = parse_mapping(mapping_file)

    sequence = parse_log_sequence(log_file)

    file_sequence = []
    for block in sequence:
        if block in mapping:
            file_sequence.append(mapping[block])
        else:
            print(f"WARNING: Block {block} not found in mapping file!")

    strict_flow = []
    for file in file_sequence:
        if not strict_flow or strict_flow[-1] != file:
            strict_flow.append(file)

    first_appearance = []
    seen = set()
    for file in file_sequence:
        if file not in seen:
            seen.add(file)
            first_appearance.append(file)

    print("=" * 80)
    print(f" Total blocks: {len(sequence)} | Mapped file nodes: {len(file_sequence)}")
    print("=" * 80)

    print("\n[1. First Appearance Order (global dedup - which files are loaded/called first)]")
    for idx, file in enumerate(first_appearance, 1):
        print(f"  {idx:02d}. {file}")

    print("\n" + "=" * 80)
    print("[2. Full Call Flow (adjacent dedup - shows alternating call traces between files)]")
    for idx, file in enumerate(strict_flow, 1):
        print(f"  [{idx:02d}] -> {file}")

if __name__ == "__main__":

    log_file_path = "C:\\TechLearning\\ai-powered-legacy-maintenance\\projects\\clean_room_revamp_php\\scenario_data\\instrumentor-log-20260530_221016-manual_http.txt"
    mapping_file_path = "C:\\TechLearning\\ai-powered-legacy-maintenance\\projects\\clean_room_revamp_php\\block-line-mapping.txt"

    analyze_file_order(log_file_path, mapping_file_path)