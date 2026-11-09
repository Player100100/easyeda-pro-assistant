const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function padInfo(pd) {
  let hole = null, shape = null;
  try { hole = pd.getState_Hole(); } catch (e) { hole = String(e); }
  try { shape = pd.getState_Pad(); } catch (e) { shape = String(e); }
  return {
    id: pd.getState_PrimitiveId(), number: pd.getState_PadNumber(), net: pd.getState_Net(),
    x: pd.getState_X(), y: pd.getState_Y(), layer: pd.getState_Layer(),
    rotation: pd.getState_Rotation(), padType: pd.getState_PadType(),
    plated: pd.getState_Metallization(), shape: shape, hole: hole
  };
}
const out = { project: null, editorVersion: null, boards: null, pcb: {} };
const p = await eda.dmt_Project.getCurrentProjectInfo();
out.project = p ? { uuid: p.uuid, name: p.friendlyName || p.name } : null;
out.editorVersion = eda.sys_Environment.getEditorCurrentVersion();
out.boards = await eda.dmt_Board.getAllBoardsInfo();
const board = out.boards[0];
const pcbUuid = board.pcb.uuid;
const tabId = await eda.dmt_EditorControl.openDocument(pcbUuid);
if (tabId) await eda.dmt_EditorControl.activateDocument(tabId);
await sleep(2500);
const pcbComps = (await eda.pcb_PrimitiveComponent.getAll()) || [];
out.pcb.components = [];
for (const c of pcbComps) {
  const id = c.getState_PrimitiveId();
  let pads = [];
  try {
    const ps = (await eda.pcb_PrimitiveComponent.getAllPinsByPrimitiveId(id)) || [];
    pads = ps.map(padInfo);
  } catch (e) { pads = [{ error: String(e) }]; }
  out.pcb.components.push({
    id: id, designator: c.getState_Designator(), name: c.getState_Name(),
    component: c.getState_Component(), footprint: c.getState_Footprint(),
    layer: c.getState_Layer(), rotation: c.getState_Rotation(),
    x: c.getState_X(), y: c.getState_Y(), addIntoBom: c.getState_AddIntoBom(),
    manufacturer: c.getState_Manufacturer(), manufacturerId: c.getState_ManufacturerId(),
    supplier: c.getState_Supplier(), supplierId: c.getState_SupplierId(),
    other: c.getState_OtherProperty(), pads: pads
  });
}
out.pcb.allPads = ((await eda.pcb_PrimitivePad.getAll()) || []).map(padInfo);
out.pcb.tracks = ((await eda.pcb_PrimitiveLine.getAll()) || []).map((l) => ({
  id: l.getState_PrimitiveId(), net: l.getState_Net(), layer: l.getState_Layer(),
  width: l.getState_LineWidth(), x1: l.getState_StartX(), y1: l.getState_StartY(),
  x2: l.getState_EndX(), y2: l.getState_EndY(), locked: l.getState_PrimitiveLock()
}));
out.pcb.vias = ((await eda.pcb_PrimitiveVia.getAll()) || []).map((v) => ({
  id: v.getState_PrimitiveId(), net: v.getState_Net(), x: v.getState_X(), y: v.getState_Y(),
  diameter: v.getState_Diameter(), holeDiameter: v.getState_HoleDiameter(),
  viaType: v.getState_ViaType(), blindVia: v.getState_DesignRuleBlindViaName(),
  locked: v.getState_PrimitiveLock()
}));
out.pcb.pours = ((await eda.pcb_PrimitivePour.getAll()) || []).map((z) => ({
  id: z.getState_PrimitiveId(), net: z.getState_Net(), layer: z.getState_Layer(),
  name: z.getState_PourName(), priority: z.getState_PourPriority(),
  fillMethod: z.getState_PourFillMethod(), lineWidth: z.getState_LineWidth(),
  preserveSilos: z.getState_PreserveSilos()
}));
out.pcb.outline = ((await eda.pcb_PrimitivePolyline.getAll(undefined, 11)) || []).map((o) => ({
  id: o.getState_PrimitiveId(), layer: o.getState_Layer(), polygon: o.getState_Polygon()
}));
out.pcb.outlineLines = ((await eda.pcb_PrimitiveLine.getAll(undefined, 11)) || []).map((l) => ({
  id: l.getState_PrimitiveId(), x1: l.getState_StartX(), y1: l.getState_StartY(), x2: l.getState_EndX(), y2: l.getState_EndY()
}));
out.pcb.layers = ((await eda.pcb_Layer.getAllLayers()) || []).filter((l) => l.layerStatus === 1);
out.pcb.nets = (await eda.pcb_Net.getAllNets()) || [];
out.pcb.netNames = (await eda.pcb_Net.getAllNetsName()) || [];
out.pcb.drcVerbose = await eda.pcb_Drc.check(true, false, true);
out.pcb.drcPass = await eda.pcb_Drc.check(true, false, false);
out.pcb.realtimeDrc = await eda.pcb_Drc.getRealTimeDrcStatus();
out.pcb.ruleName = await eda.pcb_Drc.getCurrentRuleConfigurationName();
out.pcb.rules = await eda.pcb_Drc.getCurrentRuleConfiguration();
out.pcb.netRules = await eda.pcb_Drc.getNetRules();
out.pcb.netByNetRules = await eda.pcb_Drc.getNetByNetRules();
out.pcb.netClasses = await eda.pcb_Drc.getAllNetClasses();
out.pcb.diffPairs = await eda.pcb_Drc.getAllDifferentialPairs();
out.pcb.equalLengthGroups = await eda.pcb_Drc.getAllEqualLengthNetGroups();
out.pcb.attrs = ((await eda.pcb_PrimitiveAttribute.getAll()) || []).map((a) => ({
  id: a.getState_PrimitiveId(), parent: a.getState_ParentPrimitiveId(), key: a.getState_Key(),
  value: a.getState_Value(), layer: a.getState_Layer(), visible: a.getState_ValueVisible(),
  x: a.getState_X(), y: a.getState_Y()
}));
out.pcb.strings = ((await eda.pcb_PrimitiveString.getAll()) || []).map((s) => ({
  id: s.getState_PrimitiveId(), text: s.getState_Text(), layer: s.getState_Layer(),
  x: s.getState_X(), y: s.getState_Y()
}));
const f = await eda.pcb_ManufactureData.getNetlistFile();
out.pcb.netlistText = f ? await f.text() : null;
return out;
