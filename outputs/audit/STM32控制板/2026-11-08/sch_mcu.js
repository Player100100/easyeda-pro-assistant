const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const PAGE_UUID = "240de6c063579f30";
const out = { page: { uuid: PAGE_UUID, name: "主控", components: [], wires: [], ercPass: null, ercVerbose: null, netlistText: null } };
const tabId = await eda.dmt_EditorControl.openDocument(PAGE_UUID);
if (tabId) await eda.dmt_EditorControl.activateDocument(tabId);
await sleep(2500);
const comps = (await eda.sch_PrimitiveComponent.getAll()) || [];
for (let i = 0; i < comps.length; i += 10) {
  const batch = comps.slice(i, i + 10);
  const recs = await Promise.all(batch.map(async (c) => {
    const id = c.getState_PrimitiveId();
    let pins = [];
    try {
      const ps = (await eda.sch_PrimitiveComponent.getAllPinsByPrimitiveId(id)) || [];
      pins = ps.map((pin) => ({
        id: pin.getState_PrimitiveId(), number: pin.getState_PinNumber(),
        name: pin.getState_PinName(), noConnected: pin.getState_NoConnected(),
        pinType: pin.getState_pinType(), x: pin.getState_X(), y: pin.getState_Y()
      }));
    } catch (e) { pins = [{ error: String(e) }]; }
    return {
      id: id, designator: c.getState_Designator(), name: c.getState_Name(),
      component: c.getState_Component(), symbol: c.getState_Symbol(), footprint: c.getState_Footprint(),
      rotation: c.getState_Rotation(), mirror: c.getState_Mirror(), x: c.getState_X(), y: c.getState_Y(),
      addIntoBom: c.getState_AddIntoBom(), addIntoPcb: c.getState_AddIntoPcb(),
      net: c.getState_Net(), manufacturer: c.getState_Manufacturer(),
      manufacturerId: c.getState_ManufacturerId(), supplier: c.getState_Supplier(),
      supplierId: c.getState_SupplierId(), other: c.getState_OtherProperty(), pins: pins
    };
  }));
  out.page.components.push.apply(out.page.components, recs);
}
out.page.wires = ((await eda.sch_PrimitiveWire.getAll()) || []).map((w) => ({
  id: w.getState_PrimitiveId(), net: w.getState_Net(), points: w.getState_Line(),
  lineWidth: w.getState_LineWidth()
}));
try { out.page.ercPass = await eda.sch_Drc.check(true, false, false); } catch (e) { out.page.ercPass = String(e); }
try { out.page.ercVerbose = await eda.sch_Drc.check(true, false, true); } catch (e) { out.page.ercVerbose = String(e); }
const f = await eda.sch_ManufactureData.getNetlistFile();
out.page.netlistText = f ? await f.text() : null;
return out;
