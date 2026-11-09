const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));
const out={pages:[]};
const pages=[["接口","613cc1fb4d9e0a7b"],["电源","5d43f43155e9271e"],["主控","240de6c063579f30"]];
for(const [name,uuid] of pages){
  const tabId=await eda.dmt_EditorControl.openDocument(uuid);
  if(tabId) await eda.dmt_EditorControl.activateDocument(tabId);
  await sleep(2000);
  const rec={name:name,texts:[],attrs:[]};
  try{ const ts=await eda.sch_PrimitiveText.getAll(); rec.texts=(ts||[]).map(t=>({text:t.getState_Content(),x:t.getState_X?t.getState_X():null,y:t.getState_Y?t.getState_Y():null})); }catch(e){rec.texts=String(e);}
  out.pages.push(rec);
}
return out;
