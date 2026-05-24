#!/usr/bin/env python3
"""
LogMonitorServer.py - HTTP monitoring server for Python instrumentation logs.

Provides endpoints:
  /clear  - Clear all collected logs
  /flush  - Write logs to disk
  /status - Report current log count
  /push   - Receive log data from instrumented code

Usage: python LogMonitorServer.py [--port PORT] [--log-dir DIR]
"""

import json
import os
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

# Import InstrumentLog for direct access
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'instrumentor-log-recorder'))
try:
    from InstrumentLog import InstrumentLog
except ImportError:
    InstrumentLog = None


class LogStore:
    """Thread-safe store for received log data."""

    def __init__(self):
        self._lock = threading.Lock()
        self._logs = {}  # thread_name -> list of block IDs

    def push(self, thread_name, block_ids):
        with self._lock:
            if thread_name not in self._logs:
                self._logs[thread_name] = []
            self._logs[thread_name].extend(block_ids)

    def clear(self):
        with self._lock:
            self._logs.clear()

    def get_count(self):
        with self._lock:
            return sum(len(v) for v in self._logs.values())

    def get_thread_count(self):
        with self._lock:
            return len(self._logs)

    def flush_to_file(self, log_dir):
        with self._lock:
            if not self._logs:
                return None

            os.makedirs(log_dir, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            log_file = os.path.join(log_dir, f"instrumentor-log-{timestamp}-monitor.txt")

            with open(log_file, 'w', encoding='utf-8') as f:
                for thread_name, ids in self._logs.items():
                    f.write(f"[{thread_name}]\n")
                    # Deduplicate while preserving order
                    seen = set()
                    unique_ids = []
                    for block_id in ids:
                        if block_id not in seen:
                            seen.add(block_id)
                            unique_ids.append(block_id)

                    for i in range(0, len(unique_ids), 10):
                        chunk = unique_ids[i:i + 10]
                        f.write('->'.join(str(x) for x in chunk))
                        if i + 10 < len(unique_ids):
                            f.write('->')
                        f.write('\n')
                    f.write('\n')

            count = sum(len(v) for v in self._logs.values())
            self._logs.clear()
            return log_file, count


# Global log store
_log_store = LogStore()
_log_dir = os.getcwd()


class MonitorHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the log monitor server."""

    def do_GET(self):
        if self.path == '/clear':
            _log_store.clear()
            if InstrumentLog:
                InstrumentLog.clear()
            self._send_json({'status': 'ok', 'message': 'Logs cleared'})

        elif self.path == '/status':
            count = _log_store.get_count()
            if InstrumentLog:
                count += InstrumentLog.get_block_count()
            threads = _log_store.get_thread_count()
            self._send_json({
                'status': 'ok',
                'block_count': count,
                'thread_count': threads
            })

        elif self.path == '/flush':
            result = _log_store.flush_to_file(_log_dir)
            if InstrumentLog:
                InstrumentLog.flush()
            if result:
                log_file, count = result
                self._send_json({
                    'status': 'ok',
                    'message': f'Flushed {count} entries',
                    'file': log_file
                })
            else:
                self._send_json({'status': 'ok', 'message': 'No logs to flush'})

        elif self.path.startswith('/poll'):
            # Support polling from instrumented code
            self._send_json({'flush': False, 'clear': False})

        else:
            self._send_json({'status': 'error', 'message': 'Unknown endpoint'}, 404)

    def do_POST(self):
        if self.path == '/push':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')

            thread_name = self.headers.get('X-Thread-Name', 'MainThread')

            try:
                block_ids = [int(x.strip()) for x in body.split(',') if x.strip()]
                _log_store.push(thread_name, block_ids)
                self._send_json({'status': 'ok', 'received': len(block_ids)})
            except ValueError:
                self._send_json({'status': 'error', 'message': 'Invalid data'}, 400)
        else:
            self._send_json({'status': 'error', 'message': 'Unknown endpoint'}, 404)

    def _send_json(self, data, status=200):
        response = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format, *args):
        """Override to add timestamp."""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {args[0]}")


def main():
    global _log_dir

    port = 19898
    log_dir = os.getcwd()

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == '--port' and i + 1 < len(args):
            port = int(args[i + 1])
            i += 2
        elif args[i] == '--log-dir' and i + 1 < len(args):
            log_dir = os.path.abspath(args[i + 1])
            i += 2
        else:
            i += 1

    _log_dir = log_dir

    server = HTTPServer(('0.0.0.0', port), MonitorHandler)
    print(f"[LogMonitor] Server started on port {port}")
    print(f"[LogMonitor] Log directory: {log_dir}")
    print(f"[LogMonitor] Endpoints: /clear, /flush, /status, /push")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[LogMonitor] Shutting down...")
        # Flush remaining logs on shutdown
        result = _log_store.flush_to_file(_log_dir)
        if result:
            print(f"[LogMonitor] Final flush: {result[1]} entries saved to {result[0]}")
        server.server_close()


if __name__ == '__main__':
    main()
