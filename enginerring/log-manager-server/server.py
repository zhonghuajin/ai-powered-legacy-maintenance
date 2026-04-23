import os
import threading
import logging
import sys
import socket
import requests
import concurrent.futures
from flask import Flask, request, jsonify

# Import color utility from attachment (assuming utils.py exists)
try:
    from utils import Colors, print_color
except ImportError:
    class Colors:
        CYAN = '\033[96m'
        YELLOW = '\033[93m'
        GREEN = '\033[92m'
        RED = '\033[91m'
        MAGENTA = '\033[95m'
        DARKGRAY = '\033[90m'
        RESET = '\033[0m'
    def print_color(text, color):
        print(f"{color}{text}{Colors.RESET}")

app = Flask(__name__)
PORT = 5000

# Global variables
target_ips = []
active_endpoints = []  # Stores scanned (ip, port) pairs

# ==========================================
# Flask Web Service Routes
# ==========================================
@app.route('/upload', methods=['POST'])
def upload_file():
    """Receive file and save to denoised-data folder in current working directory"""
    save_dir = os.path.join(os.getcwd(), 'denoised-data')
    os.makedirs(save_dir, exist_ok=True)

    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    file_path = os.path.join(save_dir, file.filename)
    file.save(file_path)
    print_color(f"\n[+] Successfully received and saved file: {file_path}", Colors.GREEN)
    
    return jsonify({"status": "success", "message": f"File {file.filename} received"})

# ==========================================
# Command Line Interface (CLI) Logic
# ==========================================
def get_local_ip():
    """Get local LAN IP to inform LogMonitorServer"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def check_single_port(ip, port, local_ip, stop_event):
    """Worker function to check a single port using fast socket connection first"""
    # 如果其他线程已经找到了服务，直接退出
    if stop_event.is_set():
        return None

    # 1. 使用原生 Socket 进行极速端口探测 (超时设为 0.1 秒)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.1)
        try:
            result = s.connect_ex((ip, port))
            if result != 0:
                return None  # 端口未开放，直接返回
        except Exception:
            return None

    # 如果其他线程在我们探测期间找到了，退出
    if stop_event.is_set():
        return None

    # 2. 端口开放，发送 HTTP 请求验证服务
    try:
        url = f"http://{ip}:{port}/status"
        res = requests.get(url, timeout=0.5)
        if res.status_code == 200:
            # 标记已找到，通知其他线程停止
            stop_event.set()
            
            print_color(f"Found service: {ip}:{port}", Colors.GREEN)
            
            # Send setManager request
            set_mgr_url = f"http://{ip}:{port}/setManager?ip={local_ip}&port={PORT}"
            mgr_res = requests.get(set_mgr_url, timeout=1)
            if mgr_res.status_code == 200:
                print_color(f"   -> Successfully registered Manager at {ip}:{port}", Colors.GREEN)
            
            return (ip, port)
    except requests.RequestException:
        pass
    
    return None

def scan_ports():
    """Scan ports on target IPs concurrently and register Manager"""
    global active_endpoints
    active_endpoints = []
    local_ip = get_local_ip()
    
    print_color("\nStarting port scan (19898 - 19997)...", Colors.CYAN)
    for ip in target_ips:
        found_any = False
        stop_event = threading.Event()
        
        # 使用 100 个线程并发，瞬间把所有端口的探测请求发出去
        with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
            futures = [
                executor.submit(check_single_port, ip, port, local_ip, stop_event) 
                for port in range(19898, 19898 + 100)
            ]
            
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result:
                    active_endpoints.append(result)
                    found_any = True
                    
        if not found_any:
            print_color(f"No available service port found on {ip}.", Colors.RED)

def input_target_ips():
    """Handle IP input logic"""
    global target_ips
    prompt_msg = f"{Colors.MAGENTA}Enter IPs separated by ';' (press Enter for default: localhost): {Colors.RESET}"
    
    try:
        ip_str = input(prompt_msg)
    except (KeyboardInterrupt, EOFError):
        print_color("\nInterrupt signal detected, exiting...", Colors.RED)
        os._exit(0)
    
    if ip_str.strip():
        target_ips = [ip.strip() for ip in ip_str.split(';') if ip.strip()]
        print_color(f"Target IPs updated to: {target_ips}", Colors.GREEN)
    else:
        if not target_ips:
            target_ips = ['localhost']
            print_color(f"No IP entered, using defaults: {target_ips}", Colors.GREEN)
        else:
            print_color(f"No IP entered, keeping current settings: {target_ips}", Colors.YELLOW)
    
    # Scan immediately after entering IPs
    scan_ports()

def print_endpoints_menu():
    """Print scanned endpoints and available commands"""
    print()
    print_color("=========================================", Colors.CYAN)
    print_color("           Target Service List           ", Colors.YELLOW)
    print_color("=========================================", Colors.CYAN)
    
    if not active_endpoints:
        print_color("  [Empty] No available endpoints scanned.", Colors.DARKGRAY)
    else:
        for idx, (ip, port) in enumerate(active_endpoints, 1):
            print_color(f"  {idx}. {ip}:{port} (scanned endpoint)", Colors.GREEN)
            
    print_color("=========================================", Colors.CYAN)
    print_color("           Available Commands            ", Colors.YELLOW)
    print_color("=========================================", Colors.CYAN)
    print_color("  <list_number> <command_number> - Send control command to specified service", Colors.GREEN)
    print_color("      Command numbers: 1:status, 2:clear, 3:flush", Colors.GREEN)
    print_color("      Example input: '1 3' (execute flush on 1st IP in list)", Colors.DARKGRAY)
    print_color("  reip                  - Re-enter target IP addresses and scan", Colors.GREEN)
    print_color("  exit                  - Exit the log manager server and go back to main flow", Colors.RED)
    print_color("=========================================\n", Colors.CYAN)

def scan_and_manage():
    """CLI thread main loop"""
    if not target_ips:
        print_color("target_points not found.", Colors.YELLOW)
        input_target_ips()
    
    while True:
        print_endpoints_menu()
        try:
            cmd_input = input(f"{Colors.CYAN}CLI > {Colors.RESET}").strip().lower()
            
            if cmd_input == 'exit':
                print_color("Shutting down service and exiting...", Colors.RED)
                os._exit(0)
            elif cmd_input == 'reip':
                input_target_ips()
                continue
            elif cmd_input == '':
                continue
            
            # Parse "<number> <command>"
            parts = cmd_input.split()
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                idx = int(parts[0])
                cmd_id = int(parts[1])
                
                if 1 <= idx <= len(active_endpoints):
                    target_ip, target_port = active_endpoints[idx - 1]
                    cmd_map = {1: "status", 2: "clear", 3: "flush"}
                    
                    if cmd_id in cmd_map:
                        action = cmd_map[cmd_id]
                        url = f"http://{target_ip}:{target_port}/{action}"
                        print_color(f"Sending request to {url}...", Colors.CYAN)
                        try:
                            # flush may trigger file upload, give a bit more timeout
                            res = requests.get(url, timeout=5)
                            print_color(f"Response:\n{res.text}", Colors.GREEN)
                        except Exception as e:
                            print_color(f"Request failed: {e}", Colors.RED)
                    else:
                        print_color("Invalid command number. Please enter 1, 2, or 3.", Colors.RED)
                else:
                    print_color("Invalid list number.", Colors.RED)
            else:
                print_color("Invalid input format. See [Available Commands] above for help.", Colors.DARKGRAY)
                
        except (KeyboardInterrupt, EOFError):
            print_color("\nInterrupt signal detected, exiting...", Colors.RED)
            os._exit(0)

# ==========================================
# Main Entry Point
# ==========================================
if __name__ == '__main__':
    cli_thread = threading.Thread(target=scan_and_manage, daemon=True)
    cli_thread.start()
    
    log = logging.getLogger('werkzeug')
    log.disabled = True
    try:
        import flask.cli
        flask.cli.show_server_banner = lambda *args: None
    except Exception:
        pass

    try:
        app.run(host='0.0.0.0', port=PORT)
    except (KeyboardInterrupt, SystemExit):
        pass