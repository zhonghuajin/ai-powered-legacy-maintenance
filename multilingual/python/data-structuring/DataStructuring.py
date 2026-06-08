import os
import sys
import ast
import glob
import re
from typing import List, Dict, Optional, Set, Any

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
        self.lines = file_content.splitlines()

        self.current_module = ""
        self.class_stack: List[str] = []
        self.node_stack: List[ast.AST] = []
        self.closure_names: Dict[int, str] = {}

        self.methods: Dict[str, MethodNode] = {}

    def get_original_line(self, node: ast.AST) -> int:
        """
        尝试从节点或其前后的注释中寻找 '# line: 123' 形式的原始行号。
        如果找不到，则返回 AST 节点的默认起始行。
        """

        start_line = getattr(node, 'lineno', 1)

        lookback = max(0, start_line - 4)
        for i in range(start_line - 1, lookback - 1, -1):
            if i < len(self.lines):
                line_str = self.lines[i]
                match = re.search(r'#\s*line:\s*(\d+)', line_str)
                if match:
                    return int(match.group(1))

        return start_line

    def compute_closure_name(self, node: ast.AST) -> str:
        """
        推导嵌套函数（闭包）或 Lambda 的名称（对应 PHP 的 computeClosureName）
        """
        n = len(self.node_stack)
        parent = self.node_stack[-1] if n >= 1 else None
        grand = self.node_stack[-2] if n >= 2 else None

        if isinstance(parent, ast.Assign):

            if len(parent.targets) == 1 and isinstance(parent.targets[0], ast.Name):
                return parent.targets[0].id

            elif len(parent.targets) == 1 and isinstance(parent.targets[0], ast.Attribute):
                return parent.targets[0].attr

        if isinstance(parent, (ast.Call, ast.keyword)):
            callee = 'callback'
            call_node = grand if isinstance(grand, ast.Call) else parent
            if isinstance(call_node, ast.Call):
                if isinstance(call_node.func, ast.Name):
                    callee = call_node.func.id
                elif isinstance(call_node.func, ast.Attribute):
                    callee = call_node.func.attr
            return f"{callee}$cb"

        return 'closure'

    def visit(self, node: ast.AST):
        """
        重写 visit 方法以维护 node_stack 并实现 enterNode / leaveNode 逻辑
        """

        is_closure = isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)) and len(self.class_stack) > 0 and len([n for n in self.node_stack if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]) > 0
        is_lambda = isinstance(node, ast.Lambda)

        if is_closure or is_lambda:
            self.closure_names[id(node)] = self.compute_closure_name(node)

        if isinstance(node, ast.ClassDef):
            class_name = node.name if node.name else 'anonymous'
            self.class_stack.append(class_name)

        self.node_stack.append(node)

        is_func = isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
        if is_func:
            self._process_function(node)

        self.generic_visit(node)

        self.node_stack.pop()
        if isinstance(node, ast.ClassDef):
            self.class_stack.pop()

    def _process_function(self, node: ast.AST):

        if self.is_empty_method(node):
            return

        is_lambda = isinstance(node, ast.Lambda)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            method_name = node.name

            if method_name in ('__init__', '__del__'):
                return
        else:
            method_name = self.closure_names.get(id(node), 'closure')

        param_count = len(node.args.args)
        if node.args.vararg: param_count += 1
        if node.args.kwarg: param_count += 1

        start_line = self.get_original_line(node)

        source_code = ""
        if hasattr(node, 'lineno') and hasattr(node, 'end_lineno'):

            start_idx = node.lineno - 1
            end_idx = node.end_lineno
            source_code = "\n".join(self.lines[start_idx:end_idx])

        is_global_func = len(self.class_stack) == 0
        if is_global_func:
            full_name = f"{self.current_module}.{method_name}" if self.current_module else method_name
            signature = f"{full_name}@{start_line}"
            class_name = "<global>"
        else:
            current_class = self.class_stack[-1] if self.class_stack else ""
            if current_class:
                full_class_name = f"{self.current_module}.{current_class}" if self.current_module else current_class
                signature = f"{full_class_name}::{method_name}@{start_line}"
                class_name = full_class_name
            else:
                signature = f"{method_name}@{start_line}"
                class_name = ""

        node_obj = MethodNode(
            signature=signature,
            class_name=class_name,
            method_name=method_name,
            param_count=param_count,
            source_code=source_code,
            file_path=self.file_path,
            start_line=start_line
        )

        calls_in_method = []
        self.collect_calls(node, calls_in_method)
        node_obj.calls = calls_in_method

        self.methods[signature] = node_obj

    def is_empty_method(self, node: ast.AST) -> bool:
        if isinstance(node, ast.Lambda):
            return node.body is None
        if not hasattr(node, 'body') or not node.body:
            return True

        if len(node.body) == 1:
            stmt = node.body[0]
            if isinstance(stmt, ast.Pass):
                return True
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                return True
        return False

    def collect_calls(self, parent_node: ast.AST, calls: List[MethodCallInfo]):
        """
        在当前方法体内部，使用一个局部的 Visitor 收集所有的 Call 节点，
        但遇到嵌套的 FunctionDef/Lambda 时停止向下遍历（避免混入闭包内部的调用）。
        """
        class CallVisitor(ast.NodeVisitor):
            def __init__(self, calls_ref: List[MethodCallInfo]):
                self.calls_ref = calls_ref

            def visit(self, node: ast.AST):

                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                    return

                if isinstance(node, ast.Call):
                    scope = None
                    name = ""
                    arg_count = len(node.args) + len(node.keywords)

                    if isinstance(node.func, ast.Attribute):
                        name = node.func.attr
                        if isinstance(node.func.value, ast.Name):
                            scope = node.func.value.id

                    elif isinstance(node.func, ast.Name):
                        name = node.func.id

                    if name:
                        self.calls_ref.append(MethodCallInfo(scope, name, arg_count))

                self.generic_visit(node)

        visitor = CallVisitor(calls)

        if isinstance(parent_node, ast.Lambda):
            visitor.visit(parent_node.body)
        else:
            for stmt in parent_node.body:
                visitor.visit(stmt)

class DataStructuring:
    @staticmethod
    def run(argv: List[str]) -> int:
        if len(argv) < 2:
            sys.stderr.write("Usage: python DataStructuring.py <pruned_directory_path>\n")
            sys.stderr.write("Example: python DataStructuring.py ./pruned\n")
            return 1

        pruned_dir_path = argv[1]
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

        thread_dirs = sorted([
            d for d in glob.glob(os.path.join(pruned_dir_path, '*'))
            if os.path.isdir(d)
        ])

        order = 0
        for thread_path in thread_dirs:
            thread_name = os.path.basename(thread_path)
            print(f"Processing thread: {thread_name}")

            md += f"# Thread: {thread_name} (Order: {order})\n\n"
            order += 1

            py_files = DataStructuring.get_py_files(thread_path)

            for py_file in py_files:
                try:
                    with open(py_file, 'r', encoding='utf-8', errors='replace') as f:
                        code = f.read()

                    tree = ast.parse(code, filename=py_file)

                    rel_path = os.path.relpath(py_file, pruned_dir_path).replace('\\', '/')

                    parts = rel_path.split('/')
                    if len(parts) > 1:
                        parts.pop(0)
                        rel_path = '/'.join(parts)

                    visitor = MethodCollectorVisitor(rel_path, code)
                    visitor.visit(tree)

                    if not visitor.methods:
                        continue

                    md += f"## File: `{rel_path}`\n\n"
                    md += DataStructuring.render_call_tree(visitor.methods)

                except Exception as e:
                    sys.stderr.write(f"Warning: Failed to parse file {py_file} : {str(e)}\n")

        with open(output_file_path, 'w', encoding='utf-8') as f:
            f.write(md)
        print(f"[SUCCESS] Markdown generated at: {output_file_path}")

        return 0

    @staticmethod
    def get_py_files(directory: str) -> List[str]:
        py_files = []
        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith('.py'):
                    py_files.append(os.path.join(root, file))
        return sorted(py_files)

    @staticmethod
    def render_call_tree(methods: Dict[str, MethodNode]) -> str:
        md = ""
        called_signatures: Set[str] = set()
        adjacency_list: Dict[str, List[str]] = {sig: [] for sig in methods}

        for sig, node in methods.items():
            for call in node.calls:
                for target_sig, target_node in methods.items():
                    if target_node.method_name == call.name:
                        is_match = False

                        if call.scope is None or call.scope in ('self', 'cls'):
                            is_match = True
                        elif call.scope == target_node.class_name or target_node.class_name.endswith('.' + call.scope):
                            is_match = True

                        if is_match:
                            adjacency_list[sig].append(target_sig)
                            called_signatures.add(target_sig)

            adjacency_list[sig] = list(dict.fromkeys(adjacency_list[sig]))

        root_signatures = [sig for sig in methods if sig not in called_signatures]
        if not root_signatures:
            root_signatures = list(methods.keys())

        visited: Dict[str, bool] = {}

        for root_sig in root_signatures:
            md += DataStructuring.dfs_render(root_sig, methods, adjacency_list, 0, visited)

        for sig in methods:
            if sig not in visited:
                md += DataStructuring.dfs_render(sig, methods, adjacency_list, 0, visited)

        return md

    @staticmethod
    def dfs_render(
        sig: str,
        methods: Dict[str, MethodNode],
        adjacency_list: Dict[str, List[str]],
        depth: int,
        visited: Dict[str, bool]
    ) -> str:
        indent = '    ' * depth
        if sig in visited:
            node = methods[sig]
            return f"{indent}- **Method:** `{node.signature}` *(See above)*\n{indent}---\n\n"

        visited[sig] = True
        node = methods[sig]
        md = DataStructuring.render_method(node, depth)
        md += f"{indent}---\n\n"

        if sig in adjacency_list:
            for child_sig in adjacency_list[sig]:
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

                if call.scope and call.scope not in ('self', 'cls'):
                    scope_str = f"{call.scope}."
                md += f"{indent}    - `{scope_str}{call.name}({call.arg_count} args)`\n"

        md += "\n"
        return md

if __name__ == '__main__':
    sys.exit(DataStructuring.run(sys.argv))