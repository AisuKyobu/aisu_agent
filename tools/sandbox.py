import os
import shutil
import subprocess
from pathlib import Path

from config import DATA_DIR, SANDBOX_IMAGE, SANDBOX_MODE

SANDBOX_DIR = os.path.join(os.path.abspath(DATA_DIR), "sandbox")
_SANDBOX_RESOLVED = str(Path(SANDBOX_DIR).resolve())


def ensure_sandbox():
    os.makedirs(SANDBOX_DIR, exist_ok=True)
    return SANDBOX_DIR


def in_sandbox(path: str) -> bool:
    try:
        Path(path).resolve().relative_to(_SANDBOX_RESOLVED)
        return True
    except (ValueError, OSError):
        return False


def sandbox_path(path: str) -> str:
    try:
        Path(path).resolve().relative_to(_SANDBOX_RESOLVED)
        return path
    except (ValueError, OSError):
        return os.path.join(SANDBOX_DIR, os.path.basename(path))


def _docker_available() -> bool:
    try:
        result = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
        return result.returncode == 0
    except Exception:
        return False


def exec_in_docker(cmd: str, timeout: int) -> str:
    container = subprocess.run(
        ["docker", "run", "--rm", "-i",
         "--user", "1000:1000",
         "--security-opt=no-new-privileges",
         "--cap-drop=ALL",
         "--memory=512m",
         "--cpus=1",
         "-v", f"{SANDBOX_DIR}:/workspace",
         "-w", "/workspace",
         SANDBOX_IMAGE,
         "sh", "-c", cmd],
        capture_output=True, text=True, timeout=timeout,
    )
    if container.returncode != 0:
        stderr = container.stderr.strip()
        return container.stdout.strip() + (f"\n(stderr: {stderr})" if stderr else "")
    return container.stdout.strip() or "(命令执行完成，无输出)"


def exec_on_host(cmd: str, timeout: int) -> str:
    import re
    suspicious = re.findall(r'(\/(?:etc|proc|sys|dev|root|home|var|tmp|usr|opt|boot|mnt|run)\/[^\s]*)', cmd)
    if suspicious:
        raise RuntimeError(f"拒绝执行: 命令包含系统绝对路径 {suspicious[0][:60]}，请使用沙箱内相对路径")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True,
                                 cwd=SANDBOX_DIR, timeout=timeout, text=False)
        out = result.stdout.decode("utf-8", errors="replace").strip()
        err = result.stderr.decode("utf-8", errors="replace").strip()
        if result.returncode != 0:
            msg = out if out else err
            raise RuntimeError(msg or f"命令退出码: {result.returncode}")
        return out or "(命令执行完成，无输出)"
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"命令执行超时（{timeout}秒）")


def execute(cmd: str, timeout: int) -> str:
    if SANDBOX_MODE == "docker" and _docker_available():
        return exec_in_docker(cmd, timeout)
    import logging
    logging.getLogger("aisu.sandbox").warning("Docker 不可用，降级为 host 模式（有安全风险）")
    return exec_on_host(cmd, timeout)


def copy_to_sandbox(src_dir: str, dest_rel: str) -> str:
    ensure_sandbox()
    dest = os.path.join(SANDBOX_DIR, dest_rel)
    if os.path.isdir(src_dir):
        shutil.copytree(src_dir, dest, dirs_exist_ok=True)
    return dest


# ── Environment Grounding ──

def capture_env_snapshot() -> dict:
    """捕获当前沙箱环境的轻量快照（供 Verifier 对比）。"""
    import sys, subprocess as sp
    snap = {"cwd": os.getcwd(), "python": sys.version.split()[0]}
    try:
        r = sp.run(["pip", "list", "--format=json"], capture_output=True, text=True, timeout=5,
                    cwd=SANDBOX_DIR)
        if r.returncode == 0:
            import json as _json
            pkgs = _json.loads(r.stdout)
            snap["pip_hash"] = str(hash(str(sorted(p["name"] for p in pkgs))))
    except Exception:
        snap["pip_hash"] = "unavailable"
    snap["sandbox_files"] = _scan_recent_files(SANDBOX_DIR)
    return snap


def _scan_recent_files(root: str, limit: int = 20) -> list[str]:
    """扫描沙箱中最近修改的文件列表。"""
    import time as _time
    try:
        files = []
        for entry in os.scandir(root):
            try:
                st = entry.stat()
                files.append((entry.name, st.st_mtime))
            except Exception:
                continue
        files.sort(key=lambda x: x[1], reverse=True)
        return [f[0] for f in files[:limit]]
    except Exception:
        return []


def diff_env_snapshot(before: dict, after: dict) -> str:
    """对比前后快照，输出差异摘要。"""
    diffs = []
    if before.get("pip_hash") != after.get("pip_hash"):
        diffs.append("已安装包发生变化")
    bf = set(before.get("sandbox_files", []))
    af = set(after.get("sandbox_files", []))
    new_files = af - bf
    if new_files:
        diffs.append(f"新增文件: {', '.join(sorted(list(new_files))[:5])}")
    return "; ".join(diffs) if diffs else ""
