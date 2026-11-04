"""Small dependency-free terminal UI; progress counts completed stages, not time."""
import contextlib
import os
import subprocess
import sys
import threading
import time
from pathlib import Path


class Progress:
    def __init__(self, total=1, plain=False, stream=None):
        self.total = total
        self.done = 0
        self.stream = stream or sys.stderr
        self.animated = not plain and self.stream.isatty() and os.environ.get('TERM') != 'dumb'
        self.color = self.animated and 'NO_COLOR' not in os.environ

    def banner(self):
        title = '  ≋  WinTide  ·  Windows apps. Linux flow.'
        self.stream.write(('\033[1;36m' + title + '\033[0m' if self.color else title) + '\n\n')
        self.stream.flush()

    def line(self, label, symbol):
        width = 20
        filled = width * self.done // max(self.total, 1)
        bar = '━' * filled + '─' * (width - filled)
        return f'{symbol} [{bar}] {self.done}/{self.total}  {label}'

    @contextlib.contextmanager
    def step(self, label, animate=True):
        stop = threading.Event()
        worker = None
        start = time.monotonic()
        def spin():
            frames = '⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
            i = 0
            while not stop.is_set():
                text = self.line(label, frames[i % len(frames)])
                self.stream.write('\r\033[2K' + text + f'  {int(time.monotonic()-start)}s')
                self.stream.flush()
                i += 1
                stop.wait(0.1)
        if self.animated and animate:
            worker = threading.Thread(target=spin, daemon=True)
            worker.start()
        else:
            print(self.line(label, '…'), file=self.stream, flush=True)
        success = False
        try:
            yield
            success = True
        finally:
            stop.set()
            if worker:
                worker.join()
                self.stream.write('\r\033[2K')
            if success:
                self.done += 1
            print(self.line(label, '✓' if success else '✗'), file=self.stream, flush=True)


def logged_run(command, log_path, env=None):
    """Keep build output inspectable without filling the animated terminal."""
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, env=env)
    if result.returncode:
        raise RuntimeError(f'Step failed (exit {result.returncode}). Details: {path}')
