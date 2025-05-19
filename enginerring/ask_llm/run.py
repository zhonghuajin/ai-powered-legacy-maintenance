# run.py
import os
import sys
import subprocess

def check_env():
    env_file = ".env"
    if not os.path.exists(env_file):
        print("\033[33m[*] .env file not found. Generating template...\033[0m")
        
        env_template = """# Fill in your API Keys here (leave blank if not needed)
OPENAI_API_KEY=""
DEEPSEEK_API_KEY=""
ZHIPU_API_KEY=""
MOONSHOT_API_KEY=""
DASHSCOPE_API_KEY=""
ANTHROPIC_API_KEY=""
POE_API_KEY=""

# Optional: Explicitly specify which provider to use. 
# Available options: deepseek, deepseek-v4pro, claude, gpt, glm, kimi, qwen, poe
STANDARD_LLM_PROVIDER=""
ADVANCED_LLM_PROVIDER=""
"""
        with open(env_file, "w", encoding="utf-8") as f:
            f.write(env_template)
        
        print("\033[32m[!] .env file generated. Please fill in your API keys and run this script again.\033[0m")
        sys.exit(1)

def check_dependencies():
    try:
        import openai
        import anthropic
        import dotenv
        import aiohttp
    except ImportError:
        print("\033[31m[Error] Missing dependencies detected.\033[0m")
        print("\033[33mPlease run 'python init.py' in the project root directory first to install required packages.\033[0m")
        sys.exit(1)


def run_api(file_path: str, output_path: str, provider: str = None, reasoning: str = "off", stream: bool = True):
    """
    Exposed interface for direct external calls, facilitating breakpoint debugging in the same process.
    """
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8')

    check_dependencies()

    import llm_chat
    
    if file_path and not provider:
        filename = os.path.basename(file_path)
        target_prompts = ["AI_Task_Prompt.md"]
        
        if filename in target_prompts:
            provider = os.environ.get('ADVANCED_LLM_PROVIDER')
            print(f"\033[33m[*] Matched advanced task file ({filename}), routing to Advanced Provider: '{provider}'\033[0m")
        else:
            provider = os.environ.get('STANDARD_LLM_PROVIDER')
            print(f"\033[36m[*] Standard task file ({filename}), routing to Standard Provider: '{provider}'\033[0m")

    if not provider:
        print("\n\033[36m========================================")
        print("          Select an LLM Provider        ")
        print("========================================")
        print("  1. DeepSeek")
        print("  2. Claude (Anthropic)")
        print("  3. GPT (OpenAI)")
        print("  4. GLM (Zhipu)")
        print("  5. Kimi (Moonshot)")
        print("  6. Qwen (DashScope)")
        print("  7. Poe")
        print("  8. DeepSeek V4 Pro")
        print("========================================\033[0m")

        provider_map = {
            "1": "deepseek", "2": "claude", "3": "gpt",
            "4": "glm", "5": "kimi", "6": "qwen", "7": "poe",
            "8": "deepseek-v4pro"
        }

        while not provider:
            choice = input("Enter a number (1-8): ").strip()
            if choice in provider_map:
                provider = provider_map[choice]
            else:
                print("\033[31m[!] Invalid input. Please enter a number between 1 and 8.\033[0m")

    print(f"\n\033[36m[*] Starting request via API using provider [{provider}]...\033[0m")
    llm_chat.run_chat_app(
        provider=provider,
        file_path=file_path,
        output=output_path,
        reasoning=reasoning,
        stream=stream
    )


def main():
    # Set console encoding to UTF-8
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8')

    # 1. Check and generate .env file
    check_env()

    # 2. Check dependencies
    check_dependencies()

    # Import llm_chat after dependencies are guaranteed to be installed
    import llm_chat

    # 4. Process arguments (filter out user-provided -p if any, check for file)
    args = sys.argv[1:]
    new_args = []
    skip_next = False
    has_file = False
    file_path = None

    for i in range(len(args)):
        if skip_next:
            skip_next = False
            continue
        # Ignore -p or --provider if passed by habit
        if args[i] in ("-p", "--provider"):
            skip_next = True
            continue
        if args[i] in ("-f", "--file"):
            has_file = True
            if i + 1 < len(args):
                file_path = args[i+1]
        new_args.append(args[i])

    # Prompt for file path if not provided in arguments
    if not has_file:
        print()
        file_path = input("Enter the Markdown file path (e.g., C:\\path\\to\\prompt.md): ").strip()
        if not file_path:
            print("\033[31m[Error] File path cannot be empty. Exiting.\033[0m")
            sys.exit(1)
        new_args.extend(["-f", file_path])

    # 3. Provider Selection (Based on file type)
    filename = os.path.basename(file_path) if file_path else ""
    target_prompts = ["AI_Task_Prompt.md"]
    
    if filename in target_prompts:
        provider = os.environ.get('ADVANCED_LLM_PROVIDER')
        print(f"\033[33m[*] Matched advanced task file ({filename}), routing to Advanced Provider: '{provider}'\033[0m")
    else:
        provider = os.environ.get('STANDARD_LLM_PROVIDER')
        print(f"\033[36m[*] Standard task file ({filename}), routing to Standard Provider: '{provider}'\033[0m")

    if not provider:
        print("\n\033[36m========================================")
        print("          Select an LLM Provider        ")
        print("========================================")
        print("  1. DeepSeek")
        print("  2. Claude (Anthropic)")
        print("  3. GPT (OpenAI)")
        print("  4. GLM (Zhipu)")
        print("  5. Kimi (Moonshot)")
        print("  6. Qwen (DashScope)")
        print("  7. Poe")
        print("  8. DeepSeek V4 Pro")
        print("========================================\033[0m")

        provider_map = {
            "1": "deepseek",
            "2": "claude",
            "3": "gpt",
            "4": "glm",
            "5": "kimi",
            "6": "qwen",
            "7": "poe",
            "8": "deepseek-v4pro"
        }

        while not provider:
            choice = input("Enter a number (1-8): ").strip()
            if choice in provider_map:
                provider = provider_map[choice]
            else:
                print("\033[31m[!] Invalid input. Please enter a number between 1 and 8.\033[0m")

    # Add the selected provider to arguments
    new_args.extend(["-p", provider])

    # 5. Execute llm_chat logic via interface
    print(f"\n\033[36m[*] Starting request using provider [{provider}]...\033[0m")
    llm_chat.main(new_args)

if __name__ == "__main__":
    main()