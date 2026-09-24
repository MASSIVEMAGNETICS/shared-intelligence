from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Literal, Optional

try:
    import fcntl
except ImportError:  # pragma: no cover - exercised on Windows
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover - exercised on POSIX
    msvcrt = None

from bando_sources import SourceObjective, github_pr_objectives, intent_graph_objectives

State = Literal["QUEUED", "ACTIVE", "BLOCKED", "DONE", "ARCHIVED", "FAILED"]
Stage = Literal["DISCOVERY", "BUILD", "VERIFY", "DEPLOY", "SELL", "OBSERVE", "SCALE"]

TERMINAL_STATES = {"DONE", "ARCHIVED", "FAILED"}
OPEN_STATES = {"QUEUED", "ACTIVE", "BLOCKED"}

class DriverError(RuntimeError): pass
class CapacityError(DriverError): pass
class ValidationError(DriverError): pass

@dataclass
class Objective:
    id: str
    title: str
    next_action: str
    state: State = "QUEUED"
    stage: Stage = "DISCOVERY"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    value: float = 3.0
    readiness: float = 3.0
    evidence: float = 3.0
    reversibility: float = 3.0
    leverage: float = 3.0
    cost: float = 3.0
    delay: float = 3.0
    dependency: float = 3.0
    revenue_potential: float = 0.0
    deployment_gap: float = 0.0
    novelty_quarantine_until: Optional[str] = None
    blocker: Optional[str] = None
    evidence_ref: Optional[str] = None
    kill_condition: Optional[str] = None

    def validate(self) -> None:
        if not self.id.strip(): raise ValidationError("objective id is required")
        if not self.title.strip(): raise ValidationError("objective title is required")
        if not self.next_action.strip() and self.state not in TERMINAL_STATES: raise ValidationError("open objective requires next_action")
        for name in ("value","readiness","evidence","reversibility","leverage","cost","delay","dependency","revenue_potential","deployment_gap"):
            v = getattr(self, name)
            if not isinstance(v, (int, float)) or not math.isfinite(v): raise ValidationError(f"{name} must be finite")
            if v < 0 or v > 5: raise ValidationError(f"{name} must be between 0 and 5")
        if self.cost <= 0 or self.delay <= 0 or self.dependency <= 0: raise ValidationError("cost, delay, dependency must be > 0")
        if self.state == "BLOCKED" and not self.blocker: raise ValidationError("BLOCKED objective requires blocker")

    def quarantined(self, now: Optional[datetime] = None) -> bool:
        if not self.novelty_quarantine_until: return False
        now = now or datetime.now(timezone.utc)
        try: until = datetime.fromisoformat(self.novelty_quarantine_until)
        except ValueError as exc: raise ValidationError("invalid novelty_quarantine_until") from exc
        if until.tzinfo is None: until = until.replace(tzinfo=timezone.utc)
        return now < until

    def score(self) -> float:
        self.validate()
        base = (self.value*self.readiness*self.evidence*self.reversibility*self.leverage)/(self.cost*self.delay*self.dependency)
        revenue_boost = 1.0 + (0.18*self.revenue_potential)
        deployment_boost = 1.0 + (0.12*self.deployment_gap)
        stage_boost = {"DISCOVERY":0.70,"BUILD":0.90,"VERIFY":1.05,"DEPLOY":1.20,"SELL":1.35,"OBSERVE":1.10,"SCALE":1.15}[self.stage]
        blocked_penalty = 0.15 if self.state == "BLOCKED" else 1.0
        terminal_penalty = 0.0 if self.state in TERMINAL_STATES else 1.0
        return base*revenue_boost*deployment_boost*stage_boost*blocked_penalty*terminal_penalty

class BandoDriver:
    def __init__(self, registry_path: str | Path = ".bando_driver.json", max_active: int = 3):
        if max_active < 1: raise ValidationError("max_active must be >= 1")
        self.registry_path = Path(registry_path); self.max_active=max_active; self.objectives: Dict[str,Objective]={}; self._load()

    def _load(self, *, load_policy: bool = True) -> None:
        if not self.registry_path.exists():
            self.objectives = {}
            return
        raw=json.loads(self.registry_path.read_text(encoding="utf-8"))
        if raw.get("schema_version") != 1: raise ValidationError("unsupported registry schema_version")
        if load_policy: self.max_active=int(raw.get("max_active",self.max_active))
        loaded: Dict[str,Objective]={}
        for item in raw.get("objectives",[]):
            obj=Objective(**item); obj.validate()
            if obj.id in loaded: raise ValidationError(f"duplicate objective id: {obj.id}")
            loaded[obj.id]=obj
        self.objectives=loaded

    @contextmanager
    def _mutation(self):
        """Serialize registry mutations and reconcile them against the latest state."""
        self.registry_path.parent.mkdir(parents=True,exist_ok=True)
        lock_path=self.registry_path.with_name(self.registry_path.name+".lock")
        with lock_path.open("a+b") as lock_file:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(),fcntl.LOCK_EX)
            elif msvcrt is not None:  # pragma: no cover - exercised on Windows
                lock_file.seek(0,os.SEEK_END)
                if lock_file.tell()==0:
                    lock_file.write(b"\0"); lock_file.flush()
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(),msvcrt.LK_LOCK,1)
            else:  # pragma: no cover - unsupported platform
                raise DriverError("no supported inter-process registry lock")
            try:
                self._load(load_policy=False)
                yield
                self._save()
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(),fcntl.LOCK_UN)
                elif msvcrt is not None:  # pragma: no cover - exercised on Windows
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(),msvcrt.LK_UNLCK,1)

    def _save(self) -> None:
        payload={"schema_version":1,"max_active":self.max_active,"updated_at":datetime.now(timezone.utc).isoformat(),"objectives":[asdict(o) for o in sorted(self.objectives.values(),key=lambda x:x.id)]}
        self.registry_path.parent.mkdir(parents=True,exist_ok=True)
        fd,tmp_name=tempfile.mkstemp(prefix=self.registry_path.name+".",suffix=".tmp",dir=str(self.registry_path.parent),text=True)
        try:
            with os.fdopen(fd,"w",encoding="utf-8") as fh:
                json.dump(payload,fh,indent=2,sort_keys=True); fh.write("\n"); fh.flush(); os.fsync(fh.fileno())
            os.replace(tmp_name,self.registry_path)
        finally:
            if os.path.exists(tmp_name): os.unlink(tmp_name)

    def active(self)->List[Objective]: return [o for o in self.objectives.values() if o.state=="ACTIVE"]
    def add(self,objective:Objective,activate:bool=False)->Objective:
        with self._mutation():
            if objective.id in self.objectives: raise ValidationError(f"objective already exists: {objective.id}")
            objective.validate()
            if activate: self._assert_capacity(); objective.state="ACTIVE"
            self.objectives[objective.id]=objective
        return objective
    def _assert_capacity(self,excluding:Optional[str]=None)->None:
        if sum(1 for o in self.active() if o.id!=excluding)>=self.max_active: raise CapacityError(f"active WIP limit reached ({self.max_active}); close/block/archive one objective first")
    def set_state(self,objective_id:str,state:State,*,blocker:Optional[str]=None,evidence_ref:Optional[str]=None,next_action:Optional[str]=None)->Objective:
        with self._mutation():
            obj=self.require(objective_id)
            if state=="ACTIVE" and obj.state!="ACTIVE": self._assert_capacity(excluding=obj.id)
            if state=="BLOCKED" and not blocker: raise ValidationError("BLOCKED state requires blocker")
            if state in TERMINAL_STATES and not evidence_ref: raise ValidationError(f"{state} requires evidence_ref")
            obj.state=state; obj.blocker=blocker if state=="BLOCKED" else None
            if evidence_ref is not None: obj.evidence_ref=evidence_ref
            if next_action is not None: obj.next_action=next_action
            if state in TERMINAL_STATES: obj.next_action=""
            obj.updated_at=datetime.now(timezone.utc).isoformat(); obj.validate()
        return obj
    def update(self,objective_id:str,**changes)->Objective:
        with self._mutation():
            obj=self.require(objective_id); bad={"id","created_at"}.intersection(changes)
            if bad: raise ValidationError(f"immutable fields: {sorted(bad)}")
            for key,value in changes.items():
                if not hasattr(obj,key): raise ValidationError(f"unknown field: {key}")
                setattr(obj,key,value)
            obj.updated_at=datetime.now(timezone.utc).isoformat(); obj.validate()
        return obj
    def require(self,objective_id:str)->Objective:
        try: return self.objectives[objective_id]
        except KeyError as exc: raise ValidationError(f"unknown objective: {objective_id}") from exc
    def rank(self,include_queued:bool=True,include_blocked:bool=False,now:Optional[datetime]=None)->List[Objective]:
        now=now or datetime.now(timezone.utc); allowed={"ACTIVE"}
        if include_queued: allowed.add("QUEUED")
        if include_blocked: allowed.add("BLOCKED")
        return sorted([o for o in self.objectives.values() if o.state in allowed and not o.quarantined(now)],key=lambda o:(-o.score(),o.created_at,o.id))
    def next(self,now:Optional[datetime]=None)->Objective:
        ranked=self.rank(include_queued=True,now=now)
        if not ranked:
            blocked=self.rank(include_queued=False,include_blocked=True,now=now)
            if blocked: return blocked[0]
            raise DriverError("no executable objective available")
        active=[o for o in ranked if o.state=="ACTIVE"]; queued=[o for o in ranked if o.state=="QUEUED"]
        if active:
            best=active[0]
            if queued and queued[0].score()>=best.score()*1.20 and len(self.active())<self.max_active: return queued[0]
            return best
        return ranked[0]
    def decision(self)->dict:
        chosen=self.next(); return {"objective_id":chosen.id,"title":chosen.title,"state":chosen.state,"stage":chosen.stage,"score":round(chosen.score(),6),"next_action":chosen.next_action,"reason":("resolve blocker: "+(chosen.blocker or "blocked objective")) if chosen.state=="BLOCKED" else self._reason(chosen),"active_count":len(self.active()),"max_active":self.max_active}
    def _reason(self,obj:Objective)->str:
        reasons=[]
        if obj.revenue_potential>=4: reasons.append("high revenue adjacency")
        if obj.deployment_gap>=4: reasons.append("high closure/deployment value")
        if obj.stage in {"DEPLOY","SELL","OBSERVE"}: reasons.append(f"late-stage {obj.stage.lower()} work")
        if obj.readiness>=4: reasons.append("high readiness")
        if obj.evidence>=4: reasons.append("strong evidence")
        return "; ".join(reasons or ["highest current priority score"])

    def sync_sources(self,sources:Iterable[SourceObjective],*,activate_top:bool=True,authoritative_prefixes:Iterable[str]=())->dict:
        sources=list(sources); prefixes=tuple(authoritative_prefixes)
        with self._mutation():
            imported=0; updated=0; seen={src.id for src in sources}
            for src in sources:
                target_state:State="BLOCKED" if src.blocker else "QUEUED"
                if src.id in self.objectives:
                    obj=self.objectives[src.id]
                    if obj.state in TERMINAL_STATES: continue
                    for name in ("title","next_action","stage","value","readiness","evidence","reversibility","leverage","cost","delay","dependency","revenue_potential","deployment_gap","evidence_ref"):
                        setattr(obj,name,getattr(src,name))
                    if src.blocker: obj.state="BLOCKED"
                    elif obj.state!="ACTIVE": obj.state=target_state
                    obj.blocker=src.blocker if obj.state=="BLOCKED" else None
                    obj.updated_at=datetime.now(timezone.utc).isoformat(); obj.validate(); updated+=1
                else:
                    obj=Objective(id=src.id,title=src.title,next_action=src.next_action,state=target_state,stage=src.stage,value=src.value,readiness=src.readiness,evidence=src.evidence,reversibility=src.reversibility,leverage=src.leverage,cost=src.cost,delay=src.delay,dependency=src.dependency,revenue_potential=src.revenue_potential,deployment_gap=src.deployment_gap,blocker=src.blocker,evidence_ref=src.evidence_ref)
                    obj.validate(); self.objectives[obj.id]=obj; imported+=1
            # Absence is revocation only inside explicitly authoritative namespaces.
            # Partial/ad-hoc sync calls pass no prefixes and therefore cannot revoke
            # objectives they did not observe.
            revoked_absent=[]
            if prefixes:
                for obj in self.objectives.values():
                    if obj.state in TERMINAL_STATES or obj.id in seen: continue
                    if any(obj.id.startswith(prefix) for prefix in prefixes):
                        obj.state="BLOCKED"; obj.blocker="source absent from authoritative synchronization snapshot"; obj.next_action="Re-verify source existence and authority before reactivation"; obj.updated_at=datetime.now(timezone.utc).isoformat(); obj.validate(); revoked_absent.append(obj.id)
            if activate_top:
                while len(self.active())<self.max_active:
                    candidates=[o for o in self.rank(include_queued=True) if o.state=="QUEUED"]
                    if not candidates: break
                    winner=candidates[0]; winner.state="ACTIVE"; winner.updated_at=datetime.now(timezone.utc).isoformat()
            result={"imported":imported,"updated":updated,"revoked_absent":sorted(revoked_absent),"active":[o.id for o in sorted(self.active(),key=lambda x:-x.score())],"decision":self.decision() if self.rank(include_queued=True,include_blocked=True) else None}
        return result

    def status(self)->dict:
        counts={s:0 for s in ["QUEUED","ACTIVE","BLOCKED","DONE","ARCHIVED","FAILED"]}
        for obj in self.objectives.values(): counts[obj.state]+=1
        return {"counts":counts,"open_loops":sum(counts[s] for s in OPEN_STATES),"active_count":counts["ACTIVE"],"max_active":self.max_active,"wip_ok":counts["ACTIVE"]<=self.max_active}

def _float_0_5(value:str)->float:
    v=float(value)
    if not 0<=v<=5: raise argparse.ArgumentTypeError("must be between 0 and 5")
    return v

def build_parser()->argparse.ArgumentParser:
    p=argparse.ArgumentParser(description="BANDO_DRIVER: closure-first execution governor"); p.add_argument("--registry",default=".bando_driver.json"); p.add_argument("--max-active",type=int,default=3); sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("status"); sub.add_parser("next")
    sync=sub.add_parser("sync"); sync.add_argument("--github-repo",action="append",default=[]); sync.add_argument("--intent-graph"); sync.add_argument("--no-activate",action="store_true"); sync.add_argument("--config")
    add=sub.add_parser("add"); add.add_argument("--id",required=True); add.add_argument("--title",required=True); add.add_argument("--next-action",required=True); add.add_argument("--stage",choices=["DISCOVERY","BUILD","VERIFY","DEPLOY","SELL","OBSERVE","SCALE"],default="DISCOVERY"); add.add_argument("--activate",action="store_true")
    for name in ["value","readiness","evidence","reversibility","leverage","cost","delay","dependency","revenue-potential","deployment-gap"]: add.add_argument(f"--{name}",type=_float_0_5,default=0.0 if name in {"revenue-potential","deployment-gap"} else 3.0)
    state=sub.add_parser("state"); state.add_argument("id"); state.add_argument("state",choices=["QUEUED","ACTIVE","BLOCKED","DONE","ARCHIVED","FAILED"]); state.add_argument("--blocker"); state.add_argument("--evidence-ref"); state.add_argument("--next-action")
    ls=sub.add_parser("list"); ls.add_argument("--state",choices=["QUEUED","ACTIVE","BLOCKED","DONE","ARCHIVED","FAILED"])
    return p

def main(argv:Optional[Iterable[str]]=None)->int:
    args=build_parser().parse_args(list(argv) if argv is not None else None); driver=BandoDriver(args.registry,max_active=args.max_active)
    if args.cmd=="status": print(json.dumps(driver.status(),indent=2,sort_keys=True)); return 0
    if args.cmd=="next": print(json.dumps(driver.decision(),indent=2,sort_keys=True)); return 0
    if args.cmd=="sync":
        sources=[]; repos=list(args.github_repo); intent_path=args.intent_graph; activate_top=not args.no_activate
        if args.config:
            cfg=json.loads(Path(args.config).read_text(encoding="utf-8"))
            if cfg.get("schema_version")!=1: raise DriverError("unsupported stack config schema_version")
            repos.extend(str(x) for x in cfg.get("repositories",[])); configured=cfg.get("intent_graph_snapshot")
            if configured and not intent_path and Path(configured).exists(): intent_path=configured
            if isinstance(cfg.get("max_active"),int): driver.max_active=cfg["max_active"]
            activate_top=bool(cfg.get("policy",{}).get("activate_top",activate_top)) and not args.no_activate
        repos=list(dict.fromkeys(repos))
        if repos: sources.extend(github_pr_objectives(repos))
        if intent_path: sources.extend(intent_graph_objectives(intent_path))
        if not sources and not repos: raise DriverError("sync found no source objectives")
        prefixes=[f"github:{repo}:pr:" for repo in repos]
        print(json.dumps(driver.sync_sources(sources,activate_top=activate_top,authoritative_prefixes=prefixes),indent=2,sort_keys=True)); return 0
    if args.cmd=="add":
        obj=Objective(id=args.id,title=args.title,next_action=args.next_action,stage=args.stage,value=args.value,readiness=args.readiness,evidence=args.evidence,reversibility=args.reversibility,leverage=args.leverage,cost=args.cost,delay=args.delay,dependency=args.dependency,revenue_potential=args.revenue_potential,deployment_gap=args.deployment_gap); driver.add(obj,activate=args.activate); print(json.dumps(asdict(obj),indent=2,sort_keys=True)); return 0
    if args.cmd=="state":
        obj=driver.set_state(args.id,args.state,blocker=args.blocker,evidence_ref=args.evidence_ref,next_action=args.next_action); print(json.dumps(asdict(obj),indent=2,sort_keys=True)); return 0
    if args.cmd=="list":
        rows=driver.objectives.values()
        if args.state: rows=[o for o in rows if o.state==args.state]
        print(json.dumps([asdict(o) for o in sorted(rows,key=lambda x:x.id)],indent=2,sort_keys=True)); return 0
    return 2

if __name__=="__main__": raise SystemExit(main())
