"""Simulation hors HA : cas réel de l'utilisateur après 28.8.49 (5 appareils pour 3 répéteurs).

Vérité terrain (app Freebox, firmware 2.9.3, backhaul Ethernet) :
  Grange        20:66:CF:4A:05:93  BSSID 22:66:CF:C9:A0:52 / 56
  Chambre fille 20:66:CF:4B:49:63  BSSID 22:66:CF:C6:92:D2 / D6
  Garage        20:66:CF:4B:49:69  BSSID 22:66:CF:96:92:D2 / D6
Lancer depuis la racine du dépôt : python3 tests/simulation_repeteurs_utilisateur.py
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
TRUTH={"Grange":("20:66:CF:4A:05:93","192.168.1.165","fd0f:ee:b0:0:2266:cfff:fe4a:593",["22:66:CF:C9:A0:52","22:66:CF:C9:A0:56"]),
       "Chambre fille":("20:66:CF:4B:49:63","192.168.1.87","fd0f:ee:b0:0:2266:cfff:fe4b:4963",["22:66:CF:C6:92:D2","22:66:CF:C6:92:D6"]),
       "Garage":("20:66:CF:4B:49:69","192.168.1.66","fd0f:ee:b0:0:2266:cfff:fe4b:4969",["22:66:CF:96:92:D2","22:66:CF:96:92:D6"])}
def lan(with_twins=True):
    hosts={}
    def h(mac,name,model,active=True,ips=()):
        hosts[mac]={"l2ident":{"id":mac,"type":"mac_address"},"primary_name":name,"host_type":"networking_device",
          "vendor_name":"Freebox SAS" if mac.startswith(("20:66:CF","22:66:CF")) else "","model":model,"active":active,
          "l3connectivities":[{"addr":ip} for ip in ips]}
    h("20:66:CF:4B:49:63","Repeteur Wifi Freebox","fbxwmr-r2",ips=TRUTH["Chambre fille"][1:3])
    h("20:66:CF:4B:49:69","Repeteur Wifi Freebox #2","fbxwmr-r2",ips=TRUTH["Garage"][1:3])
    h("20:66:CF:4A:05:93","Grange","fbxwmr-r2",ips=TRUTH["Grange"][1:3])
    if with_twins:
        h("22:66:CF:4B:49:69","Repeteur Wifi Freebox Garage","fbxwmr",active=False)
        h("22:66:CF:C6:92:D4","Repeteur-Wifi-Freebox-2","",active=False)
    for mac in ("AC:E2:D3:D9:E9:2E","AE:69:19:D4:56:AB","C0:F8:53:CE:6A:92"):
        h(mac,"Repeteur Wifi Freebox","fbxwmr",active=False)
    h("B4:E4:54:B7:EE:3E","Repeteur Wifi Freebox #2","fbxwmr",active=False)
    # Un client Wi-Fi par BSSID : access_point.mac = BSSID, uid opaque (sans lien avec la MAC principale).
    k=0
    for name,(_,_,_,bss) in TRUTH.items():
        for b in bss:
            k+=1; cm=f"02:00:00:00:00:{k:02X}"
            hosts[cm]={"l2ident":{"id":cm},"primary_name":f"tel{k}","host_type":"smartphone","vendor_name":"","active":True,
              "access_point":{"type":"repeater","mac":b,"uid":f"ap{k}","connectivity_type":"wifi"}}
    return hosts
API=[{"id":i,"name":n,"main_mac":m,"model":"fbxwmr-r2","status":"running",
      "backhaul":[{"type":"eth","mac":m}],"fronthaul":[{"bssid":b} for b in bss]} for i,(n,(m,_,_,bss)) in enumerate(TRUTH.items())]
# Registre HA actuel (28.8.49) : 5 appareils répéteurs + 4 anciens convertis en clients réseau.
REG=[("Repeteur Wifi Freebox","fbxwmr-r2","20:66:CF:4B:49:63",4,"test_freebox"),
     ("Repeteur Wifi Freebox Garage","fbxwmr","22:66:CF:4B:49:69",3,"garage"),
     ("Repeteur Wifi Freebox #2","fbxwmr-r2","20:66:CF:4B:49:69",3,None),
     ("Grange","fbxwmr-r2","20:66:CF:4A:05:93",4,"grange"),
     ("Repeteur-Wifi-Freebox-2","F-RP01A","22:66:CF:C6:92:D4",3,None)]
def run(label,hosts,api=None,manual=None,reg=REG):
    DEV.clear(); ENT.clear()
    aps,reps=wa.build_wifi_aps(router_mac=RM,router_name="F",router_model="v7",devices=hosts,api_repeaters=api,manual_links=manual)
    rej=aps["gateway"]["rejected_repeater_macs"]
    print(f"--- {label}")
    for k,v in reps.items(): print("   répéteur",k,repr(v["name"]),v["macs"],v["grouping"])
    for i,(name,model,mac,n,area) in enumerate(reg):
        did=f"dev{i}"; DEV[did]=Dev(did,[("d",f"repeater_{mac}")],[("mac",mac.lower())],area,model,name)
        for j in range(n): ENT[f"{did}_e{j}"]=[did,("sensor",f"u{did}{j}")]
    DEV["srv"]=Dev("srv",[("d",RM)],[("mac",RM.lower())])
    DEV["node"]=Dev("node",[("d",42)])  # identifiant int d'un nœud Home (plantage 28.8.47)
    total=len(ENT)
    dg.async_merge_repeater_devices(None,types.SimpleNamespace(entry_id="E"),RM,reps,rej,set(hosts))
    assert len(ENT)==total, "entités perdues"
    # Ajout des entités : HA applique le nom du DeviceInfo (nom du répéteur calculé).
    for d in DEV.values():
        for _,i in d.identifiers:
            if str(i).startswith("repeater_") and i[9:] in reps: d.name=reps[i[9:]]["name"]
    left={}
    for d in DEV.values():
        ids=[i for _,i in d.identifiers if str(i).startswith("repeater_")]
        if ids: left[ids[0][9:]]=(d.name_by_user or d.name,d.area_id,sum(1 for e in ENT.values() if e[0]==d.id))
    print("   appareils :",left)
    # Jamais de mauvaise fusion : chaque MAC principale reste son propre répéteur.
    mains={m for m,*_ in TRUTH.values()}
    for v in reps.values():
        assert len(mains & {x for x in v["macs"]})<=1, v["macs"]
    assert not set(rej) & {x for v in reps.values() for x in v["macs"]}
    return reps,left
def check3(left):
    assert set(left)=={"20:66:CF:4B:49:69","20:66:CF:4A:05:93","20:66:CF:4B:49:63"}, left
    g=left["20:66:CF:4B:49:69"]; assert "Garage" in g[0] and g[1]=="garage" and g[2]==6, g
    c=left["20:66:CF:4B:49:63"]; assert c[1]=="test_freebox" and c[2]==7, c
    assert left["20:66:CF:4A:05:93"]==("Grange","grange",4)

# 1. lan/browser seul (API /repeater/ indisponible) : Garage fusionné par le jumeau U/L exact ;
#    22:66:CF:C6:92:D4 rejoint le bloc BSSID C6:92:Dx mais rien ne relie ce bloc à 20:66:CF:4B:49:63.
reps,left=run("lan/browser seul",lan())
assert set(left)=={"20:66:CF:4B:49:69","20:66:CF:4A:05:93","20:66:CF:4B:49:63","22:66:CF:C6:92:D4"}, left
assert left["20:66:CF:4B:49:69"][1]=="garage" and "Garage" in left["20:66:CF:4B:49:69"][0]
assert "22:66:CF:96:92:D2" not in reps["22:66:CF:C6:92:D4"]["macs"]  # Garage ≠ Chambre fille (octet 4)
assert set(reps["22:66:CF:C6:92:D4"]["macs"])>={"22:66:CF:C6:92:D2","22:66:CF:C6:92:D6"}
# 2. + fusion manuelle choisie dans les options -> 3 répéteurs.
reps,left=run("lan/browser + fusion manuelle",lan(),manual=dg.migrate_repeater_merges({"22:66:cf:c6:92:d4":"20:66:CF:4B:49:63"}))
check3(left); assert len(reps)==3
assert len(reps["20:66:CF:4B:49:63"]["clients"])==2 and len(reps["20:66:CF:4B:49:69"]["clients"])==0
# 3. API /repeater/ disponible (fronthaul = BSSID) : tout est automatique.
reps,left=run("API /repeater/",lan(),api=API)
check3(left); assert len(reps)==3 and all(len(v["clients"])==2 for v in reps.values())
# 4. Doublons absents de lan/browser (registre seul) : le jumeau exact est quand même fusionné.
reps,left=run("doublons absents de lan/browser + API",lan(with_twins=False),api=API)
check3(left)
# 5. Ancien registre 28.8.47 (9 appareils) : même résultat.
reg9=REG+[("Repeteur Wifi Freebox","fbxwmr",m,4,None) for m in ("AC:E2:D3:D9:E9:2E","AE:69:19:D4:56:AB","C0:F8:53:CE:6A:92")]+[("Repeteur Wifi Freebox #2","fbxwmr","B4:E4:54:B7:EE:3E",4,None)]
reps,left=run("registre 28.8.47 (9 appareils) + API",lan(),api=API,reg=reg9)
check3(left)
# 6. Pièges : un hôte du bloc de Garage (96:92:Dx) ne rejoint jamais Chambre fille, et le jumeau
#    d'une MAC principale n'est jamais fusionné avec une autre principale « proche » (…49:63 / …49:69).
hosts=lan(); hosts["22:66:CF:96:92:D4"]=dict(hosts["22:66:CF:C6:92:D4"],l2ident={"id":"22:66:CF:96:92:D4"})
reps,_=run("piège bloc Garage",hosts,api=API)
assert "22:66:CF:96:92:D4" in reps["20:66:CF:4B:49:69"]["macs"] and "22:66:CF:96:92:D4" not in reps["20:66:CF:4B:49:63"]["macs"]
hosts=lan(); hosts.pop("20:66:CF:4B:49:69"); hosts.pop("22:66:CF:4B:49:69")
reps,_=run("piège Garage débranché",hosts)
assert not any("22:66:CF:4B:49:69" in v["macs"] or "20:66:CF:4B:49:69" in v["macs"] for v in reps.values())
# Jumeau périmé de Chambre fille (22:66:CF:4B:49:63) : rattaché à Chambre fille, pas à Garage.
reps,left=run("piège jumeau Chambre fille",lan(),api=API,reg=REG+[("Repeteur Wifi Freebox","fbxwmr","22:66:CF:4B:49:63",2,None)])
check3({k:(v if k!="20:66:CF:4B:49:63" else (v[0],v[1],v[2]-2)) for k,v in left.items()})
assert left["20:66:CF:4B:49:63"][2]==9 and left["20:66:CF:4B:49:69"][2]==6
assert dg.is_specific_repeater_name("Repeteur Wifi Freebox Garage") and dg.is_specific_repeater_name("Grange")
assert not any(dg.is_specific_repeater_name(n) for n in ("Repeteur Wifi Freebox","Repeteur Wifi Freebox #2","Repeteur-Wifi-Freebox-2",None))
print("SIMULATION_UTILISATEUR_OK")
