#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 EasyEDA 自己导出的 Protel 2.0 网表，校验 extract.py 重建的原理图网表。

用法：
    python src/validate_netlist.py <netlist.json> <EasyEDA导出的.net>

EasyEDA 专业版导出路径：「设计 / 制造 → 导出 → 网表」，格式选 Protel 2.0。
文件结构：若干 ``[ … ]`` 元件段，然后是 ``( 网名 … )`` 网络段；成员行形如
``U1-5 TP4056X-435-ESOP8-BAT Passive``（位号-引脚号，后面是型号-引脚名和类型）。

输出逐引脚对比和网级对比。注意两处预期内的差异（见 docs/extraction-guide.md §6.1）：

· 未连接的引脚不会出现在 EasyEDA 网表里，所以「只在我们」通常非空；
· ``Convert to PCB: no`` 的元件整个不出现。

自动网名允许变化，但共有引脚的成员分组必须一致。只在提取侧的引脚仍需解释；
退出码 0 不代表它们已被核验或多实例/多板映射已完整支持。
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict


def parse_protel(path):
    """返回每个网的成员集合：[(net_name, [(designator, pin), ...]), ...]。"""
    nets = []
    cur = None
    for raw in open(path, encoding="utf-8", errors="replace"):
        line = raw.rstrip("\n")
        if line == "(":
            cur = None
            continue
        if line == ")":
            if isinstance(cur, dict):
                nets.append(cur)
            cur = None
            continue
        if line.startswith("["):
            cur = "__skip__"          # 元件段，跳过到单独的 ]
            continue
        if cur == "__skip__":
            if line == "]":
                cur = None
            continue
        if cur is None:
            if line.strip():
                cur = {"name": line.strip(), "members": []}
            continue
        s = line.strip()
        if not s:
            continue
        des, _, pin = s.partition(" ")[0].partition("-")
        cur["members"].append((des, pin))
    return nets


def is_auto(name: str) -> bool:
    return not name or name.startswith("$")


def compare_partitions(ours, ref, common):
    """Find splits/merges by comparing membership, not generated net names."""
    ours_to_ref = defaultdict(set)
    ref_to_ours = defaultdict(set)
    for key in common:
        ours_name = ours[key].get("net") or ""
        ref_name = ref[key]
        if not ours_name or not ref_name:
            continue
        ours_to_ref[ours_name].add(ref_name)
        ref_to_ours[ref_name].add(ours_name)

    conflicts = []
    for name, matches in ours_to_ref.items():
        if len(matches) > 1:
            conflicts.append(("merge", name, sorted(matches)))
    for name, matches in ref_to_ours.items():
        if len(matches) > 1:
            conflicts.append(("split", name, sorted(matches)))
    return conflicts


def main(argv):
    if len(argv) < 3:
        print(__doc__.strip().splitlines()[2])
        return 2
    netlist_json, protel_path = argv[1], argv[2]
    data = json.load(open(netlist_json, encoding="utf-8"))

    ours = {}
    for row in data["schematic"]["pins"]:
        if row.get("is_net_flag") or not row.get("designator"):
            continue
        ours[(row["designator"], str(row["pin"]))] = row

    ref_nets = parse_protel(protel_path)
    ref = {}
    for net in ref_nets:
        for member in net["members"]:
            ref[member] = net["name"]

    common = sorted(set(ours) & set(ref))
    only_ours = sorted(set(ours) - set(ref))
    only_ref = sorted(set(ref) - set(ours))

    counts = defaultdict(int)
    diffs = []
    for key in common:
        a = ours[key].get("net") or ""
        b = ref[key]
        if a == b:
            counts["same"] += 1
        elif a and b and is_auto(a) and is_auto(b):
            counts["auto_both"] += 1
        else:
            counts["differ"] += 1
            diffs.append((key, a, b))

    # Automatic net names can differ, but their pin membership cannot.
    partition_diffs = compare_partitions(ours, ref, common)

    print(f"我们 {len(ours)} 引脚，EasyEDA 导出 {len(ref)} 引脚，共有 {len(common)}")
    print(f"同名 {counts['same']}，两侧自动编号 {counts['auto_both']}，不同 {counts['differ']}")
    print(f"只在我们 {len(only_ours)}，只在导出 {len(only_ref)}")
    if only_ours:
        print("  只在我们：", only_ours[:20], "…" if len(only_ours) > 20 else "")
    if only_ref:
        print("  只在导出：", only_ref[:20], "…" if len(only_ref) > 20 else "")
    for (des, pin), a, b in diffs[:40]:
        print(f"  DIFF {des}.{pin}: 我们={a!r} EasyEDA={b!r}")

    ours_nets = defaultdict(set)
    for key, row in ours.items():
        name = row.get("net") or ""
        if not is_auto(name):
            ours_nets[name].add(key)
    ref_sets = defaultdict(set)
    for net in ref_nets:
        if not is_auto(net["name"]):
            ref_sets[net["name"]].update(net["members"])

    print(f"\n网级：我们 {len(ours_nets)} 个命名网，导出 {len(ref_sets)} 个")
    bad = 0
    for name in sorted(set(ours_nets) | set(ref_sets)):
        a, b = ours_nets.get(name, set()), ref_sets.get(name, set())
        if a != b:
            bad += 1
            print(f"  NET {name}: 仅我们={sorted(a - b)}；仅导出={sorted(b - a)}")
    if partition_diffs:
        print(f"\n网成员分组冲突 {len(partition_diffs)} 个：")
        for kind, name, matches in partition_diffs[:40]:
            print(f"  {kind}: {name} <-> {matches}")
    return 0 if not diffs and not bad and not partition_diffs and not only_ref else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
