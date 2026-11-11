# 运行产物目录

项目保留源码、规范、模板和已经归档的历史资料。后续运行产物默认写入项目旁的 `<项目目录名>-data/`，路径由 `src/output_paths.py` 根据脚本所在位置计算，不依赖终端当前目录。当前项目对应 `../epro2-辅助绘制及审核-data/`；如果克隆目录叫 `epro2--`，则对应 `../epro2---data/`。

本文及其他流程文档中的 `<DATA_DIR>` 表示该数据目录。文档中的 `src/`、`docs/`、模板路径仍相对项目根目录；历史记录引用的旧路径仍指向原有资料。

```text
同一父目录/
├─ epro2-辅助绘制及审核/        # 项目，现有目录结构保留
└─ epro2-辅助绘制及审核-data/
   ├─ outputs/
   │  ├─ extract/<工程名>/      # 解析 JSON、摘要
   │  ├─ api/<工程名>/          # API 原始采集
   │  ├─ audit/<工程>/<版本>/   # 审核中间数据、仿真
   │  ├─ check-footprints/<轮次>/
   │  └─ eda/                  # bridge.json、bridge.log
   ├─ work/boards/<板卡>/       # 意图、基线、finding、日志、快照
   ├─ work/<系统>-<版本>/       # system-interconnect.json，多板连接模型
   └─ review/<轮次>/           # 报告及 evidence/，需要长期保留
```

在项目根目录执行：

```powershell
# 查看路径，不创建文件
python -B src/output_paths.py
# 创建基本目录；传入板卡名还会复制模板，已有文件不会被覆盖
python -B src/output_paths.py --init --board '控制板-V1.0-2026-11-09'
# 自动创建输出目录并写入提取结果
python -B src/extract.py 'D:/design/控制板.epro2'
# 获取实际路径，可用于 shell 重定向或其他只输出到终端的工具
$data = (python -B src/output_paths.py | ConvertFrom-Json).data_root
python -B src/check_footprints.py "$data/outputs/extract/控制板/pcb.json" --schematic "$data/outputs/extract/控制板/schematic.json" --run-name '控制板-V1.0-2026-11-09'
```

C-10 默认自动保存 JSON 和 Markdown 报告；不传 `--out` 时也保留原来的 JSON 标准输出。默认轮次名包含输入所在目录名和时间戳；`--run-name` 可指定轮次目录。同名轮次或显式输出文件会覆盖既有结果，复审时使用新的名称。提取器同名工程仍写入同一提取目录，可用 `--out` 指定新的外部目录。

需要更换数据位置时，在运行命令前设置绝对路径环境变量：

```powershell
$env:EPRO2_DATA_DIR = 'D:/board-data/epro2'
python -B src/output_paths.py --init
```

`--out` / `--report` 仍可指定自定义外部路径，相对路径按终端当前目录解释。脚本拒绝写入项目自身，包括解析后落入项目的符号链接路径。父目录会自动创建。环境变量影响提取、C-10、板卡初始化及 bridge 状态/日志；已有 bridge 进程使用旧位置时，应先用原配置执行 `eda.py stop` 再切换。

完整审核档案由审核流程撰写到 `<DATA_DIR>/review/<工程>-<版本>-<日期>/`：先形成 `report.md`，再据此生成 `simple-report.md`；引用证据放同目录 `evidence/`。简明版不得带入完整报告和审核数据未支持的新结论。C-10 自动报告仅覆盖封装结构检查，不代替完整审核。API 查询、网表校验及几何检查等只打印标准输出的命令，需要将重定向目标设在 `<DATA_DIR>/outputs/`；shell 的 `>` 不受 Python 路径检查控制。

多板连接模型由 `work/system-interconnect.template.json` 复制到外部系统工作目录；`--board` 初始化只复制单板模板，不会自动创建系统连接模型。复制命令与字段语义见 [多板系统联合审核](multi-board-review.md)。定稿时将实际使用的模型及其引用的线束/连接器证据复制到报告 `evidence/` 留档。

运行和测试建议使用 `python -B`，避免生成项目内的 Python 字节码缓存。数据目录不属于项目 Git 仓库，应单独备份正式报告与引用证据；临时 `outputs/` 可按任务清理。现有 `outputs/`、`review/`、`work/boards/` 下的历史文件保留，不再作为新任务输出目标。
