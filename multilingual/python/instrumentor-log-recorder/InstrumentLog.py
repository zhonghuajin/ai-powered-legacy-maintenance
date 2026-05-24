#!/usr/bin/env python3
"""
InstrumentLog.py - Runtime instrumentation log recorder for Python.

Collects execution traces (which code blocks were executed) and writes
them to a log file. Uses a process-based approach similar to the PHP version.
"""

import atexit
import os
import threading


class InstrumentLog:
    """Collects and stores execution traces for instrumented Python code."""

    _lock = threading.Lock()
    _block_set = set()
    _block_order = []
    _registered = False
    _log_dir = None
    _buffer = []
    _batch_size = 100

    @classmethod
    def staining(cls, block_id):
        """
        Record the execution of a code block.

        Args:
            block_id: The unique integer identifier of the code block.
        """
        if not cls._registered:
            atexit.register(cls.flush)
            cls._registered = True

        with cls._lock:
            if block_id not in cls._block_set:
                cls._block_set.add(block_id)
                cls._block_order.append(block_id)

            cls._buffer.append(block_id)
            if len(cls._buffer) >= cls._batch_size:
                cls._flush_buffer()

    @classmethod
    def clear(cls):
        """Clear all collected execution data."""
        with cls._lock:
            cls._block_set.clear()
            cls._block_order.clear()
            cls._buffer.clear()

    @classmethod
    def get_ordered_snapshot(cls):
        """Get an ordered snapshot of all executed block IDs."""
        with cls._lock:
            return list(cls._block_order)

    @classmethod
    def get_block_count(cls):
        """Get the number of unique blocks executed."""
        with cls._lock:
            return len(cls._block_set)

    @classmethod
    def flush(cls):
        """Flush all collected data to a log file."""
        with cls._lock:
            cls._flush_buffer()
            if not cls._block_order:
                return

            log_dir = cls._log_dir or os.getcwd()
            os.makedirs(log_dir, exist_ok=True)

            pid = os.getpid()
            thread_name = threading.current_thread().name
            log_file = os.path.join(log_dir, f"instrumentor-log-{pid}.txt")

            try:
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(f"[{thread_name}]\n")
                    ids = list(cls._block_order)
                    # Write in groups of 10 for readability
                    for i in range(0, len(ids), 10):
                        chunk = ids[i:i + 10]
                        f.write('->'.join(str(x) for x in chunk))
                        if i + 10 < len(ids):
                            f.write('->')
                        f.write('\n')
                    f.write('\n')
            except IOError as e:
                import sys
                print(f"[InstrumentLog] Failed to write log: {e}", file=sys.stderr)

    @classmethod
    def _flush_buffer(cls):
        """Internal: flush the buffer (called under lock)."""
        cls._buffer.clear()

    @classmethod
    def set_log_dir(cls, log_dir):
        """Set the directory where log files will be written."""
        cls._log_dir = log_dir

    @classmethod
    def dump(cls):
        """Print current execution trace to stdout."""
        with cls._lock:
            print(f"[InstrumentLog] Total unique blocks: {len(cls._block_set)}")
            print(f"[InstrumentLog] Execution order: {' -> '.join(str(x) for x in cls._block_order)}")


# Module-level convenience function
staining = InstrumentLog.staining
