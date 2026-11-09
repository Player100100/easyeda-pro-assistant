#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D-02 / D-03 几何间距复算（同层、异网）。

只做三件事，够用来交叉验证 EasyEDA DRC：
  1. 走线-走线最小间距（同层、异网）；
  2. 走线-焊盘最小间距（同层、异网）；
  3. 铜（焊盘/走线）到板框的最近距离。

不做：焊盘-焊盘（形状组合多，交给 DRC）、铺铜间距、内层。
单位 mil，1 mil = 0.0254 mm。

板框不再内置：优先从输入数据的 `board_size` / `outline` 读取；输入只有
`pads/tracks/vias` 时，用 `--pcb <pcb.json>` 或 `--board X0,X1,Y0,Y1` 提供。
多板工程请用 `--board` 指定目标板；`--pcb` 取第一个有板框的 PCB。
没有板框就跳过铜到板边，不拿别的板子的坐标凑结果。
"""
from __future__ import annotations

import json
import math
import sys

from pcb_connectivity import _inside_pad, _seg_seg_dist, _seg_point_dist, pad_layers


def bbox_pad(pad):
    shape = pad.get("shape") or []
    w = shape[1] if len(shape) > 2 else 0
    h = shape[2] if len(shape) > 2 else 0
    r = math.hypot(w, h) / 2
    return pad["x"] - r, pad["x"] + r, pad["y"] - r, pad["y"] + r


def _boards(data):
    if isinstance(data, dict) and isinstance(data.get("pcbs"), list):
        return data["pcbs"]
    return [data]


def board_frame(data):
    """返回 (x0, x1, y0, y1) 或 None。优先 board_size，其次 outline 点集。"""
    for board in _boards(data):
        bs = board.get("board_size")
        if isinstance(bs, dict) and all(
                k in bs for k in ("min_x", "max_x", "min_y", "max_y")):
            return (bs["min_x"], bs["max_x"], bs["min_y"], bs["max_y"])
        pts = []
        for o in board.get("outline") or []:
            pts.extend(o.get("points") or [])
        if pts:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            return (min(xs), max(xs), min(ys), max(ys))
    return None


def parse_args(argv):
    path = argv[1]
    frame = None
    pcb_path = None
    i = 2
    while i < len(argv):
        if argv[i] == "--board":
            vals = [float(v) for v in argv[i + 1].split(",")]
            if len(vals) != 4:
                raise SystemExit("--board 需要 X0,X1,Y0,Y1")
            frame = tuple(vals)
            i += 2
        elif argv[i] == "--pcb":
            pcb_path = argv[i + 1]
            i += 2
        else:
            raise SystemExit(f"未知参数: {argv[i]}")
    if pcb_path:
        pcb_data = json.load(open(pcb_path, encoding="utf-8"))
        frame = board_frame(pcb_data) or frame
    return path, frame


def main(path: str, frame=None) -> None:
    data = json.load(open(path, encoding="utf-8"))
    pads, tracks = data["pads"], data["tracks"]
    if frame is None:
        frame = board_frame(data)

    # ---- 1. 走线-走线 ----
    worst_tt = []
    for i in range(len(tracks)):
        a = tracks[i]
        for j in range(i + 1, len(tracks)):
            b = tracks[j]
            if a["layer"] != b["layer"] or a["net"] == b["net"]:
                continue
            d = _seg_seg_dist((a["x1"], a["y1"], a["x2"], a["y2"]),
                              (b["x1"], b["y1"], b["x2"], b["y2"]))
            gap = d - (a["w"] + b["w"]) / 2
            worst_tt.append((gap, a["net"], b["net"], a["layer"],
                             (a["x1"], a["y1"]), (b["x1"], b["y1"])))
    worst_tt.sort(key=lambda x: x[0])

    # ---- 2. 走线-焊盘 ----
    worst_tp = []
    for t in tracks:
        half = t["w"] / 2
        L = math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"])
        n = max(1, int(L))
        for p in pads:
            if not p.get("net") or p["net"] == t["net"]:
                continue
            if t["layer"] not in pad_layers(p):
                continue
            best = 1e9
            for k in range(n + 1):
                f = k / n
                px = t["x1"] + (t["x2"] - t["x1"]) * f
                py = t["y1"] + (t["y2"] - t["y1"]) * f
                # 二分式近似：先看是否已进入焊盘扩张区，再退化为点到中心
                if _inside_pad(px, py, p, half):
                    best = 0.0
                    break
            if best == 0.0:
                worst_tp.append((0.0, t["net"], p["net"], t["layer"], p["x"], p["y"]))
    worst_tp.sort(key=lambda x: x[0])

    # ---- 3. 铜到板边 ----
    edge = []
    if frame is not None:
        X0, X1, Y0, Y1 = frame
        for p in pads:
            if not p.get("net"):
                continue
            x0, x1, y0, y1 = bbox_pad(p)
            edge.append((min(x0 - X0, X1 - x1, y0 - Y0, Y1 - y1), "pad", p.get("net"), p["x"], p["y"]))
        for t in tracks:
            hw = t["w"] / 2
            xs = (t["x1"], t["x2"])
            ys = (t["y1"], t["y2"])
            d = min(min(xs) - hw - X0, X1 - max(xs) - hw,
                    min(ys) - hw - Y0, Y1 - max(ys) - hw)
            edge.append((d, "track", t["net"], t["x1"], t["y1"]))
        edge.sort(key=lambda x: x[0])

    print("== 走线-走线（同层异网）最小间距 ==")
    for g in worst_tt[:5]:
        print(f"  {g[0]:6.2f} mil ({g[0]*0.0254:5.3f} mm)  net {g[1]} vs {g[2]}  layer {g[3]}  @ {g[4]} / {g[5]}")
    print("== 走线-焊盘（同层异网） ==")
    if not worst_tp:
        print("  未发现焊盘被异网走线压到（采样 1 mil）")
    else:
        for g in worst_tp[:5]:
            print(f"  重叠: net {g[1]} vs {g[2]}  layer {g[3]}  pad@({g[4]},{g[5]})")
    print("== 铜到板框最近距离 ==")
    if not edge:
        print("  跳过：输入没有 board_size/outline；用 --pcb <pcb.json> 或 --board X0,X1,Y0,Y1 提供板框")
    for g in edge[:5]:
        print(f"  {g[0]:6.2f} mil ({g[0]*0.0254:5.3f} mm)  {g[1]} net {g[2]} @ ({g[3]:.1f},{g[4]:.1f})")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("用法: pcb_clearance.py <pcb_geom.json> [--pcb <pcb.json>] [--board X0,X1,Y0,Y1]")
    main(*parse_args(sys.argv))
