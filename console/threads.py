import threading
import ctypes


class Thread(threading.Thread):
    def get_id(self):
        for id, thread in threading._active.items():
            if thread is self:
                return id

    def raise_exception(self):
        thread_id = self.get_id()
        if thread_id is not None:
            res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
                ctypes.c_long(thread_id), ctypes.py_object(SystemExit))
            if res == 0:
                print("Exception raise failure")
        else:
            print("No thread")


class ThreadContainer:
    def __init__(self):
        self._threads = {}
        self._closed = False
        self._lock = threading.Lock()

    def run(self, target, args=(), kwargs=None):
        def wrapper():
            ident = threading.get_ident()
            with self._lock:
                if self._closed:
                    return
                self._threads[ident] = thread
            try:
                target(*args, **(kwargs or {}))
            finally:
                with self._lock:
                    self._threads.pop(ident, None)
        thread = Thread(target=wrapper, daemon=True)
        thread.start()
        return thread

    def close(self):
        if self._closed:
            return
        with self._lock:
            for thread in self._threads.values():
                thread.raise_exception()
            self._closed = True
