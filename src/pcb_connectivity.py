#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D-04 布线连通性复算（layer-aware）。

输入：API 导出的 pcb_geom.json（焊盘/走线/过孔几何，单位 mil）。
做法：
  1. 把焊盘、走线段、过孔建成节点；
  2. 同层几何相交即连边（焊盘/过孔/走线之间）；过孔贯通 1/2 层，通孔焊盘（layer=12）在两层都参与；
  3. 按网做并查集，看每个网的焊盘是否落在同一连通分量。

限制（报告里要写清楚）：
  - **不把铺铜算进连通**。GND / +5V / -5V 主要靠铺铜连，这类网的分裂只能算「疑似」，要人工看。
  - RECT/OVAL 使用局部形状；ELLIPSE 的扩张距离是近似，未知形状使用外接圆。
  - 走线按约 1 mil 采样；容差 0.5 mil。通孔仅按 Top/Bottom，缺少 pad-pad/via-via 等接触。
  - 异网接触单独给网对候选，尚无具体接触对象定位或 net-tie 例外处理。
  - 返回 (splits, net_pads, shorts)；CLI 是诊断输出，退出码 0 不表示设计通过。
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict


# ---------- 几何 ----------

def _to_pad_frame(px, py, pad):
    """把点转到焊盘局部坐标（焊盘框内，未旋转）。"""
    ang = -pad.get("rot", 0.0) or 0.0
    dx, dy = px - pad["x"], py - pad["y"]
    ca, sa = math.cos(ang), math.sin(ang)
    return dx * ca - dy * sa, dx * sa + dy * ca


def _inside_pad(px, py, pad, expand):
    """点到焊盘形状的距离 <= expand（Minkowski 扩张）。"""
    lx, ly = _to_pad_frame(px, py, pad)
    shape = pad.get("shape") or []
    kind = shape[0] if shape else "RECT"

    if kind == "RECT":
        w, h = shape[1], shape[2]
        dx, dy = max(abs(lx) - w / 2, 0.0), max(abs(ly) - h / 2, 0.0)
        return math.hypot(dx, dy) <= expand

    if kind == "OVAL":
        w, h = shape[1], shape[2]
        if w >= h:                      # 长轴在 x，两端半圆半径 h/2
            r = h / 2
            dx = max(abs(lx) - (w / 2 - r), 0.0)
            return math.hypot(dx, ly) <= r + expand
        r = w / 2
        dy = max(abs(ly) - (h / 2 - r), 0.0)
        return math.hypot(lx, dy) <= r + expand

    if kind == "ELLIPSE":
        rx, ry = shape[1] / 2, shape[2] / 2
        val = math.hypot(lx / rx, ly / ry)
        approx_dist = (val - 1.0) * min(rx, ry)
        return approx_dist <= expand

    # 未知形状：按外接圆，宽松判定（会掩盖部分开路，报告里注明）
    w = shape[1] if len(shape) > 2 else 0
    h = shape[2] if len(shape) > 2 else 0
    return math.hypot(lx, ly) <= math.hypot(w, h) / 2 + expand


def _seg_point_dist(px, py, x1, y1, x2, y2):
    vx, vy = x2 - x1, y2 - y1
    L2 = vx * vx + vy * vy
    if L2 == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * vx + (py - y1) * vy) / L2))
    return math.hypot(px - (x1 + t * vx), py - (y1 + t * vy))


def _seg_seg_dist(a, b):
    """线段-线段最短距离。"""
    x1, y1, x2, y2 = a
    x3, y3, x4, y4 = b

    def cross(ox, oy, ax, ay, bx, by):
        return (ax - ox) * (by - oy) - (ay - oy) * (bx - ox)

    d1 = cross(x3, y3, x4, y4, x1, y1)
    d2 = cross(x3, y3, x4, y4, x2, y2)
    d3 = cross(x1, y1, x2, y2, x3, y3)
    d4 = cross(x1, y1, x2, y2, x4, y4)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return 0.0
    return min(
        _seg_point_dist(x1, y1, x3, y3, x4, y4),
        _seg_point_dist(x2, y2, x3, y3, x4, y4),
        _seg_point_dist(x3, y3, x1, y1, x2, y2),
        _seg_point_dist(x4, y4, x1, y1, x2, y2),
    )


# ---------- 并查集 ----------
class DSU:
    def __init__(self):
        self.p = {}

    def add(self, a):
        self.p.setdefault(a, a)

    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def pad_layers(pad):
    """焊盘参与连接的铜层。layer=12 是通孔（多层）。"""
    if pad["layer"] == 12:
        return (1, 2)
    return (pad["layer"],)


def main(path: str):
    data = json.load(open(path, encoding="utf-8"))
    pads, tracks, vias = data["pads"], data["tracks"], data["vias"]
    TOL = 0.5
    dsu = DSU()
    shorts = set()

    def connect(kind_a, index_a, kind_b, index_b):
        a = {"P": pads, "T": tracks, "V": vias}[kind_a][index_a]
        b = {"P": pads, "T": tracks, "V": vias}[kind_b][index_b]
        na, nb = a.get("net"), b.get("net")
        if not na or not nb:
            return
        if na != nb:
            shorts.add(tuple(sorted((na, nb))))
            return
        dsu.union((kind_a, index_a), (kind_b, index_b))

    for i, _ in enumerate(pads):
        dsu.add(("P", i))
    for i, _ in enumerate(tracks):
        dsu.add(("T", i))
    for i, _ in enumerate(vias):
        dsu.add(("V", i))

    # 走线-走线（同层）
    by_layer = defaultdict(list)
    for i, t in enumerate(tracks):
        by_layer[t["layer"]].append(i)
    for layer, idxs in by_layer.items():
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                ia, ib = idxs[a], idxs[b]
                ta, tb = tracks[ia], tracks[ib]
                # 包围盒剪枝
                if (min(ta["x1"], ta["x2"]) > max(tb["x1"], tb["x2"]) + 20 or
                        min(tb["x1"], tb["x2"]) > max(ta["x1"], ta["x2"]) + 20 or
                        min(ta["y1"], ta["y2"]) > max(tb["y1"], tb["y2"]) + 20 or
                        min(tb["y1"], tb["y2"]) > max(ta["y1"], ta["y2"]) + 20):
                    continue
                d = _seg_seg_dist((ta["x1"], ta["y1"], ta["x2"], ta["y2"]),
                                  (tb["x1"], tb["y1"], tb["x2"], tb["y2"]))
                if d <= (ta["w"] + tb["w"]) / 2 + TOL:
                    connect("T", ia, "T", ib)

    # 走线-焊盘
    for i, t in enumerate(tracks):
        half = t["w"] / 2
        step = 1.0
        L = math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"])
        n = max(1, int(L / step))
        for pi, p in enumerate(pads):
            if t["layer"] not in pad_layers(p):
                continue
            if not p.get("net"):
                continue
            if abs(p["x"] - t["x1"]) > 200 and abs(p["x"] - t["x2"]) > 200:
                continue
            hit = False
            for k in range(n + 1):
                f = k / n
                px = t["x1"] + (t["x2"] - t["x1"]) * f
                py = t["y1"] + (t["y2"] - t["y1"]) * f
                if _inside_pad(px, py, p, half + TOL):
                    hit = True
                    break
            if hit:
                connect("T", i, "P", pi)

    # 走线-过孔
    for i, v in enumerate(vias):
        for ti, t in enumerate(tracks):
            if t["layer"] not in (1, 2):
                continue
            d = _seg_point_dist(v["x"], v["y"], t["x1"], t["y1"], t["x2"], t["y2"])
            if d <= t["w"] / 2 + v["d"] / 2 + TOL:
                connect("T", ti, "V", i)

    # 焊盘-过孔
    for pi, p in enumerate(pads):
        if not p.get("net"):
            continue
        for vi, v in enumerate(vias):
            if abs(p["x"] - v["x"]) > 60 or abs(p["y"] - v["y"]) > 60:
                continue
            if _inside_pad(v["x"], v["y"], p, v["d"] / 2 + TOL):
                connect("P", pi, "V", vi)

    # 按网汇总
    net_pads = defaultdict(list)
    for i, p in enumerate(pads):
        if p.get("net"):
            net_pads[p["net"]].append(i)

    splits = {}
    for net, idxs in net_pads.items():
        roots = defaultdict(list)
        for i in idxs:
            roots[dsu.find(("P", i))].append(i)
        if len(roots) > 1:
            splits[net] = sorted(roots.values(), key=len, reverse=True)

    return splits, net_pads, sorted(shorts)


if __name__ == "__main__":
    path = sys.argv[1]
    splits, net_pads, shorts = main(path)
    print(f"nets with pads: {len(net_pads)}; pads: {sum(len(v) for v in net_pads.values())}")
    if not splits:
        print("已建模同网子图未发现分裂；未计铺铜/完整层跨越，不能作为整板通过结论")
    else:
        for net, groups in sorted(splits.items(), key=lambda kv: -len(kv[1])):
            names = [
                "+".join(f"{f'P'}{i}" for i in g) for g in groups
            ]
            print(f"{net}: {len(groups)} 个分量 -> {groups}")
    if shorts:
        print("潜在异网短路（几何候选）:")
        for a, b in shorts:
            print(f"  {a} <> {b}")
    sys.exit(0)
