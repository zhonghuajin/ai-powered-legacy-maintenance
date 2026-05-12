import os
import re

def validate_path_string(path_str, check_exists=False):
    """
    Validate whether the given string is a legitimate file/directory path format.
    
    :param path_str: The path string to validate
    :param check_exists: Whether to strictly check if the path exists on the disk
    """
    if not isinstance(path_str, str):
        raise ValueError(f"Input must be a string, currently: {type(path_str)}")
    
    if not path_str.strip():
        raise ValueError("Path cannot be empty or contain only whitespace characters.")
        
    if '\n' in path_str or '\r' in path_str:
        raise ValueError(f"Path cannot contain newline characters, this might be an illegal multi-line string: {path_str}")
        
    # Check for illegal characters common in Windows/Linux file systems
    # Note: Colons (:) and slashes (\/) are excluded as they are valid path separators and drive indicators
    illegal_chars = re.compile(r'[<>\"|?*]')
    if illegal_chars.search(path_str):
        raise ValueError(f"Path contains illegal special characters (<, >, \", |, ?, *): {path_str}")

    # [Optional Constraint] If you want to ensure these paths actually exist on the current machine, enable this:
    if check_exists and not os.path.exists(path_str):
        raise ValueError(f"Path does not exist in the current file system: {path_str}")

    return True


def generate_prompt(dependency_files, whitelist_paths, dependency_snippet):
    """
    Generate a prompt for analyzing where to add an instrumentation dependency.

    :param dependency_files: list of str, paths to dependency management files
    :param whitelist_paths: list of str, whitelist directories needing instrumentation
    :param dependency_snippet: str, the dependency XML snippet to be added
    :return: str, the assembled prompt
    """

    # 0. Add input constraint validation
    if not isinstance(dependency_files, list) or not isinstance(whitelist_paths, list):
        raise ValueError("dependency_files and whitelist_paths must be of type list.")

    for file_path in dependency_files:
        validate_path_string(file_path)
        # If you want to further restrict dependency files to specific extensions, uncomment below:
        # if not (file_path.endswith('pom.xml') or file_path.endswith('package.json')):
        #     raise ValueError(f"Dependency file must be pom.xml or package.json: {file_path}")

    for dir_path in whitelist_paths:
        validate_path_string(dir_path)

    # 1. Format dependency management file list
    formatted_files = "\n".join([f"- {file}" for file in dependency_files])

    # 2. Format instrumentation whitelist list
    formatted_whitelist = "\n".join([f"- {path}" for path in whitelist_paths])

    # 3. Prompt template (English only)
    prompt_template = f"""You are an experienced software development engineer and build tool expert.
I need to add an instrumentation dependency in a multi-module project. Based on the provided "Instrumentation Whitelist Directories", analyze and infer which "Dependency Management Files" should include this dependency.

### 1. Candidate Dependency Management Files:
{formatted_files}

### 2. Instrumentation Whitelist Directories (directories where instrumentation should take effect):
{formatted_whitelist}

### 3. Instrumentation Dependency to Add:
```xml
{dependency_snippet}
```

### Task Requirements:
Analyze which module(s) the whitelist directories belong to, matching them to the dependency management files above.
Output ONLY the exact file paths that need modification, one path per line. 
Do not include brackets, bullet points, explanations, or any extra commentary. 

Example Output Format:
D:\temp\scenario-based-runtime-context-for-ai\poc\pom.xml
D:\temp\scenario-based-runtime-context-for-ai\poc\instrumentor-test\pom.xml
"""
    return prompt_template