# C:\TechLearning\ai-powered-legacy-maintenance\multilingual\python\instrumentor-log-recorder\InstrumentLog.py

import sys
import threading
from typing import List, Dict, Any

# =====================================================================
# 线程安全的事件 Buffer (对应 Java ThreadEventBuffer)
# =====================================================================
class ThreadEventBuffer:
    def __init__(self, thread_id: int):
        self.thread_id = thread_id
        self.event_ids: List[int] = []
        self.share_object_ids: List[int] = []
        self.item_ids: List[int] = []
        self.nano_times: List[int] = []
        self.count = 0

    def append(self, event_id: int, share_object_id: int, item_id: int, nano_time: int):
        self.event_ids.append(event_id)
        self.share_object_ids.append(share_object_id)
        self.item_ids.append(item_id)
        self.nano_times.append(nano_time)
        self.count += 1


# =====================================================================
# 核心日志记录器 (对应 InstrumentLog)
# =====================================================================
class InstrumentLog:
    # 基础块插桩日志: { thread_id: { block_id: None } }
    _block_map: Dict[int, Dict[int, None]] = {}
    _block_map_lock = threading.Lock()

    # 事件插桩日志
    _all_buffers: List[ThreadEventBuffer] = []
    _buffers_lock = threading.Lock()

    # 线程局部变量
    _local_buffer = threading.local()

    # 记录线程出现顺序
    _key_order: List[int] = []
    _key_order_lock = threading.Lock()

    # 首次记录标记
    _first_log = True
    _first_log_lock = threading.Lock()

    @classmethod
    def _check_first_log(cls):
        """
        对应 Java 的 checkFirstLog 和 fireFirstLogHooks。
        在 Python 中，我们直接实例化并调用 LogMonitorServer。
        """
        need_trigger = False
        with cls._first_log_lock:
            if cls._first_log:
                cls._first_log = False
                need_trigger = True
        
        if need_trigger:
            try:
                # 动态导入已安装的 LogMonitorServer，防止循环引用
                from LogMonitorServer import LogMonitorServer
                hook = LogMonitorServer()
                hook.on_first_log()
            except Exception as e:
                print(f"[InstrumentLog] Failed to invoke first log hook: {e}", file=sys.stderr)

    @classmethod
    def _register_thread_order(cls, thread_id: int):
        with cls._key_order_lock:
            if thread_id not in cls._key_order:
                cls._key_order.append(thread_id)

    @classmethod
    def staining(cls, *args):
        """
        重载方法：
        1. staining(block_id: int) -> 基础块插桩
        2. staining(event_id: int, share_object_id: int, item_id: int, nano_time: int) -> 详细事件插桩
        """
        cls._check_first_log()
        thread_id = threading.get_ident()

        if len(args) == 1:
            # 基础块插桩
            block_id = args[0]
            with cls._block_map_lock:
                if thread_id not in cls._block_map:
                    cls._block_map[thread_id] = {}
                    cls._register_thread_order(thread_id)
                cls._block_map[thread_id][block_id] = None

        elif len(args) == 4:
            # 详细事件插桩
            event_id, share_object_id, item_id, nano_time = args
            
            if not hasattr(cls._local_buffer, "buffer"):
                buf = ThreadEventBuffer(thread_id)
                cls._local_buffer.buffer = buf
                with cls._buffers_lock:
                    cls._all_buffers.append(buf)
                cls._register_thread_order(thread_id)
            
            cls._local_buffer.buffer.append(event_id, share_object_id, item_id, nano_time)

    @classmethod
    def get_object_hash(cls, obj: Any) -> int:
        return 0 if obj is None else id(obj)

    @classmethod
    def get_thread_order(cls) -> List[int]:
        with cls._key_order_lock:
            return list(cls._key_order)

    @classmethod
    def get_all_event_buffers(cls) -> List[ThreadEventBuffer]:
        with cls._buffers_lock:
            return list(cls._all_buffers)

    @classmethod
    def get_ordered_snapshot(cls) -> Dict[int, List[int]]:
        snapshot = {}
        thread_order = cls.get_thread_order()
        with cls._block_map_lock:
            for tid in thread_order:
                if tid in cls._block_map:
                    snapshot[tid] = list(cls._block_map[tid].keys())
        return snapshot

    @classmethod
    def clear(cls):
        with cls._block_map_lock:
            cls._block_map.clear()
        with cls._buffers_lock:
            cls._all_buffers.clear()
        with cls._key_order_lock:
            cls._key_order.clear()
        cls._local_buffer = threading.local()