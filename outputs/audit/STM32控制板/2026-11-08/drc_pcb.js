const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));
const out={};
const boards=await eda.dmt_Board.getAllBoardsInfo();
const pcbUuid=boards[0].pcb.uuid;
const tabId=await eda.dmt_EditorControl.openDocument(pcbUuid);
if(tabId) await eda.dmt_EditorControl.activateDocument(tabId);
await sleep(3000);
out.checkVerbose=await eda.pcb_Drc.check(true,false,true);
out.checkSimple=await eda.pcb_Drc.check(true,false,false);
try{ out.netNames=await eda.pcb_Net.getAllNetName(); }catch(e){out.netNames='ERR '+e;}
return out;
