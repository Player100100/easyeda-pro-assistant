#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EasyEDA Pro bridge 的自动连接 / 守护脚本。

解决的问题：bridge-server.mjs 一旦退出（或被会话结束带走），EasyEDA 里的
run-api-gateway 扩展**不会自己回来**——它只在启动时扫一遍 49620-49629。
所以每次都要人手动点「API Gateway → 重新连接」。

这个脚本管两件事：
  1. 桥进程用**脱离会话**的方式拉起（Windows: DETACHED_PROCESS），
     Claude Code / 终端关掉也不影响；
  2. 轮询 /health 直到 EasyEDA 真的连上，连不上给出明确的下一步。

用法（在项目根目录 `projects/epro2-辅助绘制及审核/` 下）：

    python src/eda.py up                 # 确保桥在跑，并等 EasyEDA 连上（默认 60s）
    python src/eda.py up --timeout 0     # 只保证桥在跑，不等客户端
    python src/eda.py status             # 桥端口、EDA 连接、打开的工程
    python src/eda.py wait --timeout 300 # 只等客户端连上
    python src/eda.py watch              # 常驻守护：桥挂了自动重启
    python src/eda.py exec "return await eda.dmt_Project.getCurrentProjectInfo();"
    python src/eda.py exec -f code.js --timeout 120
    python src/eda.py stop               # 停掉本脚本拉起的桥

退出码：0 成功；1 桥起不来；2 等不到客户端（超时）；3 /execute 失败。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PORT_START = int(os.environ.get("EASYEDA_PORT_START", 49620))
PORT_END = int(os.environ.get("EASYEDA_PORT_END", 49629))
SERVICE_ID = "easyeda-bridge"

# <ws>/projects/<project>/src/eda.py → parents: 0=src 1=<project> 2=projects 3=<ws>
WORKSPACE = Path(__file__).resolve().parents[3]
STATE_DIR = WORKSPACE / "outputs" / "eda"
STATE_FILE = STATE_DIR / "bridge.json"
LOG_FILE = STATE_DIR / "bridge.log"

SKILL_DIR = Path(
    os.environ.get("EASYEDA_SKILL_DIR")
    or Path.home() / ".claude" / "skills" / "easyeda-api-skill"
)
BRIDGE_JS = SKILL_DIR / "scripts" / "bridge-server.mjs"


# ── 输出 ────────────────────────────────────────────────────────────
def _safe_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def say(msg: str = "") -> None:
    print(msg, flush=True)


# ── HTTP ────────────────────────────────────────────────────────────
def _get_json(url: str, timeout: float = 1.0):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def health(port: int, timeout: float = 1.0) -> dict | None:
    try:
        data = _get_json(f"http://127.0.0.1:{port}/health", timeout)
    except Exception:
        return None
    return data if data.get("service") == SERVICE_ID else None


def scan_ports() -> int | None:
    """返回正在跑的 bridge 端口；没有就 None。"""
    for port in range(PORT_START, PORT_END + 1):
        if health(port, timeout=0.3):
            return port
    return None


def list_windows(port: int) -> dict:
    try:
        return _get_json(f"http://127.0.0.1:{port}/eda-windows", timeout=3)
    except Exception:
        return {"windows": [], "activeWindowId": None, "count": 0}


def execute(port: int, code: str, timeout: float = 60.0) -> dict:
    """执行 JS。失败的请求服务端回 HTTP 500，但 body 里仍是有用的 JSON。"""
    body = json.dumps({"code": code}).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/execute",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
    return json.loads(raw)


# ── 状态文件 ────────────────────────────────────────────────────────
def read_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_state(**kw) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state = read_state()
    state.update(kw)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


# ── 启动 / 停止 ─────────────────────────────────────────────────────
def _pid_alive(pid: int) -> bool:
    """进程是否还活着。

    注意：**Windows 上不能用 `os.kill(pid, 0)`**——CPython 会把它当成
    TerminateProcess(pid, 0)，直接把人杀了。必须走 OpenProcess。
    """
    if not pid:
        return False
    if os.name == "nt":
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            if not k32.GetExitCodeProcess(h, ctypes.byref(code)):
                return False
            return code.value == STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _kill_pid(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        os.kill(pid, 15)


def ensure_bridge(start_timeout: float = 20.0) -> int:
    """桥在跑就返回端口，否则脱离会话拉起一个。起不来抛 RuntimeError。"""
    port = scan_ports()
    if port:
        return port

    if not BRIDGE_JS.is_file():
        raise RuntimeError(f"找不到 bridge-server.mjs：{BRIDGE_JS}")
    node = shutil.which("node")
    if not node:
        raise RuntimeError("PATH 里没有 node")

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    log = open(LOG_FILE, "ab")
    log.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} 启动 bridge ---\n".encode("utf-8"))
    log.flush()

    kwargs: dict = dict(cwd=str(SKILL_DIR), stdin=subprocess.DEVNULL,
                        stdout=log, stderr=log, close_fds=True)
    if os.name == "nt":
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP：父进程退出后继续活
        kwargs["creationflags"] = 0x00000008 | 0x00000200
    else:
        kwargs["start_new_session"] = True

    proc = subprocess.Popen([node, str(BRIDGE_JS)], **kwargs)
    write_state(pid=proc.pid, log=str(LOG_FILE))

    deadline = time.time() + start_timeout
    while time.time() < deadline:
        port = scan_ports()
        if port:
            return port
        if proc.poll() is not None and proc.returncode != 0:
            tail = _tail_log(6)
            raise RuntimeError(f"bridge 启动失败（exit={proc.returncode}）\n{tail}")
        time.sleep(0.4)
    raise RuntimeError(f"{start_timeout:.0f}s 内没等到 bridge 起来，日志：{LOG_FILE}")


def _tail_log(n: int) -> str:
    try:
        lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n:])
    except Exception:
        return "(无日志)"


def _pid_on_port(port: int) -> int | None:
    """谁在监听这个端口。Windows 用 netstat，其他平台用 lsof。"""
    try:
        if os.name == "nt":
            out = subprocess.run(["netstat", "-ano", "-p", "TCP"],
                                 capture_output=True, text=True, timeout=10).stdout
            for line in out.splitlines():
                f = line.split()
                if len(f) >= 5 and f[1].endswith(f":{port}") and f[3] == "LISTENING":
                    return int(f[4])
        else:
            out = subprocess.run(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
                                 capture_output=True, text=True, timeout=10).stdout
            first = out.split()
            if first:
                return int(first[0])
    except Exception:
        pass
    return None


def stop_bridge() -> bool:
    state = read_state()
    pid = int(state.get("pid") or 0)
    port = scan_ports()
    if not port:
        say("bridge 本来就没在跑")
        return True
    if not _pid_alive(pid):
        found = _pid_on_port(port)
        if found:
            say(f"state 里的 pid 不是当前那个，改用端口 {port} 上的 pid {found}")
            pid = found
        else:
            say(f"bridge 在 {port} 上，但找不到对应进程，不动它。")
            return False
    try:
        _kill_pid(pid)
    except OSError:
        pass
    for _ in range(50):
        if not scan_ports():
            write_state(pid=None)
            say(f"bridge 已停（pid {pid}）")
            return True
        time.sleep(0.2)
    say(f"pid {pid} 似乎没退，端口 {port} 仍可访问")
    return False


# ── 等待客户端 ──────────────────────────────────────────────────────
def wait_for_eda(port: int, timeout: float) -> dict | None:
    deadline = time.time() + timeout
    last = time.time()
    dots = 0
    while time.time() < deadline:
        h = health(port, timeout=0.5)
        if h and h.get("edaConnected"):
            if dots:
                say()
            return h
        if time.time() - last >= 1.0:
            last = time.time()
            dots += 1
            print(".", end="", flush=True)
    if dots:
        say()
    return None


def print_hint() -> None:
    say()
    say("EasyEDA 客户端没连上。扩展只在启动时扫一遍端口，桥换了进程它不会自己回来：")
    say("  → EasyEDA 顶部菜单「API Gateway」→「重新连接」")
    say("  → 若菜单里没有这一项，在同一菜单里把「自动连接」开关切换一次")
    say(f"  → 仍不行就重启 EasyEDA 客户端（日志：{LOG_FILE}）")


def show_status(port: int) -> int:
    h = health(port) or {}
    wins = list_windows(port)
    say(f"bridge   : 127.0.0.1:{port}  ({h.get('status', '?')})")
    say(f"EDA 连接 : {'是' if h.get('edaConnected') else '否'}  窗口数 {h.get('edaWindowCount', 0)}")
    for w in wins.get("windows") or []:
        mark = " (active)" if w.get("windowId") == wins.get("activeWindowId") else ""
        say(f"  - {w.get('windowId')}{mark}")
    if h.get("edaConnected"):
        try:
            r = execute(port, "const p=await eda.dmt_Project.getCurrentProjectInfo();"
                              "const t=await eda.dmt_EditorControl.getSplitScreenTree();"
                              "return {project:p?p.friendlyName||p.name:null,"
                              "tabs:(t.tabs||[]).map(x=>x.title)};", timeout=15)
            res = r.get("result") or {}
            say(f"当前工程 : {res.get('project') or '（未打开工程）'}")
            if res.get("tabs"):
                say(f"打开的页 : {', '.join(res['tabs'])}")
        except Exception as e:
            say(f"当前工程 : 查询失败 {e}")
    return 0 if h.get("edaConnected") else 0


# ── 子命令 ──────────────────────────────────────────────────────────
def cmd_up(args) -> int:
    try:
        port = ensure_bridge()
    except RuntimeError as e:
        say(f"❌ {e}")
        return 1
    say(f"✅ bridge 在 {port}")
    if args.timeout <= 0:
        return 0
    say(f"等 EasyEDA 连上（最多 {args.timeout:.0f}s）", )
    h = wait_for_eda(port, args.timeout)
    if not h:
        print_hint()
        return 2
    say(f"✅ 已连上，窗口 {h.get('activeWindowId')}")
    show_status(port)
    return 0


def cmd_status(args) -> int:
    port = scan_ports()
    if not port:
        say("bridge 没在跑。`python src/eda.py up` 拉起来。")
        return 1
    return show_status(port)


def cmd_wait(args) -> int:
    port = scan_ports()
    if not port:
        say("bridge 没在跑。先 `python src/eda.py up --timeout 0`。")
        return 1
    h = wait_for_eda(port, args.timeout)
    if not h:
        print_hint()
        return 2
    say(f"✅ 已连上，窗口 {h.get('activeWindowId')}")
    return 0


def cmd_exec(args) -> int:
    code = args.code
    if args.file:
        code = Path(args.file).read_text(encoding="utf-8")
    if not code:
        say("要么给 code，要么给 -f 文件")
        return 3
    port = scan_ports()
    if not port:
        say("bridge 没在跑。先 `python src/eda.py up --timeout 0`。")
        return 1
    try:
        r = execute(port, code, timeout=args.timeout)
    except urllib.error.URLError as e:
        say(f"❌ 请求失败：{e}")
        return 3
    if not r.get("success"):
        say(f"❌ {r.get('error')}")
        return 3
    out = r.get("result")
    say(json.dumps(out, ensure_ascii=False, indent=1) if isinstance(out, (dict, list))
        else str(out))
    return 0


def cmd_watch(args) -> int:
    say("守护模式（Ctrl-C 退出）")
    was_connected = None
    was_port = None
    try:
        while True:
            port = scan_ports()
            if port is None:
                if was_port is not None:
                    say(f"[{time.strftime('%H:%M:%S')}] bridge 掉了，重启…")
                try:
                    port = ensure_bridge()
                    say(f"[{time.strftime('%H:%M:%S')}] bridge 起来了：{port}")
                except RuntimeError as e:
                    say(f"[{time.strftime('%H:%M:%S')}] 重启失败：{e}")
                    time.sleep(args.interval)
                    continue
            was_port = port
            h = health(port) or {}
            connected = bool(h.get("edaConnected"))
            if connected != was_connected:
                if connected:
                    say(f"[{time.strftime('%H:%M:%S')}] EasyEDA 已连上：{h.get('activeWindowId')}")
                elif was_connected:
                    say(f"[{time.strftime('%H:%M:%S')}] EasyEDA 断开——请在客户端点「API Gateway → 重新连接」")
                was_connected = connected
            time.sleep(args.interval)
    except KeyboardInterrupt:
        say("\n退出守护（bridge 保留运行）")
        return 0


def cmd_stop(args) -> int:
    return 0 if stop_bridge() else 1


def main(argv) -> int:
    _safe_stdout()
    p = argparse.ArgumentParser(
        prog="eda.py",
        description="EasyEDA bridge 自动连接 / 守护",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("用法")[1] if "用法" in __doc__ else None,
    )
    sub = p.add_subparsers(dest="cmd")

    a = sub.add_parser("up", help="确保桥在跑并等待 EasyEDA 连上（默认命令）")
    a.add_argument("--timeout", type=float, default=60, help="等客户端秒数，0=不等")
    a.set_defaults(func=cmd_up)

    a = sub.add_parser("status", help="显示桥端口 / 连接 / 当前工程")
    a.set_defaults(func=cmd_status)

    a = sub.add_parser("wait", help="只等 EasyEDA 连上")
    a.add_argument("--timeout", type=float, default=120)
    a.set_defaults(func=cmd_wait)

    a = sub.add_parser("exec", help="在 EasyEDA 里执行 JS")
    a.add_argument("code", nargs="?")
    a.add_argument("-f", "--file", help="从文件读 JS")
    a.add_argument("--timeout", type=float, default=60)
    a.set_defaults(func=cmd_exec)

    a = sub.add_parser("watch", help="常驻守护：桥挂了自动重启")
    a.add_argument("--interval", type=float, default=5)
    a.set_defaults(func=cmd_watch)

    a = sub.add_parser("stop", help="停掉本脚本拉起的桥")
    a.set_defaults(func=cmd_stop)

    args = p.parse_args(argv)
    if not getattr(args, "func", None):
        args = p.parse_args(["up"] + argv)     # 裸跑 = up
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
