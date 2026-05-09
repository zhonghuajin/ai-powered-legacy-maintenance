import os
import sys
import argparse
import subprocess


def main():

    # ========== Install shared utilities package (shared_utils) ==========
    print("\nStep 0: Installing shared utilities package (shared_utils)...")
    # Get the directory of the current script (project root directory)
    script_dir = os.path.dirname(os.path.abspath(__file__))
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

    print("\nChecking Java environment variables...")
    java_home = os.environ.get("JAVA_HOME")
    if not java_home:
        print("Error: JAVA_HOME Environment variable not configured. Please set JAVA_HOME to point to your JDK installation directory.", file=sys.stderr)
        sys.exit(1)

    print(f"Using JAVA_HOME: {java_home}")
    os.environ["PATH"] = f"{os.path.join(java_home, 'bin')}{os.pathsep}{os.environ.get('PATH', '')}"

    mvn_cmd = "mvn.cmd" if os.name == "nt" else "mvn"

    # ========== Build Core Instrumentor ==========
    print("\nStep 1: Executing mvn clean install to build the core instrumentor...")
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
    print("\nStep 2: Executing mvn clean package to build the PHP Redis Log Monitor...")
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

    print("\nAll build steps completed successfully.")


if __name__ == "__main__":
    main()