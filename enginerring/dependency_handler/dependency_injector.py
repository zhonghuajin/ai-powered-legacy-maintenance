# enginerring/dependency_handler/dependency_injector.py
import os
import json
import re
from print_utils.utils import Colors, print_color

# Import LLM client for AI-driven injection
try:
    from enginerring.ask_llm.llm_chat import LLMClient
except ImportError:
    LLMClient = None

def load_snippets(json_path):
    if not os.path.exists(json_path):
        print_color(f"[!] Dependency snippets JSON not found at {json_path}", Colors.RED)
        return {}
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def parse_llm_response(response_text):
    """
    Parse LLM response to extract each line as an absolute file path.
    """
    lines = response_text.strip().split('\n')
    return [line.strip() for line in lines if line.strip()]

def _build_injection_prompt(file_path, original_content, snippet):
    """
    Build a prompt to ask the LLM to inject the given snippet into the file
    and return the complete modified file content.
    """
    ext = os.path.splitext(file_path)[1].lower().replace('.', '')
    lang_marker = ext if ext else 'text'

    prompt = f"""You are an expert build engineer. Given the file path, its current content, and a dependency snippet that must be added, produce the **complete modified file content** that correctly includes the snippet in the appropriate location.

### File Path
{file_path}

### Current File Content
{original_content}

### Dependency Snippet to Add
```{lang_marker}
{snippet}
```

### Output Requirements
- Return ONLY the complete modified file content, wrapped in a markdown code block with language identifier (e.g. ```{lang_marker} ... ```).
- Ensure the syntax is well-formed (e.g., valid JSON for composer.json/package.json, valid XML for pom.xml) and the snippet is placed respecting the file's structure.
- Do not include any explanation, just the code block."""
    return prompt

def _extract_code_from_response(answer):
    """
    Extract the content of the first code block from the LLM answer.
    Returns the code as a string, or None if not found.
    """
    match = re.search(r'```[a-zA-Z]*\s*\n(.*?)\n```', answer, re.DOTALL)
    if match:
        return match.group(1).strip()
    
    print_color("[!] AI response might not be perfectly formatted; attempting fallback extraction.", Colors.YELLOW)
    clean_answer = re.sub(r'^```[a-zA-Z]*\s*', '', answer.strip())
    clean_answer = re.sub(r'\s*```$', '', clean_answer)
    return clean_answer.strip()

def inject_dependency_into_file(file_path, snippet, work_dir=None):
    """
    Ask the AI to decide how to inject the dependency snippet into the file,
    then overwrite the file with the AI-provided modified content.
    """
    if not os.path.exists(file_path):
        print_color(f"[!] File not found: {file_path}", Colors.RED)
        return False

    # Read original file content
    with open(file_path, 'r', encoding='utf-8') as f:
        original_content = f.read()

    filename = os.path.basename(file_path)
    print_color(f"  [AI Injection] Asking AI to inject dependency into {filename}...", Colors.CYAN)

    # Build the prompt
    prompt = _build_injection_prompt(file_path, original_content, snippet)

    # Determine LLM provider from environment (set earlier in the workflow)
    provider = os.environ.get('AUTO_SELECTED_LLM_PROVIDER', 'deepseek')
    if LLMClient is None:
        print_color("[!] LLM client module not available. Falling back to simple injection.", Colors.YELLOW)
        return _simple_inject(file_path, snippet, original_content)

    try:
        client = LLMClient(provider=provider)
        answer = client.chat(prompt, stream=False)
    except Exception as e:
        print_color(f"[!] LLM call failed: {e}", Colors.RED)
        return False

    new_content = _extract_code_from_response(answer)
    if not new_content:
        print_color("[!] Failed to extract file content from AI response.", Colors.RED)
        return False

    if work_dir:
        normalized_work_dir = work_dir.replace('\\', '/')
        new_content = new_content.replace('{{CURRENT_WORKING_DIR}}', normalized_work_dir)

    # Overwrite the file with the new content
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return True
    except Exception as e:
        print_color(f"[!] Failed to write {file_path}: {e}", Colors.RED)
        return False

def _simple_inject(file_path, snippet, content):
    """
    Fallback simple injection logic (original behavior) for cases where AI is unavailable.
    """
    filename = os.path.basename(file_path).lower()
    if filename == "pom.xml":
        if snippet in content:
            print_color(f"[-] Dependency already exists in {file_path}", Colors.YELLOW)
            return True
        insert_idx = content.rfind('</dependencies>')
        if insert_idx != -1:
            new_content = content[:insert_idx] + f"    {snippet}\n" + content[insert_idx:]
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            return True
        else:
            print_color(f"[!] Could not find </dependencies> tag in {file_path}", Colors.RED)
            return False
    else:
        print_color(f"[!] Auto-injection for {filename} is not fully implemented yet. Please add manually:\n{snippet}", Colors.YELLOW)
        return False

# Added work_dir parameter with default None for backward compatibility
def run_injection(llm_response_file, snippets_json_path, work_dir=None):
    if not os.path.exists(llm_response_file):
        print_color(f"[!] LLM response file not found: {llm_response_file}", Colors.RED)
        return

    with open(llm_response_file, 'r', encoding='utf-8') as f:
        response_text = f.read()

    target_files = parse_llm_response(response_text)
    if not target_files:
        print_color("[-] No target dependency files identified by LLM.", Colors.YELLOW)
        return

    snippets = load_snippets(snippets_json_path)
    
    print_color(f"\n>>> Injecting dependencies into {len(target_files)} files...", Colors.CYAN)
    for file_path in target_files:
        filename = os.path.basename(file_path)
        snippet = snippets.get(filename)
        
        if not snippet:
            print_color(f"[!] No snippet defined for {filename} in JSON.", Colors.RED)
            continue
            
        if work_dir and snippet:
            normalized_work_dir = work_dir.replace('\\', '/')
            snippet = snippet.replace('{{CURRENT_WORKING_DIR}}', normalized_work_dir)
            snippet = snippet.replace('{{WORK_DIR}}', normalized_work_dir)
            
        success = inject_dependency_into_file(file_path, snippet, work_dir)
        if success:
            print_color(f"[+] Successfully injected dependency into {file_path}", Colors.GREEN)