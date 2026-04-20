import os
import json
import subprocess
import shutil
from pathlib import Path

def run_cmd(cmd, check=True):
    """Run shell command and return output"""
    print(f"Executing command: {' '.join(cmd)}")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if check and result.returncode != 0:
        print(f"Command failed: {result.stderr}")
        result.check_returncode()
    return result.stdout.strip()

def sync_files(project_file_path):
    """
    Synchronize modified files based on the project configuration.
    """
    if project_file_path is None:
        print("Error: project_file_path cannot be None.")
        return False

    current_project_file = Path(project_file_path)
    if not current_project_file.exists():
        print(f"Error: File not found: {current_project_file}")
        return False

    with open(current_project_file, 'r', encoding='utf-8') as f:
        config = json.load(f)

    original_git_root = config.get("original_git_root")
    source_branch = config.get("source_branch")

    if not original_git_root or not source_branch:
        print("Error: Missing original_git_root or source_branch in current_project file")
        return False

    print(f"Retrieved Git root: {original_git_root}")
    print(f"Retrieved source branch: {source_branch}")

    os.chdir(original_git_root)
    print(f"Working directory changed to: {os.getcwd()}")

    # 1. 检查当前分支是否为 source_branch
    current_branch = run_cmd(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
    if current_branch != source_branch:
        print(f"Error: Current branch is '{current_branch}', but expected '{source_branch}'. Incremental sync aborted.")
        return False

    target_branch = "shadow-project-for-instrumention"

    # 2. 检查是否有未 commit 的代码，如果有则直接 commit（必须在 diff 之前执行）
    status_output = run_cmd(['git', 'status', '--porcelain'])
    has_uncommitted_changes = bool(status_output.strip())
    
    if has_uncommitted_changes:
        print("\n" + "!" * 70)
        print("\033[1;31m" + "【 WARNING: UNCOMMITTED CHANGES DETECTED 】".center(64) + "\033[0m")
        print(f"\033[1;33mUncommitted changes found in branch '{source_branch}'. Executing 'git commit'...\033[0m")
        run_cmd(['git', 'add', '.'])
        run_cmd(['git', 'commit', '-m', 'Auto-commit before incremental instrumentation'])
        print("\033[1;31m" + f"YOUR CHANGES IN '{source_branch}' HAVE BEEN COMMITTED!".center(64) + "\033[0m")
        print("!" * 70 + "\n")

    # 3. 获取真正被用户修改的文件
    # 找到 source_branch 和 shadow 分支的共同祖先 (Merge Base)
    print("Calculating merge base to find actual modified files...")
    merge_base = run_cmd(['git', 'merge-base', 'HEAD', target_branch])
    
    # 比较共同祖先和当前 HEAD 的差异，这才是用户真正修改的文件
    diff_output = run_cmd(['git', 'diff', '--name-only', f'{merge_base}..HEAD'])

    modified_files = set()
    for line in diff_output.splitlines():
        filepath = line.strip()
        if filepath:
            if filepath.startswith('"') and filepath.endswith('"'):
                filepath = filepath[1:-1]
            modified_files.add(filepath)

    if not modified_files:
        print("No modified files found compared to the base commit.")
        return True # 没有修改直接返回成功即可
    else:
        print(f"Found {len(modified_files)} modified file(s).")

    # 4. 备份修改的文件到 ~/modified
    user_home = Path.home()
    modified_dir = user_home / "modified"
    if not modified_dir.exists():
        modified_dir.mkdir(parents=True)

    for file_rel_path in modified_files:
        src_file = Path(original_git_root) / file_rel_path
        if not src_file.is_file():
            continue

        dst_file = modified_dir / file_rel_path
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dst_file)
        print(f"Backed up: {file_rel_path} -> {dst_file}")

    # 5. 切换到 shadow-project-for-instrumention
    run_cmd(['git', 'checkout', target_branch])

    # 6. 恢复文件到当前影子分支
    print("Starting to overwrite files in shadow branch...")
    synced_absolute_paths = []
    for file_rel_path in modified_files:
        src_file = modified_dir / file_rel_path
        if not src_file.is_file():
            continue

        dst_file = Path(original_git_root) / file_rel_path
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dst_file)

        synced_absolute_paths.append(str(dst_file.resolve()))
        print(f"Restored: {src_file} -> {dst_file}")

    # 7. 保存绝对路径列表到配置文件
    config["synced_absolute_paths"] = synced_absolute_paths
    with open(current_project_file, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
    print(f"Saved {len(synced_absolute_paths)} absolute path(s) to {current_project_file.name}.")

    print("All operations completed successfully!")
    return True

def main():
    pass

if __name__ == "__main__":
    main()