#!/usr/bin/env python3
"""
BlockWrapperTool.py - Ensures all compound statements in Python source files
use multi-line block format (body on separate indented lines).

Usage: python BlockWrapperTool.py <file_or_directory_path>
"""

import ast
import os
import sys
import re


def find_single_line_compounds(source_lines):
    """
    Find compound statements where the body is on the same line.
    e.g., `if x: return y` -> should become:
        if x:
            return y
    """
    changes = []
    try:
        tree = ast.parse('\n'.join(source_lines))
    except SyntaxError:
        return changes

    for node in ast.walk(tree):
        # Check compound statements: If, For, While, With, Try
        if isinstance(node, (ast.If, ast.For, ast.While, ast.With)):
            # Check if body starts on same line as the statement
            if node.body and node.body[0].lineno == node.lineno:
                changes.append({
                    'lineno': node.lineno,
                    'col_offset': node.col_offset,
                    'type': type(node).__name__
                })

            # Handle elif/else for If
            if isinstance(node, ast.If):
                for handler in (node.orelse if node.orelse else []):
                    if isinstance(handler, ast.If) and handler.body and handler.body[0].lineno == handler.lineno:
                        changes.append({
                            'lineno': handler.lineno,
                            'col_offset': handler.col_offset,
                            'type': 'Elif'
                        })

        # Handle else clauses on for/while
        if isinstance(node, (ast.For, ast.While)) and node.orelse:
            # else clause body on same line
            pass

    return changes


def expand_single_line_compound(line):
    """
    Expand a single-line compound statement to multi-line.
    e.g., 'if x: return y' -> 'if x:\n    return y'
    """
    # Match patterns like: <indent><keyword> <condition>: <body>
    pattern = r'^(\s*)(if\s+.+?|elif\s+.+?|else|for\s+.+?|while\s+.+?|with\s+.+?|try|except.*?|finally):\s*(.+)$'
    match = re.match(pattern, line)
    if match:
        indent = match.group(1)
        header = match.group(2)
        body = match.group(3).strip()
        if body and not body.startswith('#'):
            return f"{indent}{header}:\n{indent}    {body}"
    return line


def process_file(file_path):
    """Process a single Python file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except (IOError, UnicodeDecodeError) as e:
        print(f"[Error] Cannot read {file_path}: {e}")
        return

    lines = content.split('\n')
    has_changed = False
    new_lines = []

    for line in lines:
        expanded = expand_single_line_compound(line)
        if expanded != line:
            has_changed = True
            new_lines.append(expanded)
        else:
            new_lines.append(line)

    if has_changed:
        new_content = '\n'.join(new_lines)
        # Verify the new content is still valid Python
        try:
            ast.parse(new_content)
        except SyntaxError:
            print(f"[Skip] Expansion would create invalid syntax: {file_path}")
            return

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"[Updated] {file_path}")
    else:
        pass  # No changes needed


def process_directory_or_file(target_path):
    """Recursively process Python files."""
    skip_dirs = {'__pycache__', '.git', '.venv', 'venv', 'node_modules', '.tox', '.mypy_cache', 'dist', 'build', '.eggs'}

    if os.path.isfile(target_path):
        if target_path.endswith('.py'):
            process_file(target_path)
        return

    if os.path.isdir(target_path):
        for root, dirs, files in os.walk(target_path):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for f in files:
                if f.endswith('.py'):
                    process_file(os.path.join(root, f))
    else:
        print(f"Path does not exist: {target_path}")
        sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print("Usage: python BlockWrapperTool.py <file or directory path>")
        sys.exit(1)

    target_path = os.path.abspath(sys.argv[1])

    if not os.path.exists(target_path):
        print(f"Path does not exist: {target_path}")
        sys.exit(1)

    print(f"Start processing: {target_path}")
    process_directory_or_file(target_path)
    print("Processing completed!")


if __name__ == '__main__':
    main()
