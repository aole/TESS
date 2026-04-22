"""System information gathering service."""
import platform
import subprocess
import sys
import re
import asyncio
from typing import Optional


def _run(cmd: list[str], timeout: int = 8) -> str:
    """Run a subprocess and return stdout, or empty string on failure."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _get_os() -> str:
    system = platform.system()
    if system == "Windows":
        try:
            out = _run(["wmic", "os", "get", "Caption,Version", "/value"])
            caption = ""
            version = ""
            for line in out.splitlines():
                if line.startswith("Caption="):
                    caption = line.split("=", 1)[1].strip()
                elif line.startswith("Version="):
                    version = line.split("=", 1)[1].strip()
            if caption:
                return f"{caption} (Build {version})" if version else caption
        except Exception:
            pass
        return platform.platform()
    elif system == "Darwin":
        ver = platform.mac_ver()[0]
        return f"macOS {ver}" if ver else platform.platform()
    else:
        try:
            out = _run(["lsb_release", "-ds"])
            if out:
                return out.strip('"')
        except Exception:
            pass
        return f"Linux {platform.release()}"


def _get_ram_gb() -> str:
    system = platform.system()
    try:
        if system == "Windows":
            out = _run(["wmic", "OS", "get", "TotalVisibleMemorySize", "/value"])
            for line in out.splitlines():
                if line.startswith("TotalVisibleMemorySize="):
                    kb = int(line.split("=", 1)[1].strip())
                    gb = round(kb / (1024 ** 2))
                    return f"{gb} GB"
        elif system == "Darwin":
            out = _run(["sysctl", "-n", "hw.memsize"])
            if out:
                return f"{round(int(out) / (1024**3))} GB"
        else:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return f"{round(kb / (1024**2))} GB"
    except Exception:
        pass
    return "Unknown"


def _get_gpus() -> list[dict]:
    """Return list of dicts with 'name' and 'vram' keys."""
    gpus = []

    # --- Try nvidia-smi first ---
    nvidia_out = _run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"])
    if nvidia_out:
        for line in nvidia_out.splitlines():
            parts = line.rsplit(",", 1)
            if len(parts) == 2:
                name = parts[0].strip()
                try:
                    mb = int(parts[1].strip())
                    vram = f"{round(mb / 1024)} GB"
                except ValueError:
                    vram = parts[1].strip() + " MB"
                gpus.append({"name": name, "vram": vram})
        if gpus:
            return gpus

    # --- Windows: fall back to WMIC ---
    if platform.system() == "Windows":
        wmic_out = _run(["wmic", "path", "win32_VideoController", "get", "Name,AdapterRAM", "/format:list"])
        current: dict = {}
        for line in wmic_out.splitlines():
            if "=" in line:
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip()
                if key == "Name":
                    if current.get("name"):
                        gpus.append(current)
                    current = {"name": val, "vram": "Unknown"}
                elif key == "AdapterRAM":
                    try:
                        b = int(val)
                        if b > 0:
                            current["vram"] = f"{round(b / (1024**3))} GB"
                    except ValueError:
                        pass
        if current.get("name"):
            gpus.append(current)
        if gpus:
            return gpus

    # --- Linux: read /sys ---
    if platform.system() == "Linux":
        lspci_out = _run(["lspci"])
        for line in lspci_out.splitlines():
            if "VGA" in line or "3D" in line or "Display" in line:
                name = line.split(":", 2)[-1].strip()
                gpus.append({"name": name, "vram": "Unknown"})
        if gpus:
            return gpus

    return [{"name": "No GPU detected", "vram": ""}]


def _get_cuda_version() -> str:
    out = _run(["nvcc", "--version"])
    if out:
        m = re.search(r"release\s+([\d.]+)", out)
        if m:
            return m.group(1)
    # Try nvidia-smi
    out2 = _run(["nvidia-smi"])
    if out2:
        m = re.search(r"CUDA Version:\s*([\d.]+)", out2)
        if m:
            return m.group(1)
    return "Not found"


def _get_python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def _get_ollama_version() -> str:
    out = _run(["ollama", "--version"])
    if out:
        # e.g. "ollama version 0.6.5" or "ollama version is 0.2.7"
        parts = out.split()
        return parts[-1] if parts else out
    return "Not found"


def _get_cpu() -> str:
    system = platform.system()
    try:
        if system == "Windows":
            out = _run(["wmic", "cpu", "get", "Name", "/value"])
            for line in out.splitlines():
                if line.startswith("Name="):
                    return line.split("=", 1)[1].strip()
        elif system == "Darwin":
            out = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
            if out:
                return out
        else:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("model name"):
                        return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return platform.processor() or "Unknown"


def _get_disk_info() -> str:
    try:
        import shutil
        total, used, free = shutil.disk_usage("/")
        total_gb = round(total / (1024**3))
        free_gb = round(free / (1024**3))
        return f"{free_gb} GB free / {total_gb} GB total"
    except Exception:
        return "Unknown"


def collect_system_info() -> dict:
    """Collect all system information synchronously."""
    return {
        "os": _get_os(),
        "cpu": _get_cpu(),
        "ram": _get_ram_gb(),
        "gpus": _get_gpus(),
        "python": _get_python_version(),
        "cuda": _get_cuda_version(),
        "ollama": _get_ollama_version(),
        "disk": _get_disk_info(),
        "arch": platform.machine(),
    }
