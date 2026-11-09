const out = { pcbNets: null, pcbNetlist: null, schNetlist: null, drc: null };
try { out.pcbNets = await eda.pcb_Net.getAllNets(); } catch(e){ out.pcbNets = 'ERR '+e; }
try { out.pcbNetlist = await eda.pcb_Net.getNetlist('EasyEDA'); } catch(e){ out.pcbNetlist = 'ERR '+e; }
try { out.schNetlist = await eda.sch_Netlist.getNetlist('EasyEDA'); } catch(e){ out.schNetlist = 'ERR '+e; }
try { out.drc = await eda.pcb_Drc.check(true,false,true); } catch(e){ out.drc = 'ERR '+e; }
return out;
