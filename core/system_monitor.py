"""Real-time system monitoring via psutil."""
import json
import subprocess
import sys

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from PyQt6.QtCore import QObject, pyqtSignal, QTimer


class SystemMonitor(QObject):
    stats_ready = pyqtSignal(str)  # emits JSON string

    def __init__(self, interval_ms: int = 2000):
        super().__init__()
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._collect)
        self._start_time = None

    def start(self):
        if HAS_PSUTIL:
            self._start_time = psutil.boot_time()
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def _collect(self):
        data = self._get_stats()
        self.stats_ready.emit(json.dumps(data))

    def get_initial(self) -> str:
        return json.dumps(self._get_stats())

    def _get_stats(self) -> dict:
        if not HAS_PSUTIL:
            return {"error": "psutil not installed"}

        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        # Network
        net_io = psutil.net_io_counters()

        # Temperatures (may not be available on all platforms)
        temps = {}
        try:
            raw = psutil.sensors_temperatures()
            if raw:
                for name, entries in raw.items():
                    if entries:
                        temps[name] = entries[0].current
        except Exception:
            pass

        # GPU — best-effort via nvidia-smi
        gpu_pct = None
        gpu_temp = None
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=1,
                creationflags=_NO_WINDOW
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split(", ")
                if len(parts) >= 2:
                    gpu_pct = int(parts[0])
                    gpu_temp = int(parts[1])
        except Exception:
            pass

        # Uptime
        import time
        uptime_secs = int(time.time() - self._start_time) if self._start_time else 0
        h, rem = divmod(uptime_secs, 3600)
        m = rem // 60
        uptime_str = f"{h}г {m}хв" if h else f"{m}хв"

        # Process count
        proc_count = len(psutil.pids())

        # Top processes
        procs = []
        for p in sorted(
            psutil.process_iter(["name", "cpu_percent", "memory_info"]),
            key=lambda x: x.info.get("cpu_percent") or 0,
            reverse=True,
        )[:8]:
            try:
                mem_mb = round((p.info["memory_info"].rss or 0) / 1024 / 1024)
                procs.append({
                    "name": p.info["name"] or "?",
                    "cpu": round(p.info.get("cpu_percent") or 0, 1),
                    "mem": f"{mem_mb} MB",
                })
            except Exception:
                pass

        # Disk info
        disks = []
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disks.append({
                    "device": part.device,
                    "mountpoint": part.mountpoint,
                    "fstype": part.fstype,
                    "total": _fmt_bytes(usage.total),
                    "free": _fmt_bytes(usage.free),
                    "percent": usage.percent,
                })
            except Exception:
                pass

        cpu_temp = temps.get("coretemp", temps.get("cpu_thermal",
                   temps.get("k10temp", None)))

        return {
            "cpu": cpu,
            "ram": mem.percent,
            "ram_used": _fmt_bytes(mem.used),
            "ram_total": _fmt_bytes(mem.total),
            "disk": disk.percent,
            "disk_free": _fmt_bytes(disk.free),
            "disk_total": _fmt_bytes(disk.total),
            "net_sent": _fmt_bytes(net_io.bytes_sent),
            "net_recv": _fmt_bytes(net_io.bytes_recv),
            "gpu": gpu_pct,
            "gpu_temp": gpu_temp,
            "cpu_temp": cpu_temp,
            "uptime": uptime_str,
            "proc_count": proc_count,
            "processes": procs,
            "disks": disks,
        }


def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"
