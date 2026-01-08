import time
import threading
import traceback

from .logger import ProcessLogger

class CustomThread(ProcessLogger):
    def __init__(self, name, task, interval, join_timeout=2.0, pause_event=None, loop=True, daemon=True):
        self.name = f"{name}_{self.__class__.__name__}"
        super().__init__(self.name)

        self.interval = max(0.001, interval)
        self.join_timeout = join_timeout

        self.task = task
        self.daemon = daemon

        self.running = False
        self.thread = None
        self.pause_event = pause_event
        self.loop = loop
        self._check_pause_loop_conflict()

    def start(self):
        if not self.task:
            self.log_error(f"Cannot start thread: task not provided")
            raise ValueError(f"Cannot start thread: task not provided")

        if self.running:
            self.log_warning(f"Thread already running")
            return

        self.running = True
        self.thread = threading.Thread(target=self._worker, daemon=self.daemon, name=self.name)
        self.thread.start()
        self.log_info(f"Thread started")
        
    def stop(self):
        self.log_info(f"Stopping thread")
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=self.join_timeout) 
            self.log_info(f"Thread stopped")
    
    def _worker(self):
        self.log_info(f"Worker thread started")
        while self.running:
            try:
                if self.pause_event is not None:
                    self.pause_event.wait()

                self.task()

                if not self.loop:
                    self.running = False
                else:
                    time.sleep(self.interval)

            except Exception as e:
                self.log_error(f"Error in worker: {traceback.format_exc()}")
        self.log_info(f"Worker thread stopped")

    def _check_pause_loop_conflict(self):
        """Warns if loop=False but pause_event is set"""
        if not self.loop and self.pause_event:
            self.log_warning(
                "loop=False but pause_event is set; thread may block unexpectedly"
            )


def delayed_call(func, delay, args=None, kwargs=None):
    if args is None:
        args = ()
    if kwargs is None:
        kwargs = {}

    timer = threading.Timer(delay, func, args=args, kwargs=kwargs)
    timer.daemon = True
    timer.start()