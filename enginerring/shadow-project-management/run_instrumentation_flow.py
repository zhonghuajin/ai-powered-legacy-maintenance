import os
import sys
import argparse
import subprocess
import shutil

def run_instrumentation_flow(target_folders_file=None, target_folders_list=None, skip_build_and_test=False):
    """
    Pure Python implementation of the instrumentation flow.
    Ensures cross-platform compatibility without relying on PowerShell.
    """
    print("\n--- Starting Instrumentation Flow ---")
    
    target_folders = []

    # 1. Read and validate target folders
    if target_folders_list:
        target_folders = target_folders_list
    else:
        if not target_folders_file:
            target_folders_file = os.path.join(".", "target-folders.txt")
            
        if not os.path.exists(target_folders_file):
            print(f"Error: Target folders file does not exist: {target_folders_file}")
            return False
            
        with open(target_folders_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    target_folders.append(line)
                    
        if not target_folders:
            print(f"Error: No target folders found in file: {target_folders_file}")
            return False
            
        print(f"Loaded {len(target_folders)} target folder(s) from file: {target_folders_file}")
    
    for folder in target_folders:
        if not os.path.exists(folder):
            print(f"Error: Target folder does not exist: {folder}")
            return False
            
    print(f"Target folders: {', '.join(target_folders)}")

    # 2. Check Java environment variables
    print("\nChecking Java environment variables...")
    java_home = os.environ.get("JAVA_HOME")
    if not java_home:
        print("Error: JAVA_HOME Environment variable not configured. Please set JAVA_HOME to point to your JDK installation directory.")
        return False
        
    print(f"Using JAVA_HOME: {java_home}")
    
    # Update PATH for the current process to ensure the correct Java/Mvn is used
    java_bin = os.path.join(java_home, "bin")
    os.environ["PATH"] = f"{java_bin}{os.pathsep}{os.environ.get('PATH', '')}"

    # Find executables dynamically (handles .exe/.cmd on Windows automatically)
    mvn_exe = shutil.which("mvn")
    java_exe = shutil.which("java")
    
    if not mvn_exe:
        print("Error: Maven (mvn) not found in PATH.")
        return False
    if not java_exe:
        print("Error: Java (java) not found in PATH.")
        return False

    pom_path = os.path.join(".", "core", "pom.xml")

    # 3. First build
    print("\nExecuting mvn clean package to build the instrumentor...")
    mvn_build_cmd = [mvn_exe, "-f", pom_path, "clean", "package", "-DskipTests"]
    if subprocess.run(mvn_build_cmd).returncode != 0:
        print("Error: Maven build failed")
        return False

    # 4. Execute Instrumentor related Java commands
    print("\nExecuting code instrumentation (Instrumentor)...")
    
    jars_to_run = [
        ("Main instrumentation", os.path.join(".", "core", "instrumentor", "target", "instrumentor-1.0-SNAPSHOT.jar")),
        ("Encoding mapping", os.path.join(".", "core", "instrumentor-with-encoding", "target", "instrumentor-with-encoding-1.0-SNAPSHOT.jar")),
        ("Activator", os.path.join(".", "core", "instrumentor-activator", "target", "instrumentor-activator-1.0-SNAPSHOT.jar"))
    ]
    
    for step_name, jar_path in jars_to_run:
        print(f"Running {step_name}...")
        java_cmd = [java_exe, "-jar", jar_path] + target_folders
        if subprocess.run(java_cmd).returncode != 0:
            print(f"Warning: {step_name} step returned non-zero exit code.")

    # 5. Second build and tests
    if not skip_build_and_test:
        print("\nExecuting mvn clean package again...")
        if subprocess.run(mvn_build_cmd).returncode != 0:
            print("Error: Second Maven build failed")
            return False

        print("\nExecuting SyncTest...")
        test_cp = os.path.join(".", "core", "instrumentor-test", "target", "instrumentor-test-1.0-SNAPSHOT.jar")
        test_cmd = [java_exe, "-cp", test_cp, "com.example.instrumentor.happens.before.SyncTest"]
        if subprocess.run(test_cmd).returncode != 0:
            print("Warning: Test execution returned non-zero exit code.")
    else:
        print("\nSkipping second build and test execution (SkipBuildAndTest flag is set)")

    print("\nInstrumentation and testing phase completed. Please check the generated log file timestamp and use process-logs-demo.py for subsequent processing.")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Executes the instrumentation build, instrumentation process, and testing flow.")
    parser.add_argument("-f", "--target-folders-file", default=os.path.join(".", "target-folders.txt"), 
                        help="Specify a file containing target folder paths (one per line)")
    parser.add_argument("-t", "--target-folders", nargs='+', 
                        help="Specify one or more target folder paths for instrumentation (space-separated)")
    parser.add_argument("--skip-build-and-test", action="store_true", 
                        help="Skip the second build and test execution steps")
    
    args = parser.parse_args()
    
    success = run_instrumentation_flow(
        target_folders_file=args.target_folders_file,
        target_folders_list=args.target_folders,
        skip_build_and_test=args.skip_build_and_test
    )
    
    if not success:
        sys.exit(1)