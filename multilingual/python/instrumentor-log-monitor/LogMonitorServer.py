# C:\TechLearning\ai-powered-legacy-maintenance\multilingual\python\instrumentor-log-monitor\LogMonitorServer.py

import os
import sys
import time
import threading
import socket
import urllib.parse
import urllib.request
from datetime import datetime
from typing import List, Dict, Set, Any, Optional

class LogLifecycleHook:
    """
    日志生命周期钩子接口。
    任何想要在首次日志记录时执行初始化逻辑的类，都可以继承并实现该接口。
    """
    def on_first_log(self) -> None:
        raise NotImplementedError("Subclasses must implement on_first_log")


class LogMonitorServer(LogLifecycleHook):
    DEFAULT_PORT = 19898
    PROP_PORT = "instrumentor.monitor.port"
    PROP_AUTO_FLUSH = "instrumentor.monitor.autoFlushOnShutdown"
    TS_FMT = "%Y%m%d_%H%M%S"

    _flushed_lock = threading.Lock()
    _flushed = False

    # 管理端配置
    manager_ip: Optional[str] = None
    manager_port: int = -1

    # 新增：用于保存 HTTP 服务器实例和线程，以便优雅关闭
    _server_instance = None
    _server_thread: Optional[threading.Thread] = None

    def on_first_log(self) -> None:
        """
        实现生命周期接口：在首次产生日志时，启动后台 HTTP 监控服务线程并注册退出钩子
        """
        port = int(os.environ.get(self.PROP_PORT, self.DEFAULT_PORT))
        
        # 启动独立的 HTTP 监控线程
        # 保持 daemon=True 作为双重保险，但我们会通过 atexit 显式 shutdown 它
        LogMonitorServer._server_thread = threading.Thread(
            target=self._start_http_server, 
            args=(port,), 
            name="LogMonitor-HttpServer"
        )
        LogMonitorServer._server_thread.daemon = False  
        LogMonitorServer._server_thread.start()

        # 注册进程退出时的自动 Flush 钩子
        auto_flush = os.environ.get(self.PROP_AUTO_FLUSH, "true").lower() == "true"
        if auto_flush:
            import atexit
            atexit.register(self._shutdown_hook)
            self._log("Auto-flush enabled: shutdown hook registered.")

    @classmethod
    def _shutdown_hook(cls):
        cls._log("Shutdown hook triggered. Cleaning up...")
        
        # 1. 优先关闭 HTTP 服务器，防止其阻塞进程退出或占用端口
        if cls._server_instance:
            try:
                cls._log("Stopping HTTP server...")
                # shutdown() 会停止 serve_forever() 循环，安全释放 socket
                cls._server_instance.shutdown() 
                cls._server_instance.server_close()
            except Exception as e:
                cls._log("Error closing HTTP server during shutdown: %s", str(e))

        # 2. 执行 Flush 逻辑
        cls.flush_now("shutdown")

    @classmethod
    def _log(cls, fmt: str, *args):
        msg = fmt % args if args else fmt
        print(f"[LogMonitor] {msg}", file=sys.stderr)

    @classmethod
    def reset_flush_state(cls):
        with cls._flushed_lock:
            cls._flushed = False

    # ======================== HTTP Server ========================

    def _start_http_server(self, initial_port: int):
        from http.server import HTTPServer
        
        port = initial_port
        max_tries = 100
        server = None

        for i in range(max_tries):
            try:
                server = HTTPServer(('0.0.0.0', port), self._make_handler_class())
                break
            except Exception as e:
                if i == max_tries - 1:
                    self._log("Exception occurred while starting HTTP service on port %d: %s", port, str(e))
                    return
                port += 1

        if server is None:
            self._log("Unable to start HTTP service, port range %d - %d all occupied.", 
                      initial_port, initial_port + max_tries - 1)
            return

        # 将实例保存到类变量中，以便 atexit 钩子可以访问并关闭它
        LogMonitorServer._server_instance = server

        self._log("Instrumentor monitoring service started: http://localhost:%d", port)
        try:
            server.serve_forever()
        except Exception as e:
            # 如果是被主动 shutdown 的，不打印错误日志
            if LogMonitorServer._server_instance:
                self._log("Unable to run HTTP service: %s", str(e))

    def _make_handler_class(self):
        from http.server import BaseHTTPRequestHandler
        # 延迟导入已安装的 InstrumentLog，避免循环引用
        from InstrumentLog import InstrumentLog 

        class LogMonitorHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass  # 抑制控制台默认的请求日志输出

            def do_GET(self):
                parsed_url = urllib.parse.urlparse(self.path)
                path = parsed_url.path
                query_params = urllib.parse.parse_qs(parsed_url.query)

                if path == "/clear":
                    InstrumentLog.clear()
                    self._send_text_response(200, "[LogMonitor] Logs cleared.\n")
                elif path == "/flush":
                    LogMonitorServer.reset_flush_state()
                    LogMonitorServer.flush_now("manual_http")
                    self._send_text_response(200, "[LogMonitor] Flush triggered. Files sent to manager or saved locally.\n")
                elif path == "/status":
                    self._handle_status()
                elif path == "/setManager":
                    self._handle_set_manager(query_params)
                else:
                    self._send_text_response(404, "Not Found")

            def _send_text_response(self, status_code: int, body: str):
                self.send_response(status_code)
                self.send_header("Content-Type", "text/plain; charset=UTF-8")
                encoded = body.encode('utf-8')
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def _handle_status(self):
                log_snapshot = InstrumentLog.get_ordered_snapshot()
                buffers = InstrumentLog.get_all_event_buffers()
                total_logs = sum(len(v) for v in log_snapshot.values())
                total_events = sum(buf.count for buf in buffers)
                thread_order = InstrumentLog.get_thread_order()

                sb = []
                sb.append("[LogMonitor] Current Status")
                sb.append(f"  Total Threads  : {len(thread_order)}")
                sb.append(f"  Total Basic Log Entries: {total_logs}")
                sb.append(f"  Total Event Log Entries: {total_events}")
                if LogMonitorServer.manager_ip:
                    sb.append(f"  Manager Address: http://{LogMonitorServer.manager_ip}:{LogMonitorServer.manager_port}")
                
                self._send_text_response(200, "\n".join(sb) + "\n")

            def _handle_set_manager(self, params: Dict[str, List[str]]):
                ip_list = params.get("ip")
                port_list = params.get("port")
                if ip_list and port_list:
                    try:
                        LogMonitorServer.manager_ip = ip_list[0]
                        LogMonitorServer.manager_port = int(port_list[0])
                        msg = f"[LogMonitor] Manager set to {LogMonitorServer.manager_ip}:{LogMonitorServer.manager_port}\n"
                        LogMonitorServer._log(msg.strip())
                        self._send_text_response(200, msg)
                    except ValueError:
                        self._send_text_response(400, "[LogMonitor] Invalid port number.\n")
                else:
                    self._send_text_response(400, "[LogMonitor] Missing ip or port parameters.\n")

        return LogMonitorHandler

    # ======================== Flush & Format ========================

    @classmethod
    def flush_now(cls, source: str = "manual"):
        from InstrumentLog import InstrumentLog

        with cls._flushed_lock:
            if cls._flushed:
                cls._log("flush_now(%s) skipped — already flushed.", source)
                return
            cls._flushed = True

        try:
            ts = datetime.now().strftime(cls.TS_FMT)
            log_file_name = f"instrumentor-log-{ts}-{source}.txt"
            event_file_name = f"instrumentor-events-{ts}-{source}.txt"

            log_snapshot = InstrumentLog.get_ordered_snapshot()
            buffers = InstrumentLog.get_all_event_buffers()
            total_events = sum(buf.count for buf in buffers)

            if log_snapshot:
                log_content = cls._format_log_snapshot(log_snapshot)
                cls._handle_file_output(log_file_name, log_content, source)

            if total_events > 0:
                dictionary = cls._load_dictionary()
                event_content = cls._format_event_snapshot(buffers, dictionary)
                cls._handle_file_output(event_file_name, event_content, source)

            if not log_snapshot and total_events == 0:
                cls._log("flush_now(%s): no logs to flush.", source)
        except Exception as e:
            cls._log("flush_now(%s) failed: %s", source, str(e))

    @classmethod
    def _handle_file_output(cls, file_name: str, content: str, source: str):
        if cls.manager_ip and cls.manager_port > 0:
            target_url = f"http://{cls.manager_ip}:{cls.manager_port}/upload"
            try:
                boundary = f"----WebKitFormBoundary{int(time.time() * 1000)}"
                parts = [
                    f"--{boundary}".encode('utf-8'),
                    f'Content-Disposition: form-data; name="file"; filename="{file_name}"'.encode('utf-8'),
                    b'Content-Type: application/octet-stream\r\n',
                    content.encode('utf-8'),
                    f"--{boundary}--".encode('utf-8')
                ]
                body = b'\r\n'.join(parts) + b'\r\n'

                req = urllib.request.Request(target_url, data=body, method="POST")
                req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
                
                # 降低超时时间至 2 秒，防止退出时由于目标服务器不通而长时间卡死
                with urllib.request.urlopen(req, timeout=2) as response:
                    if response.status == 200:
                        cls._log("flush_now(%s): successfully sent %s to Manager at %s", source, file_name, target_url)
                        return
                    else:
                        cls._log("flush_now(%s): failed to send %s to Manager. Response code: %d", source, file_name, response.status)
            except Exception as e:
                cls._log("flush_now(%s): exception sending %s to Manager: %s", source, file_name, str(e))
        
        cls._save_locally(file_name, content, source)

    @classmethod
    def _save_locally(cls, file_name: str, content: str, source: str):
        with open(file_name, 'w', encoding='utf-8') as f:
            f.write(content)
        cls._log("flush_now(%s): log written locally to %s", source, os.path.abspath(file_name))

    @classmethod
    def _load_dictionary(cls) -> Dict[int, str]:
        dict_map = {}
        dict_path = "event_dictionary.txt"
        if os.path.exists(dict_path):
            try:
                with open(dict_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or '=' not in line:
                            continue
                        idx = line.find('=')
                        dict_map[int(line[:idx])] = line[idx+1:]
            except Exception as e:
                cls._log("Failed to load dictionary: %s", str(e))
        return dict_map

    @classmethod
    def _format_log_snapshot(cls, snapshot: Dict[int, List[int]]) -> str:
        groups = {}
        for thread_id, logs in snapshot.items():
            canonical_key = ",".join(map(str, sorted(list(set(logs)))))
            groups.setdefault(canonical_key, []).append((thread_id, logs))

        sb = []
        sb.append(f"# InstrumentLog (Deduplicated) @ {datetime.now().isoformat()}")
        sb.append(f"# Original thread count: {len(snapshot)}, Deduplicated group count: {len(groups)}\n")

        order = 1
        for canonical_key, group in groups.items():
            representative_tid, logs = group[0]
            sb.append(f"[Thread-{representative_tid}] (Group Order: #{order}, Count: {len(logs)})")
            order += 1
            if len(group) > 1:
                merged = ", ".join(f"Thread-{tid}" for tid, _ in group)
                sb.append(f"  # Merged from {len(group)} threads: {merged}")
            
            if logs:
                sb.append("  " + " -> ".join(map(str, logs)))
        
        return "\n".join(sb) + "\n"

    @classmethod
    def _format_event_snapshot(cls, buffers: List[Any], dictionary: Dict[int, str]) -> str:
        class EventRecord:
            def __init__(self, thread_id: int, nano_time: int, event_id: int, obj_id: int, item_id: int, action_name: str):
                self.thread_id = thread_id
                self.nano_time = nano_time
                self.event_id = event_id
                self.obj_id = obj_id
                self.item_id = item_id
                self.action_name = action_name

        all_events: List[EventRecord] = []
        min_time = sys.maxsize
        item_thread_map = {}

        for buf in buffers:
            for i in range(buf.count):
                t = buf.nano_times[i]
                if t < min_time:
                    min_time = t
                
                event_id = buf.event_ids[i]
                obj_id = buf.share_object_ids[i]
                item_id = buf.item_ids[i]
                action = dictionary.get(event_id, f"EVT_{event_id}")

                all_events.append(EventRecord(buf.thread_id, t, event_id, obj_id, item_id, action))

                if item_id != 0:
                    item_thread_map.setdefault(item_id, set()).add(buf.thread_id)

        if min_time == sys.maxsize:
            min_time = 0

        obj_map = {}
        item_map = {}
        obj_counter = 1
        item_counter = 1

        for record in all_events:
            if record.obj_id != 0 and record.obj_id not in obj_map:
                obj_map[record.obj_id] = f"O{obj_counter}"
                obj_counter += 1
            if record.item_id != 0 and record.item_id not in item_map:
                item_map[record.item_id] = f"I{item_counter}"
                item_counter += 1

        all_events.sort(key=lambda x: x.nano_time)

        compressed_events = []
        last_action_map = {}

        for current in all_events:
            if current.item_id != 0:
                accessing_threads = item_thread_map.get(current.item_id)
                if accessing_threads and len(accessing_threads) <= 1:
                    continue
            
            state_key = f"{current.thread_id}_{current.item_id}_{current.action_name}"
            last = last_action_map.get(state_key)

            if last and last.action_name == current.action_name:
                continue

            last_action_map[state_key] = current
            compressed_events.append(current)

        sb = []
        sb.append(f"# AI-Optimized Event Log Dump @ {datetime.now().isoformat()}")
        sb.append(f"# BaseTime: {min_time}")
        sb.append("# Format: DeltaTime, Thread, Action, Object, Item")
        sb.append("# Field Descriptions:")
        sb.append("#   - DeltaTime: Time elapsed (in nanoseconds) since the first recorded event.")
        sb.append("#   - Thread: The identifier of the thread performing the action.")
        sb.append("#   - Action: The operation performed (e.g., READ, WRITE, SYNC_ENTER).")
        sb.append("#   - Object: The shared resource the thread is operating on.")
        sb.append("#   - Item: The specific data object being passed, read, or written.")
        sb.append("# Note: Thread-local items are filtered. Redundant consecutive actions are merged.\n")

        for record in compressed_events:
            delta = record.nano_time - min_time
            obj_alias = "-" if record.obj_id == 0 else obj_map.get(record.obj_id, "-")
            item_alias = "-" if record.item_id == 0 else item_map.get(record.item_id, "-")
            sb.append(f"{delta}, T{record.thread_id}, {record.action_name}, {obj_alias}, {item_alias}")

        return "\n".join(sb) + "\n"