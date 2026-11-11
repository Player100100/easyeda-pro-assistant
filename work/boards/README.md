# 板子审核临时工作区

本目录保留历史记录和 `_template/` 模板。新任务执行 `python -B src/output_paths.py --init --board "<工程名>-<版本>-<日期>"`，将模板复制到项目外的 `<DATA_DIR>/work/boards/`，已有记录不会覆盖。**新报告写到 `<DATA_DIR>/review/`**。`<DATA_DIR>` 见项目 `docs/output-directories.md`。

## 命名

```
<DATA_DIR>/work/boards/<工程名>-<版本>-<日期>/
```

例：`<DATA_DIR>/work/boards/信号滤波器成品-V1.0-2026-11-07/`

## 一块板子的目录

```
<工程名>-<版本>-<日期>/
  source.md          # 板卡来源、版本、许可证、文件清单
  intent.md          # 设计意图卡；可跳过，跳过时由 agent 填「推断」段
  requirements.yaml  # 要求基线；agent 取完网表后生成
  findings.md        # finding 状态表；规则见 docs/finding-lifecycle.md
  footprint-review.md # C-10 封装匹配：逐对象/子项证据、复用范围与未检查项
  footprint-expectations.json # C-10 自动比对基线；从厂商/BOM 证据填写，初始为空
  power-charge-budget.md # C-11 逐轨/工况：负载、电源、电容、路径预算与缺失证据
  logs/              # 运行日志、命令、工具版本、错误
  snapshot/          # 本次审核用的只读快照/中间结果
  audit.json         # 机器可读的 findings（可选，先有再规范）
  notes.md           # 过程记录、待确认项、人工裁决
```

## 规则

- 使用初始化命令将项目中的 `_template/` 复制到外部板卡目录，不要直接改模板。
- `snapshot/` 只读；需要改数据时写新文件并记录原因。
- 日志至少记录：时间、命令/API、输入、输出、工具版本、错误。
- 推断出来的设计意图、要求、结论都必须标 `inferred`，不能伪装成用户确认。
- 本目录不是审核档案；定稿证据按 `review-method.md` 复制到 `<DATA_DIR>/review/<工程>-<版本>-<日期>/evidence/`。
