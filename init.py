import os
import sys
import argparse
import subprocess
import urllib.request
import socket

def is_port_open(host, port, timeout=1):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False

def get_clean_env():
    clean_env = os.environ.copy()
    proxy_vars = [
        "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
        "ALL_PROXY", "all_proxy", "FTP_PROXY", "ftp_proxy"
    ]
    for var in proxy_vars:
        clean_env.pop(var, None)
    return clean_env

def run_without_proxy(*args, **kwargs):
    if "env" not in kwargs:
        kwargs["env"] = get_clean_env()
    else:
        clean_env = kwargs["env"].copy()
        proxy_vars = [
            "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
            "ALL_PROXY", "all_proxy", "FTP_PROXY", "ftp_proxy"
        ]
        for var in proxy_vars:
            clean_env.pop(var, None)
        kwargs["env"] = clean_env
    return subprocess.run(*args, **kwargs)

def main():
    parser = argparse.ArgumentParser(description="Project Build Script")
    parser.add_argument(
        "--skip-composer",
        action="store_true",
        help="Skip executing 'composer install' in the PHP directories"
    )
    parser.add_argument(
        "--skip-npm",
        action="store_true",
        help="Skip executing 'npm install' in the JavaScript directory"
    )
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))

    print("\nStarting initialization...\n")

    print("\nStep 1: Opening .env file for configuration...")
    env_dir = os.path.join(script_dir, "enginerring", "ask_llm")
    env_file_path = os.path.join(env_dir, ".env")

    if not os.path.exists(env_dir):
        os.makedirs(env_dir, exist_ok=True)
    if not os.path.exists(env_file_path):
        with open(env_file_path, "w", encoding="utf-8") as f:
            f.write("# Please configure your environment variables here\n")

    print(f"Waiting for you to edit and close the file: {env_file_path}")

    try:
        editor_env = get_clean_env()
        if os.name == "nt":
            editor = os.environ.get("EDITOR", "notepad")
            subprocess.run([editor, env_file_path], env=editor_env)
        elif sys.platform == "darwin":
            editor = os.environ.get("EDITOR")
            if editor:
                subprocess.run([editor, env_file_path], env=editor_env)
            else:
                subprocess.run(["open", "-W", "-t", env_file_path], env=editor_env)
        else:
            editor = os.environ.get("EDITOR", "nano")
            subprocess.run([editor, env_file_path], env=editor_env)

        print(".env file configuration completed. You can now leave it running.")
    except Exception as e:
        print(
            f"Warning: Could not open editor automatically: {e}", file=sys.stderr)
        print(f"Please manually edit the file at: {env_file_path}")
        input("Press Enter when you are done editing...")

    print("\nStep 2: Installing shared utilities package...")
    shared_utils_dir = os.path.join(script_dir, "enginerring", "shared_utils")

    if not os.path.isdir(shared_utils_dir):
        print(
            f"Error: shared_utils directory not found: {shared_utils_dir}",
            file=sys.stderr
        )
        sys.exit(1)

    try:
        result = run_without_proxy(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-build-isolation",
                "-e",
                "."
            ],
            cwd=shared_utils_dir,
            check=False
        )
        if result.returncode != 0:
            print(
                "Warning: pip install shared_utils failed "
                f"(return code {result.returncode}). "
                "Proceeding with the build, but shared utilities may not be available.",
                file=sys.stderr
            )
        else:
            print("shared_utils installed successfully.")
    except Exception as e:
        print(
            f"Error: Could not run pip to install shared_utils: {e}",
            file=sys.stderr
        )
        sys.exit(1)

    print("\nStep 3: Installing required Python packages for LLM...")

    proxy_set = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY") or \
                os.environ.get("http_proxy") or os.environ.get("https_proxy")

    llm_env = os.environ.copy()

    if not proxy_set:
        is_china = False
        try:
            req = urllib.request.Request("https://ipinfo.io/country")
            proxy_handler = urllib.request.ProxyHandler({})
            opener = urllib.request.build_opener(proxy_handler)
            with opener.open(req, timeout=3) as response:
                country = response.read().decode("utf-8").strip()
                if country == "CN":
                    is_china = True
        except Exception:
            pass

        if is_china:
            print("\033[33m[!] Mainland China network detected.\033[0m")

            if is_port_open("127.0.0.1", 7890):
                print("\033[32m[+] Detected active proxy port 7890 on 127.0.0.1. Automatically applying proxy...\033[0m")

                llm_env["HTTP_PROXY"] = "http://127.0.0.1:7890"
                llm_env["HTTPS_PROXY"] = "http://127.0.0.1:7890"
                llm_env["http_proxy"] = "http://127.0.0.1:7890"
                llm_env["https_proxy"] = "http://127.0.0.1:7890"
            else:
                print(
                    "\033[33mYou may need to configure a proxy to install "
                    "dependencies and access LLM APIs.\n\033[0m"
                )
                print(
                    "\033[36mPlease configure your proxy manually. "
                    "Example commands:\033[0m"
                )

                if os.name == "nt":
                    print("set HTTP_PROXY=http://127.0.0.1:7890")
                    print("set HTTPS_PROXY=http://127.0.0.1:7890\n")
                else:
                    print('export HTTP_PROXY="http://127.0.0.1:7890"')
                    print('export HTTPS_PROXY="http://127.0.0.1:7890"\n')

                print(
                    "\033[33mAfter configuring the proxy, run this script again.\033[0m")
                print("\033[31mExiting...\033[0m")
                sys.exit(1)

    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "-q",
                "openai<2.0.0",
                "anthropic",
                "python-dotenv",
                "aiohttp",
                "flask"
            ],
            env=llm_env,
            check=True
        )
        print(
            "Python dependencies "
            "(openai<2.0.0, anthropic, python-dotenv, aiohttp, flask) "
            "installed successfully."
        )
    except subprocess.CalledProcessError:
        print(
            "\033[31m[Error] Failed to install Python dependencies. "
            "Please check your Python/pip environment.\033[0m",
            file=sys.stderr
        )
        print(
            "\033[33mNote: If you encounter a "
            "'check_hostname requires server_hostname' error due to your proxy, "
            "please upgrade pip first by running:\033[0m",
            file=sys.stderr
        )
        print(f"{sys.executable} -m pip install --upgrade pip", file=sys.stderr)
        sys.exit(1)

    print("\nChecking Java environment variables...")
    java_home = os.environ.get("JAVA_HOME")
    if not java_home:
        print(
            "Error: JAVA_HOME environment variable is not configured. "
            "Please set JAVA_HOME to point to your JDK installation directory.",
            file=sys.stderr
        )
        sys.exit(1)

    print(f"Using JAVA_HOME: {java_home}")

    clean_env_with_java = get_clean_env()
    clean_env_with_java["PATH"] = (
        f"{os.path.join(java_home, 'bin')}"
        f"{os.pathsep}"
        f"{clean_env_with_java.get('PATH', '')}"
    )

    mvn_cmd = "mvn.cmd" if os.name == "nt" else "mvn"

    print("\nStep 4: Executing mvn clean install to build the instrumentor...")
    core_pom_path = os.path.join("multilingual", "java", "pom.xml")

    if not os.path.isfile(core_pom_path):
        print(f"Error: POM file not found at {core_pom_path}", file=sys.stderr)
        sys.exit(1)

    try:
        result = run_without_proxy(
            [mvn_cmd, "-f", core_pom_path, "clean", "install", "-DskipTests"],
            env=clean_env_with_java
        )
        if result.returncode != 0:
            print("Maven build failed for instrumentor.", file=sys.stderr)
            sys.exit(1)
        else:
            print("Core instrumentor built successfully.")
    except FileNotFoundError:
        print(
            f"Error: Maven command '{mvn_cmd}' not found. "
            "Please ensure Maven is installed and in your PATH.",
            file=sys.stderr
        )
        sys.exit(1)

    print("\nStep 5: Executing mvn clean install to build the block wrapper...")
    block_wrapper_pom_path = os.path.join(
        "multilingual", "java", "block-wrapper", "pom.xml")

    if not os.path.isfile(block_wrapper_pom_path):
        print(
            f"Error: POM file not found at {block_wrapper_pom_path}",
            file=sys.stderr
        )
        sys.exit(1)

    try:
        result = run_without_proxy(
            [
                mvn_cmd,
                "-f",
                block_wrapper_pom_path,
                "clean",
                "install",
                "-DskipTests"
            ],
            env=clean_env_with_java
        )
        if result.returncode != 0:
            print("Maven build failed for block wrapper.", file=sys.stderr)
            sys.exit(1)
        else:
            print("Core block wrapper built successfully.")
    except FileNotFoundError:
        print(
            f"Error: Maven command '{mvn_cmd}' not found. "
            "Please ensure Maven is installed and in your PATH.",
            file=sys.stderr
        )
        sys.exit(1)

    print("\nStep 6: Executing mvn clean package to build the PHP Redis Log Monitor...")
    php_monitor_pom_path = os.path.join(
        "multilingual",
        "php",
        "instrumentor-log-monitor",
        "pom.xml"
    )

    if not os.path.isfile(php_monitor_pom_path):
        print(
            f"Error: POM file not found at {php_monitor_pom_path}", file=sys.stderr)
        sys.exit(1)

    try:
        result = run_without_proxy(
            [mvn_cmd, "-f", php_monitor_pom_path,
                "clean", "package", "-DskipTests"],
            env=clean_env_with_java
        )
        if result.returncode != 0:
            print("Maven build failed for PHP Redis Log Monitor.", file=sys.stderr)
            sys.exit(1)
        else:
            print("PHP Redis Log Monitor built successfully.")
    except FileNotFoundError:
        print(
            f"Error: Maven command '{mvn_cmd}' not found. "
            "Please ensure Maven is installed and in your PATH.",
            file=sys.stderr
        )
        sys.exit(1)

    print("\nStep 7: Executing composer install for PHP environment...")
    php_dir = os.path.join(script_dir, "multilingual", "php")

    if args.skip_composer:
        print("Skipped 'composer install' as requested.")
        print("Note: If you need PHP support later, run it manually:")
        print(f"      cd {php_dir}")
        print("      composer install")
    else:
        if not os.path.isdir(php_dir):
            print(
                f"Error: PHP directory not found at {php_dir}", file=sys.stderr)
            sys.exit(1)

        composer_cmd = "composer.bat" if os.name == "nt" else "composer"
        try:
            result = run_without_proxy(
                [composer_cmd, "install"],
                cwd=php_dir
            )
            if result.returncode != 0:
                print("Composer install failed.", file=sys.stderr)
                sys.exit(1)
            else:
                print("Composer install completed successfully.")
        except FileNotFoundError:
            print(
                f"Error: Composer command '{composer_cmd}' not found. "
                "Please ensure Composer is installed and in your PATH.",
                file=sys.stderr
            )
            sys.exit(1)

    # ================= 新增步骤 =================
    print("\nStep 8: Executing composer install for PHP data-structuring environment...")
    php_data_structuring_dir = os.path.join(script_dir, "multilingual", "php", "data-structuring")

    if args.skip_composer:
        print("Skipped 'composer install' for data-structuring as requested.")
        print("Note: If you need PHP data-structuring support later, run it manually:")
        print(f"      cd {php_data_structuring_dir}")
        print("      composer install")
    else:
        if not os.path.isdir(php_data_structuring_dir):
            print(
                f"Error: PHP data-structuring directory not found at {php_data_structuring_dir}", 
                file=sys.stderr
            )
            sys.exit(1)

        composer_cmd = "composer.bat" if os.name == "nt" else "composer"
        try:
            result = run_without_proxy(
                [composer_cmd, "install"],
                cwd=php_data_structuring_dir
            )
            if result.returncode != 0:
                print("Composer install for data-structuring failed.", file=sys.stderr)
                sys.exit(1)
            else:
                print("Composer install for data-structuring completed successfully.")
        except FileNotFoundError:
            print(
                f"Error: Composer command '{composer_cmd}' not found. "
                "Please ensure Composer is installed and in your PATH.",
                file=sys.stderr
            )
            sys.exit(1)
    # ============================================

    print(
        "\nStep 9: Executing mvn clean package to build the "
        "JavaScript Redis Log Monitor..."
    )
    js_monitor_pom_path = os.path.join(
        "multilingual",
        "javascript",
        "instrumentor-log-monitor",
        "pom.xml"
    )

    if not os.path.isfile(js_monitor_pom_path):
        print(
            f"Error: POM file not found at {js_monitor_pom_path}", file=sys.stderr)
        sys.exit(1)

    try:
        result = run_without_proxy(
            [mvn_cmd, "-f", js_monitor_pom_path, "clean", "package", "-DskipTests"],
            env=clean_env_with_java
        )
        if result.returncode != 0:
            print("Maven build failed for JavaScript Redis Log Monitor.",
                  file=sys.stderr)
            sys.exit(1)
        else:
            print("JavaScript Redis Log Monitor built successfully.")
    except FileNotFoundError:
        print(
            f"Error: Maven command '{mvn_cmd}' not found. "
            "Please ensure Maven is installed and in your PATH.",
            file=sys.stderr
        )
        sys.exit(1)

    print("\nStep 10: Executing npm install for JavaScript environment...")
    js_dir = os.path.join(script_dir, "multilingual", "javascript")

    if args.skip_npm:
        print("Skipped 'npm install' as requested.")
        print("Note: If you need JavaScript support later, run it manually:")
        print(f"      cd {js_dir}")
        print("      npm install")
    else:
        if not os.path.isdir(js_dir):
            print(
                f"Error: JavaScript directory not found at {js_dir}", file=sys.stderr)
            sys.exit(1)

        npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
        try:
            result = run_without_proxy(
                [npm_cmd, "install"],
                cwd=js_dir
            )
            if result.returncode != 0:
                print("npm install failed.", file=sys.stderr)
                sys.exit(1)
            else:
                print("npm install completed successfully.")
        except FileNotFoundError:
            print(
                f"Error: npm command '{npm_cmd}' not found. "
                "Please ensure Node.js/npm is installed and in your PATH.",
                file=sys.stderr
            )
            sys.exit(1)

    print("\nAll build steps completed successfully.")

if __name__ == "__main__":
    main()