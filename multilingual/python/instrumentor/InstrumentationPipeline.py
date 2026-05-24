#!/usr/bin/env python3
"""
InstrumentationPipeline.py - Python instrumentation pipeline.

Three-step pipeline:
  1. Instrument: Inject instrumentation comments at block starts
  2. Encoding:   Build/update comment -> ID mapping
  3. Activation:  Replace comments with staining() function calls

Usage:
  python InstrumentationPipeline.py [--incremental] [--mapping FILE] <target1> [target2 ...]
"""

import ast
import os
import re
import sys
from datetime import datetime


class InstrumentationPipeline:
    # Match original comments injected during instrumentation, e.g. # /abs/path/foo.py:123
    ORIGINAL_COMMENT_PATTERN = re.compile(r'^(\s*)# (.+\.py:\d+)\s*$', re.MULTILINE)
    # Match already-mapped comments, e.g. # INST#42
    MAPPED_COMMENT_PATTERN = re.compile(r'^(\s*)# INST#(\d+)\s*$', re.MULTILINE)

    def __init__(self, is_incremental, mapping_file):
        self.is_incremental = is_incremental
        self.mapping_file = mapping_file
        self.id_to_comment = {}
        self.comment_to_id = {}
        self.next_id = 1

    def run(self, targets):
        if self.is_incremental and not os.path.exists(self.mapping_file):
            print("Warning: mapping file not found, falling back to full mode.")
            self.is_incremental = False

        mode = "Incremental" if self.is_incremental else "Full"
        print(f"=== Python Instrumentation Pipeline ({mode} mode) ===")

        files = self.collect_py_files(targets)
        if not files:
            print("No Python files found.", file=sys.stderr)
            sys.exit(1)

        # Step 1: Instrument (inject comments at block starts)
        print(">> Step: Code Instrumentation")
        self.instrument_files(files)

        # Step 2: Encoding (generate / update ID mapping)
        print(">> Step: Encoding Mapping")
        self.encode_mapping(files)

        # Step 3: Activation (replace comments with function calls)
        print(">> Step: Activation")
        self.activate(files)

        print("=== Pipeline complete ===")

    def instrument_files(self, files):
        """Step 1: Parse each file and inject instrumentation comments."""
        for file_path in files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    source = f.read()

                try:
                    tree = ast.parse(source)
                except SyntaxError as e:
                    print(f"Parse error in {file_path}: {e}")
                    continue

                lines = source.split('\n')
                # Collect block start lines
                block_lines = set()
                for node in ast.walk(tree):
                    self._collect_block_starts(node, block_lines)

                if not block_lines:
                    continue

                # Sort in reverse order to insert from bottom to top
                sorted_lines = sorted(block_lines, reverse=True)

                for line_no in sorted_lines:
                    if line_no < 1 or line_no > len(lines):
                        continue
                    # Determine indentation of the target line
                    target_line = lines[line_no - 1]
                    indent = len(target_line) - len(target_line.lstrip())
                    indent_str = ' ' * indent
                    comment = f"{indent_str}# {file_path}:{line_no}"
                    lines.insert(line_no - 1, comment)

                new_source = '\n'.join(lines)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(new_source)

            except (IOError, UnicodeDecodeError) as e:
                print(f"Error processing {file_path}: {e}")

    def _collect_block_starts(self, node, block_lines):
        """Collect the start line of each block body."""
        # Nodes with 'body' attribute (compound statements)
        bodies_to_check = []

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                             ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith)):
            if hasattr(node, 'body') and node.body:
                bodies_to_check.append(node.body)
            # else clause for for/while
            if hasattr(node, 'orelse') and node.orelse:
                bodies_to_check.append(node.orelse)

        elif isinstance(node, ast.If):
            if node.body:
                bodies_to_check.append(node.body)
            if node.orelse:
                bodies_to_check.append(node.orelse)

        elif isinstance(node, ast.Try):
            if node.body:
                bodies_to_check.append(node.body)
            if node.orelse:
                bodies_to_check.append(node.orelse)
            if hasattr(node, 'finalbody') and node.finalbody:
                bodies_to_check.append(node.finalbody)

        elif isinstance(node, ast.ExceptHandler):
            if node.body:
                bodies_to_check.append(node.body)

        # Python 3.11+ TryStar
        if hasattr(ast, 'TryStar') and isinstance(node, ast.TryStar):
            if node.body:
                bodies_to_check.append(node.body)
            if node.orelse:
                bodies_to_check.append(node.orelse)
            if hasattr(node, 'finalbody') and node.finalbody:
                bodies_to_check.append(node.finalbody)

        for body in bodies_to_check:
            if body and len(body) > 0:
                first_stmt = body[0]
                if hasattr(first_stmt, 'lineno') and first_stmt.lineno > 0:
                    block_lines.add(first_stmt.lineno)

    def encode_mapping(self, files):
        """Step 2: Build or update comment -> ID mapping."""
        id_to_comment = {}
        comment_to_id = {}

        # Preserve non-target entries when incremental
        if self.is_incremental and os.path.exists(self.mapping_file):
            existing_map = self._load_raw_mapping(self.mapping_file)
            target_file_set = set(files)

            for id_val, comment in existing_map.items():
                file_path = self._extract_file_path(comment)
                if file_path is not None and file_path in target_file_set:
                    continue
                id_to_comment[id_val] = comment
                comment_to_id[comment] = id_val

        # Scan original comments from target files
        new_comments = []
        seen = set()
        for file_path in files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                for match in self.ORIGINAL_COMMENT_PATTERN.finditer(content):
                    comment = match.group(2)
                    if comment not in seen:
                        seen.add(comment)
                        new_comments.append(comment)
            except (IOError, UnicodeDecodeError):
                continue

        # Sort by path and line for stable IDs
        self._sort_comments_by_path_and_line(new_comments)

        # Allocate IDs
        next_id = max(id_to_comment.keys()) + 1 if id_to_comment else 1
        for comment in new_comments:
            if comment not in comment_to_id:
                id_to_comment[next_id] = comment
                comment_to_id[comment] = next_id
                next_id += 1

        if not id_to_comment:
            print("   No instrumentation points found.")
            return

        # Replace comments with INST#ID in target sources
        for file_path in files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                def replace_comment(match):
                    indent = match.group(1)
                    original_comment = match.group(2)
                    cid = comment_to_id.get(original_comment)
                    if cid is not None:
                        return f"{indent}# INST#{cid}"
                    return match.group(0)

                new_content = self.ORIGINAL_COMMENT_PATTERN.sub(replace_comment, content)
                if new_content != content:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
            except (IOError, UnicodeDecodeError):
                continue

        # Save mapping
        self._write_mapping_file(id_to_comment)
        print(f"   Mapping saved to {self.mapping_file} (Total: {len(id_to_comment)})")

        self.id_to_comment = id_to_comment
        self.comment_to_id = comment_to_id

    def activate(self, files):
        """Step 3: Replace INST# comments with staining() function calls."""
        total_activated = 0

        for file_path in files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                file_activated = 0

                def replace_mapped(match):
                    nonlocal file_activated, total_activated
                    indent = match.group(1)
                    id_val = match.group(2)
                    total_activated += 1
                    file_activated += 1
                    return f"{indent}instrument_log.staining({id_val})"

                new_content = self.MAPPED_COMMENT_PATTERN.sub(replace_mapped, content)

                if file_activated > 0:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
            except (IOError, UnicodeDecodeError):
                continue

        print(f"   Activated {total_activated} instrumentation points.")

    def _write_mapping_file(self, id_to_comment):
        """Write the mapping file."""
        lines = [
            "# ================================================",
            "# Instrumentation Comment -> Integer ID Mapping Table",
            f"# Generation Time: {datetime.now().isoformat()}",
            f"# Total Entries: {len(id_to_comment)}",
            "# ================================================",
            "# Format: Integer ID = File Absolute Path:Code Block Start Line Number",
            ""
        ]

        for id_val in sorted(id_to_comment.keys()):
            lines.append(f"{id_val} = {id_to_comment[id_val]}")

        dir_name = os.path.dirname(self.mapping_file)
        if dir_name and not os.path.isdir(dir_name):
            os.makedirs(dir_name, exist_ok=True)

        with open(self.mapping_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')

    def _load_raw_mapping(self, mapping_file):
        """Load existing mapping file."""
        result = {}
        try:
            with open(mapping_file, 'r', encoding='utf-8') as f:
                for line in f:
                    trimmed = line.strip()
                    if not trimmed or trimmed.startswith('#'):
                        continue
                    match = re.match(r'^(\d+)\s*=\s*(.+)$', trimmed)
                    if match:
                        result[int(match.group(1))] = match.group(2).strip()
        except IOError:
            pass
        return result

    def _extract_file_path(self, comment):
        """Extract file path from comment like '/abs/path/foo.py:123'."""
        last_colon = comment.rfind(':')
        if last_colon <= 0:
            return None
        after_colon = comment[last_colon + 1:]
        if after_colon.isdigit():
            return comment[:last_colon]
        return None

    def _sort_comments_by_path_and_line(self, comments):
        """Sort comments by file path and line number."""
        def sort_key(comment):
            last_colon = comment.rfind(':')
            path = comment[:last_colon]
            line = int(comment[last_colon + 1:])
            return (path, line)

        comments.sort(key=sort_key)

    def collect_py_files(self, targets):
        """Collect .py files from targets."""
        files = []
        skip_dirs = {'__pycache__', '.git', '.venv', 'venv', 'node_modules',
                     '.tox', '.mypy_cache', 'dist', 'build'}

        for target in targets:
            full_path = os.path.abspath(target)
            if not os.path.exists(full_path):
                continue

            if os.path.isfile(full_path) and full_path.endswith('.py'):
                files.append(full_path)
            elif os.path.isdir(full_path):
                for root, dirs, filenames in os.walk(full_path):
                    dirs[:] = [d for d in dirs if d not in skip_dirs]
                    for fn in filenames:
                        if fn.endswith('.py'):
                            files.append(os.path.join(root, fn))

        return list(set(files))


def main():
    args = sys.argv[1:]
    is_incremental = False
    mapping_file = os.path.join(os.getcwd(), 'comment-mapping.txt')
    targets = []

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == '--incremental':
            is_incremental = True
        elif arg == '--mapping':
            i += 1
            if i < len(args):
                mapping_file = os.path.abspath(args[i])
        elif arg.startswith('--mapping='):
            mapping_file = os.path.abspath(arg.split('=', 1)[1])
        else:
            targets.append(arg)
        i += 1

    if not targets:
        print("Usage: python InstrumentationPipeline.py [--incremental] [--mapping FILE] <target1> [target2 ...]",
              file=sys.stderr)
        sys.exit(1)

    pipeline = InstrumentationPipeline(is_incremental, mapping_file)
    pipeline.run(targets)


if __name__ == '__main__':
    main()
