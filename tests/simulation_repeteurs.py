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
# Données au format de lan/browser (API_FREEBOX_OS.txt) : l2ident.id, primary_name,
# vendor_name, host_type, active, model, l3connectivities, access_point {type, mac, uid}.
# Pas d'API /repeater/ (non documentée) : api_repeaters vide.
hosts={}
def h(mac,name,model=None,ips=(),active=True):
    hosts[mac]={"l2ident":{"id":mac,"type":"mac_address"},"primary_name":name,"host_type":"networking_device",
      "vendor_name":"Freebox SAS","model":model,"active":active,
      "l3connectivities":[{"addr":ip,"af":"ipv6" if ":" in ip else "ipv4","active":active} for ip in ips]}
def v6(mac):  # SLAAC EUI-64 de la MAC principale
    b=[int(x,16) for x in mac.split(":")]; b[0]^=2
    return "fd0f:ee:b0:0:%02x%02x:%02xff:fe%02x:%02x%02x"%tuple(b)
REPS=[("8C:97:EA:55:BB:B6","16:E4:EF:4D:F7:1F","8E:97:EA:9B:1F:95","8C:97:EA:9B:1F:9","1","192.168.1.23","fbxwmr"),
      ("8C:97:EA:12:34:56","5A:11:22:33:44:55","8E:97:EA:AA:00:05","8C:97:EA:AA:00:0","2","192.168.1.24","fbxwmr-r2"),
      ("8C:97:EA:77:88:99","2E:66:77:88:99:00","8E:97:EA:CC:10:05","8C:97:EA:CC:10:0","3","192.168.1.25","fbxwmr")]
names=[("Repeteur Wifi Freebox","Repeteur Wifi Freebox #2","Repeteur-Wifi-Freebox-2"),
       ("Repeteur Wifi Freebox #2","Repeteur Wifi Freebox","Repeteur Wifi Freebox"),
       ("Repeteur Wifi Freebox Garage","Repeteur Wifi Freebox","Repeteur Wifi Freebox")]
for (main,eth,bh,fh,uid,ip,model),(n1,n2,n3) in zip(REPS,names):
    h(main,n1,model,[ip,v6(main)])
    h(bh,n2,model,[ip],active=False)       # backhaul Wi-Fi ponté : même IPv4
    h(eth,n3,"F-RP01A",[ip],active=False)  # backhaul Ethernet : même IPv4
    for k,suffix in enumerate(("0","4")):
        cm=f"AA:BB:CC:0{uid}:00:0{k}"
        hosts[cm]={"l2ident":{"id":cm},"primary_name":f"client{uid}{k}","active":True,"wifi":{"connectivity":"wifi"},
          "access_point":{"type":"repeater","mac":fh+suffix,"uid":uid,"connectivity_type":"wifi"}}
_,old=wa.build_wifi_aps(router_mac=RM,router_name="F",router_model="v7",devices=hosts)
aps,reps=wa.build_wifi_aps(router_mac=RM,router_name="F",router_model="v7",devices=hosts)
for k,v in reps.items(): print(k,v["name"],v["model"],v["client_count"],v["macs"]); print("   ",v["grouping"])
assert len(reps)==3, len(reps)
assert set(reps)=={"8C:97:EA:55:BB:B6","8C:97:EA:12:34:56","8C:97:EA:77:88:99"}
# BSSID des clients non reliés de façon fiable à un hôte : pas de fusion, pas d'appareil.
assert all(v["client_count"]==0 for v in reps.values())
# registry like user's: 9 devices
i=0
def dev(mac,area=None,model="fbxwmr",n=3,name="x"):
    global i; i+=1; did=f"dev{i}"; DEV[did]=Dev(did,[("d",f"repeater_{mac}")],[("mac",mac.lower())],area,model,name)
    for j in range(n): ENT[f"{did}_e{j}"]=[did,("sensor",f"u{did}{j}")]
    return did
for m,a,mo,n in [("8C:97:EA:55:BB:B6","test","fbxwmr",4),("8C:97:EA:12:34:56",None,"fbxwmr-r2",3),("8E:97:EA:9B:1F:95",None,"fbxwmr",4),("8E:97:EA:CC:10:05",None,"fbxwmr",3),
  ("8E:97:EA:AA:00:05",None,"fbxwmr-r2",3),("8C:97:EA:9B:1F:94",None,"fbxwmr",4),("8C:97:EA:77:88:99","garage","fbxwmr",3),("16:E4:EF:4D:F7:1F",None,"F-RP01A",3),("8C:97:EA:AA:00:04",None,"fbxwmr",3)]:
    dev(m,a,mo,n)
DEV["srv"]=Dev("srv",[("d",RM)],[("mac",RM.lower())])
ENT["stale"]=["dev6",("binary_sensor",f"{RM}_repeater_8C:97:EA:9B:1F:94")]
total=len([e for e,(d,k) in ENT.items() if k[0]!="binary_sensor"])
n=dg.async_merge_repeater_devices(None,types.SimpleNamespace(entry_id="E"),RM,reps)
left=[d for d in DEV if d!="srv"]
print("fusionnés:",n,"restants:",left)
# Hôtes fusionnés par IP partagée ; les 2 appareils « BSSID seul » (sans lien fiable)
# sont conservés (avertissement), pas fusionnés au hasard.
assert len(left)==5 and n==4, (left, n)
assert set(left)>={"dev1","dev2","dev7","dev6","dev9"}
assert len(ENT)==total+1  # rien de supprimé (l'entité « En ligne » du BSSID reste sur son appareil)
areas={DEV[d].area_id for d in ("dev1","dev2","dev7")}; assert areas=={"test",None,"garage"},areas
assert all(len(DEV[d].identifiers)==1 for d in left)
print("SIMULATION_OK")
