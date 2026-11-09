// collect.js — 在 EasyEDA Pro 里取出原理图网表（配合 easyeda-api skill 使用）
//
// 用法：把本文件内容作为 `code` 发到 easyeda-api 的 bridge：
//   POST http://127.0.0.1:49620/execute  {"code": "<本文件内容>"}
// 返回：{ ok, result: { name, netlist } } —— netlist 是 .enet 的 JSON 文本
//
// 也可以直接用 CLI：
//   lceda-pro invoke --session <sid> --ext-uuid eda --timeout 120000 --code "<本文件内容>"

const schematics = await eda.dmt_Schematic.getAllSchematicsInfo();
const pages = await eda.dmt_Schematic.getAllSchematicPagesInfo();

// 网表导出依赖当前文档，先打开第一页
if (pages.length) {
  await eda.dmt_EditorControl.openDocument(pages[0].uuid);
  await new Promise((r) => setTimeout(r, 2500));
}

const file = await eda.sch_ManufactureData.getNetlistFile();
const text = await file.text();

return {
  name: file.name,
  size: text.length,
  schematics: schematics.map((s) => s.name),
  pages: pages.map((p) => p.name),
  netlist: text,
};
