#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import tempfile
import subprocess

def _detect_editor():
    """
    Detect system default editor
    """
    env_editor = os.environ.get('EDITOR')
    if env_editor:
        return env_editor
    if sys.platform == 'darwin':
        return 'nano'
    if os.name == 'nt':
        return 'notepad'
    for candidate in ('nano', 'vim', 'vi'):
        return candidate
    return 'vi'

def get_multiline_input_via_editor(step_title, prompt_hint):
    """
    Get multiline input via system default editor
    
    :param step_title: Step title prompt
    :param prompt_hint: Input hint for user (example, etc.)
    :return: User input string or empty string
    """
    editor = _detect_editor()
    
    # Create temporary file
    with tempfile.NamedTemporaryFile(mode='w+', suffix='.txt', delete=False, encoding='utf-8') as tf:
        tf.write(f"# {step_title}\n")
        tf.write(f"# {prompt_hint}\n")
        tf.write("# Please enter your content below (Lines starting with '#' are ignored).\n")
        tf.write("# After saving and closing the editor, the program will continue automatically.\n\n")
        temp_path = tf.name

    print(f"\n💬 {step_title}")
    print(f"👉 Opening editor ({editor}) for multiline input. Please save and close the window to continue...")
    
    # Blocking call to editor
    subprocess.call(f'{editor} "{temp_path}"', shell=True)

    # Read user input
    content_lines = []
    with open(temp_path, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip().startswith('#'):
                content_lines.append(line)

    # Clean up temporary file
    os.remove(temp_path)
    
    result = "".join(content_lines).strip()
    if not result:
        print("⚠️ No valid input detected, returning empty string.")
        return ""
        
    return result