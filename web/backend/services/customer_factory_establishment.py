"""Customer Factory product-establishment controls.

Tenant-scoped governance, plans, audit, snapshots, stall detection and recovery.
No function in this module grants financial authority.
"""
from __future__ import annotations
import json, shutil, time, uuid
from pathlib import Path
from typing import Any
from orchestrator.sqlite_manager import SQLiteManager
from web.backend.services.tenant_workspaces import customer_workspace_context, read_customer_pipeline_state, write_customer_product

PLAN_LIMITS = {
    "free": {"projects": 3, "personnel": 4, "managers": 1, "active_tasks": 12, "concurrent_missions": 1, "retries_per_hour": 8, "history": 100},
    "maker": {"projects": 20, "personnel": 20, "managers": 4, "active_tasks": 40, "concurrent_missions": 5, "retries_per_hour": 30, "history": 500},
    "studio": {"projects": 100, "personnel": 75, "managers": 15, "active_tasks": 150, "concurrent_missions": 20, "retries_per_hour": 100, "history": 2000},
    "enterprise": {"projects": 1000, "personnel": 500, "managers": 100, "active_tasks": 1000, "concurrent_missions": 200, "retries_per_hour": 1000, "history": 10000},
}

MISSION_TEMPLATES = [
    {"id":"market_validation","label":"Market Validation","prompt":"Validate demand, willingness to pay, competition, AI advantage, feasibility, and launch risks for: "},
    {"id":"competitor_analysis","label":"Competitor Analysis","prompt":"Map the strongest competitors, pricing, positioning, weaknesses, customer complaints, and exploitable gaps for: "},
    {"id":"lead_generation","label":"Lead Generation","prompt":"Design an evidence-backed lead generation system, customer segments, acquisition channels, qualification rules, and launch plan for: "},
    {"id":"product_validation","label":"Product Validation","prompt":"Stress-test the product concept, target user, core workflow, monetization, technical feasibility, and reasons it could fail: "},
    {"id":"funding_research","label":"Funding Research","prompt":"Research realistic non-binding funding opportunities, eligibility, evidence requirements, risks, and owner decision points for: "},
    {"id":"marketing_launch","label":"Marketing Launch","prompt":"Prepare a launch strategy with audience, positioning, channels, offers, proof points, metrics, and primary risks for: "},
    {"id":"operations_review","label":"Operations Review","prompt":"Audit the operating model, bottlenecks, automation opportunities, controls, unit economics, and next operational improvements for: "},
]

def limits_for(plan: str | None) -> dict[str, int]:
    return dict(PLAN_LIMITS.get(str(plan or 'free').lower(), PLAN_LIMITS['free']))

def _root(customer_id: str) -> Path:
    return Path(customer_workspace_context(customer_id)["tenant_root"])

def _audit_path(customer_id: str) -> Path:
    p=_root(customer_id)/"logs"/"factory_audit.jsonl"; p.parent.mkdir(parents=True, exist_ok=True); return p

def emit_audit(customer_id: str, event: str, *, actor: str="owner", product_id: str|None=None, task_id: str|None=None, detail: dict[str,Any]|None=None) -> dict[str,Any]:
    row={"id":f"evt-{uuid.uuid4().hex[:12]}","timestamp":time.time(),"event":event,"actor":actor,"product_id":product_id,"task_id":task_id,"detail":detail or {},"financial_authority":False}
    with _audit_path(customer_id).open('a', encoding='utf-8') as f: f.write(json.dumps(row, separators=(',',':'))+'\n')
    return row

def read_audit(customer_id: str, limit: int=200) -> list[dict[str,Any]]:
    p=_audit_path(customer_id)
    if not p.exists(): return []
    lines=p.read_text(encoding='utf-8', errors='replace').splitlines()[-max(1,min(limit,2000)):]
    out=[]
    for line in lines:
        try: out.append(json.loads(line))
        except Exception: pass
    return out

def usage_summary(customer_id: str, plan: str, workforce: list[dict[str,Any]]|None=None) -> dict[str,Any]:
    state=read_customer_pipeline_state(customer_id); tasks=list(state.get('task_queue') or []); products=list((state.get('products') or {}).values())
    workforce=workforce or []
    status={}
    retries=0
    for t in tasks:
        s=str(t.get('status') or 'pending').lower(); status[s]=status.get(s,0)+1; retries+=int(t.get('retry_count') or 0)
    active=sum(status.get(x,0) for x in ('pending','running','blocked'))
    managers=sum(1 for x in workforce if x.get('role_class')=='manager' and not x.get('disabled'))
    
    economics={}
    try:
        from web.backend.services.product_economics import get_product_llm_costs
        economics=get_product_llm_costs({str(p.get("id")) for p in products if p.get("id")})
    except Exception:
        economics={}
    llm_calls=sum(int(v.get("llm_call_count") or 0) for v in economics.values())
    llm_tokens=sum(int(v.get("llm_total_tokens") or 0) for v in economics.values())
    llm_cost=round(sum(float(v.get("llm_cost_usd") or 0) for v in economics.values()),6)
    return {"plan":plan,"limits":limits_for(plan),"projects":len(products),"personnel":len([x for x in workforce if not x.get('disabled')]),"managers":managers,"tasks_total":len(tasks),"active_tasks":active,"task_status":status,"task_retries":retries,"llm_calls":llm_calls,"llm_tokens":llm_tokens,"llm_estimated_cost_usd":llm_cost}


def enforce_capacity(customer_id: str, plan: str, kind: str, workforce: list[dict[str,Any]]|None=None) -> None:
    u=usage_summary(customer_id,plan,workforce); lim=u['limits']
    mapping={"project":("projects","projects"),"personnel":("personnel","personnel"),"manager":("managers","managers"),"active_task":("active_tasks","active_tasks")}
    if kind not in mapping: return
    used_key,limit_key=mapping[kind]
    if int(u.get(used_key,0)) >= int(lim[limit_key]): raise ValueError(f"{plan.title()} plan {kind.replace('_',' ')} limit reached")



def enforce_mission_capacity(customer_id: str, plan: str) -> None:
    state=read_customer_pipeline_state(customer_id); limits=limits_for(plan)
    products=list((state.get("products") or {}).values()); tasks=list(state.get("task_queue") or [])
    if len(products) >= limits["projects"]:
        raise ValueError(f"{plan.title()} plan project limit reached")
    active_projects=set()
    active_tasks=0
    for t in tasks:
        if str(t.get("status") or "").lower() in {"pending","running","blocked"}:
            active_tasks += 1
            if t.get("product_id"): active_projects.add(str(t.get("product_id")))
    if len(active_projects) >= limits["concurrent_missions"]:
        raise ValueError(f"{plan.title()} plan concurrent mission limit reached")
    if active_tasks + 7 > limits["active_tasks"]:
        raise ValueError(f"{plan.title()} plan active task capacity would be exceeded")

def stall_for(product: dict[str,Any], tasks: list[dict[str,Any]], now: float|None=None, stall_seconds: float=900.0) -> dict[str,Any]:
    now=now or time.time()
    if product.get('archived') or product.get('owner_decision',{}).get('action')=='archive': return {"stalled":False}
    pt=[t for t in tasks if str(t.get('product_id') or '')==str(product.get('id') or '')]
    active=[t for t in pt if str(t.get('status') or '').lower() in {'pending','running','blocked'}]
    if not active: return {"stalled":False}
    stamps=[]
    for t in pt:
        for k in ('completed_at','started_at','created_at'):
            try:
                if t.get(k): stamps.append(float(t[k]))
            except Exception: pass
    try: stamps.append(float(product.get('updated_at') or 0))
    except Exception: pass
    last=max(stamps or [now]); age=max(0.0,now-last)
    blocked=[t for t in active if str(t.get('status') or '').lower()=='blocked']
    stalled=bool(blocked) or age>=stall_seconds
    reason='blocked task waiting for recovery' if blocked else ('no mission progress recently' if stalled else '')
    return {"stalled":stalled,"age_seconds":round(age,1),"reason":reason,"blocked_tasks":len(blocked),"recommendation":"Retry failed/blocked work or ask the manager for a focused follow-up." if stalled else None}

def project_control(customer_id: str, product_id: str, action: str) -> dict[str,Any]:
    ctx=customer_workspace_context(customer_id); sm=SQLiteManager(ctx['pipeline_db'],workspace_id=ctx['workspace_id']); sm.connect(); now=time.time()
    try:
        p=sm.get_product(product_id)
        if not p: raise ValueError('Project not found in this customer Factory')
        if action=='pause':
            with sm.conn: sm.conn.execute("UPDATE tasks SET status='blocked', error=COALESCE(error,'Paused by owner') WHERE workspace_id=? AND product_id=? AND lower(status)='pending'",(ctx['workspace_id'],product_id))
            p['factory_paused']=True; p['updated_at']=now; sm.upsert_product(p)
        elif action=='resume':
            with sm.conn: sm.conn.execute("UPDATE tasks SET status='pending', error=NULL WHERE workspace_id=? AND product_id=? AND lower(status)='blocked' AND error='Paused by owner'",(ctx['workspace_id'],product_id))
            p['factory_paused']=False; p['updated_at']=now; sm.upsert_product(p); Path(ctx['tenant_root'],'state','.wake').touch(exist_ok=True)
        elif action=='archive':
            with sm.conn: sm.conn.execute("UPDATE tasks SET status='blocked', error=COALESCE(error,'Archived by owner') WHERE workspace_id=? AND product_id=? AND lower(status)='pending'",(ctx['workspace_id'],product_id))
            p['archived']=True; p['factory_paused']=True; p['updated_at']=now; sm.upsert_product(p)
        elif action=='restore':
            with sm.conn: sm.conn.execute("UPDATE tasks SET status='pending', error=NULL WHERE workspace_id=? AND product_id=? AND lower(status)='blocked' AND error='Archived by owner'",(ctx['workspace_id'],product_id))
            p['archived']=False; p['factory_paused']=False; p['updated_at']=now; sm.upsert_product(p); Path(ctx['tenant_root'],'state','.wake').touch(exist_ok=True)
        else: raise ValueError('Unsupported project control')
    finally: sm.close()
    emit_audit(customer_id,f"project_{action}",product_id=product_id)
    return {"ok":True,"product_id":product_id,"action":action,"financial_authority":False}

def tenant_snapshot(customer_id: str, retention: int=7) -> dict[str,Any]:
    root=_root(customer_id); backups=root/'backups'; backups.mkdir(parents=True,exist_ok=True); ts=time.strftime('%Y%m%d-%H%M%S',time.gmtime())
    base=backups/f"tenant-{ts}"
    tmp=root/'.snapshot-staging'
    if tmp.exists(): shutil.rmtree(tmp,ignore_errors=True)
    tmp.mkdir(parents=True)
    for name in ('state','config','reports','logs'):
        src=root/name
        if src.exists(): shutil.copytree(src,tmp/name,dirs_exist_ok=True)
    archive=Path(shutil.make_archive(str(base),'zip',root_dir=tmp)); shutil.rmtree(tmp,ignore_errors=True)
    files=sorted(backups.glob('tenant-*.zip'), key=lambda x:x.stat().st_mtime, reverse=True)
    for old in files[max(1,retention):]: old.unlink(missing_ok=True)
    row={"path":str(archive),"filename":archive.name,"size_bytes":archive.stat().st_size,"created_at":time.time()}; emit_audit(customer_id,'tenant_snapshot',detail={"filename":archive.name,"size_bytes":row['size_bytes']}); return row

def snapshot_status(customer_id: str) -> dict[str,Any]:
    files=sorted((_root(customer_id)/'backups').glob('tenant-*.zip'), key=lambda x:x.stat().st_mtime, reverse=True) if (_root(customer_id)/'backups').exists() else []
    return {"count":len(files),"latest":({"filename":files[0].name,"size_bytes":files[0].stat().st_size,"created_at":files[0].stat().st_mtime} if files else None)}

def maybe_daily_snapshot(customer_id: str) -> None:
    st=snapshot_status(customer_id); latest=st.get('latest') or {}
    if time.time()-float(latest.get('created_at') or 0)>86400: tenant_snapshot(customer_id)

def auto_delegate(customer_id: str, product_id: str) -> dict[str, Any]:
    from web.backend.services.customer_workforce import create_customer_personnel, delegate_customer_manager_task, list_customer_personnel
    state=read_customer_pipeline_state(customer_id); product=(state.get('products') or {}).get(product_id)
    if not product: raise ValueError('Project not found in this customer Factory')
    workforce=list_customer_personnel(customer_id)
    managers=[x for x in workforce if x.get('role_class')=='manager' and not x.get('disabled') and 'assign_work' in (x.get('permissions') or [])]
    if not managers:
        manager=create_customer_personnel(customer_id,'Research recovery manager that challenges evidence and delegates follow-up research',role_class='manager',label='Recovery Manager'); managers=[manager]
    manager=managers[0]
    workers=[x for x in workforce if x.get('role_class')=='worker' and not x.get('disabled') and (not x.get('supervisor_id') or x.get('supervisor_id')==manager['id'])]
    if not workers:
        workers=[create_customer_personnel(customer_id,'Analyst that performs focused evidence-backed follow-up research',role_class='worker',label='Recovery Analyst')]
    tasks=list(state.get('task_queue') or []); stall=stall_for(product,tasks)
    directive=(f"Recover this mission. Current issue: {stall.get('reason') or 'owner-requested follow-up'}. "
               "Inspect the weakest assumptions, perform fresh evidence-backed research, and return concise findings for manager and owner review.")
    result=delegate_customer_manager_task(customer_id,manager_id=manager['id'],worker_id=workers[0]['id'],product_id=product_id,directive=directive)
    emit_audit(customer_id,'manager_auto_delegation',actor=manager['id'],product_id=product_id,task_id=result.get('task_id'),detail={"worker_id":workers[0]['id'],"reason":stall.get('reason')})
    return {**result,"automatic":True,"reason":stall.get('reason')}


def onboarding(customer_id: str, goal: str, plan: str) -> dict[str, Any]:
    from web.backend.services.customer_workforce import create_customer_personnel, list_customer_personnel
    from web.backend.services.empire_missions import create_customer_mission
    mission=str(goal or '').strip()
    if len(mission)<8: raise ValueError('Business goal is too short')
    workforce=list_customer_personnel(customer_id)
    created=[]
    if not any(x.get('role_class')=='manager' for x in workforce):
        enforce_capacity(customer_id,plan,'manager',workforce); created.append(create_customer_personnel(customer_id,'Research manager who coordinates market validation and evidence reviews',role_class='manager',label='Launch Manager'))
        workforce=list_customer_personnel(customer_id)
    worker_specs=[('Market Analyst','researches customer need and competitors'),('Economics Analyst','researches pricing revenue and willingness to pay'),('Feasibility Analyst','researches technical feasibility and operational risks')]
    for label,desc in worker_specs:
        if len([x for x in workforce if x.get('role_class')=='worker'])>=3: break
        enforce_capacity(customer_id,plan,'personnel',workforce); created.append(create_customer_personnel(customer_id,desc,role_class='worker',label=label)); workforce=list_customer_personnel(customer_id)
    enforce_mission_capacity(customer_id,plan)
    result=create_customer_mission(customer_id,mission)
    emit_audit(customer_id,'onboarding_completed',product_id=result['product_id'],detail={"created_personnel":[x['id'] for x in created]})
    return {"mission":result,"created_personnel":created,"onboarding_complete":True}


def retry_failed_for_project(customer_id: str, product_id: str, limit: int = 10) -> dict[str, Any]:
    from web.backend.services.customer_task_recovery import retry_customer_task
    state=read_customer_pipeline_state(customer_id)
    if product_id not in (state.get("products") or {}): raise ValueError("Project not found in this customer Factory")
    failed=[t for t in (state.get("task_queue") or []) if str(t.get("product_id") or "")==product_id and str(t.get("status") or "").lower() in {"failed","blocked"}]
    results=[]
    for task in failed[:max(1,min(limit,25))]:
        try: results.append(retry_customer_task(customer_id,str(task.get("id") or "")))
        except ValueError: pass
    emit_audit(customer_id,"retry_failed_batch",product_id=product_id,detail={"requested":len(failed),"queued":len(results)})
    return {"product_id":product_id,"failed_found":len(failed),"recovery_tasks":results,"queued":len(results)}

def audit_provider_transition(customer_id: str, health: dict[str, Any]) -> None:
    current = "online" if health.get("online") else "offline"
    recent = read_audit(customer_id, limit=50)
    previous = next((str((row.get("detail") or {}).get("status")) for row in reversed(recent) if row.get("event") == "provider_status"), None)
    if previous != current:
        emit_audit(customer_id, "provider_status", actor="system", detail={"provider": health.get("provider"), "status": current, "version": health.get("version"), "models": health.get("models") or [], "error": health.get("error")})
