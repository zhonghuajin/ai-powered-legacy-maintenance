#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import re
import json

# ==========================================
# 1. Path resolution logic
# ==========================================

def load_base_dirs(dirs_file_path):
    """Load the list of base directories from the configuration file."""
    if not os.path.exists(dirs_file_path):
        print(f"Warning: Base directory file '{dirs_file_path}' not found. Using current directory as fallback.")
        return ["."]
        
    base_dirs = []
    try:
        with open(dirs_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    base_dirs.append(line)
    except Exception as e:
        print(f"Failed to read base directory file: {e}")
        return ["."]
        
    if not base_dirs:
        base_dirs = ["."]
    return base_dirs

def resolve_file_path(relative_path, base_dirs):
    """
    Search for a relative path within the given base directories and return the absolute path.
    Supports recursive search to match package paths like 'com/example/...'.
    """
    norm_rel_path = os.path.normpath(relative_path)
    
    for base_dir in base_dirs:
        if not os.path.exists(base_dir):
            continue
            
        # 1. Try direct concatenation
        direct_path = os.path.normpath(os.path.join(base_dir, norm_rel_path))
        if os.path.exists(direct_path) and os.path.isfile(direct_path):
            return direct_path
            
        # 2. If direct concatenation fails, search recursively in base_dir
        for root, dirs, files in os.walk(base_dir):
            for file in files:
                full_path = os.path.join(root, file)
                if full_path.endswith(norm_rel_path):
                    return full_path
                    
    return None

# ==========================================
# 2. Parse output.md content
# ==========================================

def parse_output_md(content):
    """
    Parse output.md to extract file paths and their corresponding content.
    Returns a dictionary: { 'relative/path/to/File.java': 'file_content' }
    """
    files_to_update = {}
    
    # Strategy 1: Try to match the <!-- FILE_CONTENT_START: [filepath] --> format
    pattern = r'<!-- FILE_CONTENT_START:\s*(.*?)\s*-->(.*?)<!-- FILE_CONTENT_END -->'
    matches = re.findall(pattern, content, re.DOTALL)
    
    if matches:
        for filepath, file_content in matches:
            files_to_update[filepath.strip()] = file_content.strip() + "\n"
        return files_to_update

    # Strategy 2: If no markers, try to infer the path via Java package and class declarations
    # Split file blocks by "package " (ignore the first empty block)
    blocks = content.split("package ")
    for block in blocks[1:]:
        block = "package " + block
        
        # Extract package name
        pkg_match = re.search(r'package\s+([a-zA-Z0-9_.]+)\s*;', block)
        # Extract public class name
        cls_match = re.search(r'public\s+(?:class|interface|enum)\s+([a-zA-Z0-9_]+)', block)
        
        if pkg_match and cls_match:
            pkg_path = pkg_match.group(1).replace('.', '/')
            cls_name = cls_match.group(1)
            filepath = f"{pkg_path}/{cls_name}.java"
            files_to_update[filepath] = block.strip() + "\n"
            
    return files_to_update

# ==========================================
# 3. Main program logic
# ==========================================

def run_apply_fix(fixed_code_path=None, base_dirs=None, prompt_context=None, proj_path=None):
    """
    Exposed interface to run the fix application logic.
    """
    print("="*50)
    print(" AI Code Fix Auto-Apply Tool")
    print("="*50)
    
    if not fixed_code_path:
        fixed_code_path = input("1. Please enter the file path containing the fixed code [Default: output.md]:\n> ").strip() or "output.md"
        
    if not os.path.exists(fixed_code_path):
        print(f"Error: File '{fixed_code_path}' not found.")
        return False
        
    if base_dirs is None:
        dirs_file = input("\n2. Please enter the file path containing the base search directories [Default: target-folders.txt]:\n> ").strip() or "target-folders.txt"
        base_dirs = load_base_dirs(dirs_file)
        
    print(f"Loaded {len(base_dirs)} base search directories.")

    # Read output.md
    try:
        with open(fixed_code_path, 'r', encoding='utf-8') as f:
            output_content = f.read()
    except Exception as e:
        print(f"Failed to read {fixed_code_path}: {e}")
        return False
        
    # Parse file content
    files_to_update = parse_output_md(output_content)
    
    if not files_to_update:
        print("Failed to parse any valid code blocks or file paths in the file.")
        return False
        
    print(f"\nSuccessfully parsed {len(files_to_update)} files, preparing to replace...")
    
    # Find and replace local files
    success_count = 0
    success_files = []
    for rel_path, new_content in files_to_update.items():
        print(f"\nProcessing: {rel_path}")
        abs_path = resolve_file_path(rel_path, base_dirs)
        
        if not abs_path:
            if base_dirs and len(base_dirs) > 0:
                abs_path = os.path.normpath(os.path.join(base_dirs[0], rel_path))
                os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                print(f"   Info: File not found locally. Assuming it is a NEW file inferred by AI.")
                print(f"   Info: Creating directories for -> {abs_path}")
            else:
                print(f"   Failed: Could not find the file and no base directories available.")
                continue
            
        try:
            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"   Success: Overwrote/Created file -> {abs_path}")
            success_count += 1
            success_files.append(rel_path)
        except Exception as e:
            print(f"   Failed to write file {abs_path}: {e}")
            
    # Update the prompt context with modified paths and remove additional_info
    if prompt_context:
        if "additional_info" in prompt_context:
            del prompt_context["additional_info"]
        
        prompt_context["modified_paths"] = success_files
        
        context_file_path = os.path.join(os.getcwd(), 'last_prompt_context.json')
        try:
            with open(context_file_path, 'w', encoding='utf-8') as f:
                json.dump(prompt_context, f, ensure_ascii=False, indent=4)
            print(f"   Success: Updated prompt context at -> {context_file_path}")
        except Exception as e:
            print(f"[WARN] Failed to update prompt context: {e}")

    print("\n" + "="*50)
    print(f"Execution completed! Successfully updated {success_count}/{len(files_to_update)} files.")
    print("="*50)
    return True

if __name__ == "__main__":
    try:
        success = run_apply_fix()
        if not success:
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
        sys.exit(0)