# workflow_steps.py
import os
import sys
import subprocess
import re
import platform
import glob
import shutil
import json
from print_utils.utils import Colors, print_color
from .prechecks import setup_windows_proxy
from enginerring.shadow_project_management.instrument_with_shadow_project import run_instrumentation_mode

# 导入依赖处理相关的模块
from enginerring.dependency_handler.scan_deps import find_project_files
from enginerring.dependency_handler.prompt_organizer import generate_prompt
from enginerring.dependency_handler.dependency_injector import run_injection


def instrument_code(work_dir, proj_path=None, git_root=None):
    print_color(
        "\n>>> Setting up shadow branch and instrumenting code...", Colors.CYAN)

    print()
    print_color("========================================", Colors.YELLOW)
    print_color(" IMPORTANT PATH EXPLANATION", Colors.YELLOW)
    print_color("========================================", Colors.YELLOW)
    print_color(
        " The path requested here is the Git root directory of the target project.", Colors.YELLOW)
    print_color(
        " It is NOT the same as the paths listed in target-folders.txt.", Colors.YELLOW)
    print_color(
        " The paths in target-folders.txt are the specific source folders to instrument.", Colors.YELLOW)
    print_color(
        " The path entered below must be the top-level Git repository root that contains those folders.", Colors.YELLOW)
    print_color("========================================", Colors.YELLOW)

    if git_root:
        git_root_dir = git_root
        print_color(
            f"Using saved Git repository root directory: {git_root_dir}", Colors.GREEN)
    else:
        git_root_dir = ""
        while not git_root_dir:
            git_root_dir = input(
                "Please enter the Git repository root directory of the project that contains the folders listed in target-folders.txt: "
            ).strip()
            if not git_root_dir:
                print_color("[!] Path cannot be empty.", Colors.RED)

    print()
    print_color("========================================", Colors.CYAN)
    print_color("       Select Instrumentation Mode      ", Colors.CYAN)
    print_color("========================================", Colors.CYAN)
    print("  1. Full Instrumentation\n  2. Incremental Instrumentation\n  3. Skip (if project is already instrumented)")
    print_color("========================================", Colors.CYAN)

    inst_mode_choice = ""
    while not re.match(r"^[1-3]$", inst_mode_choice):
        inst_mode_choice = input(
            "Enter a number (1-3) for the instrumentation mode: ").strip()
        if not re.match(r"^[1-3]$", inst_mode_choice):
            print_color(
                "[!] Invalid input. Please enter 1, 2, or 3.", Colors.RED)

    if inst_mode_choice == "3":
        print_color("[Mode Selection] Skipping instrumentation.", Colors.GREEN)
        return

    mode_arg = "full" if inst_mode_choice == "1" else "incremental"
    print_color(f"[Mode Selection] Selected mode: {mode_arg}", Colors.GREEN)

    project_file_path = os.path.join(work_dir, "current_project")

    success = run_instrumentation_mode(
        git_root=git_root_dir,
        mode=mode_arg,
        project_file=project_file_path,
        original_cwd=os.getcwd(),
        proj_path=proj_path
    )

    if not success:
        print_color(
            "Error: Failed to setup shadow branch and instrument code. Exiting.", Colors.RED)
        sys.exit(1)

    # Move instrumentation output files to project directory after success
    if proj_path:
        _move_instrumentation_outputs_to_project(work_dir, proj_path)


def _move_instrumentation_outputs_to_project(work_dir, proj_path):
    """Move event_dictionary.txt and comment-mapping.txt from work_dir to proj_path."""
    files_to_move = ["event_dictionary.txt", "comment-mapping.txt"]
    for filename in files_to_move:
        src = os.path.join(work_dir, filename)
        dst = os.path.join(proj_path, filename)
        if os.path.isfile(src):
            shutil.move(src, dst)
            print_color(f"[Move] {filename} -> {proj_path}", Colors.GREEN)
        else:
            print_color(
                f"[WARN] {filename} not found in working directory, skip.", Colors.YELLOW)


def handle_instrumentation_dependencies(work_dir, proj_path, git_root, ask_llm_dir):
    """
    处理插桩后的依赖添加：
    1. 扫描依赖文件
    2. 获取白名单
    3. 生成 Prompt 并请求 LLM
    4. 解析 LLM 响应并注入依赖
    """
    print_color("\n>>> Handling Instrumentation Dependencies...", Colors.CYAN)

    # 1. 获取 files_input
    files_input = find_project_files(git_root)
    if not files_input:
        print_color("[-] No dependency management files found.", Colors.YELLOW)
        return

    # 2. 获取 whitelist_input
    config_path = os.path.join(proj_path, "config.json")
    whitelist_input = []
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)
            whitelist_input = config_data.get("original-target-folders", [])

    # 3. 获取 dependency_input
    snippets_json_path = os.path.join(
        work_dir, "enginerring", "dependency_handler", "dependency_snippets.json")
    dependency_input = ""
    if os.path.exists(snippets_json_path):
        with open(snippets_json_path, "r", encoding="utf-8") as f:
            snippets = json.load(f)
            # 默认用 pom.xml 的片段作为 prompt 示例供大模型参考
            dependency_input = snippets.get(
                "pom.xml", "<dependency>...</dependency>")

    # 4. 生成 Prompt
    prompt = generate_prompt(files_input, whitelist_input, dependency_input)

    # 将 Prompt 写入 ask_llm 目录供 LLM 读取
    prompt_file = os.path.join(ask_llm_dir, "dependency_prompt.txt")
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(prompt)

    print_color(
        f"[+] Dependency prompt generated at {prompt_file}", Colors.GREEN)

    # 5. 调用 LLM (通过直接导入模块同进程调用，方便打断点)
    llm_response_file = os.path.join(
        ask_llm_dir, "dependency_llm_response.txt")

    print_color(
        ">>> Asking LLM to identify target dependency files...", Colors.CYAN)

    # 将 ask_llm 目录加入 sys.path 以便导入
    if ask_llm_dir not in sys.path:
        sys.path.insert(0, ask_llm_dir)

    try:
        import run as ask_llm_run

        # 切换到 ask_llm 目录执行，确保 .env 文件能被正确读取
        original_cwd = os.getcwd()
        os.chdir(ask_llm_dir)

        # 直接调用暴露的 API 接口
        ask_llm_run.run_api(
            file_path="dependency_prompt.txt",
            output_path="dependency_llm_response.txt"
        )

        # 切回工作目录
        os.chdir(original_cwd)

    except ImportError as e:
        print_color(
            f"[!] Failed to import run.py from {ask_llm_dir}: {e}", Colors.RED)
        return

    # 切回工作目录
    os.chdir(original_cwd)

    # 6. 注入依赖
    print_color(
        "\n>>> Parsing LLM response and injecting dependencies...", Colors.CYAN)
    run_injection(llm_response_file, snippets_json_path)


def compile_and_run(instrumentor_test_path):
    print_color("\n>>> Compiling and running instrumentor test...", Colors.CYAN)
    os.chdir(instrumentor_test_path)

    mvn_cmd = "mvn.cmd" if platform.system() == "Windows" else "mvn"
    print_color(
        f"Executing: {mvn_cmd} clean package -DskipTests", Colors.RESET)
    subprocess.run([mvn_cmd, "clean", "package", "-DskipTests"])

    jar_path = os.path.join("target", "instrumentor-test-1.0-SNAPSHOT.jar")
    print_color(f"Executing: java -jar {jar_path}", Colors.RESET)
    subprocess.run(["java", "-jar", jar_path])

    print_color(
        f"Program execution finished. Please verify that instrumentor-events-*.txt and instrumentor-log-*.txt have been generated in {instrumentor_test_path}",
        Colors.GREEN
    )


def startup_log_manager_server(work_dir):
    print_color("\n>>> Starting Log Manager Server...", Colors.CYAN)
    server_script = os.path.join(
        work_dir, "enginerring", "log_manager_server", "server.py")

    if os.path.exists(server_script):
        print_color(f"Launching {server_script}...", Colors.GREEN)
        subprocess.run([sys.executable, server_script])
    else:
        print_color(f"server.py not found at: {server_script}", Colors.RED)


def analyze_logs(work_dir, instrumentor_test_path, proj_path=None):
    print_color(
        "\n>>> Analyzing logs and extracting denoised data...", Colors.CYAN)
    os.chdir(work_dir)

    # Adapt to the new save path under scenario_data
    scenario_dir = os.path.join(work_dir, 'scenario_data')
    if os.path.isdir(scenario_dir):
        search_dir = scenario_dir
    else:
        search_dir = instrumentor_test_path   # fallback for backward compatibility

    log_files = sorted(
        glob.glob(os.path.join(search_dir, "instrumentor-log-*.txt")),
        key=os.path.getmtime,
        reverse=True
    )
    events_files = sorted(
        glob.glob(os.path.join(search_dir, "instrumentor-events-*.txt")),
        key=os.path.getmtime,
        reverse=True
    )

    if log_files and events_files:
        log_file = log_files[0]
        events_file = events_files[0]
        print(f"Found log file: {log_file}")
        print(f"Found events file: {events_file}")

        target_folders_file = os.path.join(
            proj_path, "target-folders.txt") if proj_path else ".\\target-folders.txt"

        # Use project directory for mapping files if available, otherwise fall back to work_dir
        if proj_path:
            comment_mapping_file = os.path.join(
                proj_path, "comment-mapping.txt")
            event_dict_file = os.path.join(proj_path, "event_dictionary.txt")
        else:
            comment_mapping_file = ".\\comment-mapping.txt"
            event_dict_file = ".\\event_dictionary.txt"

        # Safety check: ensure required files exist
        if not os.path.exists(comment_mapping_file):
            print_color(
                f"[WARN] comment-mapping.txt not found at {comment_mapping_file}", Colors.YELLOW)
        if not os.path.exists(event_dict_file):
            print_color(
                f"[WARN] event_dictionary.txt not found at {event_dict_file}", Colors.YELLOW)

        ps_exe = "powershell" if platform.system() == "Windows" else "pwsh"
        ps_cmd = [
            ps_exe, "-ExecutionPolicy", "Bypass", "-File", ".\\process-logs-demo.ps1",
            "-TargetFoldersFile", target_folders_file,
            "-LogFile", log_file,
            "-CommentMappingFile", comment_mapping_file,
            "-EventDictionaryFile", event_dict_file,
            "-EventsFile", events_file
        ]
        subprocess.run(ps_cmd)
    else:
        print_color(
            f"Could not find generated log or events file in: {search_dir}. "
            "Please check whether Step 2 executed successfully and generated the logs.",
            Colors.RED
        )


def generate_ai_prompt(work_dir):
    print_color("\n>>> Generating AI Prompt...", Colors.CYAN)
    os.chdir(work_dir)

    ai_app_path = os.path.join(work_dir, "core", "scenario_data_ai_app")
    python_script_path = os.path.join(
        ai_app_path, "generate_bug_localization_prompt.py")

    if os.path.exists(python_script_path):
        print_color(
            f"Running Python script from {work_dir} to generate the prompt...", Colors.GREEN)
        subprocess.run([sys.executable, python_script_path])
    else:
        print_color(
            f"AI prompt generation script not found at: {python_script_path}", Colors.RED)


def ask_llm_for_localization(ask_llm_dir):
    print_color("\n>>> Asking LLM for Bug Localization...", Colors.CYAN)
    setup_windows_proxy()

    os.chdir(ask_llm_dir)
    if os.path.exists("run.py"):
        subprocess.run([sys.executable, "run.py"])
    else:
        print_color(f"run.py not found in {ask_llm_dir}", Colors.RED)


def generate_fix_prompt(work_dir):
    print_color("\n>>> Generating Fix Prompt...", Colors.CYAN)

    fix_bug_dir = os.path.join(work_dir, "enginerring", "fix_bug")
    generate_fix_script = os.path.join(fix_bug_dir, "generate_fix_prompt.py")

    if os.path.exists(generate_fix_script):
        subprocess.run([sys.executable, generate_fix_script])
    else:
        print_color(
            f"generate_fix_prompt.py not found at: {generate_fix_script}", Colors.RED)


def ask_llm_for_code_fix(ask_llm_dir):
    print_color("\n>>> Asking LLM for Code Fix...", Colors.CYAN)
    os.chdir(ask_llm_dir)
    if os.path.exists("run.py"):
        subprocess.run([sys.executable, "run.py"])
    else:
        print_color(f"run.py not found in {ask_llm_dir}", Colors.RED)


def apply_fix(work_dir):
    print_color("\n>>> Applying Fix to Source Code...", Colors.CYAN)

    fix_bug_dir = os.path.join(work_dir, "enginerring", "fix_bug")
    apply_fix_script = os.path.join(fix_bug_dir, "apply_fix.py")

    if os.path.exists(apply_fix_script):
        subprocess.run([sys.executable, apply_fix_script])
    else:
        print_color(
            f"apply_fix.py not found at: {apply_fix_script}", Colors.RED)
