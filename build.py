import os
import sys
import argparse
import subprocess

def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="执行 Instrumentation 构建 (仅包含 Step 1 和 Step 2)")
    parser.add_argument("--target-folders-file", default="target-folders.txt", help="指定包含目标文件夹路径的文件")
    parser.add_argument("--target-folders", nargs="*", help="指定一个或多个目标文件夹路径")
    # 忽略了 SkipBuildAndTest 参数，因为第2步之后的测试步骤已被完全移除

    args = parser.parse_args()
    target_folders = args.target_folders

    # 读取并校验目标文件夹
    if not target_folders:
        if not os.path.exists(args.target_folders_file):
            print(f"Error: Target folders file does not exist: {args.target_folders_file}", file=sys.stderr)
            sys.exit(1)

        target_folders = []
        with open(args.target_folders_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    target_folders.append(line)

        if not target_folders:
            print(f"Error: No target folders found in file: {args.target_folders_file}", file=sys.stderr)
            sys.exit(1)

        print(f"Loaded {len(target_folders)} target folder(s) from file: {args.target_folders_file}")

    # 校验文件夹是否存在
    for folder in target_folders:
        if not os.path.exists(folder):
            print(f"Error: Target folder does not exist: {folder}", file=sys.stderr)
            sys.exit(1)

    print(f"Target folders: {', '.join(target_folders)}")

    # 1. 检查 Java 环境变量
    print("\nChecking Java environment variables...")
    java_home = os.environ.get("JAVA_HOME")
    if not java_home:
        print("Error: JAVA_HOME Environment variable not configured. Please set JAVA_HOME to point to your JDK installation directory.", file=sys.stderr)
        sys.exit(1)

    print(f"Using JAVA_HOME: {java_home}")
    # 将 JAVA_HOME/bin 加入 PATH (os.pathsep 自动处理跨平台的 ';' 或 ':')
    os.environ["PATH"] = f"{os.path.join(java_home, 'bin')}{os.pathsep}{os.environ.get('PATH', '')}"

    # 2. 第一次构建 (First build)
    print("\nExecuting mvn clean package to build the instrumentor...")
    pom_path = os.path.join("core", "pom.xml")
    
    # 跨平台处理 Maven 命令 (Windows 下是 mvn.cmd, Linux/Mac 下是 mvn)
    mvn_cmd = "mvn.cmd" if os.name == "nt" else "mvn"

    try:
        result = subprocess.run([mvn_cmd, "-f", pom_path, "clean", "package", "-DskipTests"])
        if result.returncode != 0:
            print("Maven build failed", file=sys.stderr)
            sys.exit(1)
    except FileNotFoundError:
        print(f"Error: Maven command ('{mvn_cmd}') not found. Please ensure Maven is installed and in your PATH.", file=sys.stderr)
        sys.exit(1)
        
    print("\nStep 1 and Step 2 completed successfully. (Subsequent steps ignored)")

if __name__ == "__main__":
    main()