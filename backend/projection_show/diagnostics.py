"""Best-effort host telemetry, sampled off the show clock thread; unavailable means null."""

import os
import platform
import resource
import shutil
import subprocess
import time
from pathlib import Path


class HostStats:
    def __init__(self, root):
        self.root = root
        self.last_time = time.monotonic()
        self.last_cpu = time.process_time()

    def sample(self):
        now, cpu = time.monotonic(), time.process_time()
        usage = 100 * (cpu - self.last_cpu) / max(0.001, now - self.last_time)
        self.last_time, self.last_cpu = now, cpu
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        memory = peak if platform.system() == "Darwin" else peak * 1024
        measurement = "peak process RSS"
        try:
            memory = int(Path("/proc/self/statm").read_text().split()[1]) * os.sysconf(
                "SC_PAGE_SIZE"
            )
            measurement = "current process RSS"
        except (OSError, ValueError, IndexError):
            pass
        temperature = None
        try:
            temperature = int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000
        except (OSError, ValueError):
            pass
        throttling = None
        command = shutil.which("vcgencmd")
        if command:
            try:
                result = subprocess.run(
                    [command, "get_throttled"],
                    capture_output=True,
                    text=True,
                    timeout=0.5,
                    check=True,
                )
                throttling = result.stdout.strip()[:100]
            except (OSError, subprocess.SubprocessError):
                pass
        return {
            "cpu_percent": round(usage, 1),
            "memory_bytes": memory,
            "memory_measurement": measurement,
            "free_disk_bytes": shutil.disk_usage(self.root).free,
            "temperature_c": temperature,
            "throttling": throttling,
        }
