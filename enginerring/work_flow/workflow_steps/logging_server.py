import os
import sys
import time
import glob
import shutil
import socket
import json
import subprocess
from print_utils.utils import Colors, print_color

def startup_log_manager_server(work_dir, proj_path=None):
    print_color("\n>>> Starting Log Manager Server...", Colors.CYAN)

    if proj_path:
        config_file = os.path.join(proj_path, 'config.json')
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                if config.get('skip_log_and_manager') is True:
                    print_color(
                        "[Skip] Verification failed previously. Skipping Log Manager Server.", Colors.YELLOW)
                    return False
            except Exception as e:
                print_color(
                    f"[Warning] Failed to read config.json: {e}", Colors.YELLOW)

    if proj_path:
        config_file = os.path.join(proj_path, 'config.json')
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)

            if config.get('language') == 'php':
                is_running = False
                for port in range(19898, 19999):
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.settimeout(0.05)
                        if s.connect_ex(('127.0.0.1', port)) == 0:
                            is_running = True
                            break

                if is_running:
                    print_color(
                        '[PHP Monitor] Detected existing service on ports 19898-19998. Skipping startup.', Colors.GREEN)
                else:
                    jar_path = os.path.join(
                        work_dir, 'multilingual', 'php', 'instrumentor-log-monitor', 'target', 'redis-log-monitor-1.0-SNAPSHOT.jar')
                    if os.path.exists(jar_path):
                        print_color(
                            '[PHP Monitor] No running service found. Auto-starting monitor in background...', Colors.GREEN)
                        log_file_path = os.path.join(
                            proj_path, 'php_monitor_startup.log')
                        log_file = open(log_file_path, 'w')
                        subprocess.Popen(
                            ['java', '-jar', jar_path],
                            cwd=work_dir,
                            stdout=log_file,
                            stderr=subprocess.STDOUT
                        )
                    else:
                        print_color(
                            f'[Warning] PHP log monitor jar not found at: {jar_path}', Colors.YELLOW)

            if config.get('language') in ['javascript', 'js']:
                jar_path = os.path.join(
                    work_dir, 'multilingual', 'javascript', 'instrumentor-log-monitor', 'target', 'js-log-monitor-1.0-SNAPSHOT.jar')
                if os.path.exists(jar_path):
                    print_color(
                        '[JS Monitor] Auto-starting monitor in background...', Colors.GREEN)
                    log_file_path = os.path.join(
                        proj_path, 'js_monitor_startup.log')
                    log_file = open(log_file_path, 'w')
                    subprocess.Popen(
                        ['java', '-jar', jar_path],
                        cwd=work_dir,
                        stdout=log_file,
                        stderr=subprocess.STDOUT
                    )
                else:
                    print_color(
                        f'[Warning] JS log monitor jar not found at: {jar_path}', Colors.YELLOW)

    server_dir = os.path.join(work_dir, "enginerring", "log_manager_server")

    if server_dir not in sys.path:
        sys.path.insert(0, server_dir)

    try:
        if 'log_manager' in sys.modules:
            del sys.modules['log_manager']

        import log_manager as log_server

        log_server.SCENARIO_SAVE_ROOT = proj_path if proj_path else os.getcwd()

        print_color(f"Launching log manager server interface...", Colors.GREEN)
        return log_server.run_manager()
    except ImportError as e:
        print_color(
            f"Failed to import log_manager module from {server_dir}: {e}", Colors.RED)
        return False

def analyze_logs(work_dir, proj_path=None, auto_analyze=False):
    print_color(
        "\n>>> Analyzing logs and extracting denoised data...", Colors.CYAN)

    if proj_path:
        config_file = os.path.join(proj_path, 'config.json')
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                if config.get('skip_log_and_manager') is True:
                    print_color(
                        "[Skip] Verification failed previously. Skipping Log Analysis.", Colors.YELLOW)
                    return
            except Exception as e:
                print_color(
                    f"[Warning] Failed to read config.json: {e}", Colors.YELLOW)

    if auto_analyze:
        print_color(
            "[Auto] Flush command detected. Automatically executing Log Analysis...", Colors.GREEN)
        choice = "2"
    else:
        print()
        print_color("========================================", Colors.CYAN)
        print_color("       Analyze Logs Options             ", Colors.CYAN)
        print_color("========================================", Colors.CYAN)
        print("  1. Skip (Default)\n  2. Execute Log Analysis")
        print_color("========================================", Colors.CYAN)

        choice = input(
            "Enter a number (1-2) or press Enter to skip [1]: ").strip() or "1"

    if choice == "1":
        print_color(
            "[Log Analysis] Skipping log analysis and denoising.", Colors.GREEN)
        return

    os.chdir(work_dir)

    pruned_dir = os.path.join(work_dir, 'pruned')
    if os.path.exists(pruned_dir):
        shutil.rmtree(pruned_dir)
        print_color(
            f"[CLEAN] Removed existing pruned directory: {pruned_dir}", Colors.GREEN)
    os.makedirs(pruned_dir, exist_ok=True)
    print_color(
        f"[CLEAN] Ensured fresh pruned directory: {pruned_dir}", Colors.GREEN)

    if proj_path and os.path.isdir(proj_path):
        search_dir = os.path.join(proj_path, 'scenario_data')
    else:
        search_dir = os.path.join(work_dir, 'scenario_data')
        print_color(
            "[WARNING] proj_path not provided, falling back to global scenario_data directory.",
            Colors.YELLOW
        )

    project_lang = "java"
    base_reference_dir = None
    if proj_path:
        config_path = os.path.join(proj_path, 'config.json')
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                    project_lang = config_data.get('language', 'java').lower()
                    base_reference_dir = config_data.get('original_git_root')
            except Exception as e:
                print_color(
                    f"[WARN] Failed to read language or original_git_root from config.json: {e}", Colors.YELLOW)

    if not os.path.isdir(search_dir):
        print_color(
            f"[WARNING] scenario_data directory not found at {search_dir}.",
            Colors.YELLOW
        )

    wait_count = 0
    while True:
        log_files = sorted(
            glob.glob(os.path.join(search_dir, "instrumentor-log-*.txt")),
            key=os.path.getmtime,
            reverse=True
        )

        if log_files:
            break

        wait_count += 1
        print_color(
            f"[WAIT] No log files found in {search_dir} yet. "
            f"Waiting for Step 2 to generate logs... (Waited {wait_count * 3}s)",
            Colors.YELLOW
        )
        time.sleep(3)

    events_files = sorted(
        glob.glob(os.path.join(search_dir, "instrumentor-events-*.txt")),
        key=os.path.getmtime,
        reverse=True
    )

    if not events_files:
        print_color(
            f"[Auto-Fix] Could not find events file in: {search_dir}. Automatically creating a fake empty event file.",
            Colors.YELLOW
        )
        os.makedirs(search_dir, exist_ok=True)
        fake_events_file = os.path.join(
            search_dir, "instrumentor-events-fake.txt")
        with open(fake_events_file, "w", encoding="utf-8") as f:
            pass
        events_files = [fake_events_file]

    log_file = log_files[0]
    events_file = events_files[0]
    print(f"Found log file: {log_file}")
    print(f"Found events file: {events_file}")

    target_folders_file = os.path.join(
        proj_path, "target-folders.txt") if proj_path else ".\\target-folders.txt"

    if proj_path:
        block_line_mapping_file = os.path.join(
            proj_path, "block-line-mapping.txt")
        block_signature_file = os.path.join(
            proj_path, "block-signature.txt")
        event_dict_file = os.path.join(proj_path, "event_dictionary.txt")
    else:
        block_line_mapping_file = ".\\block-line-mapping.txt"
        block_signature_file = ".\\block-signature.txt"
        event_dict_file = ".\\event_dictionary.txt"

    if not os.path.exists(block_line_mapping_file):
        print_color(
            f"[WARN] block-line-mapping.txt not found at {block_line_mapping_file}", Colors.YELLOW)
    if not os.path.exists(block_signature_file):
        print_color(
            f"[WARN] block-signature.txt not found at {block_signature_file}", Colors.YELLOW)
    if not os.path.exists(event_dict_file):
        print_color(
            f"[WARN] event_dictionary.txt not found at {event_dict_file}", Colors.YELLOW)

    if work_dir not in sys.path:
        sys.path.insert(0, work_dir)
    try:
        from enginerring.log_processor import process_logs
    except ImportError as e:
        print_color(f"Failed to import process_logs: {e}", Colors.RED)
        return

    try:
        process_logs.process_logs(
            language=project_lang,
            target_folders_file=target_folders_file,
            log_file=log_file,
            block_line_mapping_file=block_line_mapping_file,
            block_signature_file=block_signature_file,
            events_file=events_file,
            event_dictionary_file=event_dict_file,
            base_reference_dir=base_reference_dir,
        )
    except Exception as e:
        print_color(f"Log processing failed: {e}", Colors.RED)