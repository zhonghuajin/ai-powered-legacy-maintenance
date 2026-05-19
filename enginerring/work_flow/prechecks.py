# prechecks.py
import os
import sys
import subprocess
import re
import platform
from print_utils.utils import Colors, print_color


def print_disclaimer():
    print_color("-------------------------------------------------------", Colors.YELLOW)
    print_color(" [GENERAL WORKFLOW]", Colors.YELLOW)
    print_color("   1. Code Instrumentation", Colors.YELLOW)
    print_color("   2. Execution & Log Generation", Colors.YELLOW)
    print_color("   3. Log Denoising", Colors.YELLOW)
    print_color("   4. AI Prompt Generation", Colors.YELLOW)
    print_color("   5. Ask LLM", Colors.YELLOW)
    print_color("   6. Apply The Solution Provided by AI", Colors.YELLOW)
    print_color("-------------------------------------------------------\n", Colors.YELLOW)


def check_java_version():
    is_valid_jdk = False
    current_version = "Unknown"

    try:
        result = subprocess.run(['java', '-version'], capture_output=True, text=True, check=True)
        java_output = result.stderr

        for line in java_output.splitlines():
            match = re.search(r'version "(\d+)', line)
            if match:
                major_version = int(match.group(1))
                if major_version == 1:
                    sub_match = re.search(r'version "1\.(\d+)', line)
                    if sub_match:
                        current_version = f"1.{sub_match.group(1)}"
                else:
                    current_version = str(major_version)

                if major_version >= 17:
                    is_valid_jdk = True
                break
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_color("Java command not detected in environment variables.", Colors.YELLOW)

    if is_valid_jdk:
        print_color(f"[Environment Check] System Java version is {current_version}, meets requirement (>= 17), skipping path configuration.", Colors.GREEN)
    else:
        if current_version != "Unknown":
            print_color(f"[Environment Check] System Java version is {current_version}, lower than required JDK 17.", Colors.YELLOW)
        else:
            print_color("[Environment Check] No valid Java environment detected.", Colors.YELLOW)

        print_color("Please ensure you have JDK 17 or higher installed.", Colors.YELLOW)
        jdk_path = input("Enter the installation path of JDK (>=17) (e.g., C:\\Program Files\\Java\\jdk-17) [Press Enter to skip]: ").strip()

        if jdk_path:
            os.environ['JAVA_HOME'] = jdk_path
            os.environ['PATH'] = f"{os.path.join(jdk_path, 'bin')}{os.pathsep}{os.environ.get('PATH', '')}"
            print_color("Temporarily added the specified JDK to environment variables.", Colors.GREEN)
        else:
            print_color("No path entered. Will attempt to use current environment; this may cause compilation or runtime failures.", Colors.RED)


def check_llm_env(ask_llm_dir):
    env_file = os.path.join(ask_llm_dir, ".env")

    if not os.path.exists(env_file):
        print_color("\n[*] Pre-flight check: .env file not found for LLM steps. Generating template...", Colors.YELLOW)
        os.makedirs(ask_llm_dir, exist_ok=True)

        env_template = """# Fill in the API keys you want to use here. Leave unused ones empty.
OPENAI_API_KEY=""
DEEPSEEK_API_KEY=""
ZHIPU_API_KEY=""
MOONSHOT_API_KEY=""
DASHSCOPE_API_KEY=""
ANTHROPIC_API_KEY=""
POE_API_KEY=""

# Optional: Explicitly specify which provider to use. 
# Available options: deepseek, deepseek-v4pro, claude, gpt, glm, kimi, qwen, poe
# If left blank, the script will auto-select based on available keys.
STANDARD_LLM_PROVIDER=""
ADVANCED_LLM_PROVIDER=""
"""
        with open(env_file, 'w', encoding='utf-8') as f:
            f.write(env_template)

        print_color(f"[!] .env file generated at: {env_file}", Colors.GREEN)
        print_color("[!] Please fill in your API keys in the generated .env file and run this quickstart script again.", Colors.RED)
        sys.exit(1)
    else:
        print_color("[Environment Check] LLM .env file found.", Colors.GREEN)
    
    return env_file

#Priority Lists: I added two lists: `advanced_priority` and `standard_priority`.  
#Automatic Sorting: Using `sort` with a `lambda` function, if `poe` is in the candidate list, its index is 0, so it gets moved to the front; `deepseek-v4pro` has an index of 3, so it gets placed further back.  
#Final Selection: The code still takes `advanced_candidates[0][1]`, but because the list has already been sorted by priority, as long as you have `POE_API_KEY` configured, it will always prioritize selecting `poe` as the advanced model.
#Advanced Model Priority: `poe` > `claude` > `gpt` > `deepseek-v4pro`. This way, as long as you have `POE_API_KEY` configured, the advanced model will be locked in as `poe` first.
#Standard Model Priority: `deepseek` > `glm` > `qwen` > `kimi`.

def auto_select_llm_provider(env_file):
    print()
    print_color("========================================", Colors.CYAN)
    print_color("      Auto-Selecting LLM Provider       ", Colors.CYAN)
    print_color("========================================", Colors.CYAN)

    # Map API keys to a tuple of (Display Name, Internal Provider ID, Is_Advanced)
    llm_providers_map = {
        "DEEPSEEK_API_KEY": [
            ("DeepSeek", "deepseek", False), 
            # ("DeepSeek V4 Pro", "deepseek-v4pro", True)
        ],
        "ANTHROPIC_API_KEY": [("Claude (Anthropic)", "claude", True)],
        "OPENAI_API_KEY": [("GPT (OpenAI)", "gpt", True)],
        "ZHIPU_API_KEY": [("GLM (Zhipu)", "glm", False)],
        "MOONSHOT_API_KEY": [("Kimi (Moonshot)", "kimi", False)],
        "DASHSCOPE_API_KEY": [("Qwen (DashScope)", "qwen", False)],
        "POE_API_KEY": [("Poe", "poe", True)]
    }

    available_providers = []
    user_standard = None
    user_advanced = None

    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            if '=' in line:
                key, val = line.split('=', 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")

                if val:
                    if key == "STANDARD_LLM_PROVIDER":
                        user_standard = val
                    elif key == "ADVANCED_LLM_PROVIDER":
                        user_advanced = val
                    elif key in llm_providers_map:
                        available_providers.extend(llm_providers_map[key])

    if not available_providers:
        print_color("[!] No valid API keys found in .env file. Please configure at least one API key.", Colors.RED)
        sys.exit(1)

    # Separate available into advanced and standard
    advanced_candidates = [p for p in available_providers if p[2]]
    standard_candidates = [p for p in available_providers if not p[2]]

    # Define Priority for Auto-Selection (lower index = higher priority)
    advanced_priority = ["poe", "claude", "gpt", "deepseek-v4pro"]
    standard_priority = ["deepseek", "glm", "qwen", "kimi"]

    # Sort candidates based on priority
    advanced_candidates.sort(key=lambda x: advanced_priority.index(x[1]) if x[1] in advanced_priority else 999)
    standard_candidates.sort(key=lambda x: standard_priority.index(x[1]) if x[1] in standard_priority else 999)

    # Determine Advanced Provider
    if user_advanced:
        final_advanced = user_advanced
    elif advanced_candidates:
        final_advanced = advanced_candidates[0][1]
    else:
        final_advanced = available_providers[0][1] # Fallback to whatever is available

    # Determine Standard Provider
    if user_standard:
        final_standard = user_standard
    elif standard_candidates:
        final_standard = standard_candidates[0][1]
    else:
        final_standard = available_providers[0][1] # Fallback to whatever is available

    os.environ['ADVANCED_LLM_PROVIDER'] = final_advanced
    os.environ['STANDARD_LLM_PROVIDER'] = final_standard

    print_color(f"[Environment Check] Standard LLM Provider mapped to: {final_standard}", Colors.GREEN)
    print_color(f"[Environment Check] Advanced LLM Provider mapped to: {final_advanced}", Colors.GREEN)


def setup_windows_proxy():
    if platform.system() == "Windows":
        try:
            import winreg
            internet_settings = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r'Software\Microsoft\Windows\CurrentVersion\Internet Settings'
            )
            proxy_enable, _ = winreg.QueryValueEx(internet_settings, 'ProxyEnable')

            if proxy_enable == 1:
                proxy_server, _ = winreg.QueryValueEx(internet_settings, 'ProxyServer')
                if proxy_server:
                    proxy_address = proxy_server
                    match = re.search(r"http=([^;]+)", proxy_server)
                    if match:
                        proxy_address = match.group(1)

                    if not re.match(r"^http(s)?://", proxy_address):
                        proxy_address = f"http://{proxy_address}"

                    os.environ['HTTP_PROXY'] = proxy_address
                    os.environ['HTTPS_PROXY'] = proxy_address
                    print_color("[Proxy Check] Detected system proxy is enabled.", Colors.YELLOW)
                    print_color(f"Automatically configured HTTP_PROXY and HTTPS_PROXY to: {proxy_address}", Colors.GREEN)
        except Exception:
            pass
    else:
        print_color(
            "[Proxy Check] Non-Windows OS detected. Relying on existing HTTP_PROXY/HTTPS_PROXY environment variables.",
            Colors.DARKGRAY
        )