import os
import sys
import argparse
import subprocess


def main():

    # ========== 新增：安装共享工具包 shared_utils ==========
    print("\nStep 0: Installing shared utilities package (shared_utils)...")
    # 获取当前脚本所在的目录（项目根目录）
    script_dir = os.path.dirname(os.path.abspath(__file__))
    shared_utils_dir = os.path.join(script_dir, "enginerring", "shared_utils")

    if not os.path.isdir(shared_utils_dir):
        print(
            f"Error: shared_utils directory not found: {shared_utils_dir}", file=sys.stderr)
        sys.exit(1)

    # 使用当前 Python 解释器执行 pip install -e .
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

    print("\nExecuting mvn clean package to build the instrumentor...")
    pom_path = os.path.join("core", "pom.xml")

    mvn_cmd = "mvn.cmd" if os.name == "nt" else "mvn"

    try:
        result = subprocess.run(
            [mvn_cmd, "-f", pom_path, "clean", "install", "-DskipTests"])
        if result.returncode != 0:
            print("Maven build failed", file=sys.stderr)
            sys.exit(1)
    except FileNotFoundError:
        print(
            f"Error: Maven command ('{mvn_cmd}') not found. Please ensure Maven is installed and in your PATH.", file=sys.stderr)
        sys.exit(1)

    print("\nStep 1 and Step 2 completed successfully. (Subsequent steps ignored)")


if __name__ == "__main__":
    main()
