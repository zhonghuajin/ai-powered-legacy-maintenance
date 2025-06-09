import ast
import os
import sys
import glob
import re
from typing import List, Optional, Dict, Any

class MethodNode:
    def __init__(
        self,
        signature: str,
        class_name: str,
        method_name: str,
        param_count: int,
        source_code: str,
        file_path: Optional[str],
        start_line: int
    ):
        self.signature = signature
        self.class_name = class_name
        self.method_name = method_name
        self.param_count = param_count
        self.source_code = source_code
        self.file_path = file_path
        self.start_line = start_line
        self.calls: List['MethodCallInfo'] = []

class MethodCallInfo:
    def __init__(self, scope: Optional[str], name: str, arg_count: int):
        self.scope = scope
        self.name = name
        self.arg_count = arg_count

class MethodCollectorVisitor(ast.NodeVisitor):
    def __init__(self, file_path: str, file_content: str):
        self.file_path = file_path
        self.file_content = file_content
        self.file_lines = file_content.splitlines()
        
        self.class_stack: List[str] = []
        self.methods: Dict[str, MethodNode] = {}
        
        # Add parent pointers to all nodes to help with lambda naming
        self.tree = ast.parse(file_content)
        for node in ast.walk(self.tree):
            for child in ast.iter_child_nodes(node):
                child.parent = node

    def get_original_line(self, node: ast.AST) -> int:
        """
        Attempts to find the injected 'line: X' string literal at the beginning of the function body.
        Falls back to the AST node's line number.
        """
        # First, try to extract the line number from the injected docstring-like constant
        if hasattr(node, 'body') and isinstance(node.body, list) and len(node.body) > 0:
            first_stmt = node.body[0]
            if isinstance(first_stmt, ast.Expr) and isinstance(getattr(first_stmt, 'value', None), ast.Constant):
                val = first_stmt.value.value
                if isinstance(val, str):
                    match = re.search(r'line:\s*(\d+)', val)
                    if match:
                        return int(match.group(1))
        
        # Fallback to the current line number in the pruned file
        return getattr(node, 'lineno', 1)

    def compute_closure_name(self, node: ast.Lambda) -> str:
        parent = getattr(node, 'parent', None)
        grand = getattr(parent, 'parent', None)

        if isinstance(parent, ast.Assign):
            for target in parent.targets:
                if isinstance(target, ast.Name):
                    return target.id
                elif isinstance(target, ast.Attribute):
                    return target.attr

        if isinstance(parent, ast.Call):
            callee = 'callback'
            if isinstance(parent.func, ast.Name):
                callee = parent.func.id
            elif isinstance(parent.func, ast.Attribute):
                callee = parent.func.attr
            return f"{callee}$cb"

        return 'closure'

    def is_empty_method(self, node: ast.AST) -> bool:
        if isinstance(node, ast.Lambda):
            return False # Lambdas always have an expression body
            
        if not hasattr(node, 'body') or not node.body:
            return True
            
        # Consider empty if it only contains 'pass' or a docstring (Expr with Str/Constant)
        for stmt in node.body:
            if isinstance(stmt, ast.Pass):
                continue
            if isinstance(stmt, ast.Expr) and isinstance(getattr(stmt, 'value', None), (ast.Str, ast.Constant)):
                continue
            return False
        return True

    def extract_calls(self, node: ast.AST) -> List[MethodCallInfo]:
        calls = []
        
        class CallVisitor(ast.NodeVisitor):
            def visit_FunctionDef(self, inner_node):
                pass # Don't traverse into nested functions
            def visit_AsyncFunctionDef(self, inner_node):
                pass
            def visit_Lambda(self, inner_node):
                pass
                
            def visit_Call(self, inner_node):
                arg_count = len(inner_node.args) + len(inner_node.keywords)
                if isinstance(inner_node.func, ast.Name):
                    calls.append(MethodCallInfo(None, inner_node.func.id, arg_count))
                elif isinstance(inner_node.func, ast.Attribute):
                    scope = None
                    if isinstance(inner_node.func.value, ast.Name):
                        scope = inner_node.func.value.id
                    calls.append(MethodCallInfo(scope, inner_node.func.attr, arg_count))
                self.generic_visit(inner_node)

        visitor = CallVisitor()
        # Traverse the body of the function/lambda
        if isinstance(node, ast.Lambda):
            visitor.visit(node.body)
        else:
            for stmt in node.body:
                visitor.visit(stmt)
                
        return calls

    def visit_ClassDef(self, node: ast.ClassDef):
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    def process_function(self, node: ast.AST, is_lambda: bool = False):
        if self.is_empty_method(node):
            return

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            method_name = node.name
            if method_name in ('__init__', '__del__'):
                return
            param_count = len(node.args.args) + len(node.args.kwonlyargs)
        else:
            method_name = self.compute_closure_name(node)
            param_count = len(node.args.args) + len(node.args.kwonlyargs)

        start_line = self.get_original_line(node)
        source_code = ast.get_source_segment(self.file_content, node) or ""

        current_class = self.class_stack[-1] if self.class_stack else ''
        
        if current_class:
            signature = f"{current_class}::{method_name}@{start_line}"
            class_name = current_class
        else:
            signature = f"{method_name}@{start_line}" if not is_lambda else f"{method_name}@{start_line}"
            class_name = '<global>' if not is_lambda else ''

        node_obj = MethodNode(
            signature=signature,
            class_name=class_name,
            method_name=method_name,
            param_count=param_count,
            source_code=source_code,
            file_path=self.file_path,
            start_line=start_line
        )

        node_obj.calls = self.extract_calls(node)
        self.methods[signature] = node_obj

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self.process_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self.process_function(node)
        self.generic_visit(node)

    def visit_Lambda(self, node: ast.Lambda):
        self.process_function(node, is_lambda=True)
        self.generic_visit(node)

    def run(self):
        self.visit(self.tree)


class DataStructuring:
    @staticmethod
    def run(args: List[str]) -> int:
        if len(args) < 2:
            sys.stderr.write("Usage: python data_structuring.py <pruned_directory_path>\n")
            sys.stderr.write("Example: python data_structuring.py ./pruned\n")
            return 1

        pruned_dir_path = args[1]
        output_file_path = "final-output-calltree.md"

        if not os.path.isdir(pruned_dir_path):
            sys.stderr.write(f"[ERROR] The directory does not exist: {pruned_dir_path}\n")
            return 1

        md = "# File-Internal Method Index (Call Tree View)\n\n"
        md += "> **Description & Legend:**\n"
        md += "> This document lists every function/method extracted via AST analysis, organized as a Call Tree.\n"
        md += "> - Indentation represents the file-internal calling hierarchy.\n"
        md += "> - Each method is emitted with a signature identical to the instrumentation pipeline (`name@line`, or `Class::method@line`).\n"
        md += "> - The line numbers and signatures are mapped back to the **original source code** using the injected comments.\n"
        md += "> - `*Calls:*` lists direct call expressions for reference only; it does not affect signature matching.\n\n"

        thread_dirs = [os.path.join(pruned_dir_path, d) for d in os.listdir(pruned_dir_path) 
                       if os.path.isdir(os.path.join(pruned_dir_path, d))]
        thread_dirs.sort()

        order = 0

        for thread_path in thread_dirs:
            thread_name = os.path.basename(thread_path)
            print(f"Processing thread: {thread_name}")

            md += f"# Thread: {thread_name} (Order: {order})\n\n"
            order += 1

            python_files = DataStructuring.get_python_files(thread_path)

            for py_file in python_files:
                try:
                    with open(py_file, 'r', encoding='utf-8') as f:
                        code = f.read()

                    if not code.strip():
                        continue

                    relative_path = os.path.relpath(py_file, pruned_dir_path).replace('\\', '/')
                    parts = relative_path.split('/')
                    if len(parts) > 1:
                        parts.pop(0)
                        relative_path = '/'.join(parts)

                    visitor = MethodCollectorVisitor(relative_path, code)
                    visitor.run()

                    if not visitor.methods:
                        continue

                    md += f"## File: `{relative_path}`\n\n"
                    md += DataStructuring.render_call_tree(visitor.methods)

                except Exception as e:
                    sys.stderr.write(f"Warning: Failed to parse file {py_file} : {str(e)}\n")

        with open(output_file_path, 'w', encoding='utf-8') as f:
            f.write(md)
            
        print(f"[SUCCESS] Markdown generated at: {output_file_path}")
        return 0

    @staticmethod
    def get_python_files(directory: str) -> List[str]:
        files = []
        for root, _, filenames in os.walk(directory):
            for filename in filenames:
                if filename.endswith('.py'):
                    files.append(os.path.join(root, filename))
        return files

    @staticmethod
    def render_call_tree(methods: Dict[str, MethodNode]) -> str:
        md = ""
        called_signatures = {}
        adjacency_list = {sig: [] for sig in methods}

        for sig, node in methods.items():
            for call in node.calls:
                for target_sig, target_node in methods.items():
                    if target_node.method_name == call.name:
                        is_match = False
                        if call.scope is None or call.scope in ['self', 'cls', 'super']:
                            is_match = True
                        elif call.scope == target_node.class_name or target_node.class_name.endswith('.' + call.scope):
                            is_match = True

                        if is_match:
                            adjacency_list[sig].append(target_sig)
                            called_signatures[target_sig] = True

            # Remove duplicates while preserving order
            adjacency_list[sig] = list(dict.fromkeys(adjacency_list[sig]))

        root_signatures = [sig for sig in methods if sig not in called_signatures]
        
        if not root_signatures:
            root_signatures = list(methods.keys())

        visited = {}
        for root_sig in root_signatures:
            md += DataStructuring.dfs_render(root_sig, methods, adjacency_list, 0, visited)

        for sig in methods:
            if sig not in visited:
                md += DataStructuring.dfs_render(sig, methods, adjacency_list, 0, visited)

        return md

    @staticmethod
    def dfs_render(sig: str, methods: Dict[str, MethodNode], adjacency_list: Dict[str, List[str]], depth: int, visited: Dict[str, bool]) -> str:
        if sig in visited:
            node = methods[sig]
            indent = '    ' * depth
            return f"{indent}- **Method:** `{node.signature}` *(See above)*\n{indent}---\n\n"

        visited[sig] = True
        node = methods[sig]
        md = DataStructuring.render_method(node, depth)
        md += ('    ' * depth) + "---\n\n"

        for child_sig in adjacency_list.get(sig, []):
            md += DataStructuring.dfs_render(child_sig, methods, adjacency_list, depth + 1, visited)

        return md

    @staticmethod
    def render_method(node: MethodNode, depth: int = 0) -> str:
        indent = '    ' * depth

        md = f"{indent}- **Method:** `{node.signature}` (Params: {node.param_count})\n"
        md += f"{indent}- **File Path:** `{node.file_path}`\n"
        md += f"{indent}- **Original Line:** `{node.start_line}`\n\n"

        if node.source_code:
            source = node.source_code.strip()
            lines = source.split('\n')
            indented_source = f"\n{indent}".join(lines)

            md += f"{indent}```python\n"
            md += f"{indent}{indented_source}\n"
            md += f"{indent}```\n"

        if node.calls:
            md += f"\n{indent}*Calls:*\n"
            for call in node.calls:
                scope_str = f"{call.scope}." if call.scope else ""
                md += f"{indent}    - `{scope_str}{call.name}({call.arg_count} args)`\n"

        md += "\n"
        return md


if __name__ == "__main__":
    sys.exit(DataStructuring.run(sys.argv))