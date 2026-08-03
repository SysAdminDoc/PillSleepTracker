#!/usr/bin/env python3
"""
 ===============================================================================
  PillSleepTracker Pro  -  Premium Desktop Health Widget
  A floating, always-on-top pill & sleep tracker with analytics
  Inspired by Microsoft Sticky Notes  |  Dark themed  |  Self-contained
 ===============================================================================
  Author : SysAdminDoc
  Version: 2.0
  License: MIT
 ===============================================================================
"""

# ==============================================================================
#  SECTION 1 : AUTO-BOOTSTRAP  (installs missing packages before any imports)
# ==============================================================================
import subprocess, sys, os, importlib

def _pip_install(package):
    for extra in [[], ["--user"], ["--break-system-packages"]]:
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", package, "-q"] + extra,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    return False

_REQUIRED = {"customtkinter": "customtkinter", "matplotlib": "matplotlib", "PIL": "Pillow", "cryptography": "cryptography"}
_OPTIONAL = {"pystray": "pystray",
             "winrt.windows.data.xml.dom": "winrt-Windows.Data.Xml.Dom",
             "winrt.windows.ui.notifications": "winrt-Windows.UI.Notifications"}
_FROZEN = bool(getattr(sys,"frozen",False))

_miss = []
if not _FROZEN:
    for _mod, _pkg in _REQUIRED.items():
        try: importlib.import_module(_mod)
        except ImportError: _miss.append(_pkg)
    if _miss:
        print(f"[PST] Installing: {', '.join(_miss)} ...")
        for _pkg in _miss:
            if not _pip_install(_pkg):
                print(f"  FAILED: {_pkg}  ->  pip install {_pkg}"); sys.exit(1)
        print("[PST] Ready.")
    for _mod, _pkg in _OPTIONAL.items():
        try: importlib.import_module(_mod)
        except ImportError: _pip_install(_pkg)

# ==============================================================================
#  SECTION 2 : IMPORTS
# ==============================================================================
import json, uuid, math, threading, csv
from html import escape
import tkinter as tk
from tkinter import messagebox, filedialog, simpledialog
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

import customtkinter as ctk
import matplotlib; matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from tracker_core import (
    adherence_for_day,
    adherence_rows,
    bedtime_consistency_coach,
    calculate_sleep_score,
    check_interactions,
    DATA_ENCRYPTION_PREFIX,
    DataPassphraseRequired,
    decrypt_json_payload,
    dose_status,
    due_doses as scheduled_due_doses,
    encrypt_json_payload,
    export_fhir_bundle,
    export_monthly_adherence_pdf,
    export_tracker_csv,
    latest_dose_action,
    import_wearable_csv,
    import_tracker_csv,
    hash_pin,
    MEQ_QUESTIONS,
    normalize_schedule_times,
    reorder_alerts as forecast_reorder_alerts,
    scheduled_doses_for_date,
    score_chronotype,
    normalize_tracker_data,
    verify_pin,
)

try:
    from PIL import Image, ImageDraw; HAS_PIL = True
except ImportError: HAS_PIL = False
try:
    import pystray; HAS_TRAY = True
except ImportError: HAS_TRAY = False
try:
    from winrt.windows.data.xml.dom import XmlDocument
    from winrt.windows.ui.notifications import ToastNotification, ToastNotificationManager
    HAS_NATIVE_TOAST = True
except ImportError:
    HAS_NATIVE_TOAST = False

# ==============================================================================
#  SECTION 3 : THEME & CONSTANTS
# ==============================================================================
class T:
    BG="#0d1117"; SURFACE="#161b22"; SURFACE_HI="#1c2333"; CARD="#1c2333"
    SIDEBAR="#0d1117"; SIDEBAR_ACT="#1c2333"; TITLEBAR="#010409"
    BLUE="#58a6ff"; GREEN="#3fb950"; RED="#f85149"; AMBER="#d29922"
    PURPLE="#bc8cff"; TEAL="#39d2c0"; PINK="#f778ba"
    TEXT="#e6edf3"; TEXT_SEC="#8b949e"; TEXT_MUTED="#484f58"
    BORDER="#30363d"; DIVIDER="#21262d"
    HOVER="#1f2a3d"; ACTIVE="#253048"
    INPUT_BG="#0d1117"; INPUT_BD="#30363d"
    BTN_PRI="#238636"; BTN_PRI_H="#2ea043"; BTN_DNG="#da3633"; BTN_DNG_H="#f85149"
    CHART_BG="#0d1117"; CHART_GRID="#21262d"; CHART_TICK="#8b949e"
    PAD_XS=4; PAD_SM=8; PAD_MD=12; PAD_LG=16; PAD_XL=24; RAD=8

PILL_COLOURS = {
    "Blue":"#58a6ff","Green":"#3fb950","Red":"#f85149","Amber":"#d29922",
    "Purple":"#bc8cff","Teal":"#39d2c0","Pink":"#f778ba","Orange":"#f0883e",
    "Cyan":"#76e3ea","White":"#e6edf3",
}
QUALITY_LABELS  = {1:"Terrible",2:"Poor",3:"Fair",4:"Good",5:"Excellent"}
QUALITY_COLOURS = {1:T.RED,2:"#f0883e",3:T.AMBER,4:T.GREEN,5:T.BLUE}
SLEEP_FACTORS   = ["Caffeine","Alcohol","Exercise","Screen Time","Stress","Nap","Late Meal","Medication"]

# ==============================================================================
#  SECTION 4 : DATA MANAGER
# ==============================================================================
DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / "PillSleepTracker"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATA_FILE = DATA_DIR / "tracker_data.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
DEFAULT_SETTINGS = {"window_x":150,"window_y":80,"window_w":520,"window_h":740,
                    "always_on_top":True,"opacity":0.96,"active_page":"dashboard",
                    "reminders_enabled":True,"reminder_grace_minutes":30,
                    "reminder_snooze_minutes":15,"low_stock_lead_days":7,
                    "native_notifications":True,"active_profile_id":"default",
                    "data_encrypted":False,"sync_folder":""}

class DataManager:
    def __init__(self, passphrase=None):
        self.settings = self._load(SETTINGS_FILE, DEFAULT_SETTINGS.copy())
        for k,v in DEFAULT_SETTINGS.items(): self.settings.setdefault(k,v)
        self.local_data_dir=DATA_DIR
        configured_folder=str(self.settings.get("sync_folder","")).strip()
        self.data_dir=Path(configured_folder).expanduser() if configured_folder else self.local_data_dir
        try: self.data_dir.mkdir(parents=True,exist_ok=True)
        except (IOError,OSError): self.data_dir=self.local_data_dir; self.settings["sync_folder"]=""
        self.data_file=self.data_dir/"tracker_data.json"
        self._data_passphrase = str(passphrase) if passphrase is not None else os.environ.get("PST_DATA_PASSPHRASE","")
        self.data_encrypted = False
        loaded = self._load_data_file()
        self.data = normalize_tracker_data(loaded)
        self.settings["data_encrypted"] = self.data_encrypted
        if not any(p.get("id")==self.settings.get("active_profile_id") for p in self.data["profiles"]):
            self.settings["active_profile_id"]="default"

    @staticmethod
    def _load(path, default):
        try:
            if path.exists():
                with open(path,"r",encoding="utf-8") as f: return json.load(f)
        except (json.JSONDecodeError, IOError): pass
        return default

    def save_settings(self): self._write(SETTINGS_FILE, self.settings)

    def _load_data_file(self, path=None):
        default={"medications":[],"med_log":[],"sleep_log":[],"profiles":[],"audit_log":[]}
        path=path or self.data_file
        if not path.exists(): return default
        try:
            text=path.read_text(encoding="utf-8")
        except (IOError, OSError): return default
        if text.lstrip().startswith(DATA_ENCRYPTION_PREFIX+"$"):
            if not self._data_passphrase: raise DataPassphraseRequired("A passphrase is required to open tracker_data.json.")
            loaded=decrypt_json_payload(text,self._data_passphrase); self.data_encrypted=True; return loaded
        try:
            loaded=json.loads(text); self.data_encrypted=False; return loaded
        except (json.JSONDecodeError,IOError): return default

    @staticmethod
    def _write(path, obj):
        try:
            tmp=path.with_suffix(".tmp")
            with open(tmp,"w",encoding="utf-8") as f: json.dump(obj,f,indent=2,ensure_ascii=False)
            tmp.replace(path)
        except IOError: pass

    @staticmethod
    def _write_text(path, text):
        try:
            tmp=path.with_suffix(".tmp"); tmp.write_text(text,encoding="utf-8"); tmp.replace(path)
        except (IOError,OSError): pass

    def save_data(self):
        if self.data_encrypted:
            if not self._data_passphrase: raise DataPassphraseRequired("A passphrase is required to save encrypted tracker data.")
            self._write_text(self.data_file,encrypt_json_payload(self.data,self._data_passphrase))
        else: self._write(self.data_file,self.data)

    def enable_encryption(self, passphrase):
        passphrase=str(passphrase)
        if len(passphrase)<8: raise ValueError("Use an encryption passphrase with at least 8 characters.")
        self._data_passphrase=passphrase; self.data_encrypted=True; self.settings["data_encrypted"]=True
        self._audit("enabled","encryption","",{"algorithm":"AES-GCM"},profile_id="")
        self.save_data(); self.save_settings()

    def disable_encryption(self):
        self.data_encrypted=False; self.settings["data_encrypted"]=False; self._audit("disabled","encryption","",{},profile_id=""); self._data_passphrase=""
        self.save_data(); self.save_settings()

    def configure_sync_folder(self, folder):
        target=Path(folder).expanduser(); target.mkdir(parents=True,exist_ok=True); target_file=target/"tracker_data.json"
        if target_file.exists(): incoming=self._load_data_file(target_file)
        else: incoming=self.data
        self.data_dir=target; self.data_file=target_file; self.data=normalize_tracker_data(incoming)
        self.settings["sync_folder"]="" if target.resolve()==self.local_data_dir.resolve() else str(target)
        self.settings["data_encrypted"]=self.data_encrypted
        self._audit("configured","sync_folder","",{"path":str(target)},profile_id="")
        self.save_data(); self.save_settings(); return self.data_dir

    def export_json(self, path): self._write(Path(path),self.data); return Path(path)
    def import_json(self, path):
        with open(path,"r",encoding="utf-8-sig") as handle: imported=json.load(handle)
        self.data=normalize_tracker_data(imported)
        if not any(p.get("id")==self.profile_id for p in self.data["profiles"]): self.settings["active_profile_id"]="default"
        self._audit("imported","tracker_data",Path(path).name,{"format":"json"},profile_id="")
        self.save_data(); self.save_settings(); return self.data
    def export_csv(self, path): return export_tracker_csv(path,self.data)
    def export_fhir(self, path): return export_fhir_bundle(path,self.meds,self.sleep_entries,self.profile)
    def import_csv(self, path):
        self.data=import_tracker_csv(path)
        if not any(p.get("id")==self.profile_id for p in self.data["profiles"]): self.settings["active_profile_id"]="default"
        self._audit("imported","tracker_data",Path(path).name,{"format":"csv"},profile_id="")
        self.save_data(); self.save_settings(); return self.data

    @property
    def profile_id(self): return self.settings.get("active_profile_id","default")
    @property
    def profile(self): return next((p for p in self.data["profiles"] if p.get("id")==self.profile_id),self.data["profiles"][0])
    @property
    def profiles(self): return self.data["profiles"]
    @property
    def meds(self): return [m for m in self.data["medications"] if m.get("profile_id","default")==self.profile_id and m.get("active",True)]
    @property
    def all_meds(self): return [m for m in self.data["medications"] if m.get("profile_id","default")==self.profile_id]
    @property
    def sleep_entries(self): return [s for s in self.data["sleep_log"] if s.get("profile_id","default")==self.profile_id]
    @property
    def audit_entries(self): return [e for e in self.data.get("audit_log",[]) if e.get("profile_id","") in ("",self.profile_id)]
    def _med_logs(self): return [l for l in self.data["med_log"] if l.get("profile_id","default")==self.profile_id]

    def _audit(self, action, entity, entity_id="", details=None, profile_id=None):
        event={"id":str(uuid.uuid4()),"timestamp":datetime.now().isoformat(timespec="seconds"),"action":str(action),
               "entity":str(entity),"entity_id":str(entity_id or ""),"profile_id":self.profile_id if profile_id is None else str(profile_id),
               "details":dict(details or {})}
        self.data.setdefault("audit_log",[]).append(event)
        self.data["audit_log"]=self.data["audit_log"][-2000:]

    def create_profile(self, name, pin=""):
        name=str(name).strip()
        if not name or any(p.get("name","").casefold()==name.casefold() for p in self.profiles): return None
        profile={"id":f"profile-{uuid.uuid4().hex[:12]}","name":name,"pin_hash":hash_pin(str(pin))}
        self.profiles.append(profile); self._audit("created","profile",profile["id"],{"name":name},profile_id=""); self.save_data(); return profile
    def switch_profile(self, profile_id, pin=""):
        profile=next((p for p in self.profiles if p.get("id")==profile_id),None)
        if not profile or not verify_pin(str(pin),profile.get("pin_hash","")): return False
        previous=self.profile_id; self.settings["active_profile_id"]=profile_id; self._audit("switched","profile",profile_id,{"from":previous},profile_id=""); self.save_data(); self.save_settings(); return True
    def delete_profile(self, profile_id):
        if profile_id=="default" or profile_id==self.profile_id: return False
        profile=next((p for p in self.profiles if p.get("id")==profile_id),None)
        if not profile: return False
        self.data["profiles"]=[p for p in self.profiles if p.get("id")!=profile_id]
        for key in ("medications","med_log","sleep_log"): self.data[key]=[item for item in self.data[key] if item.get("profile_id","default")!=profile_id]
        self._audit("deleted","profile",profile_id,{"name":profile.get("name","")},profile_id="")
        self.save_data(); return True

    def add_med(self, d):
        d.setdefault("id",str(uuid.uuid4())); d.setdefault("created",datetime.now().isoformat())
        d.setdefault("active",True); d.setdefault("profile_id",self.profile_id); d.setdefault("clinician","")
        d.setdefault("refill_history",[]); d.setdefault("dose_changes",[]); d.setdefault("photo_path","")
        self.data["medications"].append(d); self._audit("created","medication",d["id"],{"name":d.get("name","")}); self.save_data()
    def update_med(self, mid, upd):
        upd=dict(upd)
        for m in self.data["medications"]:
            if m["id"]==mid and m.get("profile_id","default")==self.profile_id:
                note=upd.pop("dose_change_note","") if isinstance(upd,dict) else ""
                changed=[key for key,value in upd.items() if m.get(key)!=value]
                if "dosage" in upd and upd.get("dosage")!=m.get("dosage"):
                    m.setdefault("dose_changes",[]).append({"date":datetime.now().strftime("%Y-%m-%d"),"from":m.get("dosage",""),"to":upd.get("dosage",""),"notes":note})
                m.update(upd)
                if changed: self._audit("updated","medication",mid,{"name":m.get("name",""),"fields":changed})
                break
        self.save_data()
    def delete_med(self, mid):
        med=self.get_med(mid)
        self.data["medications"]=[m for m in self.data["medications"] if m["id"]!=mid or m.get("profile_id","default")!=self.profile_id]
        if med: self._audit("deleted","medication",mid,{"name":med.get("name","")})
        self.save_data()
    def get_med(self, mid):
        for m in self.data["medications"]:
            if m["id"]==mid and m.get("profile_id","default")==self.profile_id: return m
        return None
    def record_refill(self, mid, quantity, note=""):
        med=self.get_med(mid)
        try: quantity=int(quantity)
        except (TypeError,ValueError): return False
        if not med or quantity<=0: return False
        if med.get("supply") is None: med["supply"]=quantity
        else: med["supply"]+=quantity
        med.setdefault("refill_history",[]).append({"date":datetime.now().strftime("%Y-%m-%d"),"quantity":quantity,"note":str(note).strip()})
        self._audit("refilled","medication",mid,{"name":med.get("name",""),"quantity":quantity})
        self.save_data(); return True
    def interaction_findings(self): return check_interactions(self.meds)

    def _dose_for_med(self, mid, now=None):
        now=now or datetime.now()
        med=self.get_med(mid)
        if not med: return None
        candidates=scheduled_doses_for_date(med,now.date())
        for dose in candidates:
            logs=self._med_logs()
            if dose_status(dose,logs,now,int(self.settings.get("reminder_grace_minutes",30))) in {"due","snoozed","upcoming"}:
                if not latest_dose_action(logs,dose) or latest_dose_action(logs,dose).get("action") not in {"taken","skipped"}:
                    return dose
        return candidates[0] if candidates else None

    def log_dose_action(self, mid, action="taken", dose=None, snooze_minutes=None, reason=""):
        med=self.get_med(mid)
        if not med: return False
        now=datetime.now()
        if dose is None: dose=self._dose_for_med(mid,now)
        if isinstance(dose,dict):
            dose_id=dose.get("dose_id"); scheduled_for=dose.get("scheduled_for"); dose_date=dose.get("date")
        else:
            dose_id=dose.dose_id if dose else None
            scheduled_for=dose.scheduled_for.isoformat(timespec="minutes") if dose else None
            dose_date=dose.date if dose else now.strftime("%Y-%m-%d")
        if dose_id and any(l.get("dose_id")==dose_id and l.get("action") in {"taken","skipped"} for l in self._med_logs()):
            return False
        entry={"med_id":mid,"med_name":med.get("name",str(mid)),"profile_id":self.profile_id,"date":dose_date or now.strftime("%Y-%m-%d"),
               "time":now.strftime("%H:%M:%S"),"action":action,"logged_at":now.isoformat(timespec="seconds")}
        if dose_id: entry.update({"dose_id":dose_id,"scheduled_for":scheduled_for})
        if reason.strip(): entry["reason"]=reason.strip()
        if action=="snoozed":
            minutes=max(1,int(snooze_minutes or self.settings.get("reminder_snooze_minutes",15)))
            entry["snooze_until"]=(now+timedelta(minutes=minutes)).isoformat(timespec="seconds")
        self.data["med_log"].append(entry)
        if action=="taken" and med.get("supply") is not None and med["supply"]>0: med["supply"]-=1
        self._audit(action,"med_log",dose_id or mid,{"medication":med.get("name","")})
        self.save_data()
        return True

    def log_taken(self, mid, name=None, dose=None):
        return self.log_dose_action(mid,"taken",dose=dose)

    def log_skipped(self, mid, dose=None, reason=""):
        return self.log_dose_action(mid,"skipped",dose=dose,reason=reason)

    def snooze_dose(self, mid, dose=None, minutes=None):
        return self.log_dose_action(mid,"snoozed",dose=dose,snooze_minutes=minutes)

    def undo_taken(self, mid, date=None, dose_id=None):
        date=date or datetime.now().strftime("%Y-%m-%d")
        removed=False
        for i in range(len(self.data["med_log"])-1,-1,-1):
            l=self.data["med_log"][i]
            if l.get("profile_id","default")==self.profile_id and l["med_id"]==mid and l["date"]==date and l["action"]=="taken" and (not dose_id or l.get("dose_id")==dose_id):
                self.data["med_log"].pop(i)
                med=self.get_med(mid)
                if med and med.get("supply") is not None: med["supply"]+=1
                self._audit("undone","med_log",l.get("dose_id") or mid,{"medication":l.get("med_name","")})
                removed=True
                break
        self.save_data()
        return removed

    def taken_today(self, mid):
        d=datetime.now().strftime("%Y-%m-%d")
        return any(l.get("profile_id","default")==self.profile_id and l["med_id"]==mid and l["date"]==d and l["action"]=="taken" for l in self.data["med_log"])
    def taken_on_date(self, mid, d):
        return any(l.get("profile_id","default")==self.profile_id and l["med_id"]==mid and l["date"]==d and l["action"]=="taken" for l in self.data["med_log"])

    def adherence_for_range(self, days=7):
        result=[]
        for i in range(days-1,-1,-1):
            day=datetime.now().date()-timedelta(days=i); d=day.strftime("%Y-%m-%d")
            taken,total,_=adherence_for_day(self.meds,self._med_logs(),day)
            result.append((d, taken/total if total else 0))
        return result

    def due_doses(self, now=None):
        return scheduled_due_doses(self.meds,self._med_logs(),now,int(self.settings.get("reminder_grace_minutes",30)))

    def reorder_alerts(self, now=None):
        return forecast_reorder_alerts(self.meds,self._med_logs(),now,int(self.settings.get("low_stock_lead_days",7)))

    def monthly_adherence_report(self, year=None, month=None):
        now=datetime.now(); year=year or now.year; month=month or now.month
        return adherence_rows(self.meds,self._med_logs(),year,month)

    def export_monthly_adherence_pdf(self, path, year=None, month=None):
        now=datetime.now(); year=year or now.year; month=month or now.month
        return export_monthly_adherence_pdf(path,self.meds,self._med_logs(),year,month)

    def log_sleep(self, entry):
        entry.setdefault("id",str(uuid.uuid4()))
        entry.setdefault("logged_at",datetime.now().isoformat())
        entry.setdefault("is_nap",False)
        entry.setdefault("profile_id",self.profile_id)
        if entry.get("is_nap"):
            self.data["sleep_log"]=[s for s in self.data["sleep_log"] if not (s.get("profile_id","default")==self.profile_id and s.get("id")==entry.get("id"))]
        else:
            self.data["sleep_log"]=[s for s in self.data["sleep_log"] if s.get("profile_id","default")!=self.profile_id or s.get("date")!=entry["date"] or s.get("is_nap",False)]
        self.data["sleep_log"].append(entry); self._audit("created","sleep_log",entry["id"],{"date":entry.get("date",""),"is_nap":bool(entry.get("is_nap"))}); self.save_data()
    def get_sleep(self, d):
        for s in self.data["sleep_log"]:
            if s.get("profile_id","default")==self.profile_id and s.get("date")==d and not s.get("is_nap",False): return s
        return None
    def sleep_for_range(self, days=14):
        r=[]
        for i in range(days-1,-1,-1):
            d=(datetime.now()-timedelta(days=i)).strftime("%Y-%m-%d"); r.append((d,self.get_sleep(d)))
        return r
    def import_sleep_csv(self, path, provider=None):
        entries=import_wearable_csv(path,provider)
        existing={(s.get("source"),s.get("source_id")) for s in self.sleep_entries if s.get("source")}
        added=0
        for entry in entries:
            if (entry.get("source"),entry.get("source_id")) in existing:
                continue
            self.log_sleep(entry); added+=1
        return added,len(entries)

    def pill_streak(self):
        if not self.meds: return 0
        streak=0
        for i in range(365):
            day=datetime.now().date()-timedelta(days=i)
            taken,total,_=adherence_for_day(self.meds,self._med_logs(),day)
            if total and taken==total: streak+=1
            elif i==0: continue
            else: break
        return streak
    def sleep_streak(self):
        streak=0
        for i in range(365):
            d=(datetime.now()-timedelta(days=i)).strftime("%Y-%m-%d")
            if self.get_sleep(d): streak+=1
            elif i==0: continue
            else: break
        return streak

    @staticmethod
    def calc_sleep_score(dur_min, quality, recent_bedtimes=None, chronotype=None):
        return calculate_sleep_score(dur_min,quality,recent_bedtimes,chronotype)

# ==============================================================================
#  SECTION 5 : CUSTOM WIDGETS
# ==============================================================================
class ToastManager:
    def __init__(self, parent): self.parent=parent; self._active=[]
    def show(self, msg, kind="info", ms=3000, actions=None):
        clrs={"info":(T.BLUE,"#0d2240"),"success":(T.GREEN,"#0d2a1a"),
              "warning":(T.AMBER,"#2a2000"),"error":(T.RED,"#2a0d0d")}
        fg,bg=clrs.get(kind,clrs["info"])
        t=ctk.CTkFrame(self.parent,fg_color=bg,corner_radius=8,border_width=1,border_color=fg)
        t.place(relx=0.5,rely=0.0,anchor="n",y=8); t.lift()
        ctk.CTkLabel(t,text=f"  {msg}  ",text_color=fg,
                      font=ctk.CTkFont(size=12,weight="bold")).pack(padx=12,pady=(8,4))
        if actions:
            ar=ctk.CTkFrame(t,fg_color="transparent"); ar.pack(fill="x",padx=8,pady=(0,8))
            for label,callback in actions:
                ctk.CTkButton(ar,text=label,height=25,font=ctk.CTkFont(size=10,weight="bold"),
                              fg_color=T.SURFACE,hover_color=T.HOVER,text_color=fg,
                              command=lambda cb=callback:self._run_action(t,cb)).pack(side="left",fill="x",expand=True,padx=2)
        self._active.append(t)
        self.parent.after(ms, lambda: self._kill(t))
        return t
    def _run_action(self,t,callback):
        self._kill(t)
        try: callback()
        except Exception: pass
    def _kill(self,t):
        try: t.destroy()
        except Exception: pass
        if t in self._active: self._active.remove(t)


class NativeToastManager:
    """Optional Windows toast provider with protocol-backed dose actions."""
    APP_ID="PillSleepTracker.Pro"
    def __init__(self, dm):
        self.dm=dm
        self.enabled=HAS_NATIVE_TOAST and sys.platform=="win32" and not os.environ.get("PST_TEST_MODE")
    def show_dose(self,dose):
        if not self.enabled or not self.dm.settings.get("native_notifications",True): return False
        try:
            from urllib.parse import quote
            dose_id=quote(str(dose.get("dose_id","")),safe="")
            name=str(dose.get("med_name","Medication"))
            status=str(dose.get("status","due")).title()
            xml=("<toast launch=\"pillsleeptracker://dose/view/{0}\"><visual><binding template=\"ToastGeneric\">"
                 "<text>{1}</text><text>{2} dose scheduled for {3}</text></binding></visual><actions>"
                 "<action content=\"Take\" activationType=\"protocol\" arguments=\"pillsleeptracker://dose/taken/{0}\"/>"
                 "<action content=\"Snooze\" activationType=\"protocol\" arguments=\"pillsleeptracker://dose/snooze/{0}\"/>"
                 "<action content=\"Skip\" activationType=\"protocol\" arguments=\"pillsleeptracker://dose/skipped/{0}\"/>"
                 "</actions></toast>").format(dose_id,escape(name),escape(status),escape(str(dose.get("scheduled_for",""))))
            doc=XmlDocument(); doc.load_xml(xml)
            notification=ToastNotification(doc)
            ToastNotificationManager.create_toast_notifier(self.APP_ID).show(notification)
            return True
        except Exception:
            return False


def _register_toast_protocol():
    if sys.platform!="win32" or not HAS_NATIVE_TOAST or os.environ.get("PST_TEST_MODE"): return
    try:
        import winreg
        if _FROZEN:
            command=f'"{sys.executable}" "%1"'
        else:
            command=f'"{sys.executable}" "{Path(__file__).resolve()}" "%1"'
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r"Software\Classes\pillsleeptracker") as key:
            winreg.SetValueEx(key,"",0,winreg.REG_SZ,"URL:PillSleepTracker Protocol")
            winreg.SetValueEx(key,"URL Protocol",0,winreg.REG_SZ,"")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r"Software\Classes\pillsleeptracker\shell\open\command") as key:
            winreg.SetValueEx(key,"",0,winreg.REG_SZ,command)
    except (OSError,ImportError):
        pass


class ReminderManager:
    def __init__(self, app, dm, toast):
        self.app=app; self.dm=dm; self.toast=toast; self.native=NativeToastManager(dm)
        self._seen_doses=set(); self._seen_stock=set(); self._after_id=None
    def start(self): self._check()
    def stop(self):
        if self._after_id:
            try: self.app.after_cancel(self._after_id)
            except Exception: pass
            self._after_id=None
    def _refresh(self):
        try: self.app._nav(self.dm.settings.get("active_page","dashboard"))
        except Exception: pass
    def _take(self,dose):
        if self.dm.log_dose_action(dose["med_id"],"taken",dose=dose):
            self.toast.show(f"{dose['med_name']} taken","success"); self._refresh()
    def _snooze(self,dose):
        if self.dm.snooze_dose(dose["med_id"],dose=dose):
            self.toast.show(f"Snoozed {dose['med_name']}","info"); self._seen_doses.discard(dose["dose_id"])
    def _skip(self,dose):
        if self.dm.log_skipped(dose["med_id"],dose=dose):
            self.toast.show(f"Skipped {dose['med_name']}","warning"); self._refresh()
    def _check(self):
        if self.dm.settings.get("reminders_enabled",True):
            for dose in self.dm.due_doses():
                key=f"{dose['dose_id']}:{dose.get('status')}:{dose.get('snooze_until')}"
                if key in self._seen_doses: continue
                self._seen_doses.add(key)
                label="Missed" if dose.get("status")=="missed" else "Dose due"
                self.toast.show(f"{label}: {dose['med_name']}","warning",ms=12000,
                                actions=[("Take",lambda d=dose:self._take(d)),
                                         ("Snooze",lambda d=dose:self._snooze(d)),
                                         ("Skip",lambda d=dose:self._skip(d))])
                self.native.show_dose(dose)
            today=datetime.now().strftime("%Y-%m-%d")
            for alert in self.dm.reorder_alerts():
                key=f"{today}:{alert['med_id']}"
                if key in self._seen_stock: continue
                self._seen_stock.add(key)
                days=f"~{alert['days_left']} days left" if alert.get("days_left") is not None else "reorder soon"
                self.toast.show(f"Low stock: {alert['name']} ({days})","warning",ms=10000)
        self._after_id=self.app.after(60000,self._check)

class StatCard(ctk.CTkFrame):
    def __init__(self, parent, title="", value="", sub="", accent=T.BLUE, **kw):
        super().__init__(parent,fg_color=T.CARD,corner_radius=T.RAD,border_width=1,border_color=T.BORDER,**kw)
        f=ctk.CTkFrame(self,fg_color="transparent"); f.pack(fill="both",expand=True,padx=T.PAD_MD,pady=T.PAD_SM)
        ctk.CTkLabel(f,text=title,font=ctk.CTkFont(size=11),text_color=T.TEXT_SEC).pack(anchor="w")
        self._v=ctk.CTkLabel(f,text=value,font=ctk.CTkFont(size=22,weight="bold"),text_color=accent)
        self._v.pack(anchor="w",pady=(2,0))
        self._s=ctk.CTkLabel(f,text=sub,font=ctk.CTkFont(size=10),text_color=T.TEXT_MUTED)
        self._s.pack(anchor="w")
    def update_values(self, v=None, s=None, a=None):
        if v is not None: self._v.configure(text=v)
        if s is not None: self._s.configure(text=s)
        if a is not None: self._v.configure(text_color=a)

class ChartFrame(ctk.CTkFrame):
    def __init__(self, parent, title="", height=200, **kw):
        super().__init__(parent,fg_color=T.CARD,corner_radius=T.RAD,border_width=1,border_color=T.BORDER,**kw)
        if title:
            ctk.CTkLabel(self,text=title,font=ctk.CTkFont(size=13,weight="bold"),
                          text_color=T.TEXT).pack(anchor="w",padx=T.PAD_MD,pady=(T.PAD_SM,0))
        self.fig=Figure(figsize=(5,height/100),dpi=100,facecolor=T.CHART_BG)
        self.fig.subplots_adjust(left=0.12,right=0.96,top=0.92,bottom=0.22)
        self.ax=self.fig.add_subplot(111); self._style()
        self.canvas=FigureCanvasTkAgg(self.fig,master=self)
        self.canvas.get_tk_widget().configure(bg=T.CHART_BG,highlightthickness=0)
        self.canvas.get_tk_widget().pack(fill="both",expand=True,padx=4,pady=(0,4))
    def _style(self):
        ax=self.ax; ax.set_facecolor(T.CHART_BG)
        ax.tick_params(colors=T.CHART_TICK,labelsize=8)
        for sp in ("top","right"): ax.spines[sp].set_visible(False)
        for sp in ("bottom","left"): ax.spines[sp].set_color(T.CHART_GRID)
        ax.yaxis.label.set_color(T.CHART_TICK); ax.xaxis.label.set_color(T.CHART_TICK)
        ax.grid(axis="y",color=T.CHART_GRID,linewidth=0.5,alpha=0.5)
    def redraw(self): self.ax.clear(); self._style()
    def render(self):
        try: self.fig.tight_layout(pad=0.8)
        except: pass
        self.canvas.draw_idle()

# ==============================================================================
#  SECTION 6 : SIDEBAR
# ==============================================================================
class Sidebar(ctk.CTkFrame):
    ITEMS=[("dashboard","Home"),("meds","Meds"),("sleep","Sleep"),("analytics","Stats"),("settings","Gear")]
    def __init__(self, parent, on_nav, **kw):
        super().__init__(parent,width=62,fg_color=T.SIDEBAR,corner_radius=0,**kw)
        self.pack_propagate(False); self._nav=on_nav; self._btns={}
        ctk.CTkLabel(self,text="PST",font=ctk.CTkFont(size=15,weight="bold"),
                      text_color=T.BLUE).pack(pady=(14,16))
        for key,label in self.ITEMS:
            b=ctk.CTkButton(self,text=label,width=56,height=44,font=ctk.CTkFont(size=10),
                             fg_color="transparent",hover_color=T.HOVER,text_color=T.TEXT_SEC,
                             anchor="center",corner_radius=6,command=lambda k=key:self._go(k))
            b.pack(pady=2,padx=3); self._btns[key]=b
        ctk.CTkFrame(self,fg_color="transparent",height=1).pack(fill="both",expand=True)
        self._clk=ctk.CTkLabel(self,text="",font=ctk.CTkFont(size=9),text_color=T.TEXT_MUTED)
        self._clk.pack(pady=(0,8)); self._tick()
    def _go(self,k): self.set_active(k); self._nav(k)
    def set_active(self,k):
        for key,btn in self._btns.items():
            btn.configure(fg_color=T.SIDEBAR_ACT if key==k else "transparent",
                          text_color=T.BLUE if key==k else T.TEXT_SEC)
    def _tick(self):
        self._clk.configure(text=datetime.now().strftime("%H:%M")); self._clk.after(30000,self._tick)

# ==============================================================================
#  SECTION 7 : PAGES
# ==============================================================================

# ── 7A : DASHBOARD ───────────────────────────────────────────────────────────
class DashboardPage(ctk.CTkScrollableFrame):
    def __init__(self, parent, dm, toast, on_nav, **kw):
        super().__init__(parent,fg_color=T.BG,scrollbar_button_color=T.BORDER,
                         scrollbar_button_hover_color=T.TEXT_MUTED,**kw)
        self.dm=dm; self.toast=toast; self._nav=on_nav; self._build()

    def _build(self):
        h=datetime.now().hour
        greet="Good morning" if h<12 else "Good afternoon" if h<18 else "Good evening"
        ctk.CTkLabel(self,text=greet,font=ctk.CTkFont(size=20,weight="bold"),
                      text_color=T.TEXT).pack(anchor="w",padx=T.PAD_LG,pady=(T.PAD_MD,2))
        ctk.CTkLabel(self,text=datetime.now().strftime("%A, %B %d, %Y"),font=ctk.CTkFont(size=12),
                      text_color=T.TEXT_SEC).pack(anchor="w",padx=T.PAD_LG,pady=(0,T.PAD_MD))

        # Stat cards
        sr=ctk.CTkFrame(self,fg_color="transparent"); sr.pack(fill="x",padx=T.PAD_MD,pady=(0,T.PAD_SM))
        sr.columnconfigure((0,1,2),weight=1,uniform="s")
        self.c_adh=StatCard(sr,"Today's Meds","--",""); self.c_adh.grid(row=0,column=0,padx=3,pady=3,sticky="nsew")
        self.c_slp=StatCard(sr,"Last Sleep","--","",T.PURPLE); self.c_slp.grid(row=0,column=1,padx=3,pady=3,sticky="nsew")
        self.c_str=StatCard(sr,"Pill Streak","--","",T.AMBER); self.c_str.grid(row=0,column=2,padx=3,pady=3,sticky="nsew")

        # Quick Take header
        qh=ctk.CTkFrame(self,fg_color="transparent"); qh.pack(fill="x",padx=T.PAD_LG,pady=(T.PAD_SM,4))
        ctk.CTkLabel(qh,text="Quick Take",font=ctk.CTkFont(size=14,weight="bold"),text_color=T.TEXT).pack(side="left")
        ctk.CTkButton(qh,text="Manage >",width=80,height=24,font=ctk.CTkFont(size=11),fg_color="transparent",
                       hover_color=T.HOVER,text_color=T.BLUE,command=lambda:self._nav("meds")).pack(side="right")
        self._qt=ctk.CTkFrame(self,fg_color=T.CARD,corner_radius=T.RAD,border_width=1,border_color=T.BORDER)
        self._qt.pack(fill="x",padx=T.PAD_MD,pady=(0,T.PAD_SM))

        # Sleep summary header
        sh=ctk.CTkFrame(self,fg_color="transparent"); sh.pack(fill="x",padx=T.PAD_LG,pady=(T.PAD_SM,4))
        ctk.CTkLabel(sh,text="Sleep Overview",font=ctk.CTkFont(size=14,weight="bold"),text_color=T.TEXT).pack(side="left")
        ctk.CTkButton(sh,text="Log Sleep >",width=90,height=24,font=ctk.CTkFont(size=11),fg_color="transparent",
                       hover_color=T.HOVER,text_color=T.BLUE,command=lambda:self._nav("sleep")).pack(side="right")
        self._sc=ctk.CTkFrame(self,fg_color=T.CARD,corner_radius=T.RAD,border_width=1,border_color=T.BORDER)
        self._sc.pack(fill="x",padx=T.PAD_MD,pady=(0,T.PAD_SM))

        self._alerts=ctk.CTkFrame(self,fg_color="transparent"); self._alerts.pack(fill="x",padx=T.PAD_MD,pady=(0,T.PAD_MD))

    def refresh(self):
        meds=self.dm.meds; taken=sum(1 for m in meds if self.dm.taken_today(m["id"])); total=len(meds)
        pct=f"{taken}/{total}" if total else "No meds"
        sub="All done!" if taken==total and total>0 else f"{total-taken} remaining" if total else ""
        acc=T.GREEN if taken==total and total>0 else T.BLUE
        self.c_adh.update_values(pct,sub,acc)

        today=datetime.now().strftime("%Y-%m-%d")
        sleep=self.dm.get_sleep(today) or self.dm.get_sleep((datetime.now()-timedelta(days=1)).strftime("%Y-%m-%d"))
        if sleep:
            dh,dm_=sleep.get("duration_min",0)//60, sleep.get("duration_min",0)%60
            q=sleep.get("quality",3); sc=sleep.get("score","--")
            self.c_slp.update_values(f"{dh}h {dm_}m",f"Score: {sc}  |  {QUALITY_LABELS.get(q,'')}",
                                      QUALITY_COLOURS.get(q,T.PURPLE))
        else: self.c_slp.update_values("--","Not logged",T.TEXT_MUTED)

        streak=self.dm.pill_streak()
        self.c_str.update_values(str(streak),f"consecutive day{'s' if streak!=1 else ''}",T.AMBER)

        # Quick Take grid
        for w in self._qt.winfo_children(): w.destroy()
        if not meds:
            ctk.CTkLabel(self._qt,text="No medications added yet.",font=ctk.CTkFont(size=12),
                          text_color=T.TEXT_MUTED).pack(pady=T.PAD_LG)
        else:
            g=ctk.CTkFrame(self._qt,fg_color="transparent"); g.pack(fill="x",padx=T.PAD_SM,pady=T.PAD_SM)
            for idx,med in enumerate(meds):
                done=self.dm.taken_today(med["id"]); color=med.get("color",T.BLUE)
                r,c=divmod(idx,2); g.columnconfigure(c,weight=1)
                bf=ctk.CTkFrame(g,fg_color=T.SURFACE if not done else "#0d2a1a",corner_radius=6,
                                 border_width=1,border_color=color if not done else T.GREEN)
                bf.grid(row=r,column=c,padx=3,pady=3,sticky="nsew")
                inn=ctk.CTkFrame(bf,fg_color="transparent"); inn.pack(fill="x",padx=T.PAD_SM,pady=T.PAD_SM)
                nr=ctk.CTkFrame(inn,fg_color="transparent"); nr.pack(fill="x")
                ctk.CTkFrame(nr,width=10,height=10,fg_color=color,corner_radius=5).pack(side="left",padx=(0,6),pady=2)
                ctk.CTkLabel(nr,text=med["name"],font=ctk.CTkFont(size=12,weight="bold"),
                              text_color=T.TEXT if not done else T.GREEN,anchor="w").pack(side="left",fill="x",expand=True)
                if med.get("dosage"):
                    ctk.CTkLabel(inn,text=med["dosage"],font=ctk.CTkFont(size=10),text_color=T.TEXT_MUTED).pack(anchor="w")
                if done:
                    ctk.CTkButton(inn,text="Taken  \u2713",height=26,font=ctk.CTkFont(size=11),
                                   fg_color=T.GREEN,hover_color="#2ea043",text_color="#0d1117",
                                   command=lambda m=med:self._undo(m)).pack(fill="x",pady=(4,0))
                else:
                    ctk.CTkButton(inn,text="Take Now",height=26,font=ctk.CTkFont(size=11),
                                   fg_color=T.BTN_PRI,hover_color=T.BTN_PRI_H,
                                   command=lambda m=med:self._take(m)).pack(fill="x",pady=(4,0))

        # Sleep card
        for w in self._sc.winfo_children(): w.destroy()
        if sleep:
            row=ctk.CTkFrame(self._sc,fg_color="transparent"); row.pack(fill="x",padx=T.PAD_MD,pady=T.PAD_SM)
            dh,dm_=sleep.get("duration_min",0)//60, sleep.get("duration_min",0)%60
            q=sleep.get("quality",3); sc=sleep.get("score","--")
            left=ctk.CTkFrame(row,fg_color="transparent"); left.pack(side="left",fill="x",expand=True)
            ctk.CTkLabel(left,text=f"{sleep.get('bedtime','--')}  \u2192  {sleep.get('waketime','--')}",
                          font=ctk.CTkFont(size=13,weight="bold"),text_color=T.TEXT).pack(anchor="w")
            ctk.CTkLabel(left,text=f"{dh}h {dm_}m  |  {QUALITY_LABELS.get(q,'')}",font=ctk.CTkFont(size=11),
                          text_color=QUALITY_COLOURS.get(q,T.TEXT_SEC)).pack(anchor="w")
            fcts=sleep.get("factors",[])
            if fcts: ctk.CTkLabel(left,text=", ".join(fcts),font=ctk.CTkFont(size=10),text_color=T.TEXT_MUTED).pack(anchor="w",pady=(2,0))
            sc_c=T.GREEN if sc!="--" and int(sc)>=70 else T.AMBER if sc!="--" and int(sc)>=50 else T.RED
            sf=ctk.CTkFrame(row,fg_color=T.SURFACE,corner_radius=8,width=60,height=50); sf.pack(side="right",padx=(T.PAD_SM,0)); sf.pack_propagate(False)
            ctk.CTkLabel(sf,text=str(sc),font=ctk.CTkFont(size=18,weight="bold"),text_color=sc_c).pack(expand=True)
            ss=self.dm.sleep_streak()
            ctk.CTkLabel(self._sc,text=f"Logged {ss} night{'s' if ss!=1 else ''} in a row",
                          font=ctk.CTkFont(size=10),text_color=T.TEXT_MUTED).pack(padx=T.PAD_MD,pady=(0,T.PAD_SM))
        else:
            ctk.CTkLabel(self._sc,text="No sleep logged recently.",font=ctk.CTkFont(size=12),
                          text_color=T.TEXT_MUTED).pack(pady=T.PAD_LG)

        # Alerts
        for w in self._alerts.winfo_children(): w.destroy()
        low=[m for m in meds if m.get("supply") is not None and m["supply"]<=m.get("supply_warn",7)]
        if low:
            ctk.CTkLabel(self._alerts,text="Low Stock Alerts",font=ctk.CTkFont(size=13,weight="bold"),
                          text_color=T.AMBER).pack(anchor="w",pady=(4,4))
            for m in low:
                af=ctk.CTkFrame(self._alerts,fg_color="#2a2000",corner_radius=6,border_width=1,border_color=T.AMBER)
                af.pack(fill="x",pady=2)
                ctk.CTkLabel(af,text=f"  {m['name']}:  {m['supply']} remaining",font=ctk.CTkFont(size=11),
                              text_color=T.AMBER).pack(padx=T.PAD_SM,pady=6,anchor="w")

    def _take(self,m): self.dm.log_taken(m["id"],m["name"]); self.toast.show(f"{m['name']} taken!","success"); self.refresh()
    def _undo(self,m): self.dm.undo_taken(m["id"]); self.toast.show(f"{m['name']} undone","info"); self.refresh()

# ── 7B : MEDICATIONS ─────────────────────────────────────────────────────────
class MedicationsPage(ctk.CTkScrollableFrame):
    def __init__(self, parent, dm, toast, **kw):
        super().__init__(parent,fg_color=T.BG,scrollbar_button_color=T.BORDER,
                         scrollbar_button_hover_color=T.TEXT_MUTED,**kw)
        self.dm=dm; self.toast=toast; self._dlg=None; self._build()
    def _build(self):
        hdr=ctk.CTkFrame(self,fg_color="transparent"); hdr.pack(fill="x",padx=T.PAD_LG,pady=(T.PAD_MD,T.PAD_SM))
        ctk.CTkLabel(hdr,text="Medications",font=ctk.CTkFont(size=20,weight="bold"),text_color=T.TEXT).pack(side="left")
        ctk.CTkButton(hdr,text="Check interactions",height=30,width=128,font=ctk.CTkFont(size=11),fg_color=T.SURFACE,
                       hover_color=T.HOVER,text_color=T.AMBER,border_width=1,border_color=T.BORDER,
                       command=self._check_interactions).pack(side="right",padx=(4,0))
        ctk.CTkButton(hdr,text="+ Add",height=32,width=80,font=ctk.CTkFont(size=12,weight="bold"),
                       fg_color=T.BTN_PRI,hover_color=T.BTN_PRI_H,command=self._add).pack(side="right")
        self._lf=ctk.CTkFrame(self,fg_color="transparent"); self._lf.pack(fill="both",expand=True,padx=T.PAD_MD)

    def refresh(self):
        for w in self._lf.winfo_children(): w.destroy()
        meds=self.dm.all_meds
        if not meds:
            ctk.CTkLabel(self._lf,text="No medications yet.\nClick '+ Add' above.",font=ctk.CTkFont(size=13),
                          text_color=T.TEXT_MUTED,justify="center").pack(pady=60); return
        for med in meds:
            done=self.dm.taken_today(med["id"]); active=med.get("active",True); color=med.get("color",T.BLUE)
            card=ctk.CTkFrame(self._lf,fg_color="#0d2a1a" if done else T.CARD if active else T.SURFACE,
                               corner_radius=T.RAD,border_width=1,border_color=T.GREEN if done else T.BORDER)
            card.pack(fill="x",pady=3)
            row=ctk.CTkFrame(card,fg_color="transparent"); row.pack(fill="x",padx=T.PAD_MD,pady=T.PAD_SM)
            ctk.CTkFrame(row,width=8,height=40,fg_color=color,corner_radius=4).pack(side="left",padx=(0,T.PAD_SM))
            info=ctk.CTkFrame(row,fg_color="transparent"); info.pack(side="left",fill="x",expand=True)
            nt=med["name"]+("  (inactive)" if not active else "")
            ctk.CTkLabel(info,text=nt,font=ctk.CTkFont(size=13,weight="bold"),
                          text_color=T.GREEN if done else T.TEXT if active else T.TEXT_MUTED,anchor="w").pack(anchor="w")
            det=[]
            if med.get("dosage"): det.append(med["dosage"])
            if med.get("frequency"): det.append(med["frequency"])
            if med.get("time_of_day"): det.append(med["time_of_day"])
            if med.get("schedule_times"): det.append(" / ".join(med["schedule_times"]))
            if med.get("clinician"): det.append(f"Prescriber: {med['clinician']}")
            if det: ctk.CTkLabel(info,text="  |  ".join(det),font=ctk.CTkFont(size=11),text_color=T.TEXT_SEC,anchor="w").pack(anchor="w")
            if med.get("supply") is not None:
                s=med["supply"]; w_=med.get("supply_warn",7)
                sc=T.RED if s<=w_ else T.AMBER if s<=w_*2 else T.TEXT_SEC
                ctk.CTkLabel(info,text=f"Supply: {s}",font=ctk.CTkFont(size=10),text_color=sc).pack(anchor="w")
            btns=ctk.CTkFrame(row,fg_color="transparent"); btns.pack(side="right")
            if active:
                if done:
                    ctk.CTkButton(btns,text="Undo",width=55,height=28,font=ctk.CTkFont(size=11),fg_color=T.SURFACE,
                                   hover_color=T.HOVER,text_color=T.TEXT_SEC,command=lambda m=med:self._undo(m)).pack(pady=1)
                else:
                    ctk.CTkButton(btns,text="Take",width=55,height=28,font=ctk.CTkFont(size=11),fg_color=T.BTN_PRI,
                                   hover_color=T.BTN_PRI_H,command=lambda m=med:self._take(m)).pack(pady=1)
            ctk.CTkButton(btns,text="Edit",width=55,height=28,font=ctk.CTkFont(size=11),fg_color=T.SURFACE,
                            hover_color=T.HOVER,text_color=T.BLUE,command=lambda m=med:self._edit(m)).pack(pady=1)
            ctk.CTkButton(btns,text="Refill",width=55,height=28,font=ctk.CTkFont(size=11),fg_color=T.SURFACE,
                           hover_color=T.HOVER,text_color=T.TEAL,command=lambda m=med:self._refill(m)).pack(pady=1)
            if med.get("refill_history") or med.get("dose_changes") or med.get("photo_path"):
                ctk.CTkButton(btns,text="History",width=55,height=28,font=ctk.CTkFont(size=11),fg_color=T.SURFACE,
                               hover_color=T.HOVER,text_color=T.TEXT_SEC,command=lambda m=med:self._history(m)).pack(pady=1)

    def _take(self,m): self.dm.log_taken(m["id"],m["name"]); self.toast.show(f"{m['name']} taken!","success"); self.refresh()
    def _undo(self,m): self.dm.undo_taken(m["id"]); self.toast.show(f"{m['name']} undone","info"); self.refresh()
    def _add(self): self._form(None)
    def _edit(self, med): self._form(med)
    def _refill(self, med):
        quantity=simpledialog.askinteger("Refill",f"How many doses were added to {med['name']}?",parent=self.winfo_toplevel(),minvalue=1)
        if quantity:
            note=simpledialog.askstring("Refill note","Optional note (pharmacy, lot, etc.):",parent=self.winfo_toplevel()) or ""
            if self.dm.record_refill(med["id"],quantity,note):
                self.toast.show(f"Added {quantity} doses to {med['name']}","success"); self.refresh()
    def _history(self, med):
        lines=[f"Prescriber: {med.get('clinician') or 'Not set'}"]
        if med.get("photo_path"): lines.append(f"Reference photo: {med['photo_path']}")
        if med.get("refill_history"):
            lines.append("Refills:")
            lines.extend(f"  {item.get('date','')}: +{item.get('quantity',0)}  {item.get('note','')}" for item in med["refill_history"][-8:])
        if med.get("dose_changes"):
            lines.append("Dose changes:")
            lines.extend(f"  {item.get('date','')}: {item.get('from','—')} -> {item.get('to','—')}  {item.get('notes','')}" for item in med["dose_changes"][-8:])
        messagebox.showinfo(f"{med['name']} history","\n".join(lines),parent=self.winfo_toplevel())
    def _check_interactions(self):
        findings=self.dm.interaction_findings()
        if findings:
            text="\n\n".join(f"[{item['severity'].upper()}] {', '.join(item['medications'])}\n{item['message']}" for item in findings)
        else:
            text="No matches in the small offline screening list."
        messagebox.showinfo("Offline interaction screen",text+"\n\nThis is not a complete interaction checker. Confirm every combination with a pharmacist.",parent=self.winfo_toplevel())

    def _form(self, med):
        if self._dlg and self._dlg.winfo_exists(): self._dlg.focus(); return
        ie=med is not None
        dlg=ctk.CTkToplevel(self.winfo_toplevel()); self._dlg=dlg
        dlg.title("Edit Medication" if ie else "Add Medication"); dlg.geometry("420x720")
        dlg.configure(fg_color=T.BG); dlg.attributes("-topmost",True); dlg.resizable(False,True); dlg.grab_set()
        sc=ctk.CTkScrollableFrame(dlg,fg_color=T.BG); sc.pack(fill="both",expand=True,padx=T.PAD_MD,pady=T.PAD_MD)
        def _f(lbl,ph="",dv=""):
            ctk.CTkLabel(sc,text=lbl,font=ctk.CTkFont(size=12,weight="bold"),text_color=T.BLUE).pack(anchor="w",pady=(T.PAD_SM,2))
            e=ctk.CTkEntry(sc,placeholder_text=ph,fg_color=T.INPUT_BG,border_color=T.INPUT_BD); e.pack(fill="x",pady=(0,4))
            if dv: e.insert(0,dv)
            return e
        ne=_f("Name *","e.g. Vitamin D",med["name"] if ie else "")
        de=_f("Dosage","e.g. 1000 IU",med.get("dosage","") if ie else "")
        ce=_f("Prescribing Clinician","Optional",med.get("clinician","") if ie else "")
        dnote=_f("Dose Change Note","Only used when editing dosage","")
        ctk.CTkLabel(sc,text="Frequency",font=ctk.CTkFont(size=12,weight="bold"),text_color=T.BLUE).pack(anchor="w",pady=(T.PAD_SM,2))
        fv=ctk.StringVar(value=med.get("frequency","Daily") if ie else "Daily")
        ctk.CTkOptionMenu(sc,variable=fv,values=["Daily","Twice Daily","3x Daily","Every Other Day","Weekly","As Needed"],
                           fg_color=T.INPUT_BG,button_color=T.BORDER,button_hover_color=T.HOVER,dropdown_fg_color=T.SURFACE).pack(fill="x",pady=(0,4))
        te=_f("Time of Day","e.g. Morning",med.get("time_of_day","") if ie else "")
        schedule_value=",".join(med.get("schedule_times",[])) if ie and med.get("schedule_times") else ""
        ste=_f("Schedule Times","HH:MM, HH:MM (blank uses frequency defaults)",schedule_value)
        ctk.CTkLabel(sc,text="Colour",font=ctk.CTkFont(size=12,weight="bold"),text_color=T.BLUE).pack(anchor="w",pady=(T.PAD_SM,2))
        cv=ctk.StringVar(value="Blue")
        if ie:
            for cn,ch in PILL_COLOURS.items():
                if ch==med.get("color"): cv.set(cn); break
        cr=ctk.CTkFrame(sc,fg_color="transparent"); cr.pack(fill="x",pady=(0,4))
        cp=ctk.CTkFrame(cr,width=24,height=24,fg_color=PILL_COLOURS.get(cv.get(),T.BLUE),corner_radius=12); cp.pack(side="left",padx=(0,8))
        ctk.CTkOptionMenu(cr,variable=cv,values=list(PILL_COLOURS.keys()),fg_color=T.INPUT_BG,button_color=T.BORDER,
                           button_hover_color=T.HOVER,dropdown_fg_color=T.SURFACE,
                           command=lambda v:cp.configure(fg_color=PILL_COLOURS.get(v,T.BLUE))).pack(side="left",fill="x",expand=True)
        se=_f("Supply Count","Leave blank to skip",str(med["supply"]) if ie and med.get("supply") is not None else "")
        we=_f("Low Stock Warning","Default: 7",str(med.get("supply_warn",7)) if ie else "7")
        pe=_f("Reference Photo","For travel identification; no automatic identification",med.get("photo_path","") if ie else "")
        ctk.CTkButton(sc,text="Browse photo…",height=28,fg_color=T.SURFACE,hover_color=T.HOVER,text_color=T.TEAL,
                      command=lambda:self._browse_photo(pe)).pack(anchor="w",pady=(0,4))
        ctk.CTkLabel(sc,text="Notes",font=ctk.CTkFont(size=12,weight="bold"),text_color=T.BLUE).pack(anchor="w",pady=(T.PAD_SM,2))
        ntb=ctk.CTkTextbox(sc,height=50,fg_color=T.INPUT_BG,border_color=T.INPUT_BD,border_width=1); ntb.pack(fill="x",pady=(0,4))
        if ie and med.get("notes"): ntb.insert("1.0",med["notes"])
        if ie:
            av=ctk.BooleanVar(value=med.get("active",True))
            ctk.CTkSwitch(sc,text="Active",variable=av,font=ctk.CTkFont(size=12),text_color=T.TEXT_SEC,
                           fg_color=T.BORDER,progress_color=T.GREEN,button_color=T.TEXT,button_hover_color=T.BLUE).pack(anchor="w",pady=T.PAD_SM)
        br=ctk.CTkFrame(sc,fg_color="transparent"); br.pack(fill="x",pady=(T.PAD_MD,T.PAD_SM))
        def _save():
            n=ne.get().strip()
            if not n: messagebox.showwarning("Required","Name is required.",parent=dlg); return
            sp=None; st=se.get().strip()
            if st:
                try: sp=int(st)
                except ValueError: messagebox.showwarning("Invalid","Supply must be a number.",parent=dlg); return
            wn=7
            try: wn=int(we.get().strip())
            except: pass
            try: schedule_times=normalize_schedule_times(ste.get(),fv.get())
            except ValueError as exc:
                messagebox.showwarning("Invalid schedule",str(exc),parent=dlg); return
            d={"name":n,"dosage":de.get().strip(),"clinician":ce.get().strip(),"frequency":fv.get(),"time_of_day":te.get().strip(),
               "schedule_times":schedule_times,"color":PILL_COLOURS.get(cv.get(),T.BLUE),"supply":sp,"supply_warn":wn,
               "photo_path":pe.get().strip(),"notes":ntb.get("1.0","end").strip()}
            if ie: d["dose_change_note"]=dnote.get().strip()
            if ie: d["active"]=av.get(); self.dm.update_med(med["id"],d); self.toast.show(f"{n} updated","success")
            else: self.dm.add_med(d); self.toast.show(f"{n} added!","success")
            dlg.destroy(); self.refresh()
        ctk.CTkButton(br,text="Save",fg_color=T.BTN_PRI,hover_color=T.BTN_PRI_H,height=34,
                       font=ctk.CTkFont(size=13,weight="bold"),command=_save).pack(side="left",fill="x",expand=True,padx=(0,4))
        if ie:
            def _del():
                if messagebox.askyesno("Delete",f"Delete '{med['name']}'?",parent=dlg):
                    self.dm.delete_med(med["id"]); self.toast.show(f"Deleted","warning"); dlg.destroy(); self.refresh()
            ctk.CTkButton(br,text="Delete",fg_color=T.BTN_DNG,hover_color=T.BTN_DNG_H,height=34,
                           font=ctk.CTkFont(size=13,weight="bold"),command=_del).pack(side="left",fill="x",expand=True,padx=(4,4))
        ctk.CTkButton(br,text="Cancel",fg_color=T.SURFACE,hover_color=T.HOVER,height=34,text_color=T.TEXT_SEC,
                       command=dlg.destroy).pack(side="right",fill="x",expand=True,padx=(4,0))
    def _browse_photo(self, entry):
        fp=filedialog.askopenfilename(parent=self.winfo_toplevel(),filetypes=[("Images","*.png *.jpg *.jpeg *.webp"),("All files","*.*")])
        if fp:
            entry.delete(0,"end"); entry.insert(0,fp)

# ── 7C : SLEEP ───────────────────────────────────────────────────────────────
class SleepPage(ctk.CTkScrollableFrame):
    def __init__(self, parent, dm, toast, **kw):
        super().__init__(parent,fg_color=T.BG,scrollbar_button_color=T.BORDER,
                         scrollbar_button_hover_color=T.TEXT_MUTED,**kw)
        self.dm=dm; self.toast=toast; self._build()
    def _build(self):
        hdr=ctk.CTkFrame(self,fg_color="transparent"); hdr.pack(fill="x",padx=T.PAD_LG,pady=(T.PAD_MD,T.PAD_SM))
        ctk.CTkLabel(hdr,text="Sleep Tracker",font=ctk.CTkFont(size=20,weight="bold"),text_color=T.TEXT).pack(side="left")
        ctk.CTkButton(hdr,text="Import CSV",width=96,height=30,font=ctk.CTkFont(size=11),fg_color=T.SURFACE,
                       hover_color=T.HOVER,text_color=T.BLUE,border_width=1,border_color=T.BORDER,
                       command=self._import_csv).pack(side="right")
        self._coach=ctk.CTkFrame(self,fg_color=T.CARD,corner_radius=T.RAD,border_width=1,border_color=T.BORDER)
        self._coach.pack(fill="x",padx=T.PAD_MD,pady=(0,T.PAD_SM))
        # Quick presets
        pf=ctk.CTkFrame(self,fg_color=T.CARD,corner_radius=T.RAD,border_width=1,border_color=T.BORDER); pf.pack(fill="x",padx=T.PAD_MD,pady=(0,T.PAD_SM))
        ctk.CTkLabel(pf,text="Quick Log (ending now)",font=ctk.CTkFont(size=12,weight="bold"),text_color=T.TEXT_SEC).pack(anchor="w",padx=T.PAD_MD,pady=(T.PAD_SM,4))
        pr=ctk.CTkFrame(pf,fg_color="transparent"); pr.pack(fill="x",padx=T.PAD_MD,pady=(0,T.PAD_SM))
        for h in [5,6,7,8,9]:
            ctk.CTkButton(pr,text=f"{h}h",width=50,height=32,font=ctk.CTkFont(size=12,weight="bold"),
                           fg_color=T.SURFACE,hover_color=T.HOVER,text_color=T.PURPLE,border_width=1,border_color=T.BORDER,
                           command=lambda hrs=h:self._quick(hrs)).pack(side="left",padx=2,expand=True,fill="x")
        nr=ctk.CTkFrame(pf,fg_color="transparent"); nr.pack(fill="x",padx=T.PAD_MD,pady=(0,T.PAD_SM))
        ctk.CTkLabel(nr,text="Nap",font=ctk.CTkFont(size=11,weight="bold"),text_color=T.TEXT_SEC).pack(side="left",padx=(0,6))
        for minutes in (20,30,60):
            ctk.CTkButton(nr,text=f"{minutes}m",width=58,height=26,font=ctk.CTkFont(size=10),fg_color=T.SURFACE,
                          hover_color=T.HOVER,text_color=T.TEAL,command=lambda mins=minutes:self._quick_nap(mins)).pack(side="left",padx=2)
        # Manual form
        fm=ctk.CTkFrame(self,fg_color=T.CARD,corner_radius=T.RAD,border_width=1,border_color=T.BORDER); fm.pack(fill="x",padx=T.PAD_MD,pady=(0,T.PAD_SM))
        ctk.CTkLabel(fm,text="Manual Entry",font=ctk.CTkFont(size=13,weight="bold"),text_color=T.TEXT).pack(anchor="w",padx=T.PAD_MD,pady=(T.PAD_SM,4))
        def _tr(lbl):
            r=ctk.CTkFrame(fm,fg_color="transparent"); r.pack(fill="x",padx=T.PAD_MD,pady=2)
            ctk.CTkLabel(r,text=lbl,width=70,anchor="w",font=ctk.CTkFont(size=12),text_color=T.TEXT_SEC).pack(side="left")
            return r
        dr=_tr("Date:")
        self.date_e=ctk.CTkEntry(dr,width=120,fg_color=T.INPUT_BG,border_color=T.INPUT_BD); self.date_e.pack(side="left"); self.date_e.insert(0,datetime.now().strftime("%Y-%m-%d"))
        br=_tr("Bedtime:")
        self.bh=ctk.CTkOptionMenu(br,values=[f"{h:02d}" for h in range(24)],width=60,fg_color=T.INPUT_BG,button_color=T.BORDER,dropdown_fg_color=T.SURFACE); self.bh.set("22"); self.bh.pack(side="left",padx=2)
        ctk.CTkLabel(br,text=":",text_color=T.TEXT_MUTED).pack(side="left")
        self.bm=ctk.CTkOptionMenu(br,values=[f"{m:02d}" for m in range(0,60,5)],width=60,fg_color=T.INPUT_BG,button_color=T.BORDER,dropdown_fg_color=T.SURFACE); self.bm.set("00"); self.bm.pack(side="left",padx=2)
        wr=_tr("Wake up:")
        self.wh=ctk.CTkOptionMenu(wr,values=[f"{h:02d}" for h in range(24)],width=60,fg_color=T.INPUT_BG,button_color=T.BORDER,dropdown_fg_color=T.SURFACE); self.wh.set("06"); self.wh.pack(side="left",padx=2)
        ctk.CTkLabel(wr,text=":",text_color=T.TEXT_MUTED).pack(side="left")
        self.wm=ctk.CTkOptionMenu(wr,values=[f"{m:02d}" for m in range(0,60,5)],width=60,fg_color=T.INPUT_BG,button_color=T.BORDER,dropdown_fg_color=T.SURFACE); self.wm.set("00"); self.wm.pack(side="left",padx=2)
        self.napv=ctk.BooleanVar(value=False)
        ctk.CTkSwitch(fm,text="This is a nap",variable=self.napv,font=ctk.CTkFont(size=11),text_color=T.TEXT_SEC,
                      fg_color=T.BORDER,progress_color=T.TEAL,button_color=T.TEXT,button_hover_color=T.BLUE).pack(anchor="w",padx=T.PAD_MD,pady=(T.PAD_SM,0))
        # Quality
        qr=_tr("Quality:"); self.qv=tk.IntVar(value=4)
        self._ql=ctk.CTkLabel(qr,text="Good",font=ctk.CTkFont(size=12,weight="bold"),text_color=T.GREEN,width=70); self._ql.pack(side="right")
        self.qs=ctk.CTkSlider(qr,from_=1,to=5,number_of_steps=4,fg_color=T.BORDER,progress_color=T.PURPLE,
                               button_color=T.TEXT,button_hover_color=T.BLUE,command=self._qc); self.qs.set(4); self.qs.pack(side="left",fill="x",expand=True,padx=T.PAD_SM)
        # Factors
        ctk.CTkLabel(fm,text="Factors:",font=ctk.CTkFont(size=12),text_color=T.TEXT_SEC).pack(anchor="w",padx=T.PAD_MD,pady=(T.PAD_SM,2))
        fg=ctk.CTkFrame(fm,fg_color="transparent"); fg.pack(fill="x",padx=T.PAD_MD,pady=(0,4))
        self._fvars={}
        for i,f in enumerate(SLEEP_FACTORS):
            v=ctk.BooleanVar(value=False); self._fvars[f]=v
            ctk.CTkCheckBox(fg,text=f,variable=v,font=ctk.CTkFont(size=11),text_color=T.TEXT_SEC,
                             fg_color=T.BORDER,hover_color=T.HOVER,checkmark_color=T.PURPLE,border_color=T.BORDER).grid(row=i//2,column=i%2,padx=4,pady=2,sticky="w")
            fg.columnconfigure(i%2,weight=1)
        # Notes
        ctk.CTkLabel(fm,text="Notes:",font=ctk.CTkFont(size=12),text_color=T.TEXT_SEC).pack(anchor="w",padx=T.PAD_MD,pady=(T.PAD_SM,2))
        self.ntb=ctk.CTkTextbox(fm,height=50,fg_color=T.INPUT_BG,border_color=T.INPUT_BD,border_width=1); self.ntb.pack(fill="x",padx=T.PAD_MD,pady=(0,T.PAD_SM))
        ctk.CTkButton(fm,text="Log Sleep",height=38,font=ctk.CTkFont(size=14,weight="bold"),
                       fg_color=T.PURPLE,hover_color="#9a6aff",command=self._log).pack(fill="x",padx=T.PAD_MD,pady=(0,T.PAD_MD))
        # History
        ctk.CTkLabel(self,text="Recent Entries",font=ctk.CTkFont(size=14,weight="bold"),text_color=T.TEXT).pack(anchor="w",padx=T.PAD_LG,pady=(T.PAD_SM,4))
        self._hf=ctk.CTkFrame(self,fg_color="transparent"); self._hf.pack(fill="x",padx=T.PAD_MD,pady=(0,T.PAD_MD))

    def _qc(self,val):
        q=int(round(val)); self.qv.set(q); self._ql.configure(text=QUALITY_LABELS.get(q,""),text_color=QUALITY_COLOURS.get(q,T.TEXT))
    def _quick_nap(self,minutes):
        now=datetime.now(); bed=now-timedelta(minutes=minutes)
        self.dm.log_sleep({"date":now.strftime("%Y-%m-%d"),"bedtime":bed.strftime("%H:%M"),"waketime":now.strftime("%H:%M"),
                           "duration_min":minutes,"quality":4,"factors":["Nap"],"notes":f"Quick nap: {minutes}m","score":None,"is_nap":True})
        self.toast.show(f"Logged {minutes}m nap","success"); self.refresh()
    def _quick(self,hours):
        now=datetime.now(); bed=now-timedelta(hours=hours)
        rbt=[s.get("bedtime") for _,s in self.dm.sleep_for_range(7) if s]
        sc=DataManager.calc_sleep_score(hours*60,4,rbt,self.dm.settings.get("chronotype"))
        self.dm.log_sleep({"date":now.strftime("%Y-%m-%d"),"bedtime":bed.strftime("%H:%M"),"waketime":now.strftime("%H:%M"),
                           "duration_min":hours*60,"quality":4,"factors":[],"notes":f"Quick: {hours}h","score":sc})
        self.toast.show(f"Logged {hours}h  |  Score: {sc}","success"); self.refresh()
    def _log(self):
        ds=self.date_e.get().strip(); bhv,bmv=int(self.bh.get()),int(self.bm.get()); whv,wmv=int(self.wh.get()),int(self.wm.get())
        bt=bhv*60+bmv; wt=whv*60+wmv; dur=(wt-bt) if wt>bt else (1440-bt+wt)
        if dur<=0 or dur>1080: messagebox.showwarning("Invalid","Check your times.",parent=self.winfo_toplevel()); return
        q=self.qv.get(); fcts=[f for f,v in self._fvars.items() if v.get()]; notes=self.ntb.get("1.0","end").strip()
        rbt=[s.get("bedtime") for _,s in self.dm.sleep_for_range(7) if s]
        sc=DataManager.calc_sleep_score(dur,q,rbt,self.dm.settings.get("chronotype"))
        self.dm.log_sleep({"date":ds,"bedtime":f"{bhv:02d}:{bmv:02d}","waketime":f"{whv:02d}:{wmv:02d}",
                           "duration_min":dur,"quality":q,"factors":fcts,"notes":notes,"score":sc,"is_nap":self.napv.get()})
        self.toast.show(f"Sleep logged!  Score: {sc}/100","success"); self.ntb.delete("1.0","end")
        for v in self._fvars.values(): v.set(False)
        self.napv.set(False)
        self.refresh()
    def _import_csv(self):
        fp=filedialog.askopenfilename(parent=self.winfo_toplevel(),filetypes=[("Sleep CSV","*.csv"),("All files","*.*")])
        if not fp: return
        try:
            added,total=self.dm.import_sleep_csv(fp)
            self.toast.show(f"Imported {added} of {total} sleep entries","success"); self.refresh()
        except Exception as exc:
            messagebox.showerror("Import failed",str(exc),parent=self.winfo_toplevel())
    def _refresh_coach(self):
        for w in self._coach.winfo_children(): w.destroy()
        coach=bedtime_consistency_coach(self.dm.sleep_entries)
        row=ctk.CTkFrame(self._coach,fg_color="transparent"); row.pack(fill="x",padx=T.PAD_MD,pady=T.PAD_SM)
        left=ctk.CTkFrame(row,fg_color="transparent"); left.pack(side="left",fill="x",expand=True)
        ctk.CTkLabel(left,text="Bedtime coach",font=ctk.CTkFont(size=12,weight="bold"),text_color=T.TEAL).pack(anchor="w")
        ctk.CTkLabel(left,text=coach["recommendation"],font=ctk.CTkFont(size=10),text_color=T.TEXT_SEC,wraplength=360,justify="left").pack(anchor="w",pady=(2,0))
        if coach.get("target_bedtime"):
            ctk.CTkLabel(row,text=coach["target_bedtime"],font=ctk.CTkFont(size=18,weight="bold"),text_color=T.TEAL).pack(side="right")
    def refresh(self):
        self._refresh_coach()
        for w in self._hf.winfo_children(): w.destroy()
        entries=sorted(self.dm.sleep_entries,key=lambda s:s["date"],reverse=True)[:10]
        if not entries: ctk.CTkLabel(self._hf,text="No entries yet.",font=ctk.CTkFont(size=12),text_color=T.TEXT_MUTED).pack(pady=T.PAD_LG); return
        for s in entries:
            q=s.get("quality",3); dh,dm_=s.get("duration_min",0)//60,s.get("duration_min",0)%60; sc=s.get("score","--")
            if sc is None: sc="--"
            row=ctk.CTkFrame(self._hf,fg_color=T.CARD,corner_radius=6,border_width=1,border_color=T.BORDER); row.pack(fill="x",pady=2)
            inn=ctk.CTkFrame(row,fg_color="transparent"); inn.pack(fill="x",padx=T.PAD_MD,pady=T.PAD_SM)
            kind="Nap  " if s.get("is_nap") else ""
            source=f"  · {s.get('source').title()}" if s.get("source") else ""
            ctk.CTkLabel(inn,text=f"{kind}{s['date']}{source}",width=135,font=ctk.CTkFont(size=11),text_color=T.TEXT_MUTED).pack(side="left")
            ctk.CTkLabel(inn,text=f"{dh}h {dm_}m",font=ctk.CTkFont(size=12,weight="bold"),text_color=T.TEXT).pack(side="left",padx=T.PAD_SM)
            ctk.CTkLabel(inn,text=QUALITY_LABELS.get(q,""),font=ctk.CTkFont(size=11),text_color=QUALITY_COLOURS.get(q,T.TEXT_SEC)).pack(side="left")
            if s.get("stages"):
                stage_text="  ".join(f"{key.title()} {value}m" for key,value in s["stages"].items())
                ctk.CTkLabel(inn,text=stage_text,font=ctk.CTkFont(size=9),text_color=T.TEAL).pack(side="left",padx=4)
            sc_c=T.GREEN if sc!="--" and sc>=70 else T.AMBER if sc!="--" and sc>=50 else T.RED
            ctk.CTkLabel(inn,text=f"  {sc}",font=ctk.CTkFont(size=12,weight="bold"),text_color=sc_c).pack(side="right")
        self.date_e.delete(0,"end"); self.date_e.insert(0,datetime.now().strftime("%Y-%m-%d"))

# ── 7D : ANALYTICS ───────────────────────────────────────────────────────────
class AnalyticsPage(ctk.CTkScrollableFrame):
    def __init__(self, parent, dm, **kw):
        super().__init__(parent,fg_color=T.BG,scrollbar_button_color=T.BORDER,
                         scrollbar_button_hover_color=T.TEXT_MUTED,**kw)
        self.dm=dm; self._build()
    def _build(self):
        ctk.CTkLabel(self,text="Analytics",font=ctk.CTkFont(size=20,weight="bold"),text_color=T.TEXT).pack(anchor="w",padx=T.PAD_LG,pady=(T.PAD_MD,T.PAD_SM))
        sr=ctk.CTkFrame(self,fg_color="transparent"); sr.pack(fill="x",padx=T.PAD_MD,pady=(0,T.PAD_SM)); sr.columnconfigure((0,1,2,3),weight=1,uniform="s")
        self.sa=StatCard(sr,"Avg Sleep","--","",T.PURPLE); self.sa.grid(row=0,column=0,padx=3,pady=3,sticky="nsew")
        self.sq=StatCard(sr,"Avg Quality","--","",T.TEAL); self.sq.grid(row=0,column=1,padx=3,pady=3,sticky="nsew")
        self.sh=StatCard(sr,"Adherence","--","",T.GREEN); self.sh.grid(row=0,column=2,padx=3,pady=3,sticky="nsew")
        self.ss=StatCard(sr,"Avg Score","--","",T.BLUE); self.ss.grid(row=0,column=3,padx=3,pady=3,sticky="nsew")
        rr=ctk.CTkFrame(self,fg_color="transparent"); rr.pack(fill="x",padx=T.PAD_LG,pady=(T.PAD_SM,4))
        self._rv=ctk.StringVar(value="14")
        for v,l in [("7","7 days"),("14","14 days"),("30","30 days")]:
            ctk.CTkRadioButton(rr,text=l,variable=self._rv,value=v,font=ctk.CTkFont(size=11),text_color=T.TEXT_SEC,
                                fg_color=T.BLUE,hover_color=T.HOVER,border_color=T.BORDER,command=self.refresh).pack(side="left",padx=T.PAD_SM)
        self.ch_adh=ChartFrame(self,title="Medication Adherence (%)",height=180); self.ch_adh.pack(fill="x",padx=T.PAD_MD,pady=T.PAD_SM)
        self.ch_dur=ChartFrame(self,title="Sleep Duration (hours)",height=180); self.ch_dur.pack(fill="x",padx=T.PAD_MD,pady=T.PAD_SM)
        self.ch_q=ChartFrame(self,title="Sleep Quality & Score",height=180); self.ch_q.pack(fill="x",padx=T.PAD_MD,pady=T.PAD_SM)
        self.ch_f=ChartFrame(self,title="Sleep Factor Frequency",height=160); self.ch_f.pack(fill="x",padx=T.PAD_MD,pady=(T.PAD_SM,T.PAD_LG))

    def refresh(self):
        days=int(self._rv.get()); sd=self.dm.sleep_for_range(days); se=[s for _,s in sd if s]
        if se:
            ad=sum(s["duration_min"] for s in se)/len(se); ah,am=int(ad//60),int(ad%60); self.sa.update_values(f"{ah}h {am}m",f"{len(se)} nights")
            aq=sum(s.get("quality",3) for s in se)/len(se); self.sq.update_values(f"{aq:.1f}/5",QUALITY_LABELS.get(round(aq),""))
            scs=[s.get("score",0) for s in se if s.get("score")]; asc=sum(scs)/len(scs) if scs else 0; self.ss.update_values(f"{asc:.0f}","out of 100")
        else: self.sa.update_values("--","No data"); self.sq.update_values("--",""); self.ss.update_values("--","")
        adh=self.dm.adherence_for_range(days)
        if adh and self.dm.meds:
            aa=sum(v for _,v in adh)/len(adh)*100; self.sh.update_values(f"{aa:.0f}%",f"last {days}d")
        else: self.sh.update_values("--","")

        # Adherence chart
        ax=self.ch_adh.ax; self.ch_adh.redraw()
        if adh and self.dm.meds:
            dates=[d[-5:] for d,_ in adh]; vals=[v*100 for _,v in adh]
            cols=[T.GREEN if v>=100 else T.AMBER if v>=50 else T.RED for v in vals]
            ax.bar(range(len(dates)),vals,color=cols,width=0.6,alpha=0.85)
            ax.set_xticks(range(len(dates))); ax.set_xticklabels(dates,rotation=45,ha="right",fontsize=7)
            ax.set_ylim(0,110); ax.set_ylabel("%",fontsize=9); ax.axhline(y=100,color=T.GREEN,linewidth=0.5,alpha=0.3,linestyle="--")
        else: ax.text(0.5,0.5,"No data",transform=ax.transAxes,ha="center",va="center",color=T.TEXT_MUTED,fontsize=11)
        self.ch_adh.render()

        # Duration chart
        ax2=self.ch_dur.ax; self.ch_dur.redraw()
        if se:
            dts=[]; durs=[]
            for d,s in sd: dts.append(d[-5:]); durs.append(s["duration_min"]/60 if s else None)
            vx=[i for i,d in enumerate(durs) if d is not None]; vy=[durs[i] for i in vx]
            if vy:
                ax2.fill_between(vx,vy,alpha=0.15,color=T.PURPLE)
                ax2.plot(vx,vy,color=T.PURPLE,linewidth=2,marker="o",markersize=4,markerfacecolor=T.PURPLE)
                ax2.axhspan(7,9,alpha=0.05,color=T.GREEN)
                ax2.set_xticks(range(len(dts))); ax2.set_xticklabels(dts,rotation=45,ha="right",fontsize=7)
                ax2.set_ylabel("Hours",fontsize=9); ax2.set_ylim(0,max(12,max(vy)+1))
        else: ax2.text(0.5,0.5,"No data",transform=ax2.transAxes,ha="center",va="center",color=T.TEXT_MUTED,fontsize=11)
        self.ch_dur.render()

        # Quality chart
        ax3=self.ch_q.ax; self.ch_q.redraw()
        if se:
            dts=[]; qs=[]; scs=[]
            for d,s in sd:
                dts.append(d[-5:])
                if s: qs.append(s.get("quality",0)); scs.append(s.get("score",0)/20)
                else: qs.append(None); scs.append(None)
            vq=[(i,q) for i,q in enumerate(qs) if q]; vs=[(i,s) for i,s in enumerate(scs) if s]
            if vq:
                qx,qy=zip(*vq); qc=[QUALITY_COLOURS.get(int(round(q)),T.TEXT_MUTED) for q in qy]
                ax3.scatter(qx,qy,c=qc,s=50,zorder=3,label="Quality")
            if vs:
                sx,sy=zip(*vs); ax3.plot(sx,sy,color=T.BLUE,linewidth=1.5,alpha=0.7,linestyle="--",label="Score/20")
            ax3.set_xticks(range(len(dts))); ax3.set_xticklabels(dts,rotation=45,ha="right",fontsize=7)
            ax3.set_ylim(0,5.5); ax3.set_ylabel("Rating",fontsize=9)
            ax3.legend(loc="upper left",fontsize=7,facecolor=T.CHART_BG,edgecolor=T.BORDER,labelcolor=T.TEXT_SEC)
        else: ax3.text(0.5,0.5,"No data",transform=ax3.transAxes,ha="center",va="center",color=T.TEXT_MUTED,fontsize=11)
        self.ch_q.render()

        # Factors chart
        ax4=self.ch_f.ax; self.ch_f.redraw()
        if se:
            fc=defaultdict(int)
            for s in se:
                for f in s.get("factors",[]): fc[f]+=1
            if fc:
                sf=sorted(fc.items(),key=lambda x:x[1],reverse=True); ns=[f[0] for f in sf]; cs=[f[1] for f in sf]
                bc=[T.AMBER if n in ("Caffeine","Alcohol","Screen Time","Stress","Late Meal") else T.GREEN for n in ns]
                ax4.barh(range(len(ns)),cs,color=bc,height=0.5,alpha=0.85)
                ax4.set_yticks(range(len(ns))); ax4.set_yticklabels(ns,fontsize=8); ax4.set_xlabel("Count",fontsize=9); ax4.invert_yaxis()
            else: ax4.text(0.5,0.5,"No factors logged",transform=ax4.transAxes,ha="center",va="center",color=T.TEXT_MUTED,fontsize=11)
        else: ax4.text(0.5,0.5,"No data",transform=ax4.transAxes,ha="center",va="center",color=T.TEXT_MUTED,fontsize=11)
        self.ch_f.render()

# ── 7E : SETTINGS ────────────────────────────────────────────────────────────
class SettingsPage(ctk.CTkScrollableFrame):
    def __init__(self, parent, dm, app_ref, **kw):
        super().__init__(parent,fg_color=T.BG,scrollbar_button_color=T.BORDER,
                         scrollbar_button_hover_color=T.TEXT_MUTED,**kw)
        self.dm=dm; self.app=app_ref; self._build()
    def _sect(self,t,c=T.BLUE):
        ctk.CTkFrame(self,height=1,fg_color=T.DIVIDER).pack(fill="x",padx=T.PAD_LG,pady=(T.PAD_MD,T.PAD_SM))
        ctk.CTkLabel(self,text=t,font=ctk.CTkFont(size=14,weight="bold"),text_color=c).pack(anchor="w",padx=T.PAD_LG,pady=(0,T.PAD_SM))
    def _build(self):
        ctk.CTkLabel(self,text="Settings",font=ctk.CTkFont(size=20,weight="bold"),text_color=T.TEXT).pack(anchor="w",padx=T.PAD_LG,pady=(T.PAD_MD,T.PAD_SM))
        self._sect("Appearance")
        or_=ctk.CTkFrame(self,fg_color="transparent"); or_.pack(fill="x",padx=T.PAD_LG,pady=4)
        ctk.CTkLabel(or_,text="Opacity",font=ctk.CTkFont(size=12),text_color=T.TEXT_SEC).pack(side="left")
        self._ol=ctk.CTkLabel(or_,text=f"{int(self.dm.settings['opacity']*100)}%",font=ctk.CTkFont(size=11),text_color=T.TEXT_MUTED); self._ol.pack(side="right")
        ctk.CTkSlider(self,from_=0.3,to=1.0,number_of_steps=14,fg_color=T.BORDER,progress_color=T.BLUE,
                       button_color=T.TEXT,button_hover_color=T.BLUE,command=self._so).set(self.dm.settings["opacity"])
        self.children[list(self.children.keys())[-1]].pack(fill="x",padx=T.PAD_LG,pady=(0,T.PAD_SM))
        self._av=ctk.BooleanVar(value=self.dm.settings["always_on_top"])
        ctk.CTkSwitch(self,text="Always on Top",variable=self._av,font=ctk.CTkFont(size=12),text_color=T.TEXT_SEC,
                       fg_color=T.BORDER,progress_color=T.BLUE,button_color=T.TEXT,button_hover_color=T.BLUE,
                       command=self._ta).pack(anchor="w",padx=T.PAD_LG,pady=4)
        self._sect("Reminders")
        self._rv=ctk.BooleanVar(value=self.dm.settings.get("reminders_enabled",True))
        ctk.CTkSwitch(self,text="Dose reminders",variable=self._rv,font=ctk.CTkFont(size=12),text_color=T.TEXT_SEC,
                       fg_color=T.BORDER,progress_color=T.BLUE,button_color=T.TEXT,button_hover_color=T.BLUE,
                       command=self._tr).pack(anchor="w",padx=T.PAD_LG,pady=4)
        for label,key,values in [("Grace window","reminder_grace_minutes",["15","30","60","120"]),
                                 ("Snooze for","reminder_snooze_minutes",["5","15","30","60"]),
                                 ("Reorder lead time","low_stock_lead_days",["3","7","14","30"])]:
            rr=ctk.CTkFrame(self,fg_color="transparent"); rr.pack(fill="x",padx=T.PAD_LG,pady=2)
            ctk.CTkLabel(rr,text=label,font=ctk.CTkFont(size=11),text_color=T.TEXT_SEC).pack(side="left")
            ctk.CTkOptionMenu(rr,values=values,width=96,fg_color=T.INPUT_BG,button_color=T.BORDER,
                              dropdown_fg_color=T.SURFACE,command=lambda v,k=key:self._rs(k,v)).set(str(self.dm.settings.get(key,values[0])))
            menu=rr.winfo_children()[-1]; menu.pack(side="right")
        self._sect("Sleep personalization")
        chronotype=self.dm.settings.get("chronotype","Not set")
        self._ct_label=ctk.CTkLabel(self,text=f"Chronotype: {chronotype}",font=ctk.CTkFont(size=11),text_color=T.TEXT_SEC)
        self._ct_label.pack(anchor="w",padx=T.PAD_LG,pady=(0,4))
        ctk.CTkButton(self,text="Take 5-question MEQ quiz",height=34,font=ctk.CTkFont(size=12),fg_color=T.SURFACE,
                      hover_color=T.HOVER,text_color=T.TEAL,border_width=1,border_color=T.BORDER,
                      anchor="w",command=self._quiz).pack(fill="x",padx=T.PAD_LG,pady=2)
        self._sect("Profiles")
        self._profile_label=ctk.CTkLabel(self,text="",font=ctk.CTkFont(size=11),text_color=T.TEXT_SEC)
        self._profile_label.pack(anchor="w",padx=T.PAD_LG,pady=(0,4))
        self._profile_menu=ctk.CTkOptionMenu(self,values=[],width=220,fg_color=T.INPUT_BG,button_color=T.BORDER,
                                             dropdown_fg_color=T.SURFACE,command=self._switch_profile)
        self._profile_menu.pack(anchor="w",padx=T.PAD_LG,pady=(0,4))
        ctk.CTkButton(self,text="Add profile",height=34,font=ctk.CTkFont(size=12),fg_color=T.SURFACE,
                      hover_color=T.HOVER,text_color=T.TEAL,border_width=1,border_color=T.BORDER,
                      anchor="w",command=self._add_profile).pack(fill="x",padx=T.PAD_LG,pady=2)
        self._refresh_profile_controls()
        self._sect("Data security",T.AMBER)
        self._encryption_label=ctk.CTkLabel(self,text="",font=ctk.CTkFont(size=11),text_color=T.TEXT_SEC)
        self._encryption_label.pack(anchor="w",padx=T.PAD_LG,pady=(0,4))
        self._encryption_button=ctk.CTkButton(self,text="",height=34,font=ctk.CTkFont(size=12),fg_color=T.SURFACE,
                                              hover_color=T.HOVER,text_color=T.AMBER,border_width=1,border_color=T.BORDER,
                                              anchor="w",command=self._toggle_encryption)
        self._encryption_button.pack(fill="x",padx=T.PAD_LG,pady=2)
        self._refresh_encryption_controls()
        self._sect("Sync folder",T.TEAL)
        self._sync_label=ctk.CTkLabel(self,text="",font=ctk.CTkFont(size=11),text_color=T.TEXT_SEC,wraplength=460,justify="left")
        self._sync_label.pack(anchor="w",padx=T.PAD_LG,pady=(0,4))
        ctk.CTkButton(self,text="Choose sync folder",height=34,font=ctk.CTkFont(size=12),fg_color=T.SURFACE,
                      hover_color=T.HOVER,text_color=T.TEAL,border_width=1,border_color=T.BORDER,
                      anchor="w",command=self._choose_sync_folder).pack(fill="x",padx=T.PAD_LG,pady=2)
        ctk.CTkButton(self,text="Use local APPDATA storage",height=34,font=ctk.CTkFont(size=12),fg_color=T.SURFACE,
                      hover_color=T.HOVER,text_color=T.TEXT_SEC,border_width=1,border_color=T.BORDER,
                      anchor="w",command=self._use_local_storage).pack(fill="x",padx=T.PAD_LG,pady=2)
        self._refresh_sync_controls()
        self._sect("Data Management")
        for txt,cmd,clr in [("Export Data (JSON)",self._exp,T.BLUE),("Export Pill Log (CSV)",self._csv,T.BLUE),
                             ("Export Full Backup (CSV)",self._csv_full,T.TEAL),
                             ("Export FHIR Bundle (JSON)",self._fhir,T.PURPLE),
                             ("Export Monthly Adherence (PDF)",self._pdf,T.PURPLE),
                             ("Import Data (JSON)",self._imp,T.BLUE),("Import Full Backup (CSV)",self._imp_csv,T.TEAL),
                             ("Open Data Folder",self._folder,T.TEXT_SEC)]:
            ctk.CTkButton(self,text=txt,height=34,font=ctk.CTkFont(size=12),fg_color=T.SURFACE,hover_color=T.HOVER,
                           text_color=clr,border_width=1,border_color=T.BORDER,anchor="w",command=cmd).pack(fill="x",padx=T.PAD_LG,pady=2)
        self._sect("Danger Zone",T.RED)
        ctk.CTkButton(self,text="Reset All Data",height=34,font=ctk.CTkFont(size=12),fg_color=T.SURFACE,
                       hover_color="#2a0d0d",text_color=T.RED,border_width=1,border_color=T.BTN_DNG,
                       command=self._reset).pack(fill="x",padx=T.PAD_LG,pady=2)
        self._sect("Audit log",T.TEXT_SEC)
        ctk.CTkButton(self,text="View recent edits",height=34,font=ctk.CTkFont(size=12),fg_color=T.SURFACE,
                      hover_color=T.HOVER,text_color=T.TEXT_SEC,border_width=1,border_color=T.BORDER,
                      anchor="w",command=self._audit_log).pack(fill="x",padx=T.PAD_LG,pady=2)
        self._sect("About")
        ctk.CTkLabel(self,text=f"PillSleepTracker Pro v2.0\nData: {self.dm.data_dir}\n\nBuilt with Python + CustomTkinter + Matplotlib",
                      font=ctk.CTkFont(size=11),text_color=T.TEXT_MUTED,justify="left").pack(anchor="w",padx=T.PAD_LG,pady=(4,T.PAD_LG))
    def _so(self,v): self.dm.settings["opacity"]=round(v,2); self.app.attributes("-alpha",v); self._ol.configure(text=f"{int(v*100)}%")
    def _ta(self): self.dm.settings["always_on_top"]=self._av.get(); self.app.attributes("-topmost",self._av.get())
    def _tr(self): self.dm.settings["reminders_enabled"]=self._rv.get(); self.dm.save_settings()
    def _rs(self,key,value): self.dm.settings[key]=int(value); self.dm.save_settings()
    def _refresh_encryption_controls(self):
        if self.dm.data_encrypted:
            self._encryption_label.configure(text="Status: encrypted with AES-GCM. The passphrase is never stored.",text_color=T.GREEN)
            self._encryption_button.configure(text="Disable encrypted storage")
        else:
            self._encryption_label.configure(text="Status: plain JSON. Encryption is optional and passphrase-protected.",text_color=T.TEXT_SEC)
            self._encryption_button.configure(text="Enable AES-GCM storage")
    def _refresh_sync_controls(self):
        configured=self.dm.settings.get("sync_folder","")
        label=str(self.dm.data_dir) if configured else f"Local storage: {self.dm.data_dir}"
        self._sync_label.configure(text=f"Current data folder:\n{label}")
    def _set_sync_folder(self, folder):
        target=Path(folder).expanduser()
        if target.resolve()!=self.dm.data_dir.resolve() and (target/"tracker_data.json").exists():
            if not messagebox.askyesno("Use existing sync data","This folder already contains tracker_data.json. Use it as the canonical data file? The current local view will be replaced.",parent=self.winfo_toplevel()): return
        try:
            self.dm.configure_sync_folder(target); self._refresh_sync_controls(); self._refresh_encryption_controls()
            messagebox.showinfo("Sync folder updated",f"Tracker data now uses:\n{self.dm.data_dir}",parent=self.winfo_toplevel())
        except Exception as exc: messagebox.showerror("Sync folder failed",str(exc),parent=self.winfo_toplevel())
    def _choose_sync_folder(self):
        folder=filedialog.askdirectory(parent=self.winfo_toplevel(),title="Choose a local sync folder")
        if folder: self._set_sync_folder(folder)
    def _use_local_storage(self): self._set_sync_folder(self.dm.local_data_dir)
    def _toggle_encryption(self):
        if self.dm.data_encrypted:
            if messagebox.askyesno("Disable encryption","Write tracker_data.json as plain JSON? Anyone who can read the file will be able to see it.",parent=self.winfo_toplevel()):
                self.dm.disable_encryption(); self._refresh_encryption_controls(); messagebox.showinfo("Encryption disabled","The data file is now plain JSON.",parent=self.winfo_toplevel())
            return
        first=simpledialog.askstring("Encrypt tracker data","Choose a passphrase (at least 8 characters):",show="*",parent=self.winfo_toplevel())
        if first is None: return
        second=simpledialog.askstring("Confirm passphrase","Enter the passphrase again:",show="*",parent=self.winfo_toplevel())
        if first!=second:
            messagebox.showwarning("Passphrases differ","The passphrases did not match; encryption was not enabled.",parent=self.winfo_toplevel()); return
        try:
            self.dm.enable_encryption(first); self._refresh_encryption_controls(); messagebox.showinfo("Encryption enabled","Tracker data is now protected with AES-GCM. If you forget the passphrase, the data cannot be recovered.",parent=self.winfo_toplevel())
        except (RuntimeError,ValueError) as exc: messagebox.showerror("Encryption failed",str(exc),parent=self.winfo_toplevel())
    def _refresh_profile_controls(self):
        names=[str(profile.get("name","Profile")) for profile in self.dm.profiles]
        current=str(self.dm.profile.get("name","Default"))
        self._profile_menu.configure(values=names)
        self._profile_menu.set(current)
        self._profile_label.configure(text=f"Active profile: {current}")
    def _switch_profile(self,name):
        profile=next((item for item in self.dm.profiles if item.get("name")==name),None)
        if not profile or profile.get("id")==self.dm.profile_id:
            return
        pin=""
        if profile.get("pin_hash"):
            pin=simpledialog.askstring("Profile PIN",f"Enter the PIN for {name}:",show="*",parent=self.winfo_toplevel())
            if pin is None:
                self._refresh_profile_controls(); return
        if not self.dm.switch_profile(profile["id"],pin):
            messagebox.showwarning("Profile locked","That PIN was not accepted.",parent=self.winfo_toplevel())
            self._refresh_profile_controls(); return
        self._refresh_profile_controls(); self.app._nav("dashboard")
    def _add_profile(self):
        name=simpledialog.askstring("Add profile","Name for the new household profile:",parent=self.winfo_toplevel())
        if name is None: return
        pin=simpledialog.askstring("Set profile PIN","Optional PIN (leave blank for no PIN):",show="*",parent=self.winfo_toplevel())
        if pin is None: return
        profile=self.dm.create_profile(name,pin)
        if not profile:
            messagebox.showwarning("Profile unavailable","Use a unique non-empty profile name.",parent=self.winfo_toplevel()); return
        self.dm.switch_profile(profile["id"],pin); self._refresh_profile_controls(); self.app._nav("dashboard")
    def _quiz(self):
        dlg=ctk.CTkToplevel(self.winfo_toplevel()); dlg.title("Chronotype quiz"); dlg.geometry("520x560"); dlg.configure(fg_color=T.BG); dlg.attributes("-topmost",True); dlg.grab_set()
        sc=ctk.CTkScrollableFrame(dlg,fg_color=T.BG); sc.pack(fill="both",expand=True,padx=T.PAD_MD,pady=T.PAD_MD)
        vars_=[]
        for index,question in enumerate(MEQ_QUESTIONS,1):
            ctk.CTkLabel(sc,text=f"{index}. {question['prompt']}",font=ctk.CTkFont(size=11,weight="bold"),text_color=T.TEXT,
                          wraplength=450,justify="left").pack(anchor="w",pady=(T.PAD_SM,2))
            labels=[label for label,_ in question["options"]]; var=ctk.StringVar(value=labels[2]); vars_.append((var,dict(question["options"])))
            ctk.CTkOptionMenu(sc,values=labels,variable=var,fg_color=T.INPUT_BG,button_color=T.BORDER,
                              dropdown_fg_color=T.SURFACE).pack(fill="x",pady=(0,2))
        def _save_quiz():
            result=score_chronotype([scores[var.get()] for var,scores in vars_])
            self.dm.settings.update({"chronotype":result["category"],"chronotype_score":result["score"]}); self.dm.save_settings()
            self._ct_label.configure(text=f"Chronotype: {result['category']}  ({result['score']}/5)")
            dlg.destroy(); messagebox.showinfo("Chronotype saved",f"Profile set to {result['category']}. Future sleep scores will use this weighting.",parent=self.winfo_toplevel())
        ctk.CTkButton(dlg,text="Save result",height=36,fg_color=T.BTN_PRI,hover_color=T.BTN_PRI_H,command=_save_quiz).pack(fill="x",padx=T.PAD_MD,pady=(0,T.PAD_MD))
    def _exp(self):
        fp=filedialog.asksaveasfilename(parent=self.winfo_toplevel(),defaultextension=".json",filetypes=[("JSON","*.json")],initialfile="pillsleep_backup.json")
        if fp: self.dm.export_json(fp); messagebox.showinfo("Done",f"Exported to:\n{fp}",parent=self.winfo_toplevel())
    def _csv(self):
        fp=filedialog.asksaveasfilename(parent=self.winfo_toplevel(),defaultextension=".csv",filetypes=[("CSV","*.csv")],initialfile="pill_log.csv")
        if fp:
            with open(fp,"w",newline="",encoding="utf-8") as f:
                w=csv.writer(f); w.writerow(["Date","Time","Medication","Action"])
                for l in sorted(self.dm._med_logs(),key=lambda x:x["date"]): w.writerow([l["date"],l.get("time",""),l["med_name"],l["action"]])
            messagebox.showinfo("Done",f"CSV exported to:\n{fp}",parent=self.winfo_toplevel())
    def _csv_full(self):
        fp=filedialog.asksaveasfilename(parent=self.winfo_toplevel(),defaultextension=".csv",filetypes=[("CSV","*.csv")],initialfile="pillsleep_backup.csv")
        if fp: export_tracker_csv(fp,self.dm.data); messagebox.showinfo("Done",f"Full backup exported to:\n{fp}",parent=self.winfo_toplevel())
    def _fhir(self):
        fp=filedialog.asksaveasfilename(parent=self.winfo_toplevel(),defaultextension=".json",filetypes=[("FHIR JSON","*.json")],initialfile="pillsleep_fhir_bundle.json")
        if fp:
            try:
                self.dm.export_fhir(fp); messagebox.showinfo("Done","FHIR bundle exported for the active profile.",parent=self.winfo_toplevel())
            except Exception as exc: messagebox.showerror("FHIR export failed",str(exc),parent=self.winfo_toplevel())
    def _pdf(self):
        now=datetime.now()
        fp=filedialog.asksaveasfilename(parent=self.winfo_toplevel(),defaultextension=".pdf",
                                        filetypes=[("PDF","*.pdf")],initialfile=f"adherence_{now:%Y_%m}.pdf")
        if fp:
            try:
                self.dm.export_monthly_adherence_pdf(fp,now.year,now.month)
                messagebox.showinfo("Done",f"PDF exported to:\n{fp}",parent=self.winfo_toplevel())
            except Exception as exc:
                messagebox.showerror("Export failed",str(exc),parent=self.winfo_toplevel())
    def _imp(self):
        fp=filedialog.askopenfilename(parent=self.winfo_toplevel(),filetypes=[("JSON","*.json")])
        if fp:
            try:
                self.dm.import_json(fp); self._refresh_profile_controls(); messagebox.showinfo("Done","Imported tracker data.",parent=self.winfo_toplevel())
            except Exception as e: messagebox.showerror("Error",str(e),parent=self.winfo_toplevel())
    def _imp_csv(self):
        fp=filedialog.askopenfilename(parent=self.winfo_toplevel(),filetypes=[("CSV","*.csv")])
        if fp:
            try:
                self.dm.import_csv(fp); self._refresh_profile_controls(); messagebox.showinfo("Done","Imported full CSV backup.",parent=self.winfo_toplevel())
            except Exception as e: messagebox.showerror("Error",str(e),parent=self.winfo_toplevel())
    def _folder(self):
        try:
            if sys.platform=="win32": os.startfile(self.dm.data_dir)
            elif sys.platform=="darwin": subprocess.Popen(["open",str(self.dm.data_dir)])
            else: subprocess.Popen(["xdg-open",str(self.dm.data_dir)])
        except: messagebox.showinfo("Path",str(self.dm.data_dir),parent=self.winfo_toplevel())
    def _audit_log(self):
        dlg=ctk.CTkToplevel(self.winfo_toplevel()); dlg.title("Audit log"); dlg.geometry("720x520"); dlg.configure(fg_color=T.BG); dlg.attributes("-topmost",True)
        box=ctk.CTkTextbox(dlg,fg_color=T.INPUT_BG,text_color=T.TEXT,font=ctk.CTkFont(size=11)); box.pack(fill="both",expand=True,padx=T.PAD_MD,pady=T.PAD_MD)
        entries=sorted(self.dm.audit_entries,key=lambda event:event.get("timestamp",""),reverse=True)[:200]
        if not entries: box.insert("1.0","No edits recorded yet.")
        else:
            lines=[]
            for event in entries:
                details=json.dumps(event.get("details",{}),ensure_ascii=False,sort_keys=True)
                scope="system" if not event.get("profile_id") else event["profile_id"]
                lines.append(f"{event.get('timestamp','')}  {event.get('action','')}  {event.get('entity','')}  [{scope}]  {details}")
            box.insert("1.0","\n".join(lines))
        box.configure(state="disabled")
    def _reset(self):
        if messagebox.askyesno("Reset","DELETE all data?\nCannot be undone!",parent=self.winfo_toplevel()):
            self.dm.data=normalize_tracker_data({"medications":[],"med_log":[],"sleep_log":[],"profiles":[],"audit_log":[]})
            self.dm.settings["active_profile_id"]="default"; self.dm._audit("reset","tracker_data","",{},profile_id=""); self.dm.save_data(); self.dm.save_settings(); self.refresh()
    def refresh(self): self._refresh_profile_controls(); self._refresh_encryption_controls(); self._refresh_sync_controls()

# ==============================================================================
#  SECTION 8 : MAIN APPLICATION
# ==============================================================================
class PillSleepTrackerPro(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark"); ctk.set_default_color_theme("dark-blue")
        self.dm=self._load_data_manager(); s=self.dm.settings
        self.title("PillSleepTracker Pro")
        self.geometry(f"{s['window_w']}x{s['window_h']}+{s['window_x']}+{s['window_y']}")
        self.minsize(420,500); self.configure(fg_color=T.BG)
        self.attributes("-topmost",s["always_on_top"]); self.attributes("-alpha",s["opacity"])
        self.protocol("WM_DELETE_WINDOW",self._close); self._drag={"x":0,"y":0}
        self._build_tb()
        self.body=ctk.CTkFrame(self,fg_color=T.BG,corner_radius=0); self.body.pack(fill="both",expand=True)
        self.toast=ToastManager(self)
        self.sidebar=Sidebar(self.body,on_nav=self._nav); self.sidebar.pack(side="left",fill="y")
        self.content=ctk.CTkFrame(self.body,fg_color=T.BG,corner_radius=0); self.content.pack(side="left",fill="both",expand=True)
        self.pages={}; self._build_pages(); self._nav(s.get("active_page","dashboard"))
        self._autosave(); self._tray=None
        _register_toast_protocol()
        self.reminders=ReminderManager(self,self.dm,self.toast); self.reminders.start()
        if HAS_TRAY and HAS_PIL and not os.environ.get("PST_TEST_MODE"): threading.Thread(target=self._setup_tray,daemon=True).start()

    def _load_data_manager(self):
        passphrase=None
        for attempt in range(3):
            try:
                return DataManager(passphrase)
            except DataPassphraseRequired:
                passphrase=simpledialog.askstring("Unlock tracker data","Enter the data-file passphrase:",show="*",parent=self)
                if passphrase is None: raise SystemExit(1)
            except ValueError:
                if attempt>=2:
                    messagebox.showerror("Unable to unlock data","The passphrase was incorrect or tracker_data.json is damaged.",parent=self)
                    raise SystemExit(1)
                messagebox.showwarning("Try again","The passphrase was not accepted.",parent=self)
                passphrase=None
        raise SystemExit(1)

    def _build_tb(self):
        tb=ctk.CTkFrame(self,height=32,fg_color=T.TITLEBAR,corner_radius=0); tb.pack(fill="x"); tb.pack_propagate(False)
        tl=ctk.CTkLabel(tb,text="  PillSleepTracker Pro",font=ctk.CTkFont(size=12,weight="bold"),text_color=T.TEXT_SEC); tl.pack(side="left",padx=4)
        ctk.CTkButton(tb,text="\u2715",width=32,height=28,font=ctk.CTkFont(size=12),fg_color="transparent",hover_color=T.BTN_DNG,text_color=T.TEXT_SEC,command=self._close).pack(side="right",padx=2)
        ctk.CTkButton(tb,text="\u2014",width=32,height=28,font=ctk.CTkFont(size=10),fg_color="transparent",hover_color=T.HOVER,text_color=T.TEXT_SEC,command=self.iconify).pack(side="right",padx=2)
        self._pin=ctk.CTkButton(tb,text="\u25C9" if self.dm.settings["always_on_top"] else "\u25CB",width=32,height=28,font=ctk.CTkFont(size=14),
                                  fg_color="transparent",hover_color=T.HOVER,text_color=T.BLUE if self.dm.settings["always_on_top"] else T.TEXT_MUTED,command=self._toggle_pin)
        self._pin.pack(side="right",padx=2)
        for w in (tb,tl): w.bind("<Button-1>",self._sd); w.bind("<B1-Motion>",self._od)
    def _sd(self,e): self._drag["x"]=e.x_root-self.winfo_x(); self._drag["y"]=e.y_root-self.winfo_y()
    def _od(self,e): self.geometry(f"+{e.x_root-self._drag['x']}+{e.y_root-self._drag['y']}")
    def _toggle_pin(self):
        self.dm.settings["always_on_top"]=not self.dm.settings["always_on_top"]; aot=self.dm.settings["always_on_top"]
        self.attributes("-topmost",aot); self._pin.configure(text="\u25C9" if aot else "\u25CB",text_color=T.BLUE if aot else T.TEXT_MUTED)

    def _build_pages(self):
        self.pages["dashboard"]=DashboardPage(self.content,self.dm,self.toast,on_nav=self._nav)
        self.pages["meds"]=MedicationsPage(self.content,self.dm,self.toast)
        self.pages["sleep"]=SleepPage(self.content,self.dm,self.toast)
        self.pages["analytics"]=AnalyticsPage(self.content,self.dm)
        self.pages["settings"]=SettingsPage(self.content,self.dm,self)

    def _nav(self,k):
        for p in self.pages.values(): p.pack_forget()
        if k in self.pages: self.pages[k].pack(fill="both",expand=True); self.pages[k].refresh(); self.sidebar.set_active(k); self.dm.settings["active_page"]=k

    def _autosave(self):
        try: self.dm.settings.update({"window_x":self.winfo_x(),"window_y":self.winfo_y(),"window_w":self.winfo_width(),"window_h":self.winfo_height()})
        except: pass
        self.dm.save_settings(); self.after(30000,self._autosave)

    def _close(self):
        if getattr(self,"reminders",None): self.reminders.stop()
        try: self.dm.settings.update({"window_x":self.winfo_x(),"window_y":self.winfo_y(),"window_w":self.winfo_width(),"window_h":self.winfo_height()})
        except: pass
        self.dm.save_settings(); self.dm.save_data()
        if self._tray:
            try: self._tray.stop()
            except: pass
        self.destroy()

    def _setup_tray(self):
        try:
            img=Image.new("RGBA",(64,64),(0,0,0,0)); draw=ImageDraw.Draw(img)
            draw.rounded_rectangle([4,18,60,46],radius=14,fill="#58a6ff"); draw.rounded_rectangle([32,18,60,46],radius=14,fill="#bc8cff")
            draw.ellipse([26,26,38,38],fill="white")
            menu=pystray.Menu(pystray.MenuItem("Show",lambda i,item:self.after(0,self._show_tray),default=True),
                              pystray.Menu.SEPARATOR,pystray.MenuItem("Quit",lambda i,item:self.after(0,self._close)))
            self._tray=pystray.Icon("PST",img,"PillSleepTracker Pro",menu); self._tray.run()
        except: pass
    def _show_tray(self): self.deiconify(); self.attributes("-topmost",self.dm.settings["always_on_top"]); self.lift(); self.focus_force()

# ==============================================================================
#  SECTION 9 : ENTRY POINT
# ==============================================================================
def _handle_toast_action(uri):
    """Apply a protocol toast action in a short-lived helper process."""
    from urllib.parse import unquote, urlparse
    parsed=urlparse(uri)
    parts=[unquote(part) for part in parsed.path.strip("/").split("/") if part]
    if parsed.scheme!="pillsleeptracker" or len(parts)<2 or parts[0]!="dose": return False
    action,dose_id=parts[1],parts[2] if len(parts)>2 else ""
    dm=DataManager()
    dose=next((item for item in dm.due_doses() if item.get("dose_id")==dose_id),None)
    if not dose: return False
    if action=="taken": return dm.log_dose_action(dose["med_id"],"taken",dose=dose)
    if action=="skipped": return dm.log_dose_action(dose["med_id"],"skipped",dose=dose)
    if action=="snooze": return dm.snooze_dose(dose["med_id"],dose=dose)
    return False


if __name__=="__main__":
    if len(sys.argv)>1 and sys.argv[1].startswith("pillsleeptracker://"):
        _handle_toast_action(sys.argv[1]); sys.exit(0)
    app=PillSleepTrackerPro()
    app.mainloop()
