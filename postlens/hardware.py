"""Detect this computer's memory and graphics card to decide whether Local
AI can run at a quality and speed worth offering.

Local language models run fast only when the whole model fits in fast
memory: a graphics card's own memory (VRAM) on Windows/Linux, or the unified
memory of Apple Silicon Macs. On CPU alone they are several times slower,
which is below the bar for PostLens, so CPU-only computers don't get the
Local AI option at all.
"""
from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any

import psutil

GB = 1024 ** 3
_WIN_NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW: don't flash a console on Windows


def _run(cmd: list[str], timeout: float = 6) -> str:
    try:
        kw: dict[str, Any] = {"capture_output": True, "text": True, "timeout": timeout}
        if platform.system() == "Windows":
            kw["creationflags"] = _WIN_NO_WINDOW
        return subprocess.run(cmd, **kw).stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _nvidia() -> list[dict[str, Any]]:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return []
    out = _run([exe, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"])
    gpus = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 2 and parts[1].replace(".", "").isdigit():
            gpus.append({"vendor": "NVIDIA", "name": parts[0], "vram_gb": round(float(parts[1]) / 1024, 1)})
    return gpus


def _windows_other_gpus() -> list[dict[str, Any]]:
    # Win32_VideoController.AdapterRAM is capped at 4 GB, so read the 64-bit
    # value the display driver writes to the registry instead.
    ps = (
        "Get-ItemProperty 'HKLM:\\SYSTEM\\ControlSet001\\Control\\Class\\{4d36e968-e325-11ce-bfc1-08002be10318}\\0*' "
        "-ErrorAction SilentlyContinue | Where-Object { $_.'HardwareInformation.qwMemorySize' } | "
        "ForEach-Object { @{ name = $_.DriverDesc; bytes = [int64]$_.'HardwareInformation.qwMemorySize' } } | "
        "ConvertTo-Json -Compress"
    )
    out = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], timeout=10)
    try:
        data = json.loads(out) if out.strip() else []
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    gpus = []
    for g in data:
        name = g.get("name") or ""
        vendor = "AMD" if re.search(r"AMD|Radeon", name, re.I) else "Intel" if "Intel" in name else "NVIDIA" if "NVIDIA" in name else "Other"
        if vendor == "NVIDIA":
            continue  # nvidia-smi is more accurate
        gpus.append({"vendor": vendor, "name": name, "vram_gb": round(int(g.get("bytes") or 0) / GB, 1)})
    return gpus


def _linux_amd() -> list[dict[str, Any]]:
    gpus = []
    for f in Path("/sys/class/drm").glob("card*/device/mem_info_vram_total"):
        try:
            gpus.append({"vendor": "AMD", "name": "AMD GPU", "vram_gb": round(int(f.read_text()) / GB, 1)})
        except (OSError, ValueError):
            continue
    return gpus


@lru_cache(maxsize=1)
def detect() -> dict[str, Any]:
    system = platform.system()
    machine = platform.machine().lower()
    ram_gb = round(psutil.virtual_memory().total / GB, 1)
    disk_gb = round(psutil.disk_usage(str(Path.home())).free / GB, 1)
    info: dict[str, Any] = {"os": system, "arch": machine, "ram_gb": ram_gb, "free_disk_gb": disk_gb,
                            "apple_silicon": False, "unified_gb": None, "gpus": []}
    if system == "Darwin":
        info["apple_silicon"] = machine == "arm64"
        info["cpu"] = _run(["sysctl", "-n", "machdep.cpu.brand_string"]).strip()
        if info["apple_silicon"]:
            info["unified_gb"] = ram_gb
    else:
        gpus = _nvidia()
        if system == "Windows":
            gpus += _windows_other_gpus()
        elif system == "Linux":
            gpus += _linux_amd()
        info["gpus"] = gpus
        info["cpu"] = platform.processor()
    return info


def best_vram(info: dict[str, Any]) -> float:
    """Largest VRAM among GPUs Ollama can accelerate (NVIDIA, AMD)."""
    usable = [g["vram_gb"] for g in info["gpus"] if g["vendor"] in ("NVIDIA", "AMD")]
    return max(usable, default=0.0)


def assess(info: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    """Which tier (if any) this computer qualifies for, with plain reasons."""
    mins = catalog["minimum"]
    vram = best_vram(info)
    reasons: list[str] = []
    tier = None
    for t in catalog["tiers"]:  # tiers are listed from smallest to largest
        if info["apple_silicon"]:
            fits = (info["unified_gb"] or 0) >= t["min_unified_gb"]
        else:
            fits = vram >= t["min_vram_gb"] and info["ram_gb"] >= t["min_ram_gb"]
        if fits:
            tier = t
    if tier is None:
        if info["apple_silicon"]:
            reasons.append(f"Needs a Mac with Apple Silicon and at least {mins['apple_unified_gb']} GB memory "
                           f"(this Mac has {info['ram_gb']:.0f} GB).")
        elif info["os"] == "Darwin":
            reasons.append("Intel-based Macs aren't fast enough for Local AI.")
        else:
            if vram == 0:
                reasons.append(f"Needs an NVIDIA or AMD graphics card with at least {mins['gpu_vram_gb']} GB of video memory "
                               "(none was found).")
            elif vram < mins["gpu_vram_gb"]:
                reasons.append(f"Needs at least {mins['gpu_vram_gb']} GB of video memory (found {vram:g} GB).")
            if info["ram_gb"] < mins["ram_gb"]:
                reasons.append(f"Needs at least {mins['ram_gb']} GB of RAM (found {info['ram_gb']:.0f} GB).")
    if info["free_disk_gb"] < mins["free_disk_gb"]:
        reasons.append(f"Needs {mins['free_disk_gb']} GB of free disk space (found {info['free_disk_gb']:.0f} GB).")
        tier = None
    return {"supported": tier is not None, "tier": tier, "reasons": reasons, "vram_gb": vram}
