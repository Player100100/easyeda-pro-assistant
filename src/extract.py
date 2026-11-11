#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 .epro2 提取原理图与 PCB 的结构化信息。

用法：
    python extract.py <工程.epro2> [--out 目录] [--with-poured]

产物（默认写到 <项目同级>/<项目目录名>-data/outputs/extract/<工程名>/）：
    index.json       文档索引、层级、工程元数据
    schematic.json   原理图页：元件、引脚（绝对坐标）、导线、网络标志、文字
    pcb.json         PCB：层表、叠层、元件、焊盘（绝对坐标）、走线、过孔、铺铜、板框、规则
    netlist.json     原理图/PCB 网表与逐引脚对比
    summary.txt      人读摘要（含对不上的项）

格式依据见 docs/epro2-v3-format.md。几个容易踩的点：
  · 原理图没有现成网表，连接靠几何重建（引脚坐标 ↔ 导线端点/线段）。
  · PCB 网名以 PAD_NET 为准；独立焊盘读 PAD.payload.netName。
  · 坐标变换：镜像先做 x→-x，再按顺时针旋转（记录坐标系）。
    SCH 用 rotation/isMirror；PCB 用 angle，且 layerId==2（底层）默认镜像。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.dont_write_bytecode = True
import epru_reader as R  # noqa: E402
from output_paths import external_path, generated_path, safe_name  # noqa: E402

EPS = 0.02          # 坐标合并容差（记录单位）
ROUND = 3


# ---------------------------------------------------------------- 基础工具

def meta_of(doc) -> dict:
    for rec in doc.records:
        if rec.type == "META" and isinstance(rec.payload, dict):
            return rec.payload
    return {}


def attrs_by_parent(doc) -> dict[str, dict]:
    out: dict[str, dict] = defaultdict(dict)
    for rec in doc.records:
        if rec.type == "ATTR" and isinstance(rec.payload, dict):
            pid = rec.payload.get("parentId")
            if pid:
                out[pid][rec.payload.get("key")] = rec.payload.get("value")
    return out


def transform(x, y, cx, cy, angle, mirror=False, mirror_mode="local"):
    """把符号/封装局部坐标转到文档坐标。

    旋转（顺时针，y 轴向下的文档坐标）：
        X = cx + x·cosθ + y·sinθ
        Y = cy − x·sinθ + y·cosθ

    镜像有两种实测语义，按文档类型区分：

    · ``mirror_mode="doc"``（原理图）：先旋转，再按文档竖直轴翻转 ——
      ``X = cx − (x·cosθ + y·sinθ)``，Y 不变。
      依据：Candis 用此式后 901 个引脚与 EasyEDA 自己导出的网表 0 冲突
      （用 local 式有 8 个，集中在 Q5/C61/C102/C120）。
    · ``mirror_mode="local"``（PCB）：先把局部 x 取反再旋转 ——
      ``x = −x``。依据：底元件焊盘落在同网走线上的比例
      Candis 146/280 vs 28/280，关灯神器 34/101 vs 4/101。
    """
    x = float(x or 0)
    y = float(y or 0)
    t = math.radians(float(angle or 0))
    c, s = math.cos(t), math.sin(t)
    if mirror and mirror_mode == "doc":
        return round(cx - (x * c + y * s), ROUND), round(cy - x * s + y * c, ROUND)
    if mirror:
        x = -x
    return round(cx + x * c + y * s, ROUND), round(cy - x * s + y * c, ROUND)


def pad_size(pad: dict):
    d = pad.get("defaultPad") or {}
    return d.get("width"), d.get("height"), d.get("padType"), d.get("radius")


def parse_id(raw):
    """复合 id 是 JSON 数组的字符串；普通 id 原样返回。"""
    if isinstance(raw, str) and raw.startswith("["):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    return raw


def _rect_points(x, y, w, h, rot=0):
    """R 命令的四角。约定 (x, y) 是一个角点，rot=0 时板框为 x..x+w、y-h..y。

    rot≠0 时按锚点 (x, y) 旋转（语义未经原生读数校核，仅作保守外接）。
    """
    corners = [(0.0, 0.0), (w, 0.0), (w, -h), (0.0, -h)]
    if rot:
        import math
        a = math.radians(rot)
        ca, sa = math.cos(a), math.sin(a)
        corners = [(cx * ca - cy * sa, cx * sa + cy * ca) for cx, cy in corners]
    return [(x + cx, y + cy) for cx, cy in corners]


def num_pairs(path):
    """解析 POLY 的 path 数组，返回顶点/角点。

    path 里命令与坐标交错：`R` 后跟 6 个数（x,y,w,h,rot,round），
    `L` 后跟 2 个数（端点），`ARC` 后跟 3 个数（角度,x,y），
    以及不带命令的裸坐标对（隐式直线）。
    不能简单忽略命令串再两两配对——ARC 的角度会被当成 x 坐标。
    """
    path = path or []
    pts = []
    i, n = 0, len(path)
    while i < n:
        tok = path[i]
        if tok == "R":
            x, y, w, h = path[i + 1], path[i + 2], path[i + 3], path[i + 4]
            rot = path[i + 5] if i + 5 < n and isinstance(path[i + 5], (int, float)) else 0
            pts.extend(_rect_points(x, y, w, h, rot))
            i += 7  # R + x,y,w,h,rot,round
        elif tok == "ARC":
            pts.append((path[i + 2], path[i + 3]))
            i += 4  # ARC + angle,x,y
        elif tok == "L":
            pts.append((path[i + 1], path[i + 2]))
            i += 3  # L + x,y
        elif isinstance(tok, (int, float)) and i + 1 < n \
                and isinstance(path[i + 1], (int, float)):
            pts.append((tok, path[i + 1]))
            i += 2
        else:
            i += 1
    return pts


class DSU:
    def __init__(self):
        self.p = {}

    def add(self, a):
        self.p.setdefault(a, a)
        return a

    def find(self, a):
        self.p.setdefault(a, a)
        root = a
        while self.p[root] != root:
            root = self.p[root]
        while self.p[a] != root:
            self.p[a], a = root, self.p[a]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra
        return self.find(ra)


def on_segment(pt, seg, eps=EPS):
    x, y = pt
    x1, y1, x2, y2 = seg
    if abs(x1 - x2) <= eps and abs(x - x1) <= eps:
        return min(y1, y2) - eps <= y <= max(y1, y2) + eps
    if abs(y1 - y2) <= eps and abs(y - y1) <= eps:
        return min(x1, x2) - eps <= x <= max(x1, x2) + eps
    return False


# ---------------------------------------------------------------- 库文档

def build_symbol(doc) -> dict:
    attrs = attrs_by_parent(doc)
    meta = meta_of(doc)
    parts = []
    pins = []
    for rec in doc.records:
        if rec.type == "PART" and isinstance(rec.payload, dict):
            parts.append({
                "id": rec.id,
                "title": rec.payload.get("title"),
                "bbox": rec.payload.get("BBOX"),
            })
        elif rec.type == "PIN" and isinstance(rec.payload, dict):
            p = rec.payload
            a = attrs.get(rec.id, {})
            pins.append({
                "id": rec.id,
                "part_id": p.get("partId"),
                "x": p.get("x"),
                "y": p.get("y"),
                "length": p.get("length"),
                "rotation": p.get("rotation"),
                "shape": p.get("pinShape"),
                "number": a.get("Pin Number"),
                "name": a.get("Pin Name"),
                "type": a.get("Pin Type"),
            })
    return {
        "uuid": doc.uuid,
        "title": meta.get("title"),
        "doc_type": meta.get("docType"),
        "parts": parts,
        "pins": pins,
    }


def build_footprint(doc) -> dict:
    meta = meta_of(doc)
    pads = []
    for rec in doc.records:
        if rec.type != "PAD" or not isinstance(rec.payload, dict):
            continue
        p = rec.payload
        w, h, ptype, radius = pad_size(p)
        pads.append({
            "id": rec.id,
            "num": p.get("num"),
            "x": p.get("centerX"),
            "y": p.get("centerY"),
            "angle": p.get("padAngle"),
            "layer": p.get("layerId"),
            "shape": ptype,
            "width": w,
            "height": h,
            "radius": radius,
            "hole": p.get("hole"),
            "plated": p.get("plated"),
            "pad_type": p.get("padType"),
        })
    return {
        "uuid": doc.uuid,
        "title": meta.get("title"),
        "pads": pads,
    }


def build_device(doc) -> dict:
    meta = meta_of(doc)
    attrs = meta.get("attributes") or {}
    return {
        "uuid": doc.uuid,
        "title": meta.get("title"),
        "tags": meta.get("tags") or [],
        "symbol": attrs.get("Symbol"),
        "footprint": attrs.get("Footprint"),
        "global_net": attrs.get("Global Net Name"),
        "attributes": attrs,
    }


def build_library(docs):
    symbols, footprints, devices = {}, {}, {}
    for doc in docs:
        if doc.doc_type == "SYMBOL":
            symbols[doc.uuid] = build_symbol(doc)
        elif doc.doc_type == "FOOTPRINT":
            footprints[doc.uuid] = build_footprint(doc)
        elif doc.doc_type == "DEVICE":
            devices[doc.uuid] = build_device(doc)
    return symbols, footprints, devices


# ---------------------------------------------------------------- 原理图

def chain_points(segments):
    """把同一 WIRE 的线段尽量串成折线；有分叉时返回多条。"""
    edges = []
    for s in segments:
        a, b = (s["startX"], s["startY"]), (s["endX"], s["endY"])
        if a == b:
            continue
        edges.append((a, b))
    if not edges:
        return []
    polys = []
    used = [False] * len(edges)
    # 以只出现一次的端点为起点；没有则任意
    degree = defaultdict(int)
    for a, b in edges:
        degree[a] += 1
        degree[b] += 1
    starts = [p for p, d in degree.items() if d == 1] or [edges[0][0]]
    for start in starts:
        if all(used):
            break
        poly = [start]
        cur = start
        while True:
            nxt = None
            for i, (a, b) in enumerate(edges):
                if used[i]:
                    continue
                if a == cur:
                    nxt = (i, b)
                    break
                if b == cur:
                    nxt = (i, a)
                    break
            if nxt is None:
                break
            used[nxt[0]] = True
            cur = nxt[1]
            poly.append(cur)
        if len(poly) > 1:
            polys.append(poly)
    # 剩余闭环
    for i, (a, b) in enumerate(edges):
        if not used[i]:
            polys.append([a, b])
    return polys


def extract_page(doc, symbols: dict, devices: dict) -> dict:
    attrs = attrs_by_parent(doc)
    meta = meta_of(doc)
    components = []
    for rec in doc.records:
        if rec.type != "COMPONENT" or not isinstance(rec.payload, dict):
            continue
        c = rec.payload
        a = attrs.get(rec.id, {})
        dev = devices.get(a.get("Device")) or {}
        # 实例属性可能缺省，回落到 DEVICE 的绑定（螺丝、网络标志常见）
        sym_id = a.get("Symbol") or dev.get("symbol")
        fp_id = a.get("Footprint") or dev.get("footprint") or None
        global_net = a.get("Global Net Name") or dev.get("global_net")
        sym = symbols.get(sym_id)
        pins = []
        if sym:
            for pin in sym["pins"]:
                X, Y = transform(pin["x"], pin["y"], c.get("x", 0), c.get("y", 0),
                                 c.get("rotation"), bool(c.get("isMirror")), "doc")
                pins.append({
                    "number": pin["number"],
                    "name": pin["name"],
                    "type": pin["type"],
                    "x": X,
                    "y": Y,
                    "local_x": pin["x"],
                    "local_y": pin["y"],
                })
        components.append({
            "id": rec.id,
            "designator": a.get("Designator"),
            "name": a.get("Name"),
            "value": a.get("Value"),
            "symbol": sym_id,
            "device": a.get("Device"),
            "footprint": fp_id,
            "x": c.get("x"),
            "y": c.get("y"),
            "rotation": c.get("rotation"),
            "mirror": bool(c.get("isMirror")),
            "global_net": global_net,
            "is_net_flag": bool(global_net),
            "device_title": dev.get("title"),
            "device_tags": dev.get("tags") or [],
            "attrs": dict(a),
            "pins": pins,
        })

    groups: dict[str, list] = defaultdict(list)
    for rec in doc.records:
        if rec.type == "LINE" and isinstance(rec.payload, dict) and rec.payload.get("lineGroup"):
            groups[rec.payload["lineGroup"]].append(rec.payload)

    wires = []
    for wid, segs in groups.items():
        segs_sorted = sorted(segs, key=lambda s: (s.get("startX", 0), s.get("startY", 0)))
        wires.append({
            "id": wid,
            "net": attrs.get(wid, {}).get("NET") or None,
            "polylines": [[list(p) for p in poly] for poly in chain_points(segs_sorted)],
            "segments": [[s.get("startX"), s.get("startY"), s.get("endX"), s.get("endY")]
                         for s in segs_sorted],
        })

    texts = [{"id": r.id, "payload": r.payload} for r in doc.records
             if r.type == "TEXT" and isinstance(r.payload, dict)]
    rects = [{"id": r.id, "payload": r.payload} for r in doc.records
             if r.type == "RECT" and isinstance(r.payload, dict)]
    images = [{"id": r.id, "payload": r.payload} for r in doc.records
              if r.type == "OBJ" and isinstance(r.payload, dict)]

    # 标题栏属性常常没有 parentId，直接从原始 ATTR 里取
    paper = None
    raw_attrs = [r.payload for r in doc.records
                 if r.type == "ATTR" and isinstance(r.payload, dict)]
    width = next((a.get("value") for a in raw_attrs if a.get("key") == "Width"), None)
    height = next((a.get("value") for a in raw_attrs if a.get("key") == "Height"), None)
    if width or height:
        paper = {"width": width, "height": height, "unit": "0.01in"}

    return {
        "uuid": doc.uuid,
        "title": meta.get("title"),
        "schematic": meta.get("schematic"),
        "paper": paper,
        "components": components,
        "wires": wires,
        "texts": texts,
        "rects": rects,
        "images": images,
    }


def build_schematic_nets(pages, cross_page: bool, cross_layer: bool,
                         t_junctions: bool = False):
    """按几何重建原理图网络。

    返回 (pin_rows, nets, warnings)。
    pin_rows: 每个元件引脚一行，net 为最终网名或 None。
    """
    dsu = DSU()
    node_of = {}
    pin_rows = []
    warnings = []

    page_wire_nodes = {}
    page_pin_nodes = {}

    for page in pages:
        puuid = page["uuid"]
        # 导线节点
        wire_nodes = {}
        for w in page["wires"]:
            node = ("w", puuid, w["id"])
            dsu.add(node)
            wire_nodes[w["id"]] = node
        page_wire_nodes[puuid] = wire_nodes

        # 同一导线内的线段天然连通，不必并
        # 端点相同 → 连通
        ptmap = defaultdict(set)
        segs = []
        for w in page["wires"]:
            node = wire_nodes[w["id"]]
            for x1, y1, x2, y2 in w["segments"]:
                segs.append((w["id"], (x1, y1, x2, y2)))
                ptmap[(round(x1, ROUND), round(y1, ROUND))].add(node)
                ptmap[(round(x2, ROUND), round(y2, ROUND))].add(node)
        for nodes in ptmap.values():
            nodes = list(nodes)
            for n in nodes[1:]:
                dsu.union(nodes[0], n)

        # T 形连接：一条线的端点落在另一条线内部。
        # 注意：EasyEDA 的 PCB 网表并不把这种情况连起来（见 Candis 样本的
        # GND 标志落在 TG28_DCDC1 线上但 PCB 未短接），默认关闭。
        if t_junctions:
            for (px, py), nodes in ptmap.items():
                for wid, seg in segs:
                    if seg[0] == px and seg[1] == py or seg[2] == px and seg[3] == py:
                        continue
                    if on_segment((px, py), seg):
                        dsu.union(next(iter(nodes)), wire_nodes[wid])

        # 引脚节点
        pin_nodes = []
        for comp in page["components"]:
            for idx, pin in enumerate(comp["pins"]):
                node = ("p", puuid, comp["id"], idx)
                dsu.add(node)
                pin_nodes.append((node, comp, pin, (pin["x"], pin["y"])))
        page_pin_nodes[puuid] = [n for n, *_ in pin_nodes]

        # 引脚 → 导线
        for node, comp, pin, pt in pin_nodes:
            hit = set()
            key = (round(pt[0], ROUND), round(pt[1], ROUND))
            hit |= ptmap.get(key, set())
            if not hit:
                for wid, seg in segs:
                    if on_segment(pt, seg):
                        hit.add(wire_nodes[wid])
            for wn in hit:
                dsu.union(node, wn)
            if not hit:
                warnings.append(
                    f"引脚未落在导线上：{page['title'] or puuid} "
                    f"{comp.get('designator') or '(无位号)'} pin {pin['number']} @ {pt}"
                )

        # 引脚重合 → 直连
        by_pt = defaultdict(list)
        for node, comp, pin, pt in pin_nodes:
            by_pt[(round(pt[0], ROUND), round(pt[1], ROUND))].append(node)
        for nodes in by_pt.values():
            for n in nodes[1:]:
                dsu.union(nodes[0], n)

        # 「短接标识」是网络短接符号：两个引脚在电气上就是同一个网。
        # guandeng 样本里它把 GND 和 AGND 连成一个网，PCB 侧也正是一个网。
        ties = defaultdict(list)
        for node, comp, pin, pt in pin_nodes:
            if "短接标识" in (comp.get("device_tags") or []):
                ties[comp["id"]].append(node)

        # 合并之前先记下短接符号每一侧原本的网名，供报告使用
        local = defaultdict(set)
        for w in page["wires"]:
            if w.get("net"):
                local[dsu.find(wire_nodes[w["id"]])].add(w["net"])
        for comp in page["components"]:
            if comp.get("global_net"):
                local[dsu.find(("p", puuid, comp["id"], 0))].add(comp["global_net"])
        page["tie_labels"] = {
            cid: [sorted(local.get(dsu.find(n), [])) for n in nodes]
            for cid, nodes in ties.items()
        }

        for nodes in ties.values():
            for n in nodes[1:]:
                dsu.union(nodes[0], n)

        # 记录引脚行
        for node, comp, pin, pt in pin_nodes:
            pin_rows.append({
                "page": puuid,
                "page_title": page["title"],
                "component_id": comp["id"],
                "designator": comp.get("designator"),
                "pin": pin["number"],
                "pin_name": pin["name"],
                "pin_type": pin["type"],
                "x": pt[0],
                "y": pt[1],
                "is_net_flag": comp.get("is_net_flag", False),
                "node": node,
            })

    # 网络名来源
    wire_names = []   # (node, name, is_global)
    for page in pages:
        puuid = page["uuid"]
        for w in page["wires"]:
            if w.get("net"):
                wire_names.append((page_wire_nodes[puuid][w["id"]], w["net"], False))
        for comp in page["components"]:
            if comp.get("global_net"):
                node = ("p", puuid, comp["id"], 0)
                wire_names.append((node, comp["global_net"], True))

    # 同名合并
    by_name = defaultdict(list)
    for node, name, is_global in wire_names:
        by_name[name].append((node, is_global))
    for name, items in by_name.items():
        glob = any(g for _, g in items)
        if glob or cross_page:
            roots = [dsu.find(n) for n, _ in items]
            for r in roots[1:]:
                dsu.union(roots[0], r)

    # 根 → 别名
    root_names = defaultdict(set)
    root_flag_names = defaultdict(set)
    root_global = defaultdict(bool)
    for node, name, is_global in wire_names:
        root = dsu.find(node)
        root_names[root].add(name)
        root_global[root] = root_global[root] or is_global
        if is_global:
            root_flag_names[root].add(name)

    def canonical(root) -> str | None:
        """网名优先级：网络标志（Global Net Name）> 导线标签 > 自动编号。

        EasyEDA 自己导出的网表也按这个优先级取名（Candis：GND 标志压过
        CAM_AF_GND 标签；VCC_3V3_MAIN 标志压过 TG28_DCDC1 标签）。
        """
        flags = root_flag_names.get(root) or set()
        if flags:
            return sorted(flags)[0]
        names = root_names.get(root) or set()
        return sorted(names)[0] if names else None

    # 引脚 → 网
    for row in pin_rows:
        root = dsu.find(row["node"])
        aliases = sorted(root_names.get(root, set()))
        row["net_aliases"] = aliases
        row["net"] = canonical(root)
        row["named"] = bool(aliases)

    # 未命名网络编号（按页面、坐标稳定排序）
    unnamed = [r for r in pin_rows if not r["named"]]
    groups = defaultdict(list)
    for r in unnamed:
        groups[dsu.find(r["node"])].append(r)
    ordered = sorted(groups.items(),
                     key=lambda kv: (kv[1][0]["page"], min((p["x"], p["y"]) for p in kv[1])))
    for i, (root, rows) in enumerate(ordered, 1):
        name = f"$LOCAL{i}"
        for r in rows:
            r["net"] = name
            r["net_aliases"] = [name]
            r["named"] = False

    # 按网聚合
    nets = defaultdict(lambda: {"aliases": set(), "pins": [], "named": False})
    for r in pin_rows:
        key = r["net"]
        if not key:
            continue
        n = nets[key]
        n["aliases"].update(r["net_aliases"])
        n["named"] = n["named"] or r["named"]
        if r["is_net_flag"]:
            n.setdefault("flags", []).append(r["net"])
            continue
        n["pins"].append({
            "page": r["page_title"],
            "designator": r["designator"],
            "pin": r["pin"],
            "pin_name": r["pin_name"],
        })
    out_nets = {}
    for name, n in nets.items():
        item = {
            "aliases": sorted(n["aliases"]),
            "named": n["named"],
            "pins": n["pins"],
        }
        if n.get("flags"):
            item["flags"] = sorted(set(n["flags"]))
        out_nets[name] = item
    return pin_rows, out_nets, warnings


# ---------------------------------------------------------------- PCB

def extract_pcb(doc, footprints: dict, devices: dict, with_poured: bool = False) -> dict:
    attrs = attrs_by_parent(doc)
    meta = meta_of(doc)

    layers = []
    for rec in doc.records:
        if rec.type == "LAYER" and isinstance(rec.payload, dict):
            p = rec.payload
            layers.append({
                "id": p.get("layerId"),
                "type": p.get("layerType"),
                "name": p.get("layerName"),
                "use": p.get("use"),
                "show": p.get("show"),
            })
    layer_name = {l["id"]: l["name"] for l in layers}

    stackup = [r.payload for r in doc.records
               if r.type == "LAYER_PHYS" and isinstance(r.payload, dict)]

    # PAD_NET: [(PAD_NET, compId, padNum, padId)] → padId → net
    pad_net: dict[str, dict] = defaultdict(dict)
    for rec in doc.records:
        if rec.type != "PAD_NET" or rec.payload is R.MISSING:
            continue
        ids = parse_id(rec.id)
        if isinstance(ids, list) and len(ids) >= 4:
            pad_net[ids[1]][ids[3]] = rec.payload.get("padNet")

    components = []
    for rec in doc.records:
        if rec.type != "COMPONENT" or not isinstance(rec.payload, dict):
            continue
        c = rec.payload
        a = attrs.get(rec.id, {})
        # 有些元件（如 M2 螺丝）实例上没有 Footprint 属性，
        # 封装只在 DEVICE 的 attributes.Footprint 里。两层都查。
        dev = devices.get(a.get("Device")) or {}
        fp_uuid = a.get("Footprint") or dev.get("footprint")
        fp = footprints.get(fp_uuid)
        pads = []
        for pad in (fp["pads"] if fp else []):
            X, Y = transform(pad["x"], pad["y"], c.get("x", 0), c.get("y", 0),
                             c.get("angle"), c.get("layerId") == 2)
            pads.append({
                "pad_id": pad["id"],
                "num": pad["num"],
                "net": pad_net.get(rec.id, {}).get(pad["id"]),
                "x": X,
                "y": Y,
                "layer": pad["layer"],
                "shape": pad["shape"],
                "width": pad["width"],
                "height": pad["height"],
                "hole": pad["hole"],
                "plated": pad["plated"],
            })
        components.append({
            "id": rec.id,
            "designator": a.get("Designator"),
            "footprint": fp_uuid,
            "footprint_title": (fp or {}).get("title"),
            "footprint_source": ("component" if a.get("Footprint")
                                 else "device" if fp_uuid else None),
            "device": a.get("Device"),
            "x": c.get("x"),
            "y": c.get("y"),
            "angle": c.get("angle"),
            "layer": c.get("layerId"),
            "layer_name": layer_name.get(c.get("layerId")),
            "attrs": dict(a),
            "pads": pads,
        })

    standalone_pads = []
    for rec in doc.records:
        if rec.type == "PAD" and isinstance(rec.payload, dict):
            p = rec.payload
            w, h, ptype, radius = pad_size(p)
            standalone_pads.append({
                "id": rec.id,
                "num": p.get("num"),
                "net": p.get("netName") or None,
                "x": p.get("centerX"),
                "y": p.get("centerY"),
                "layer": p.get("layerId"),
                "shape": ptype,
                "width": w,
                "height": h,
                "radius": radius,
                "hole": p.get("hole"),
                "plated": p.get("plated"),
            })

    tracks, graphics = [], []
    for rec in doc.records:
        if rec.type != "LINE" or not isinstance(rec.payload, dict):
            continue
        p = rec.payload
        item = {
            "id": rec.id,
            "net": p.get("netName") or None,
            "layer": p.get("layerId"),
            "layer_name": layer_name.get(p.get("layerId")),
            "width": p.get("width"),
            "start": [p.get("startX"), p.get("startY")],
            "end": [p.get("endX"), p.get("endY")],
        }
        if p.get("netName") or p.get("layerId") in (1, 2) or 15 <= (p.get("layerId") or 0) <= 46:
            tracks.append(item)
        else:
            graphics.append(item)

    vias = [{
        "id": r.id,
        "net": r.payload.get("netName") or None,
        "x": r.payload.get("centerX"),
        "y": r.payload.get("centerY"),
        "hole": r.payload.get("holeDiameter"),
        "diameter": r.payload.get("viaDiameter"),
        "type": r.payload.get("viaType"),
    } for r in doc.records if r.type == "VIA" and isinstance(r.payload, dict)]

    pours = [{
        "id": r.id,
        "net": r.payload.get("netName") or None,
        "layer": r.payload.get("layerId"),
        "layer_name": layer_name.get(r.payload.get("layerId")),
        "name": r.payload.get("name"),
        "width": r.payload.get("width"),
        "type": r.payload.get("pourType"),
        "path": r.payload.get("path"),
    } for r in doc.records if r.type == "POUR" and isinstance(r.payload, dict)]

    poured = []
    if with_poured:
        poured = [{"id": r.id, "payload": r.payload} for r in doc.records
                  if r.type == "POURED"]

    texts = [{"id": r.id, "payload": r.payload} for r in doc.records
             if r.type == "STRING" and isinstance(r.payload, dict)]
    dimensions = [{"id": r.id, "payload": r.payload} for r in doc.records
                  if r.type == "DIMENSION" and isinstance(r.payload, dict)]
    shells = [{"id": r.id, "payload": r.payload} for r in doc.records
              if r.type in ("SHELL", "SHELL_ENTITY") and isinstance(r.payload, dict)]
    rules = [{"id": r.id, "payload": r.payload} for r in doc.records
             if r.type in ("RULE", "RULE_TEMPLATE", "RULE_SELECTOR")
             and isinstance(r.payload, dict)]

    # 板框：OUTLINE 层（11）上的 POLY
    outline = []
    for rec in doc.records:
        if rec.type == "POLY" and isinstance(rec.payload, dict) \
                and rec.payload.get("layerId") == 11:
            outline.append({"id": rec.id, "path": rec.payload.get("path"),
                            "points": num_pairs(rec.payload.get("path"))})
    outline_pts = [pt for o in outline for pt in o["points"]]
    board_size = None
    if outline_pts:
        xs = [p[0] for p in outline_pts]
        ys = [p[1] for p in outline_pts]
        board_size = {
            "min_x": round(min(xs), ROUND), "max_x": round(max(xs), ROUND),
            "min_y": round(min(ys), ROUND), "max_y": round(max(ys), ROUND),
            "width": round(max(xs) - min(xs), ROUND),
            "height": round(max(ys) - min(ys), ROUND),
            "unit": "mil",
        }

    return {
        "uuid": doc.uuid,
        "title": meta.get("title"),
        "board": meta.get("board"),
        "parent": meta.get("parent"),
        "source": meta.get("source"),
        "layers": layers,
        "stackup": stackup,
        "components": components,
        "standalone_pads": standalone_pads,
        "tracks": tracks,
        "graphics": graphics,
        "vias": vias,
        "pours": pours,
        "poured": poured,
        "outline": outline,
        "board_size": board_size,
        "texts": texts,
        "dimensions": dimensions,
        "shells": shells,
        "rules": rules,
    }


# ---------------------------------------------------------------- 汇总与对比

def pcb_netlist(pcb: dict):
    nets = defaultdict(list)
    for comp in pcb["components"]:
        for pad in comp["pads"]:
            if not pad["net"]:
                continue
            nets[pad["net"]].append({
                "designator": comp["designator"],
                "pad": pad["num"],
                "pad_id": pad["pad_id"],
                "footprint": comp["footprint"],
                "x": pad["x"],
                "y": pad["y"],
                "layer": pad["layer"],
            })
    standalone = defaultdict(list)
    for pad in pcb["standalone_pads"]:
        if pad["net"]:
            standalone[pad["net"]].append(pad)
    return dict(nets), dict(standalone)


def find_net_ties(pages, sch_pins):
    """找「短接标识」符号（特殊器件，无位号）。它把两个网在原理图上标为短接，
    但网表里仍是两个网；PCB 侧可能因此合并成一个网名。"""
    out = []
    for page in pages:
        labels_by_comp = page.get("tie_labels") or {}
        for comp in page["components"]:
            if "短接标识" not in (comp.get("device_tags") or []):
                continue
            rows = [r for r in sch_pins if r["component_id"] == comp["id"]]
            labels = labels_by_comp.get(comp["id"]) or []
            pins = []
            for i, r in enumerate(rows):
                side = labels[i] if i < len(labels) and labels[i] else [r["net"]]
                pins.append({"pin": r["pin"], "nets": side,
                             "merged_net": r["net"]})
            out.append({
                "page": page["title"],
                "component_id": comp["id"],
                "device_title": comp.get("device_title"),
                "x": comp["x"],
                "y": comp["y"],
                "pins": pins,
            })
    return out


def is_auto_net(name: str) -> bool:
    """$LOCAL12 / $1N6 之类是工具自动编号，不代表设计者命名。"""
    return not name or name.startswith("$")


def compare(sch_pins, sch_nets, pcb_nets, net_ties=None):
    # 短接符号连起来的网名视为同一组：原理图保留两个网名，PCB 可能只用一个
    tie_groups = []
    for tie in net_ties or []:
        names = {n for p in tie["pins"] for n in p.get("nets", []) if n}
        if len(names) > 1:
            tie_groups.append(names)

    def tie_equiv(a, b):
        return any(a in g and b in g for g in tie_groups)

    # (designator, number) → sch 引脚行；网络标志不是元件，排除
    sch_by_key = {}
    for row in sch_pins:
        if row.get("designator") and row.get("pin") is not None \
                and not row.get("is_net_flag"):
            sch_by_key[(row["designator"], str(row["pin"]))] = row

    pcb_by_key = {}
    for net, pads in pcb_nets.items():
        for p in pads:
            if p["designator"] and p["pad"] is not None:
                pcb_by_key[(p["designator"], str(p["pad"]))] = net

    common = sorted(set(sch_by_key) & set(pcb_by_key),
                    key=lambda k: (k[0], str(k[1])))
    match = mismatch = both_auto = sch_named_only = pcb_named_only = tie_equiv_n = 0
    details = []
    for key in common:
        row = sch_by_key[key]
        pcb_net = pcb_by_key[key]
        aliases = row.get("net_aliases") or []
        sch_named = [a for a in aliases if not is_auto_net(a)]
        pcb_named = not is_auto_net(pcb_net)

        if not sch_named and not pcb_named:
            both_auto += 1
        elif sch_named and not pcb_named:
            sch_named_only += 1
        elif not sch_named and pcb_named:
            pcb_named_only += 1
        elif pcb_net in sch_named:
            match += 1
        elif any(tie_equiv(a, pcb_net) for a in sch_named):
            tie_equiv_n += 1
        else:
            mismatch += 1
            details.append({
                "designator": key[0], "pin": key[1],
                "schematic": sch_named, "pcb": pcb_net,
            })

    only_sch = sorted(set(sch_by_key) - set(pcb_by_key))
    only_pcb = sorted(set(pcb_by_key) - set(sch_by_key))

    # 按网比较成员集合（只比设计者命名的网）
    net_sets_sch = {}
    for name, n in sch_nets.items():
        if n["named"]:
            for alias in n["aliases"]:
                if not is_auto_net(alias):
                    net_sets_sch[alias] = {f"{p['designator']}.{p['pin']}"
                                           for p in n["pins"] if p["designator"]}
    net_sets_pcb = {name: {f"{p['designator']}.{p['pad']}" for p in pads}
                    for name, pads in pcb_nets.items() if not is_auto_net(name)}

    def sch_expected(pcb_name):
        names = {pcb_name}
        for group in tie_groups:
            if pcb_name in group:
                names |= group
        out = set()
        for nm in names:
            out |= net_sets_sch.get(nm, set())
        return out

    net_common = sorted(n for n in net_sets_pcb if sch_expected(n))
    net_mismatch = [
        {"net": n,
         "only_schematic": sorted(sch_expected(n) - net_sets_pcb[n]),
         "only_pcb": sorted(net_sets_pcb[n] - sch_expected(n))}
        for n in net_common if sch_expected(n) != net_sets_pcb[n]
    ]

    return {
        "pins_compared": len(common),
        "match": match,
        "mismatch": mismatch,
        "net_tie_equivalent": tie_equiv_n,
        "both_auto_named": both_auto,
        "schematic_named_only": sch_named_only,
        "pcb_named_only": pcb_named_only,
        "mismatch_details": details,
        "only_in_schematic": [f"{d}.{p}" for d, p in only_sch],
        "only_in_pcb": [f"{d}.{p}" for d, p in only_pcb],
        "nets_compared": len(net_common),
        "net_mismatches": net_mismatch,
    }


# ---------------------------------------------------------------- 主流程

def dump_json(path, obj):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
        fh.write("\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description="从 .epro2 提取原理图/PCB 结构化信息")
    ap.add_argument("project")
    ap.add_argument("--out", default=None, help="项目外的输出目录；默认使用同级数据目录")
    ap.add_argument("--with-poured", action="store_true",
                    help="导出铺铜计算结果 POURED（体积可能很大）")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    try:
        explicit_out = external_path(args.out) if args.out else None
        if explicit_out is None:
            generated_path('outputs', 'extract')
    except ValueError as exc:
        ap.error(str(exc))

    project, records = R.read_project(args.project, strict=True)
    docs = list(R.iter_documents(records))
    symbols, footprints, devices = build_library(docs)

    # 配置
    cross_page = True
    cross_layer = True
    for doc in docs:
        if doc.doc_type == "CONFIG":
            for rec in doc.records:
                if rec.type == "UNIVERSAL" and isinstance(rec.payload, dict):
                    cross_page = bool(rec.payload.get("netLabelCrossPageConnection", True))
                    cross_layer = bool(rec.payload.get("netFlagCrossLayerConnection", True))

    pages = [extract_page(d, symbols, devices) for d in docs if d.doc_type == "SCH_PAGE"]
    pcbs = [extract_pcb(d, footprints, devices, args.with_poured)
            for d in docs if d.doc_type == "PCB"]

    sch_pins, sch_nets, warnings = build_schematic_nets(pages, cross_page, cross_layer)
    net_ties = find_net_ties(pages, sch_pins)

    index_docs = []
    for doc in docs:
        meta = meta_of(doc)
        index_docs.append({
            "uuid": doc.uuid,
            "doc_type": doc.doc_type,
            "title": meta.get("title"),
            "board": meta.get("board"),
            "schematic": meta.get("schematic"),
            "parent": meta.get("parent"),
            "records": len(doc.records),
        })

    # 层级
    boards = []
    for doc in docs:
        if doc.doc_type != "BOARD":
            continue
        meta = meta_of(doc)
        boards.append({
            "uuid": doc.uuid,
            "title": meta.get("title"),
            "schematics": [d.uuid for d in docs
                           if d.doc_type == "SCH" and meta_of(d).get("board") == doc.uuid],
            "pcbs": [d.uuid for d in docs
                     if d.doc_type == "PCB" and meta_of(d).get("board") == doc.uuid],
        })
    orphan_schematics = [d.uuid for d in docs
                         if d.doc_type == "SCH" and not meta_of(d).get("board")]
    orphan_pcbs = [d.uuid for d in docs
                   if d.doc_type == "PCB" and not meta_of(d).get("board")]

    index = {
        "file": os.path.abspath(args.project),
        "title": project.get("title"),
        "editor_version": project.get("editorVersion"),
        "cbb_project": project.get("cbb_project"),
        "documents": index_docs,
        "hierarchy": {
            "boards": boards,
            "orphan_schematics": orphan_schematics,
            "orphan_pcbs": orphan_pcbs,
        },
    }

    pcb_nets_by_pcb = {}
    pcb_nets_all = defaultdict(list)
    standalone_all = defaultdict(list)
    for pcb in pcbs:
        nets, standalone = pcb_netlist(pcb)
        pcb_nets_by_pcb[pcb["uuid"]] = nets
        for name, pads in nets.items():
            pcb_nets_all[name].extend(pads)
        for name, pads in standalone.items():
            standalone_all[name].extend(pads)

    # 默认拿主 PCB（有元件的那块）做对比
    main_pcb = max(pcbs, key=lambda p: len(p["components"]), default=None)
    comparison = None
    if main_pcb and sch_pins:
        comparison = compare(sch_pins, sch_nets, pcb_nets_by_pcb[main_pcb["uuid"]],
                             net_ties)
        comparison["pcb_uuid"] = main_pcb["uuid"]
        comparison["pcb_title"] = main_pcb["title"]

        sch_des = {c["designator"] for p in pages for c in p["components"]
                   if c.get("designator")}
        pcb_des = {c["designator"] for c in main_pcb["components"]
                   if c.get("designator")}
        comparison["designators_schematic"] = len(sch_des)
        comparison["designators_pcb"] = len(pcb_des)
        comparison["only_designators_schematic"] = sorted(sch_des - pcb_des)
        comparison["only_designators_pcb"] = sorted(pcb_des - sch_des)

    netlist = {
        "schematic": {
            "nets": sch_nets,
            "net_ties": net_ties,
            "pins": [{k: v for k, v in row.items() if k not in ("node", "component_id")}
                     for row in sch_pins],
        },
        "pcb": {
            "by_pcb": {uuid: {name: pads for name, pads in nets.items()}
                       for uuid, nets in pcb_nets_by_pcb.items()},
            "standalone_pads": {name: pads for name, pads in standalone_all.items()},
        },
        "comparison": comparison,
    }

    try:
        out_dir = explicit_out or generated_path('outputs', 'extract',
                                                 safe_name(project.get('title') or 'project'))
    except ValueError as exc:
        ap.error(str(exc))
    os.makedirs(out_dir, exist_ok=True)

    dump_json(os.path.join(out_dir, "index.json"), index)
    dump_json(os.path.join(out_dir, "schematic.json"),
              {"pages": pages, "symbols": symbols, "devices": devices})
    dump_json(os.path.join(out_dir, "pcb.json"), {"pcbs": pcbs, "footprints": footprints})
    dump_json(os.path.join(out_dir, "netlist.json"), netlist)

    # summary.txt
    lines = []
    lines.append(f"工程：{project.get('title')}  editor={project.get('editorVersion')}")
    lines.append(f"文件：{os.path.abspath(args.project)}")
    lines.append(f"记录 {len(records)} 条，文档 {len(docs)} 个")
    by_type = defaultdict(int)
    for d in docs:
        by_type[d.doc_type] += 1
    lines.append("文档：" + "，".join(f"{k} {v}" for k, v in sorted(by_type.items())))
    lines.append("")
    real_pins = sum(1 for r in sch_pins if not r["is_net_flag"])
    lines.append(f"原理图页 {len(pages)} 个；"
                 f"元件 {sum(1 for p in pages for c in p['components'] if c['designator'])} 个；"
                 f"引脚 {real_pins} 个（另有网络标志引脚 "
                 f"{len(sch_pins) - real_pins} 个未计入）；网络 {len(sch_nets)} 个"
                 f"（命名 {sum(1 for n in sch_nets.values() if n['named'])} 个）")
    for tie in net_ties[:20]:
        lines.append(f"  短接符号 @ ({tie['x']}, {tie['y']})：" +
                     " ↔ ".join(
                         f"{'/'.join(str(n) for n in p['nets'])}(pin {p['pin']})"
                         for p in tie["pins"]))
    if len(net_ties) > 20:
        lines.append(f"  ……另有 {len(net_ties) - 20} 个短接符号，见 netlist.json")
    for pcb in pcbs:
        pads = sum(len(c["pads"]) for c in pcb["components"])
        nets, standalone = pcb_netlist(pcb)
        lines.append(f"PCB「{pcb['title'] or pcb['uuid']}」："
                     f"元件 {len(pcb['components'])}，焊盘 {pads}，"
                     f"网络 {len(nets)}，走线 {len(pcb['tracks'])} 段，"
                     f"过孔 {len(pcb['vias'])}，铺铜 {len(pcb['pours'])}，"
                     f"独立焊盘 {len(pcb['standalone_pads'])}")
        if pcb.get("board_size"):
            bs = pcb["board_size"]
            lines.append(f"  板框 {bs['width']} × {bs['height']} mil "
                         f"({bs['width'] * 0.0254:.1f} × {bs['height'] * 0.0254:.1f} mm)")
    if comparison:
        lines.append("")
        lines.append(f"原理图 ↔ PCB 对比（{comparison['pcb_title'] or comparison['pcb_uuid']}）：")
        lines.append(f"  位号：原理图 {comparison['designators_schematic']} 个，"
                     f"PCB {comparison['designators_pcb']} 个；"
                     f"只在原理图 {comparison['only_designators_schematic'] or '无'}；"
                     f"只在 PCB {comparison['only_designators_pcb'] or '无'}")
        lines.append(f"  可比引脚 {comparison['pins_compared']} 个；"
                     f"命名一致 {comparison['match']}，命名冲突 {comparison['mismatch']}，"
                     f"经短接符号等价 {comparison['net_tie_equivalent']}，"
                     f"两侧都是自动编号 {comparison['both_auto_named']}，"
                     f"仅原理图有命名 {comparison['schematic_named_only']}，"
                     f"仅 PCB 有命名 {comparison['pcb_named_only']}")
        for d in comparison["mismatch_details"][:40]:
            lines.append(f"    不一致 {d['designator']}.{d['pin']}: "
                         f"原理图 {d['schematic']} / PCB {d['pcb']}")
        if comparison["only_in_schematic"]:
            lines.append("  只在原理图：" + ", ".join(comparison["only_in_schematic"][:40]))
        if comparison["only_in_pcb"]:
            lines.append("  只在 PCB：" + ", ".join(comparison["only_in_pcb"][:40]))
        if comparison["net_mismatches"]:
            lines.append(f"  同名网成员不一致 {len(comparison['net_mismatches'])} 个：")
            for m in comparison["net_mismatches"][:20]:
                lines.append(f"    {m['net']}: 只在原理图 {m['only_schematic']}；"
                             f"只在 PCB {m['only_pcb']}")
    if warnings:
        lines.append("")
        lines.append(f"几何告警（{len(warnings)} 条，前 40 条）：")
        lines.extend("  " + w for w in warnings[:40])
    lines.append("")
    lines.append("产物：index.json / schematic.json / pcb.json / netlist.json / summary.txt")
    lines.append("注意：原理图网表是几何重建结果；PCB 网名以 PAD_NET 为准。")

    with open(os.path.join(out_dir, "summary.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")

    if not args.quiet:
        print("\n".join(lines))
        print(f"\n输出目录：{out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
