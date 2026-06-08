import os
import sys
import ast
import re
import argparse
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

def normalize_path(path: str) -> str:
    """统一路径归一化，解决大小写及软链接带来的匹配失败问题"""
    return os.path.normcase(os.path.abspath(os.path.realpath(path)))

class BlockInstrumentorTransformer(ast.NodeTransformer):
    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = normalize_path(file_path)

    def _create_instrumentation_node(self, lineno: int) -> ast.Expr:
        payload = f"{self.file_path}:{lineno}"
        return ast.Expr(
            value=ast.Call(
                func=ast.Name(id='_INST_NOP_', ctx=ast.Load()),
                args=[ast.Constant(value=payload)],
                keywords=[]
            ),
            lineno=lineno,
            col_offset=0
        )

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self.generic_visit(node)
        if node.body:
            node.body.insert(0, self._create_instrumentation_node(node.lineno))
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self.generic_visit(node)
        if node.body:
            node.body.insert(0, self._create_instrumentation_node(node.lineno))
        return node

    def visit_Lambda(self, node: ast.Lambda):
        self.generic_visit(node)
        return node

    def visit_If(self, node: ast.If):
        self.generic_visit(node)
        if node.body:
            node.body.insert(0, self._create_instrumentation_node(node.lineno))
        if node.orelse:
            first_child = node.orelse[0]
            if not isinstance(first_child, ast.If):
                node.orelse.insert(0, self._create_instrumentation_node(first_child.lineno))
        return node

    def visit_For(self, node: ast.For):
        self.generic_visit(node)
        if node.body:
            node.body.insert(0, self._create_instrumentation_node(node.lineno))
        return node

    def visit_AsyncFor(self, node: ast.AsyncFor):
        self.generic_visit(node)
        if node.body:
            node.body.insert(0, self._create_instrumentation_node(node.lineno))
        return node

    def visit_While(self, node: ast.While):
        self.generic_visit(node)
        if node.body:
            node.body.insert(0, self._create_instrumentation_node(node.lineno))
        return node

    def visit_Try(self, node: ast.Try):
        self.generic_visit(node)
        if node.body:
            node.body.insert(0, self._create_instrumentation_node(node.lineno))
        if node.finalbody:
            node.finalbody.insert(0, self._create_instrumentation_node(node.finalbody[0].lineno))
        return node

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        self.generic_visit(node)
        if node.body:
            node.body.insert(0, self._create_instrumentation_node(node.lineno))
        return node

class MethodRangeVisitor(ast.NodeVisitor):
    def __init__(self):
        super().__init__()
        self.class_stack: List[str] = []
        self.ranges: List[Dict[str, Any]] = []

    def visit_ClassDef(self, node: ast.ClassDef):
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    def _handle_function(self, node: Any, is_async: bool = False):
        func_name = node.name
        if self.class_stack:
            full_name = ".".join(self.class_stack) + f".{func_name}"
        else:
            full_name = func_name

        start_line = node.lineno
        end_line = getattr(node, 'end_lineno', start_line)

        self.ranges.append({
            'name': f"{full_name}@{start_line}",
            'start': start_line,
            'end': end_line
        })
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._handle_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._handle_function(node, is_async=True)

    def get_ranges(self) -> List[Dict[str, Any]]:
        return self.ranges

class InstrumentationPipeline:

    ORIGINAL_COMMENT_PATTERN = re.compile(r"(\s*)_INST_NOP_\(\s*['\"](.+?\.py:\d+)['\"]\s*\)")
    MAPPED_COMMENT_PATTERN = re.compile(r"(\s*)_INST_ACTIVE_\(\s*(\d+)\s*\)")

    def __init__(self, is_incremental: bool, mapping_file: str, range_file: str, signature_file: str):
        self.is_incremental = is_incremental
        self.mapping_file = normalize_path(mapping_file)
        self.range_file = normalize_path(range_file)
        self.signature_file = normalize_path(signature_file)
        self.old_comment_map: Dict[int, str] = {}

    def _get_incremental_path(self, file_path: str) -> str:
        dir_name = os.path.dirname(file_path)
        base_name = os.path.basename(file_path)
        name, ext = os.path.splitext(base_name)
        return os.path.join(dir_name, f"{name}.incremental{ext}")

    def run(self, targets: List[str]):
        if self.is_incremental:
            if not (os.path.exists(self.mapping_file) and os.path.exists(self.range_file) and os.path.exists(self.signature_file)):
                print("Warning: mapping, range or signature file not found, falling back to full mode.")
                self.is_incremental = False

        if self.is_incremental and os.path.exists(self.mapping_file):
            self.old_comment_map = self._load_raw_mapping(self.mapping_file)

        mode = "Incremental" if self.is_incremental else "Full"
        print(f"=== Python Instrumentation Pipeline ({mode} mode) ===")

        files = self._collect_python_files(targets)
        if not files:
            print("No Python files found.")
            sys.exit(1)

        print(">> Step: Code Instrumentation & Range Collection")
        new_ranges = self._instrument_files(files)

        print(">> Step: Updating Method Ranges")
        self._update_method_ranges(files, new_ranges)

        print(">> Step: Encoding Mapping")
        self._encode_mapping(files)

        print(">> Step: Generating Block to Signature Mapping")
        self._generate_block_signatures(files)

        print(">> Step: Activation")
        self._activate(files)

        print("=== Pipeline complete ===")

    def _collect_python_files(self, targets: List[str]) -> List[str]:
        files = []
        for target in targets:
            real = normalize_path(target)
            if not os.path.exists(real):
                continue
            if os.path.isfile(real) and real.endswith('.py'):
                files.append(real)
            elif os.path.isdir(real):
                for root, _, filenames in os.walk(real):
                    for filename in filenames:
                        if filename.endswith('.py'):
                            files.append(normalize_path(os.path.join(root, filename)))
        return sorted(list(set(files)))

    def _instrument_files(self, files: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        all_ranges = {}
        for file in files:
            with open(file, 'r', encoding='utf-8') as f:
                code = f.read()
            try:
                tree = ast.parse(code, filename=file)

                range_visitor = MethodRangeVisitor()
                range_visitor.visit(tree)
                all_ranges[file] = range_visitor.get_ranges()

                transformer = BlockInstrumentorTransformer(file)
                modified_tree = transformer.visit(tree)
                ast.fix_missing_locations(modified_tree)

                new_code = ast.unparse(modified_tree)
                with open(file, 'w', encoding='utf-8') as f:
                    f.write(new_code)

            except Exception as e:
                print(f"Parse error in {file}: {e}")
        return all_ranges

    def _update_method_ranges(self, files: List[str], new_ranges: Dict[str, List[Dict[str, Any]]]):
        target_ranges = []
        for file, ranges in new_ranges.items():
            for r in ranges:
                target_ranges.append({
                    'file': file,
                    'name': r['name'],
                    'start': r['start'],
                    'end': r['end']
                })

        target_ranges.sort(key=lambda x: (x['file'], x['start']))

        output_file = self._get_incremental_path(self.range_file) if self.is_incremental else self.range_file
        self._write_range_file(output_file, target_ranges)
        print(f"   {'Incremental' if self.is_incremental else 'Full'} method ranges saved to {output_file} (Total: {len(target_ranges)} entries)")

    def _write_range_file(self, file_path: str, ranges: List[Dict[str, Any]]):
        lines = [
            "# ================================================",
            "# Method Line Range Mapping Table",
            f"# Generation Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"# Total Entries: {len(ranges)}",
            "# ================================================",
            "# Format: File Absolute Path | Method Name = Start Line-End Line",
            "# Note: This mapping needs to be regenerated after source code modifications and re-instrumentation.",
            ""
        ]
        for entry in ranges:
            lines.append(f"{entry['file']} | {entry['name']} = {entry['start']}-{entry['end']}")

        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines) + "\n")

    def _load_raw_ranges(self, range_file: str) -> List[Dict[str, Any]]:
        result = []
        if not os.path.exists(range_file):
            return result
        with open(range_file, 'r', encoding='utf-8') as f:
            for line in f:
                trimmed = line.strip()
                if not trimmed or trimmed.startswith('#'):
                    continue

                match = re.match(r"^(.+?)\s*\|\s*(.+?)\s*=\s*(\d+)-(\d+)$", trimmed)
                if match:
                    result.append({
                        'file': normalize_path(match.group(1).strip()),
                        'name': match.group(2).strip(),
                        'start': int(match.group(3)),
                        'end': int(match.group(4))
                    })
        return result

    def _encode_mapping(self, files: List[str]):
        next_id = 1
        if self.is_incremental and os.path.exists(self.mapping_file):
            existing_map = self._load_raw_mapping(self.mapping_file)
            if existing_map:
                next_id = max(existing_map.keys()) + 1

        new_comments = []
        seen = set()

        for file in files:
            with open(file, 'r', encoding='utf-8') as f:
                content = f.read()
            for match in self.ORIGINAL_COMMENT_PATTERN.finditer(content):
                comment = match.group(2)
                if comment not in seen:
                    seen.add(comment)
                    new_comments.append(comment)

        self._sort_comments_by_path_and_line(new_comments)

        incremental_id_to_comment = {}
        comment_to_id = {}
        for comment in new_comments:
            incremental_id_to_comment[next_id] = comment
            comment_to_id[comment] = next_id
            next_id += 1

        if not incremental_id_to_comment:
            print("   No new instrumentation points found.")
            return

        for file in files:
            with open(file, 'r', encoding='utf-8') as f:
                content = f.read()

            def replacer(match):
                indent = match.group(1)
                original_comment = match.group(2)
                block_id = comment_to_id.get(original_comment)
                if block_id is not None:
                    return f"{indent}_INST_ACTIVE_({block_id})"
                return match.group(0)

            new_content = self.ORIGINAL_COMMENT_PATTERN.sub(replacer, content)
            if new_content != content:
                with open(file, 'w', encoding='utf-8') as f:
                    f.write(new_content)

        output_file = self._get_incremental_path(self.mapping_file) if self.is_incremental else self.mapping_file
        self._write_mapping_file(output_file, incremental_id_to_comment)
        print(f"   {'Incremental' if self.is_incremental else 'Full'} mapping saved to {output_file} (Total: {len(incremental_id_to_comment)})")

    def _write_mapping_file(self, file_path: str, id_to_comment: Dict[int, str]):
        lines = [
            "# ================================================",
            "# Instrumentation Comment -> Integer ID Mapping Table",
            f"# Generation Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"# Total Entries: {len(id_to_comment)}",
            "# ================================================",
            "# Format: Integer ID = File Absolute Path:Code Block Start Line Number",
            "# Note: This mapping needs to be regenerated after source code modifications and re-instrumentation.",
            ""
        ]
        for block_id in sorted(id_to_comment.keys()):
            lines.append(f"{block_id} = {id_to_comment[block_id]}")

        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines) + "\n")

    def _load_raw_mapping(self, mapping_file: str) -> Dict[int, str]:
        result = {}
        if not os.path.exists(mapping_file):
            return result
        with open(mapping_file, 'r', encoding='utf-8') as f:
            for line in f:
                trimmed = line.strip()
                if not trimmed or trimmed.startswith('#'):
                    continue
                match = re.match(r"^(\d+)\s*=\s*(.+)$", trimmed)
                if match:
                    result[int(match.group(1))] = match.group(2).strip()
        return result

    def _sort_comments_by_path_and_line(self, comments: List[str]):
        def sort_key(comment: str):
            last_colon = comment.rfind(':')
            if last_colon == -1:
                return (comment, 0)
            path = normalize_path(comment[:last_colon])
            try:
                line = int(comment[last_colon+1:])
            except ValueError:
                line = 0
            return (path, line)
        comments.sort(key=sort_key)

    def _generate_block_signatures(self, files: List[str]):
        block_to_signature = {}

        mapping_to_load = self._get_incremental_path(self.mapping_file) if self.is_incremental else self.mapping_file
        ranges_to_load = self._get_incremental_path(self.range_file) if self.is_incremental else self.range_file

        comment_map = self._load_raw_mapping(mapping_to_load)
        ranges = self._load_raw_ranges(ranges_to_load)

        ranges_by_file = {}
        for r in ranges:
            ranges_by_file.setdefault(r['file'], []).append(r)

        for block_id, comment in comment_map.items():
            file_path = self._extract_file_path_from_comment(comment)
            line = self._extract_line_from_comment(comment)

            if not file_path or line is None:
                continue

            # 再次确保从 mapping 中读取的路径也是归一化的
            file_path = normalize_path(file_path)

            matched_signature = '[Global]'
            if file_path in ranges_by_file:
                best = None
                for r in ranges_by_file[file_path]:
                    if r['start'] <= line <= r['end']:
                        if (best is None or
                            r['start'] > best['start'] or
                            (r['start'] == best['start'] and r['end'] < best['end'])):
                            best = r
                if best is not None:
                    matched_signature = best['name']

            block_to_signature[block_id] = matched_signature

        output_file = self._get_incremental_path(self.signature_file) if self.is_incremental else self.signature_file
        self._write_signature_file(output_file, block_to_signature)
        print(f"   {'Incremental' if self.is_incremental else 'Full'} block signatures saved to {output_file} (Total: {len(block_to_signature)} entries)")

    def _write_signature_file(self, file_path: str, signatures: Dict[int, str]):
        lines = [
            "# ================================================",
            "# Block ID -> Method Signature Mapping Table",
            f"# Generation Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"# Total Entries: {len(signatures)}",
            "# ================================================",
            "# Format: Block ID = Method Signature",
            "# Note: This mapping needs to be regenerated after source code modifications and re-instrumentation.",
            ""
        ]
        for block_id in sorted(signatures.keys()):
            lines.append(f"{block_id} = {signatures[block_id]}")

        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines) + "\n")

    def _extract_file_path_from_comment(self, comment: str) -> Optional[str]:
        last_colon = comment.rfind(':')
        if last_colon == -1:
            return None
        return comment[:last_colon]

    def _extract_line_from_comment(self, comment: str) -> Optional[int]:
        last_colon = comment.rfind(':')
        if last_colon == -1:
            return None
        try:
            return int(comment[last_colon+1:])
        except ValueError:
            return None

    def _find_safe_import_insertion_index(self, lines: List[str]) -> int:
        idx = 0
        n = len(lines)

        if n > 0 and lines[0].startswith('#!'):
            idx += 1

        for i in range(idx, min(idx + 2, n)):
            if re.match(r"^\s*#\s*-\*-\s*coding\s*[:=]\s*([-\w.]+)\s*-\*-", lines[i]) or \
               re.match(r"^\s*#\s*coding\s*[:=]\s*([-\w.]+)", lines[i]):
                idx = i + 1

        if idx < n:
            stripped = lines[idx].strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                quote_char = '"""' if stripped.startswith('"""') else "'''"
                if stripped.endswith(quote_char) and len(stripped) >= 6:
                    idx += 1
                else:
                    idx += 1
                    while idx < n:
                        if quote_char in lines[idx]:
                            idx += 1
                            break
                        idx += 1

        while idx < n:
            line_strip = lines[idx].strip()
            if not line_strip or line_strip.startswith('#'):
                idx += 1
                continue
            if re.match(r"^\s*from\s+__future__\s+import\s+", line_strip):
                idx += 1
                if '\\' in line_strip or '(' in line_strip:
                    if '(' in line_strip and ')' not in line_strip:
                        while idx < n and ')' not in lines[idx]:
                            idx += 1
                        if idx < n:
                            idx += 1
                continue
            break

        return idx

    def _activate(self, files: List[str]):
        call_template = "{indent}_inst_staining({block_id})"
        # 修改点：更新为直接从全局安装的包中导入，不再依赖相对路径 app.instrumentation
        import_statement = "from InstrumentLog import InstrumentLog as _inst_log; _inst_staining = _inst_log.staining"

        total_activated = 0
        for file in files:
            with open(file, 'r', encoding='utf-8') as f:
                content = f.read()

            file_activated_count = 0

            def replacer(match):
                nonlocal total_activated, file_activated_count
                indent = match.group(1)
                block_id = int(match.group(2))
                total_activated += 1
                file_activated_count += 1
                return call_template.format(indent=indent, block_id=block_id)

            new_content = self.MAPPED_COMMENT_PATTERN.sub(replacer, content)

            if file_activated_count > 0:
                lines = new_content.splitlines(keepends=True)
                insert_idx = self._find_safe_import_insertion_index(lines)

                lines.insert(insert_idx, f"{import_statement}\n")

                with open(file, 'w', encoding='utf-8') as f:
                    f.writelines(lines)

        print(f"   Activated {total_activated} instrumentation points with top-level imports.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Python Instrumentation Pipeline")
    parser.add_argument('--incremental', action='store_true', help='Enable incremental mode')
    parser.add_argument('--mapping', default='block-line-mapping.txt', help='Path to mapping file')
    parser.add_argument('--range', default='method-range.txt', help='Path to range file')
    parser.add_argument('--signature', default='block-signature.txt', help='Path to signature file')
    parser.add_argument('targets', nargs='+', help='Target Python files or directories to instrument')

    args = parser.parse_args()

    pipeline = InstrumentationPipeline(
        is_incremental=args.incremental,
        mapping_file=args.mapping,
        range_file=args.range,
        signature_file=args.signature
    )
    pipeline.run(args.targets)