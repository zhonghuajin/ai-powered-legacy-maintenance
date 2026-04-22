import os
import sys
import argparse
import subprocess

def main():

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
        result = subprocess.run([mvn_cmd, "-f", pom_path, "clean", "install", "-DskipTests"])
        if result.returncode != 0:
            print("Maven build failed", file=sys.stderr)
            sys.exit(1)
    except FileNotFoundError:
        print(f"Error: Maven command ('{mvn_cmd}') not found. Please ensure Maven is installed and in your PATH.", file=sys.stderr)
        sys.exit(1)
        
    print("\nStep 1 and Step 2 completed successfully. (Subsequent steps ignored)")

if __name__ == "__main__":
    main()