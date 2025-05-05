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
    print_color("   5. Ask LLM for Bug Localization", Colors.YELLOW)
    print_color("   6. Generate Fix Prompt", Colors.YELLOW)
    print_color("   7. Ask LLM for Code Fix", Colors.YELLOW)
    print_color("   8. Apply Fix to Source Code", Colors.YELLOW)
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
"""
        with open(env_file, 'w', encoding='utf-8') as f:
            f.write(env_template)

        print_color(f"[!] .env file generated at: {env_file}", Colors.GREEN)
        print_color("[!] Please fill in your API keys in the generated .env file and run this quickstart script again.", Colors.RED)
        sys.exit(1)
    else:
        print_color("[Environment Check] LLM .env file found.", Colors.GREEN)
    
    return env_file


def auto_select_llm_provider(env_file):
    print()
    print_color("========================================", Colors.CYAN)
    print_color("      Auto-Selecting LLM Provider       ", Colors.CYAN)
    print_color("========================================", Colors.CYAN)

    # Map API keys to a tuple of (Display Name, Internal Provider ID)
    llm_providers = {
        "DEEPSEEK_API_KEY": ("DeepSeek", "deepseek"),
        "ANTHROPIC_API_KEY": ("Claude (Anthropic)", "claude"),
        "OPENAI_API_KEY": ("GPT (OpenAI)", "gpt"),
        "ZHIPU_API_KEY": ("GLM (Zhipu)", "glm"),
        "MOONSHOT_API_KEY": ("Kimi (Moonshot)", "kimi"),
        "DASHSCOPE_API_KEY": ("Qwen (DashScope)", "qwen")
    }

    selected_provider_name = None
    selected_provider_id = None

    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            if '=' in line:
                key, val = line.split('=', 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")

                if val and key in llm_providers:
                    selected_provider_name, selected_provider_id = llm_providers[key]
                    break 

    if selected_provider_id:
        # Inject the selected provider ID into the environment variables for downstream usage
        os.environ['AUTO_SELECTED_LLM_PROVIDER'] = selected_provider_id
        print_color(f"[Environment Check] LLM Provider auto-selected: {selected_provider_name}", Colors.GREEN)
    else:
        print_color("[!] No valid API keys found in .env file. Please configure at least one API key.", Colors.RED)
        sys.exit(1)


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