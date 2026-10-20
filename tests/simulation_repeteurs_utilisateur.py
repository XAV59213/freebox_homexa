"""Simulation hors HA : 3 répéteurs (données API /repeater/ réalistes) et 9 appareils en double.

Lancer depuis la racine du dépôt : python3 tests/simulation_repeteurs.py
"""
import sys,types
for m in ["homeassistant","homeassistant.config_entries","homeassistant.core","homeassistant.helpers","homeassistant.helpers.entity_registry"]:
    sys.modules[m]=types.ModuleType(m)
sys.modules["homeassistant.config_entries"].ConfigEntry=object
sys.modules["homeassistant.core"].HomeAssistant=object
class Dev:
    def __init__(s,i,idents,conns=(),area=None,model=None,name=None):
        s.id=i; s.identifiers=set(idents); s.connections=set(conns); s.area_id=area; s.name_by_user=None; s.via_device_id=None; s.config_entry_id="E"; s.model=model; s.name=name
    @property
    def config_entries(s): raise AssertionError("config_entries déprécié lu")
DEV={}
class Reg:
    @property
    def devices(s): raise AssertionError("registry.devices utilisé")
    def async_get_device(s,**k): raise AssertionError("async_get_device déprécié")
    def async_get_device_by_identifier(s,ident,e): return next((d for d in DEV.values() if ident in d.identifiers and d.config_entry_id==e),None)
    def async_get_device_by_connection(s,c,e): return next((d for d in DEV.values() if c in d.connections and d.config_entry_id==e),None)
    def async_remove_device(s,i): DEV.pop(i)
    def async_update_device(s,i,**kw):
        assert "remove_config_entry_id" not in kw
        d=DEV[i]
        if "new_identifiers" in kw: d.identifiers=kw["new_identifiers"]
        for k in ("area_id","via_device_id","name_by_user"):
            if k in kw: setattr(d,k,kw[k])
R=Reg()
dr=types.ModuleType("dr"); dr.async_get=lambda h:R; dr.CONNECTION_NETWORK_MAC="mac"; dr.DeviceEntry=Dev
dr.async_entries_for_config_entry=lambda r,e:[d for d in list(DEV.values()) if d.config_entry_id==e]
sys.modules["homeassistant.helpers"].device_registry=dr; sys.modules["homeassistant.helpers.device_registry"]=dr
ENT={}
class ER:
    def async_get_entity_id(s,dom,plat,uid): return next((e for e,(d,k) in ENT.items() if k==(dom,uid)),None)
    def async_remove(s,e): ENT.pop(e)
    def async_update_entity(s,e,device_id): ENT[e][0]=device_id
er=sys.modules["homeassistant.helpers.entity_registry"]; sys.modules["homeassistant.helpers"].entity_registry=er
E_=ER(); er.async_get=lambda h:E_
er.async_entries_for_device=lambda r,did,include_disabled_entities: [types.SimpleNamespace(entity_id=e) for e,(d,k) in ENT.items() if d==did]
pkg=types.ModuleType("fh"); pkg.__path__=[]; sys.modules["fh"]=pkg
c=types.ModuleType("fh.const"); c.DOMAIN="d"; c.REPEATER_MODEL="F-RP01A"; c.FreeboxHomeCategory=type("C",(),{}); sys.modules["fh.const"]=c
def load(name):
    m=types.ModuleType("fh."+name); src=open(f"custom_components/freebox_homexa/{name}.py").read().replace("from .","from fh.")
    sys.modules["fh."+name]=m; exec(src,m.__dict__); return m
load("registry_compat"); dg=load("device_groups"); wa=load("wifi_ap")
RM="34:27:92:D9:E0:30"
# Cas réel de l'utilisateur (28.8.47) : 9 appareils, 3 répéteurs branchés.
hosts={}
def h(mac,name,model,active=True,ips=()):
    hosts[mac]={"l2ident":{"id":mac,"type":"mac_address"},"primary_name":name,"host_type":"networking_device",
      "vendor_name":"Freebox SAS" if mac.startswith(("20:66:CF","22:66:CF")) else "","model":model,"active":active,
      "l3connectivities":[{"addr":ip} for ip in ips]}
USER=[("Repeteur Wifi Freebox","fbxwmr","AC:E2:D3:D9:E9:2E",4,None),
      ("Repeteur Wifi Freebox Garage","fbxwmr","22:66:CF:4B:49:69",3,"garage"),
      ("Repeteur Wifi Freebox","fbxwmr-r2","20:66:CF:4B:49:63",4,"test_freebox"),
      ("Repeteur Wifi Freebox #2","fbxwmr-r2","20:66:CF:4B:49:69",3,None),
      ("Grange","fbxwmr-r2","20:66:CF:4A:05:93",4,"grange"),
      ("Repeteur Wifi Freebox","fbxwmr","AE:69:19:D4:56:AB",4,None),
      ("Repeteur Wifi Freebox #2","fbxwmr","B4:E4:54:B7:EE:3E",4,None),
      ("Repeteur-Wifi-Freebox-2","F-RP01A","22:66:CF:C6:92:D4",3,None),
      ("Repeteur Wifi Freebox","fbxwmr","C0:F8:53:CE:6A:92",3,None)]
for name,model,mac,_,_ in USER:
    h(mac,name,model,active=not mac.startswith(("AC","AE","B4","C0")))
aps,reps=wa.build_wifi_aps(router_mac=RM,router_name="F",router_model="v7",devices=hosts)
rej=aps["gateway"]["rejected_repeater_macs"]
for k,v in reps.items(): print("répéteur",k,v["name"],v["macs"],v["grouping"])
print("rejetés :",rej)
# Sans IP / uid / API : aucune fusion sur la seule proximité (Garage reste séparé).
assert set(reps)=={"20:66:CF:4B:49:63","20:66:CF:4B:49:69","22:66:CF:4B:49:69","20:66:CF:4A:05:93","22:66:CF:C6:92:D4"},set(reps)
assert set(rej)=={"AC:E2:D3:D9:E9:2E","AE:69:19:D4:56:AB","B4:E4:54:B7:EE:3E","C0:F8:53:CE:6A:92"}
i=0
for name,model,mac,n,area in USER:
    i+=1; did=f"dev{i}"; DEV[did]=Dev(did,[("d",f"repeater_{mac}")],[("mac",mac.lower())],area,model,name)
    for j in range(n): ENT[f"{did}_e{j}"]=[did,("sensor",f"u{did}{j}")]
DEV["srv"]=Dev("srv",[("d",RM)],[("mac",RM.lower())])
DEV["node"]=Dev("node",[("d",42)])  # identifiant int d'un nœud Home (plantage 28.8.47)
total=len(ENT)
n=dg.async_merge_repeater_devices(None,types.SimpleNamespace(entry_id="E"),RM,reps,rej,set(hosts))
reps_left=sorted((DEV[d].name,sorted(i for _,i in DEV[d].identifiers),DEV[d].area_id) for d in DEV if any(str(i).startswith("repeater_") for _,i in DEV[d].identifiers))
clients=sorted(DEV[d].name for d in DEV if d.startswith("dev") and not DEV[d].identifiers)
print("appareils répéteurs :",reps_left); print("convertis en clients :",clients)
assert len(reps_left)==5 and len(clients)==4 and len(ENT)==total
garage=[r for r in reps_left if r[2]=="garage"]; test=[r for r in reps_left if r[2]=="test_freebox"]
assert garage and test and garage[0][1]!=test[0][1]  # Garage jamais fusionné avec TEST FREEBOX

# Variante : si le jumeau 20/22 partage la même IP (signal fiable), il est fusionné.
hosts["20:66:CF:4B:49:69"]["l3connectivities"]=[{"addr":"192.168.1.40"}]
hosts["22:66:CF:4B:49:69"]["l3connectivities"]=[{"addr":"192.168.1.40"}]
_,reps2=wa.build_wifi_aps(router_mac=RM,router_name="F",router_model="v7",devices=hosts)
assert len(reps2)==4 and any(set(v["macs"])=={"20:66:CF:4B:49:69","22:66:CF:4B:49:69"} for v in reps2.values())
assert not any("20:66:CF:4B:49:63" in v["macs"] and len(v["macs"])>1 for v in reps2.values())
print("SIMULATION_UTILISATEUR_OK")
