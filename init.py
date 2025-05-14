import os
import sys
import argparse
import subprocess
import urllib.request


def main():
    parser = argparse.ArgumentParser(description="Project Build Script")
    parser.add_argument(
        "--skip-composer", 
        action="store_true", 
        help="Skip executing 'composer install' in the PHP directory"
    )
    args = parser.parse_args()

    # =====================================================
    # Prominent user notice and pause for confirmation
    # =====================================================
    print("\n" + "="*60)
    print("\033[1;31m⚠️  IMPORTANT NOTICE ⚠️\033[0m")
    print("\033[1;33mPlease DO NOT leave during the initialization process!\033[0m")
    print("\033[1;33mYou will need to manually configure the .env file at the end.\033[0m")
    print("\033[1;33mIf you leave early, the configuration may be incomplete or the script may hang.\033[0m")
    print("-" * 60)
    print("\033[1;36mPlease DO NOT leave during the initialization process!\033[0m")
    print("\033[1;36mYou will need to manually configure the .env file at the end.\033[0m")
    print("="*60 + "\n")
    
    input("\033[1;32mI understand, press Enter to continue... \033[0m")
    print("\nStarting initialization...\n")
    # =====================================================

    script_dir = os.path.dirname(os.path.abspath(__file__))

    # ========== Install shared utilities package (shared_utils) ==========
    print("\nStep 0: Installing shared utilities package (shared_utils)...")
    shared_utils_dir = os.path.join(script_dir, "enginerring", "shared_utils")

    if not os.path.isdir(shared_utils_dir):
        print(
            f"Error: shared_utils directory not found: {shared_utils_dir}", file=sys.stderr)
        sys.exit(1)

    # Use the current Python interpreter to execute pip install -e .
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install",
                "--no-build-isolation", "-e", "."],
            cwd=shared_utils_dir,
            check=False
        )
        if result.returncode != 0:
            print("Warning: pip install shared_utils failed (return code {}). "
                  "Proceeding with the build, but shared utilities may not be available.".format(
                      result.returncode),
                  file=sys.stderr)
        else:
            print("shared_utils installed successfully.")
    except Exception as e:
        print(
            f"Error: Could not run pip to install shared_utils: {e}", file=sys.stderr)
        sys.exit(1)
    # =====================================================

    # ========== Install LLM Python Dependencies ==========
    print("\nStep 1: Installing required Python packages for LLM...")
    
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

    try:
        # Changed "openai" to "openai<2.0.0" to resolve langchain-openai conflict
        # Added "flask" to the list of dependencies to install
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "openai<2.0.0", "anthropic", "python-dotenv", "aiohttp", "flask"])
        print("Python dependencies (openai<2.0.0, anthropic, python-dotenv, aiohttp, flask) installed successfully.")
    except subprocess.CalledProcessError:
        print("\033[31m[Error] Failed to install Python dependencies. Please check your Python/pip environment.\033[0m", file=sys.stderr)
        print("\033[33mNote: If you encounter a 'check_hostname requires server_hostname' error due to your proxy, please upgrade pip first by running:\033[0m", file=sys.stderr)
        print(f"{sys.executable} -m pip install --upgrade pip", file=sys.stderr)
        sys.exit(1)
    # =====================================================

    print("\nChecking Java environment variables...")
    java_home = os.environ.get("JAVA_HOME")
    if not java_home:
        print("Error: JAVA_HOME Environment variable not configured. Please set JAVA_HOME to point to your JDK installation directory.", file=sys.stderr)
        sys.exit(1)

    print(f"Using JAVA_HOME: {java_home}")
    os.environ["PATH"] = f"{os.path.join(java_home, 'bin')}{os.pathsep}{os.environ.get('PATH', '')}"

    mvn_cmd = "mvn.cmd" if os.name == "nt" else "mvn"

    # ========== Build Core Instrumentor ==========
    print("\nStep 2: Executing mvn clean install to build the core instrumentor...")
    core_pom_path = os.path.join("core", "pom.xml")

    try:
        result = subprocess.run(
            [mvn_cmd, "-f", core_pom_path, "clean", "install", "-DskipTests"])
        if result.returncode != 0:
            print("Maven build failed for core instrumentor", file=sys.stderr)
            sys.exit(1)
        else:
            print("Core instrumentor built successfully.")
    except FileNotFoundError:
        print(
            f"Error: Maven command ('{mvn_cmd}') not found. Please ensure Maven is installed and in your PATH.", file=sys.stderr)
        sys.exit(1)

    # ========== Build PHP Redis Log Monitor (Java Version) ==========
    print("\nStep 3: Executing mvn clean package to build the PHP Redis Log Monitor...")
    php_monitor_pom_path = os.path.join("multilingual", "php", "instrumentor-log-monitor", "pom.xml")
    
    if not os.path.isfile(php_monitor_pom_path):
        print(f"Error: POM file not found at {php_monitor_pom_path}", file=sys.stderr)
        sys.exit(1)

    try:
        result = subprocess.run(
            [mvn_cmd, "-f", php_monitor_pom_path, "clean", "package", "-DskipTests"])
        if result.returncode != 0:
            print("Maven build failed for PHP Redis Log Monitor", file=sys.stderr)
            sys.exit(1)
        else:
            print("PHP Redis Log Monitor built successfully.")
    except FileNotFoundError:
        print(
            f"Error: Maven command ('{mvn_cmd}') not found. Please ensure Maven is installed and in your PATH.", file=sys.stderr)
        sys.exit(1)

    # ========== Run Composer Install for PHP ==========
    print("\nStep 4: Executing composer install for PHP environment...")
    php_dir = os.path.join(script_dir, "multilingual", "php")
    
    if args.skip_composer:
        print("Skipped 'composer install' as requested.")
        print(f"Note: If you need PHP support later, please navigate to the directory and run it manually:")
        print(f"      cd {php_dir}")
        print(f"      composer install")
    else:
        if not os.path.isdir(php_dir):
            print(f"Error: PHP directory not found at {php_dir}", file=sys.stderr)
            sys.exit(1)
            
        composer_cmd = "composer.bat" if os.name == "nt" else "composer"
        try:
            result = subprocess.run(
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
                f"Error: Composer command ('{composer_cmd}') not found. Please ensure Composer is installed and in your PATH.", file=sys.stderr)
            sys.exit(1)

    # ========== Edit .env file ==========
    print("\nStep 5: Opening .env file for configuration...")
    env_dir = os.path.join(script_dir, "enginerring", "ask_llm")
    env_file_path = os.path.join(env_dir, ".env")

    if not os.path.exists(env_dir):
        os.makedirs(env_dir, exist_ok=True)
    if not os.path.exists(env_file_path):
        with open(env_file_path, "w", encoding="utf-8") as f:
            f.write("# Please configure your environment variables here\n")

    print(f"Waiting for you to edit and close the file: {env_file_path}")
    
    try:
        if os.name == 'nt':
            editor = os.environ.get('EDITOR', 'notepad')
            subprocess.run([editor, env_file_path])
        elif sys.platform == 'darwin':
            editor = os.environ.get('EDITOR')
            if editor:
                subprocess.run([editor, env_file_path])
            else:
                subprocess.run(['open', '-W', '-t', env_file_path])
        else:
            editor = os.environ.get('EDITOR', 'nano')
            subprocess.run([editor, env_file_path])
        
        print(".env file configuration completed.")
    except Exception as e:
        print(f"Warning: Could not open editor automatically: {e}", file=sys.stderr)
        print(f"Please manually edit the file at: {env_file_path}")
        input("Press Enter when you are done editing...")

    print("\nAll build steps completed successfully.")


if __name__ == "__main__":
    main()