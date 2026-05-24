#!/usr/bin/env python3
"""
BlockPruner.py - Removes unexecuted code blocks from Python source files.

Usage: python BlockPruner.py <Source Directories> <comment-mapping file> <instrument-log file> <Output Directory>

Parameter Description:
  <Source Directories>       Python source root directories, separated by ';'
  <comment-mapping>          Instrumentation mapping file (format: ID = filePath:lineNo)
  <instrument-log>           Runtime instrumentation log file
  <Output Directory>         Output root directory for pruned source code
"""

import ast
import os
import re
import sys


class BlockLocation:
    def __init__(self, normalized_path, start_line):
        self.normalized_path = normalized_path
        self.start_line = start_line


class BlockPruner:
    @staticmethod
    def main(args):
        if len(args) < 4:
            print("Usage: python BlockPruner.py <Source Directories> <comment-mapping file> "
                  "<instrument-log file> <Output Directory>", file=sys.stderr)
            print("\nParameter Description:", file=sys.stderr)
            print("  <Source Directories>       Python source root directories, separated by ';'", file=sys.stderr)
            print("  <comment-mapping>          Instrumentation mapping file (format: ID = filePath:lineNo)", file=sys.stderr)
            print("  <instrument-log>           Runtime instrumentation log file", file=sys.stderr)
            print("  <Output Directory>         Output root directory for pruned source code", file=sys.stderr)
            sys.exit(1)

        source_dirs = []
        for part in args[0].split(';'):
            part = part.strip()
            if part:
                resolved = os.path.abspath(part)
                source_dirs.append(resolved)

        if not source_dirs:
            print("[Error] No valid source directory provided.", file=sys.stderr)
            sys.exit(1)

        mapping_file = os.path.abspath(args[1])
        log_file = os.path.abspath(args[2])
        output_dir = os.path.abspath(args[3])
        os.makedirs(output_dir, exist_ok=True)

        print("[BlockPruner] Source Directories:")
        for i, d in enumerate(source_dirs):
            print(f"  [{i + 1}] {d}")
        print(f"[BlockPruner] Mapping File: {mapping_file}")
        print(f"[BlockPruner] Log File: {log_file}")
        print(f"[BlockPruner] Output Directory: {output_dir}\n")

        block_map = BlockPruner.parse_comment_mapping(mapping_file)
        print(f"[Step 1] Loaded {len(block_map)} block mappings")

        thread_logs = BlockPruner.parse_instrument_log(log_file)
        print(f"[Step 2] Loaded execution logs for {len(thread_logs)} threads")

        file_block_index = BlockPruner.build_file_block_index(block_map)
        print(f"[Step 3] Involves {len(file_block_index)} source files")

        resolved_paths = BlockPruner.resolve_source_files(list(file_block_index.keys()), source_dirs)
        print(f"[Step 4] Successfully located {len(resolved_paths)} / {len(file_block_index)} source files")

        total_threads = len(thread_logs)
        for idx, (thread_name, executed_ids) in enumerate(thread_logs.items(), 1):
            print(f"\n[{idx}/{total_threads}] ===== Thread [{thread_name}]  "
                  f"Executed {len(executed_ids)} blocks =====")
            BlockPruner.prune_for_thread(
                thread_name, executed_ids, block_map, file_block_index,
                resolved_paths, source_dirs, output_dir
            )

        print(f"\n[BlockPruner] All processing completed. Output Directory: {output_dir}")

    @staticmethod
    def prune_for_thread(thread_name, executed_ids, block_map, file_block_index,
                         resolved_paths, source_dirs, output_dir):
        involved_files = set()
        for block_id in executed_ids:
            if block_id in block_map:
                involved_files.add(block_map[block_id].normalized_path)

        if not involved_files:
            print("  (No files involved for this thread, skipping)")
            return

        safe_dir_name = re.sub(r'[^a-zA-Z0-9_\-.]', '_', thread_name)

        for normalized_file in involved_files:
            line_to_block_id = file_block_index.get(normalized_file)
            if line_to_block_id is None:
                continue

            unexecuted_lines = {}
            for line, block_id in line_to_block_id.items():
                if block_id not in executed_ids:
                    unexecuted_lines[line] = True

            src_file = resolved_paths.get(normalized_file)
            if src_file is None:
                print(f"  [Skip] Source file not found: {normalized_file}", file=sys.stderr)
                continue

            try:
                with open(src_file, 'r', encoding='utf-8') as f:
                    code = f.read()
            except (IOError, UnicodeDecodeError):
                print(f"  [Skip] Cannot read file: {src_file}", file=sys.stderr)
                continue

            try:
                tree = ast.parse(code)
            except SyntaxError as e:
                print(f"  [Skip] Parsing failed {os.path.basename(src_file)}: {e}", file=sys.stderr)
                continue

            pruned_count = BlockPruner.prune_unexecuted_blocks(code, tree, unexecuted_lines)

            matching_source_dir = BlockPruner.find_matching_source_dir(src_file, source_dirs)
            relative_path = BlockPruner.get_relative_path(matching_source_dir, src_file)
            out_file = os.path.join(output_dir, safe_dir_name, relative_path)

            os.makedirs(os.path.dirname(out_file), exist_ok=True)

            # Write pruned code
            lines = code.split('\n')
            pruned_lines = BlockPruner.remove_lines_in_blocks(lines, tree, unexecuted_lines)
            with open(out_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(pruned_lines) + '\n')

            cleared_blocks = len(unexecuted_lines)
            msg = f"  {os.path.basename(src_file):<55} Cleared {cleared_blocks:>3} unexecuted blocks"
            if pruned_count != cleared_blocks:
                msg += f"  ⚠ AST matched {pruned_count}/{cleared_blocks}"
            print(msg)

    @staticmethod
    def prune_unexecuted_blocks(code, tree, unexecuted_lines):
        """Count how many unexecuted blocks can be matched in the AST."""
        if not unexecuted_lines:
            return 0

        pruned_count = 0
        for node in ast.walk(tree):
            # Check nodes that have body (compound statements)
            for attr in ('body', 'orelse', 'finalbody', 'handlers'):
                body = getattr(node, attr, None)
                if isinstance(body, list) and body:
                    first_stmt = body[0]
                    if hasattr(first_stmt, 'lineno') and first_stmt.lineno in unexecuted_lines:
                        pruned_count += 1

        return pruned_count

    @staticmethod
    def remove_lines_in_blocks(lines, tree, unexecuted_lines):
        """Remove content of unexecuted blocks, replacing with 'pass'."""
        if not unexecuted_lines:
            return lines

        # Collect line ranges for unexecuted blocks
        ranges_to_clear = []

        for node in ast.walk(tree):
            for attr in ('body', 'orelse', 'finalbody'):
                body = getattr(node, attr, None)
                if isinstance(body, list) and body:
                    first_stmt = body[0]
                    if hasattr(first_stmt, 'lineno') and first_stmt.lineno in unexecuted_lines:
                        start = first_stmt.lineno
                        last_stmt = body[-1]
                        end = getattr(last_stmt, 'end_lineno', last_stmt.lineno) if hasattr(last_stmt, 'end_lineno') else last_stmt.lineno
                        if start <= end:
                            ranges_to_clear.append((start, end, first_stmt.col_offset))

            # Handle except handlers
            if isinstance(node, ast.ExceptHandler):
                if node.body:
                    first_stmt = node.body[0]
                    if hasattr(first_stmt, 'lineno') and first_stmt.lineno in unexecuted_lines:
                        start = first_stmt.lineno
                        last_stmt = node.body[-1]
                        end = getattr(last_stmt, 'end_lineno', last_stmt.lineno) if hasattr(last_stmt, 'end_lineno') else last_stmt.lineno
                        if start <= end:
                            ranges_to_clear.append((start, end, first_stmt.col_offset))

        # Sort ranges by start line (reverse to process from bottom)
        ranges_to_clear.sort(key=lambda r: r[0], reverse=True)

        result = list(lines)
        for start, end, col_offset in ranges_to_clear:
            # Replace block body with 'pass'
            indent = ' ' * col_offset
            for i in range(start - 1, min(end, len(result))):
                if i == start - 1:
                    result[i] = f"{indent}pass"
                else:
                    result[i] = ''

        # Remove empty lines created by pruning
        final = []
        for line in result:
            if line == '' and final and final[-1] == '':
                continue
            final.append(line)

        return final

    @staticmethod
    def parse_comment_mapping(file_path):
        mapping = {}
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue

                    eq_idx = line.find('=')
                    if eq_idx == -1:
                        continue

                    id_part = line[:eq_idx].strip()
                    path_and_line = line[eq_idx + 1:].strip()
                    last_colon = path_and_line.rfind(':')
                    if last_colon <= 0:
                        continue

                    try:
                        block_id = int(id_part)
                        start_line = int(path_and_line[last_colon + 1:].strip())
                        file_p = path_and_line[:last_colon].strip()
                        mapping[block_id] = BlockLocation(
                            BlockPruner.normalize_path(file_p), start_line
                        )
                    except ValueError:
                        continue
        except IOError as e:
            print(f"[Error] Cannot read mapping file: {file_path}: {e}", file=sys.stderr)
            sys.exit(1)

        return mapping

    @staticmethod
    def parse_instrument_log(file_path):
        result = {}
        current_thread = None

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue

                    match = re.match(r'^\[(.+?)\]', line)
                    if match:
                        current_thread = match.group(1)
                        if current_thread not in result:
                            result[current_thread] = set()
                    elif current_thread:
                        parts = line.split('->')
                        for part in parts:
                            part = part.strip()
                            if part:
                                try:
                                    result[current_thread].add(int(part))
                                except ValueError:
                                    pass
        except IOError as e:
            print(f"[Error] Cannot read log file: {file_path}: {e}", file=sys.stderr)
            sys.exit(1)

        return result

    @staticmethod
    def build_file_block_index(block_map):
        index = {}
        for block_id, loc in block_map.items():
            if loc.normalized_path not in index:
                index[loc.normalized_path] = {}
            index[loc.normalized_path][loc.start_line] = block_id
        return index

    @staticmethod
    def resolve_source_files(normalized_paths, source_dirs):
        resolved = {}
        name_index = {}

        for source_dir in source_dirs:
            if os.path.isdir(source_dir):
                for root, dirs, files in os.walk(source_dir):
                    for fn in files:
                        if fn.endswith('.py'):
                            full_path = os.path.join(root, fn)
                            if fn not in name_index:
                                name_index[fn] = []
                            name_index[fn].append(full_path)

        for np in normalized_paths:
            found = None
            os_path = np.replace('/', os.sep)

            if os.path.isfile(os_path):
                found = os.path.abspath(os_path)
            else:
                file_name = os.path.basename(np)
                candidates = name_index.get(file_name, [])
                if len(candidates) == 1:
                    found = candidates[0]
                elif len(candidates) > 1:
                    found = candidates[0]

            if found:
                resolved[np] = found
            else:
                print(f"[Warning] Unable to locate source file: {np}", file=sys.stderr)

        return resolved

    @staticmethod
    def find_matching_source_dir(src_file, source_dirs):
        normalized = BlockPruner.normalize_path(os.path.abspath(src_file))
        for sd in source_dirs:
            if normalized.startswith(BlockPruner.normalize_path(sd)):
                return sd
        return source_dirs[0]

    @staticmethod
    def get_relative_path(base_dir, file_path):
        base = BlockPruner.normalize_path(os.path.abspath(base_dir))
        file_norm = BlockPruner.normalize_path(os.path.abspath(file_path))
        if file_norm.startswith(base):
            rel = file_norm[len(base):].lstrip('/')
            return rel.replace('/', os.sep)
        return os.path.basename(file_path)

    @staticmethod
    def normalize_path(p):
        return p.replace('\\', '/')


if __name__ == '__main__':
    BlockPruner.main(sys.argv[1:])
