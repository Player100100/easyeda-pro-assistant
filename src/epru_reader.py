#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""嘉立创EDA专业版 V3 工程（.epro2）日志读取器。

格式结论来自 8 个真实导出包的实测，见 docs/epro2-v3-format.md。

容器层：.epro2 是 ZIP，内有
    project2.json              工程元数据（title / editorVersion / ...）
    <工程名>.epru              全部设计文档的日志流
    IMAGE/<doc-uuid>.webp      各文档缩略图（可能有过期项）

日志层：UTF-8（无 BOM）、LF 换行。每个逻辑行是一条记录：

    <HEADER>||<PAYLOAD>|

  · HEADER 是 JSON 对象，至少含 type。多记录类型还含 ticket、id；
    id 是字符串，复合 id 本身又是一个 JSON 数组的字符串形式
    （例如 "[\"PAD_NET\",\"24473...\",\"1\",\"e13\"]"）。
  · PAYLOAD 可为对象、标量，或**完全省略**（写成 `HEADER|||`）。
  · 行尾的 `|` 在文件最后一条记录上会缺失（8/8 样本均如此），解析时按可选处理。
  · `||` 只作为内外层分隔符出现在每行一次；本条样本中未发现 payload 字符串内含 `||`，
    但实现仍用 raw_decode 而不是 split，以免将来被内嵌分隔符绊倒。

导出包是**压实过的日志**：8/8 样本中没有重复的 (文档, type, id)，但保留了
DELETE_DOC / META_MODIFY 等日志语义记录。读取时仍应按 ticket 取最大值的规则处理，
以兼容未压实的日志。
"""
from __future__ import annotations

import json
import sys
import zipfile
from dataclasses import dataclass, field
from typing import Any, Iterator

MISSING = object()
"""payload 被省略时的哨兵。注意与 JSON 的 null 区分。"""


@dataclass
class Record:
    header: dict
    payload: Any
    line: int

    @property
    def type(self) -> str:
        return self.header.get("type", "")

    @property
    def id(self) -> Any:
        return self.header.get("id")

    @property
    def ticket(self) -> Any:
        return self.header.get("ticket")


@dataclass
class Document:
    meta: Any
    header: Record | None = None
    records: list[Record] = field(default_factory=list)

    @property
    def doc_type(self) -> str:
        return (self.meta or {}).get("docType", "") if isinstance(self.meta, dict) else ""

    @property
    def uuid(self) -> str:
        return (self.meta or {}).get("uuid", "") if isinstance(self.meta, dict) else ""


class EpruError(Exception):
    pass


def read_epru_bytes(raw: bytes, strict: bool = False) -> list[Record]:
    """把 .epru 的字节流解析成记录列表。"""
    text = raw.decode("utf-8-sig")
    dec = json.JSONDecoder()
    pos, n, line_no = 0, len(text), 1
    records: list[Record] = []

    while pos < n:
        ch = text[pos]
        if ch == "\n":
            line_no += 1
            pos += 1
            continue
        if ch in "\r|":
            pos += 1
            continue

        start_line = line_no
        try:
            header, pos = dec.raw_decode(text, pos)
        except json.JSONDecodeError as exc:
            if strict:
                raise EpruError(f"第 {line_no} 行 header 解析失败：{exc}") from exc
            pos = _skip_line(text, pos)
            line_no = text.count("\n", 0, pos) + 1
            continue

        if not isinstance(header, dict):
            if strict:
                raise EpruError(f"第 {line_no} 行不是 JSON 对象")
            pos = _skip_line(text, pos)
            line_no = text.count("\n", 0, pos) + 1
            continue

        if text[pos:pos + 2] != "||":
            if strict:
                raise EpruError(f"第 {line_no} 行缺少内层分隔符 ||")
            pos = _skip_line(text, pos)
            line_no = text.count("\n", 0, pos) + 1
            continue
        pos += 2

        payload: Any = MISSING
        if pos < n and text[pos] not in "\r\n|":
            try:
                payload, pos = dec.raw_decode(text, pos)
            except json.JSONDecodeError as exc:
                if strict:
                    raise EpruError(f"第 {line_no} 行 payload 解析失败：{exc}") from exc
                pos = _skip_line(text, pos)
                line_no = text.count("\n", 0, pos) + 1
                continue

        if pos < n and text[pos] == "|":
            pos += 1
        elif pos < n and text[pos] not in "\r\n":
            if strict:
                raise EpruError(f"第 {line_no} 行记录末缺少 |")
            pos = _skip_line(text, pos)

        records.append(Record(header=header, payload=payload, line=start_line))

    return records


def _skip_line(text: str, pos: int) -> int:
    nl = text.find("\n", pos)
    return len(text) if nl == -1 else nl + 1


def read_epru(path: str, strict: bool = False) -> list[Record]:
    with open(path, "rb") as fh:
        return read_epru_bytes(fh.read(), strict=strict)


def read_project(path: str, strict: bool = False) -> tuple[dict, list[Record]]:
    """读 .epro2（ZIP）或裸 .epru，返回 (project2.json, records)。

    裸 .epru 没有 project2.json，返回空 dict。
    """
    if path.lower().endswith(".epru"):
        return {}, read_epru(path, strict=strict)
    with zipfile.ZipFile(path) as zf:
        epru_names = [n for n in zf.namelist() if n.lower().endswith(".epru")]
        if len(epru_names) != 1:
            raise EpruError(f"期望恰好 1 个 .epru，实得 {len(epru_names)} 个：{epru_names}")
        project = {}
        if "project2.json" in zf.namelist():
            project = json.loads(zf.read("project2.json").decode("utf-8-sig"))
        records = read_epru_bytes(zf.read(epru_names[0]), strict=strict)
    return project, records


def iter_documents(records: list[Record]) -> Iterator[Document]:
    """按 DOCHEAD 切分文档。第一个 DOCHEAD 之前的记录归入 meta=None 的文档。"""
    current = Document(meta=None)
    saw_head = False
    for rec in records:
        if rec.type == "DOCHEAD":
            if saw_head or current.records:
                yield current
            current = Document(meta=rec.payload, header=rec)
            saw_head = True
        else:
            current.records.append(rec)
    if saw_head or current.records:
        yield current


def documents(path: str, strict: bool = False) -> list[Document]:
    _, records = read_project(path, strict=strict)
    return list(iter_documents(records))


def _main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("用法：epru_reader.py <工程.epro2 | 文档.epru> [--list | --dump <uuid>]")
        return 2
    path = argv[1]
    project, records = read_project(path, strict=True)
    docs = list(iter_documents(records))

    print(f"工程：{project.get('title', '(未知)')}  editor={project.get('editorVersion', '?')}")
    print(f"记录：{len(records)}  文档：{len(docs)}")

    if "--list" in argv or len(argv) == 2:
        for doc in docs:
            meta = next(
                (r.payload for r in doc.records if r.type == "META" and isinstance(r.payload, dict)),
                {},
            )
            print(f"  {doc.doc_type:<14} {doc.uuid:<30} {meta.get('title') or meta.get('name') or ''}")
        return 0

    if "--dump" in argv:
        uuid = argv[argv.index("--dump") + 1]
        for doc in docs:
            if doc.uuid != uuid:
                continue
            for rec in doc.records:
                print(json.dumps(
                    {"type": rec.type, "id": rec.id, "ticket": rec.ticket,
                     "payload": rec.payload if rec.payload is not MISSING else "<MISSING>"},
                    ensure_ascii=False,
                ))
            return 0
        print(f"未找到文档 {uuid}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
