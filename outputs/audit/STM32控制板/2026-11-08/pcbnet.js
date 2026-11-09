const out={};
try{ out.pcb=await eda.pcb_Net.getNetlist('EasyEDA'); }catch(e){ out.pcb='ERR '+e; }
return out;
