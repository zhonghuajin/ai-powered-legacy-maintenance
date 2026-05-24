#!/usr/bin/env python3
"""
DataStructuring.py - Analyzes pruned Python code to build call graphs.

Generates a markdown document showing the execution call tree for each thread,
with actual source code inline.

Usage: python DataStructuring.py <pruned_directory>
"""

import ast
import os
import sys

DEFAULT_OUTPUT_FILE = 'final-output-calltree.md'


class MethodNode:
    def __init__(self, class_name, method_name, param_count, source_code, file_path):
        self.class_name = class_name
        self.method_name = method_name
        self.param_count = param_count
        self.source_code = source_code
        self.file_path = file_path
        self.calls = []


class MethodCallInfo:
    def __init__(self, scope, name, arg_count):
        self.scope = scope
        self.name = name
        self.arg_count = arg_count


def analyze_file(file_path, relative_path):
    """Parse a Python file and extract functions/methods and their calls."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            code = f.read()
    except (IOError, UnicodeDecodeError):
        return [], {}

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        print(f"[ERROR] Cannot parse file: {file_path}: {e}", file=sys.stderr)
        return [], {}

    methods = {}
    raw_calls = {}
    current_class = '<global>'

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            current_class = node.name

    # Use a visitor approach for proper class context
    class MethodCollector(ast.NodeVisitor):
        def __init__(self):
            self.current_class = '<global>'
            self.methods = {}
            self.raw_calls = {}

        def visit_ClassDef(self, node):
            old_class = self.current_class
            self.current_class = node.name
            self.generic_visit(node)
            self.current_class = old_class

        def visit_FunctionDef(self, node):
            self._process_function(node)

        def visit_AsyncFunctionDef(self, node):
            self._process_function(node)

        def _process_function(self, node):
            if not node.body:
                return

            method_name = node.name
            param_count = len(node.args.args)
            # Extract source code
            start_line = node.lineno - 1
            end_line = node.end_lineno if hasattr(node, 'end_lineno') and node.end_lineno else node.lineno
            source_lines = code.split('\n')[start_line:end_line]
            source_code = '\n'.join(source_lines)

            class_name = self.current_class
            sig = f"{class_name}::{method_name}_{param_count}"
            method_node = MethodNode(class_name, method_name, param_count, source_code, relative_path)
            self.methods[sig] = method_node

            # Collect calls within this function
            calls = []
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    call_info = _extract_call_info(child)
                    if call_info:
                        calls.append(call_info)

            self.raw_calls[id(method_node)] = calls

    collector = MethodCollector()
    collector.visit(tree)

    return collector.methods, collector.raw_calls


def _extract_call_info(call_node):
    """Extract call information from an ast.Call node."""
    func = call_node.func
    arg_count = len(call_node.args)

    if isinstance(func, ast.Name):
        return MethodCallInfo(None, func.id, arg_count)
    elif isinstance(func, ast.Attribute):
        scope = None
        if isinstance(func.value, ast.Name):
            scope = func.value.id
        return MethodCallInfo(scope, func.attr, arg_count)
    return None


def find_matching_method(call, method_map, caller_class):
    """Find a matching method for a call."""
    # Try matching with caller's class context
    if call.scope is None or call.scope == 'self' or call.scope == 'cls':
        key = f"{caller_class}::{call.name}_{call.arg_count}"
        if key in method_map:
            return method_map[key]

    # Try with explicit scope
    if call.scope is not None:
        key = f"{call.scope}::{call.name}_{call.arg_count}"
        if key in method_map:
            return method_map[key]

    # Try matching by name and arg count only
    for node in method_map.values():
        if node.method_name == call.name and node.param_count == call.arg_count:
            return node

    return None


def render_call_node(node, level, visited=None):
    """Render a call tree node as markdown."""
    if visited is None:
        visited = set()

    node_id = id(node)
    indent = '    ' * level
    content_indent = indent + '    '
    md = ''

    if node.file_path:
        md += f"{indent}- *File:* `{node.file_path}`\n"
    else:
        md += f"{indent}- *(no file)*\n"

    if node.source_code:
        source = node.source_code.strip()
        md += f"{content_indent}```python\n"
        for line in source.split('\n'):
            md += f"{content_indent}{line}\n"
        md += f"{content_indent}```\n"

    if node.calls:
        md += f"{content_indent}*Calls:*\n"
        for child in node.calls:
            child_id = id(child)
            if child_id in visited:
                md += f"{'    ' * (level + 1)}- *[Circular: {child.method_name}]*\n"
                continue
            visited.add(child_id)
            md += render_call_node(child, level + 1, visited)

    return md


def generate_markdown(input_dir, output_path):
    """Generate the call tree markdown document."""
    if not os.path.isdir(input_dir):
        print(f"[ERROR] Input directory does not exist: {input_dir}", file=sys.stderr)
        sys.exit(1)

    md = '# Thread Traces\n\n'
    md += '> **Data Schema & Legend:**\n'
    md += '> This section represents the execution call tree for each thread.\n'
    md += '> - **Call Tree**: Hierarchical execution flow. Each node contains the source file and pruned source code.\n\n'

    items = sorted(os.listdir(input_dir))
    order = 0

    for item in items:
        item_path = os.path.join(input_dir, item)
        if not os.path.isdir(item_path):
            continue

        print(f"Processing thread: {item}")
        md += f"## {item} (Order: {order})\n"
        order += 1

        # Collect all .py files in this thread directory
        py_files = []
        for root, dirs, files in os.walk(item_path):
            for f in files:
                if f.endswith('.py'):
                    py_files.append(os.path.join(root, f))

        if not py_files:
            md += '\n---\n\n'
            continue

        all_methods = {}
        all_raw_calls = {}

        for py_file in py_files:
            relative_path = os.path.relpath(py_file, os.getcwd()).replace('\\', '/')
            methods, raw_calls = analyze_file(py_file, relative_path)
            all_methods.update(methods)
            all_raw_calls.update(raw_calls)

        # Build call graph
        called_nodes = set()
        for caller in all_methods.values():
            calls = all_raw_calls.get(id(caller), [])
            for call in calls:
                callee = find_matching_method(call, all_methods, caller.class_name)
                if callee is not None and callee is not caller:
                    caller.calls.append(callee)
                    called_nodes.add(id(callee))

        # Find entry points (methods never called by others)
        entry_points = [n for n in all_methods.values() if id(n) not in called_nodes]
        if not entry_points and all_methods:
            entry_points = list(all_methods.values())

        for root_node in entry_points:
            md += render_call_node(root_node, 0)

        md += '\n---\n\n'

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(md)

    print(f"[SUCCESS] Static analysis completed!")
    print(f"[SUCCESS] Dependency report saved to: {output_path}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python DataStructuring.py <input_directory>")
        print("Example: python DataStructuring.py ./pruned")
        sys.exit(1)

    input_dir = sys.argv[1]
    output_path = os.path.join(os.getcwd(), DEFAULT_OUTPUT_FILE)
    generate_markdown(input_dir, output_path)


if __name__ == '__main__':
    main()
