import sys
import os
import re
import ast
from typing import List, Dict, Optional, Any

class BlockLocation:
    def __init__(self, normalized_path: str, start_line: int):
        self.normalized_path = normalized_path
        self.start_line = start_line

class BlockPruner:
    @staticmethod
    def main(args: List[str]) -> None:
        if len(args) < 4:
            sys.stderr.write("Usage: python block_pruner.py <Source Directories> <block-line-mapping file> <instrument-log file> <Output Directory> [<Base Reference Directory>]\n")
            sys.exit(1)

        source_dirs_raw = args[0].split(';')
        source_dirs = []
        for part in source_dirs_raw:
            part = part.strip()
            if part:
                resolved = os.path.realpath(part)
                source_dirs.append(resolved if os.path.exists(resolved) else part)
        
        if not source_dirs:
            sys.stderr.write("[Error] No valid source directory provided.\n")
            sys.exit(1)

        mapping_file = args[1]
        log_file = args[2]
        output_dir = os.path.realpath(args[3].rstrip(os.sep))
        os.makedirs(output_dir, exist_ok=True)

        base_ref_dir = None
        if len(args) > 4:
            base_ref_dir = os.path.realpath(args[4].strip())

        print("[BlockPruner] Source Directories:")
        for i, d in enumerate(source_dirs):
            print(f"  [{i + 1}] {d}")
        print(f"[BlockPruner] Mapping File: {mapping_file}")
        print(f"[BlockPruner] Log File: {log_file}")
        print(f"[BlockPruner] Output Directory: {output_dir}")
        if base_ref_dir:
            print(f"[BlockPruner] Base Reference Directory: {base_ref_dir}")
        print()

        block_map = BlockPruner.parse_comment_mapping(mapping_file)
        print(f"[Step 1] Loaded {len(block_map)} block mappings")

        thread_logs = BlockPruner.parse_instrument_log(log_file)
        print(f"[Step 2] Loaded execution logs for {len(thread_logs)} threads")

        file_block_index = BlockPruner.build_file_block_index(block_map)
        print(f"[Step 3] Involves {len(file_block_index)} source files")

        resolved_paths = BlockPruner.resolve_source_files(list(file_block_index.keys()), source_dirs)
        print(f"[Step 4] Successfully located {len(resolved_paths)} / {len(file_block_index)} source files")

        total_threads = len(thread_logs)
        idx = 0
        for thread_name, executed_ids in thread_logs.items():
            idx += 1
            print(f"\n[{idx}/{total_threads}] ", end="")
            BlockPruner.prune_for_thread(
                thread_name, executed_ids, block_map, file_block_index,
                resolved_paths, source_dirs, output_dir, base_ref_dir
            )

        print(f"\n[BlockPruner] All processing completed. Output Directory: {output_dir}")

    @staticmethod
    def prune_for_thread(
        thread_name: str,
        executed_ids: Dict[int, bool],
        block_map: Dict[int, BlockLocation],
        file_block_index: Dict[str, Dict[int, int]],
        resolved_paths: Dict[str, str],
        source_dirs: List[str],
        output_dir: str,
        base_ref_dir: Optional[str]
    ) -> None:
        print(f"===== Thread [{thread_name}]  Executed {len(executed_ids)} blocks =====")

        involved_files = {}
        for block_id in executed_ids:
            if block_id in block_map:
                involved_files[block_map[block_id].normalized_path] = True

        if not involved_files:
            print("  (No files involved for this thread, skipping)")
            return

        safe_dir_name = BlockPruner.sanitize_dir_name(thread_name)

        for normalized_file in involved_files.keys():
            line_to_block_id = file_block_index.get(normalized_file)
            if not line_to_block_id:
                continue

            unexecuted_lines = {}
            for line, block_id in line_to_block_id.items():
                if block_id not in executed_ids:
                    unexecuted_lines[line] = True

            src_file = resolved_paths.get(normalized_file)
            if not src_file:
                sys.stderr.write(f"  [Skip] Source file not found: {normalized_file}\n")
                continue

            try:
                with open(src_file, 'r', encoding='utf-8') as f:
                    code = f.read()
            except Exception as e:
                sys.stderr.write(f"  [Skip] Cannot read file: {src_file} ({e})\n")
                continue

            try:
                tree = ast.parse(code)
            except Exception as ex:
                sys.stderr.write(f"  [Skip] Parsing failed {os.path.basename(src_file)}: {ex}\n")
                continue

            pruned_count = BlockPruner.prune_unexecuted_blocks(tree, unexecuted_lines)

            matching_source_dir = BlockPruner.find_matching_source_dir(src_file, source_dirs)
            relative_path_base = base_ref_dir if base_ref_dir else matching_source_dir
            relative_path = BlockPruner.get_relative_path(relative_path_base, src_file)

            out_file = os.path.join(output_dir, safe_dir_name, relative_path)
            os.makedirs(os.path.dirname(out_file), exist_ok=True)

            try:
                modified_code = ast.unparse(tree)
                with open(out_file, 'w', encoding='utf-8') as f:
                    f.write(modified_code + "\n")
            except Exception as ex:
                sys.stderr.write(f"  [Skip] Unparsing failed {os.path.basename(src_file)}: {ex}\n")
                continue

            cleared_blocks = len(unexecuted_lines)
            print(f"  {os.path.basename(src_file):<55}  Cleared {cleared_blocks:>3} unexecuted blocks", end="")
            if pruned_count != cleared_blocks:
                print(f"  ⚠ AST matched {pruned_count}/{cleared_blocks}", end="")
            print()

    @staticmethod
    def find_matching_source_dir(src_file: str, source_dirs: List[str]) -> str:
        normalized = BlockPruner.normalize_path(os.path.realpath(src_file) if os.path.exists(src_file) else src_file)
        for sd in source_dirs:
            normalized_sd = BlockPruner.normalize_path(sd)
            if normalized.startswith(normalized_sd):
                return sd

        best = source_dirs[0]
        best_score = -1
        for sd in source_dirs:
            score = BlockPruner.common_suffix_length(normalized, BlockPruner.normalize_path(sd))
            if score > best_score:
                best_score = score
                best = sd
        return best

    @staticmethod
    def prune_unexecuted_blocks(tree: ast.AST, unexecuted_lines: Dict[int, bool]) -> int:
        pruned_count = [0]

        class PrunerVisitor(ast.NodeTransformer):
            def has_executed_descendant(self, node: ast.AST) -> bool:
                for child in ast.walk(node):
                    if child is not node and hasattr(child, 'lineno'):
                        if child.lineno not in unexecuted_lines:
                            return True
                return False

            def visit(self, node: ast.AST) -> Any:
                # 1. 先遍历子节点
                self.generic_visit(node)

                # 2. 剪枝未执行的 Block
                is_pruned = False
                if hasattr(node, 'body') and isinstance(node.body, list):
                    start_line = getattr(node, 'lineno', -1)
                    if start_line >= 0 and start_line in unexecuted_lines:
                        if not self.has_executed_descendant(node):
                            node.body = [ast.Pass()]
                            pruned_count[0] += 1
                            is_pruned = True

                # 处理 else / finally 的剪枝
                for attr in ['orelse', 'finalbody']:
                    if hasattr(node, attr) and isinstance(getattr(node, attr), list) and getattr(node, attr):
                        block = getattr(node, attr)
                        start_line = getattr(block[0], 'lineno', -1)
                        if start_line >= 0 and start_line in unexecuted_lines:
                            has_exec = False
                            for stmt in block:
                                for child in ast.walk(stmt):
                                    if hasattr(child, 'lineno') and child.lineno not in unexecuted_lines:
                                        has_exec = True
                                        break
                                if has_exec: break
                            
                            if not has_exec:
                                setattr(node, attr, [ast.Pass()])
                                pruned_count[0] += 1

                # 3. 最后插入行号标记（确保不会被上面的 node.body = [ast.Pass()] 覆盖）
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    start_line = getattr(node, 'lineno', -1)
                    if start_line >= 0:
                        line_str = f"line: {start_line}"
                        has_line_comment = False
                        if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
                            if node.body[0].value.value == line_str:
                                has_line_comment = True
                        
                        if not has_line_comment:
                            node.body.insert(0, ast.Expr(value=ast.Constant(value=line_str)))

                return node

        PrunerVisitor().visit(tree)
        return pruned_count[0]

    @staticmethod
    def parse_comment_mapping(file_path: str) -> Dict[int, BlockLocation]:
        block_map = {}
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' not in line:
                        continue
                    id_part, path_and_line = line.split('=', 1)
                    last_colon = path_and_line.rfind(':')
                    if last_colon <= 0:
                        continue
                    try:
                        block_id = int(id_part.strip())
                        start_line = int(path_and_line[last_colon + 1:].strip())
                        file_path_str = path_and_line[:last_colon].strip()
                        block_map[block_id] = BlockLocation(BlockPruner.normalize_path(file_path_str), start_line)
                    except ValueError:
                        continue
        except Exception as e:
            sys.stderr.write(f"[Error] Cannot read mapping file: {file_path} ({e})\n")
            sys.exit(1)
        return block_map

    @staticmethod
    def parse_instrument_log(file_path: str) -> Dict[str, Dict[int, bool]]:
        result = {}
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                current_thread = None
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    match = re.match(r'^\[(.+?)\]', line)
                    if match:
                        current_thread = match.group(1)
                        if current_thread not in result:
                            result[current_thread] = {}
                    elif current_thread is not None:
                        for part in line.split('->'):
                            part = part.strip()
                            if part:
                                try:
                                    result[current_thread][int(part)] = True
                                except ValueError:
                                    pass
        except Exception as e:
            sys.stderr.write(f"[Error] Cannot read log file: {file_path} ({e})\n")
            sys.exit(1)
        return result

    @staticmethod
    def build_file_block_index(block_map: Dict[int, BlockLocation]) -> Dict[str, Dict[int, int]]:
        index = {}
        for block_id, loc in block_map.items():
            if loc.normalized_path not in index:
                index[loc.normalized_path] = {}
            index[loc.normalized_path][loc.start_line] = block_id
        return index

    @staticmethod
    def resolve_source_files(normalized_paths: List[str], source_dirs: List[str]) -> Dict[str, str]:
        resolved = {}
        name_index = {}
        for source_dir in source_dirs:
            if os.path.isdir(source_dir):
                BlockPruner.index_directory(source_dir, name_index)

        for np in normalized_paths:
            found = BlockPruner.try_resolve_direct(np)
            if not found:
                for source_dir in source_dirs:
                    found = BlockPruner.try_resolve_by_marker(np, source_dir)
                    if found: break
            if not found:
                found = BlockPruner.try_resolve_by_name(np, name_index)

            if found:
                resolved[np] = found
            else:
                sys.stderr.write(f"[Warning] Unable to locate source file: {np}\n")
        return resolved

    @staticmethod
    def index_directory(directory: str, name_index: Dict[str, List[str]]) -> None:
        for root, _, files in os.walk(directory):
            for file in files:
                if file.lower().endswith('.py'):
                    abs_path = os.path.abspath(os.path.join(root, file))
                    if file not in name_index:
                        name_index[file] = []
                    name_index[file].append(abs_path)

    @staticmethod
    def try_resolve_direct(normalized_path: str) -> Optional[str]:
        os_path = normalized_path.replace('/', os.sep)
        return os.path.realpath(os_path) if os.path.isfile(os_path) else None

    @staticmethod
    def try_resolve_by_marker(normalized_path: str, source_dir: str) -> Optional[str]:
        for marker in ['src/', 'app/', 'lib/', 'includes/', 'modules/']:
            idx = normalized_path.find(marker)
            if idx != -1:
                candidate = os.path.join(source_dir, normalized_path[idx + len(marker):].replace('/', os.sep))
                if os.path.isfile(candidate): return os.path.realpath(candidate)
                candidate2 = os.path.join(source_dir, normalized_path[idx:].replace('/', os.sep))
                if os.path.isfile(candidate2): return os.path.realpath(candidate2)
        return None

    @staticmethod
    def try_resolve_by_name(normalized_path: str, name_index: Dict[str, List[str]]) -> Optional[str]:
        file_name = normalized_path.split('/')[-1]
        candidates = name_index.get(file_name, [])
        if len(candidates) == 1: return candidates[0]
        if len(candidates) > 1:
            return max(candidates, key=lambda c: BlockPruner.common_suffix_length(normalized_path, BlockPruner.normalize_path(c)))
        return None

    @staticmethod
    def normalize_path(path: str) -> str:
        return path.replace('\\', '/')

    @staticmethod
    def common_suffix_length(a: str, b: str) -> int:
        i, j, count = len(a) - 1, len(b) - 1, 0
        while i >= 0 and j >= 0 and a[i].lower() == b[j].lower():
            i, j, count = i - 1, j - 1, count + 1
        return count

    @staticmethod
    def sanitize_dir_name(name: str) -> str:
        return re.sub(r'[^a-zA-Z0-9_\-.]', '_', name)

    @staticmethod
    def get_relative_path(base_dir: str, file_path: str) -> str:
        base = BlockPruner.normalize_path(os.path.realpath(base_dir) if os.path.exists(base_dir) else base_dir)
        file = BlockPruner.normalize_path(os.path.realpath(file_path) if os.path.exists(file_path) else file_path)
        if file.startswith(base):
            return file[len(base):].lstrip('/').replace('/', os.sep)
        return os.path.basename(file_path)

if __name__ == "__main__":
    BlockPruner.main(sys.argv[1:])