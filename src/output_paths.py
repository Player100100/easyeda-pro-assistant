"""Paths for generated data, independent of the caller's working directory."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def external_path(value: str | Path) -> Path:
    path = Path(value).expanduser().resolve()
    if path == PROJECT_ROOT or PROJECT_ROOT in path.parents:
        raise ValueError(f"输出必须位于项目目录之外：{path}")
    return path


def data_root() -> Path:
    """Epro2 checkout and its generated data are siblings by default."""
    value = os.environ.get("EPRO2_DATA_DIR")
    if value:
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise ValueError("EPRO2_DATA_DIR 必须为绝对路径")
    else:
        path = PROJECT_ROOT.with_name(PROJECT_ROOT.name + "-data")
    return external_path(path)


def safe_name(value: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', '_', value).strip().rstrip('. ')
    if not name or name in ('.', '..'):
        raise ValueError("板卡/工程名不能为空或为 . / ..")
    if name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *[f'COM{i}' for i in range(1, 10)], *[f'LPT{i}' for i in range(1, 10)]}:
        name = '_' + name
    return name


def generated_path(*parts: str) -> Path:
    root = data_root()
    path = external_path(root.joinpath(*parts))
    if path != root and root not in path.parents:
        raise ValueError(f"输出路径超出数据目录：{path}")
    return path


def initialize(board: str | None = None) -> dict[str, str]:
    paths = {name: generated_path(name) for name in ('outputs', 'review', 'work')}
    if board:
        name = safe_name(board)
        paths.update(board=generated_path('work', 'boards', name),
                     audit=generated_path('outputs', 'audit', name),
                     report=generated_path('review', name),
                     evidence=generated_path('review', name, 'evidence'))
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    if board:
        for template in (PROJECT_ROOT / 'work' / 'boards' / '_template').iterdir():
            destination = external_path(paths['board'] / template.name)
            if template.is_file() and not destination.exists():
                shutil.copyfile(template, destination)
        for name in ('logs', 'snapshot'):
            external_path(paths['board'] / name).mkdir(parents=True, exist_ok=True)
    return {'data_root': str(data_root()), **{k: str(v) for k, v in paths.items()}}


def main(argv=None):
    parser = argparse.ArgumentParser(description='显示外部数据目录；--init 创建目录，--board 复制板卡模板')
    parser.add_argument('--init', action='store_true')
    parser.add_argument('--board', help='板卡名-版本-日期；已有文件保留')
    args = parser.parse_args(argv)
    try:
        result = initialize(args.board) if args.init or args.board else {'data_root': str(data_root())}
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
