# run.py
import os
import sys
import subprocess
import urllib.request

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
        print("\033[36m[*] Missing dependencies detected. Preparing to install...\033[0m")
        
        # Check if proxy environment variables are already set
        proxy_set = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY")
        
        if not proxy_set:
            # Attempt to detect if the user is in Mainland China
            is_china = False
            try:
                req = urllib.request.Request("https://ipinfo.io/country")
                with urllib.request.urlopen(req, timeout=3) as response:
                    country = response.read().decode('utf-8').strip()
                    if country == "CN":
                        is_china = True
            except Exception:
                # Ignore network errors during detection and proceed
                pass

            if is_china:
                print("\033[33m[!] Mainland China network detected.\033[0m")
                print("\033[33mYou may need to configure a proxy to install dependencies and access LLM APIs.\n\033[0m")
                print("\033[36mPlease configure your proxy manually. Example (run these in your terminal):\033[0m")
                
                if os.name == 'nt':
                    print("set HTTP_PROXY=http://127.0.0.1:7890")
                    print("set HTTPS_PROXY=http://127.0.0.1:7890\n")
                else:
                    print("export HTTP_PROXY=\"http://127.0.0.1:7890\"")
                    print("export HTTPS_PROXY=\"http://127.0.0.1:7890\"\n")
                
                print("\033[33mAfter configuring the proxy, run this script again.\033[0m")
                print("\033[31mExiting...\033[0m")
                sys.exit(1)

        print("\033[36m[*] Installing required Python packages...\033[0m")
        
        try:
            # Install dependencies, including aiohttp to resolve the langchain conflict
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "openai", "anthropic", "python-dotenv", "aiohttp"])
            print("\033[32m[*] Dependencies installed successfully!\033[0m")
        except subprocess.CalledProcessError:
            print("\033[31m[Error] Failed to install dependencies. Please check your Python/pip environment.\033[0m")
            print("\033[33mNote: If you encounter a 'check_hostname requires server_hostname' error due to your proxy, please upgrade pip first by running:\033[0m")
            print(f"{sys.executable} -m pip install --upgrade pip")
            sys.exit(1)


def run_api(file_path: str, output_path: str, provider: str = None, reasoning: str = "off", stream: bool = True):
    """
    Exposed interface for direct external calls, facilitating breakpoint debugging in the same process.
    """
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8')

    check_env()
    check_dependencies()

    import llm_chat

    # Attempt to load provider from environment variable if not explicitly passed
    if not provider:
        provider = os.environ.get('AUTO_SELECTED_LLM_PROVIDER')

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
        print("========================================\033[0m")

        provider_map = {
            "1": "deepseek", "2": "claude", "3": "gpt",
            "4": "glm", "5": "kimi", "6": "qwen"
        }

        while not provider:
            choice = input("Enter a number (1-6): ").strip()
            if choice in provider_map:
                provider = provider_map[choice]
            else:
                print("\033[31m[!] Invalid input. Please enter a number between 1 and 6.\033[0m")

    print("\n\033[36m[*] Starting request via API...\033[0m")
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

    # 3. Provider Selection
    provider = os.environ.get('AUTO_SELECTED_LLM_PROVIDER')
    
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
        print("========================================\033[0m")

        provider_map = {
            "1": "deepseek",
            "2": "claude",
            "3": "gpt",
            "4": "glm",
            "5": "kimi",
            "6": "qwen"
        }

        while not provider:
            choice = input("Enter a number (1-6): ").strip()
            if choice in provider_map:
                provider = provider_map[choice]
            else:
                print("\033[31m[!] Invalid input. Please enter a number between 1 and 6.\033[0m")

    # 4. Process arguments (filter out user-provided -p if any, check for file)
    args = sys.argv[1:]
    new_args = []
    skip_next = False
    has_file = False

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
        new_args.append(args[i])

    # Prompt for file path if not provided in arguments
    if not has_file:
        print()
        file_path = input("Enter the Markdown file path (e.g., C:\\path\\to\\prompt.md): ").strip()
        if not file_path:
            print("\033[31m[Error] File path cannot be empty. Exiting.\033[0m")
            sys.exit(1)
        new_args.extend(["-f", file_path])

    # Add the selected provider to arguments
    new_args.extend(["-p", provider])

    # 5. Execute llm_chat logic via interface
    print("\n\033[36m[*] Starting request...\033[0m")
    llm_chat.main(new_args)

if __name__ == "__main__":
    main()