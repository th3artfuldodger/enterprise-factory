'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Activity, AlertTriangle, Bot, Building2, CheckCircle2, ChevronRight, CircleDot, Clock3, Crown, Loader2, LockKeyhole, Network, Orbit, Play, ShieldCheck, Sparkles, WalletCards } from 'lucide-react';
import api, { type CustomerFactoryPayload } from '@/lib/api';
import { GlassCard } from '@/components/ui/GlassCard';

export default function CustomerFactoryPage() {
  const [factory, setFactory] = useState<CustomerFactoryPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [missionBusy, setMissionBusy] = useState(false);
  const [mission, setMission] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [authBusy, setAuthBusy] = useState(false);
  const [unitPrompt, setUnitPrompt] = useState('');
  const [unitRole, setUnitRole] = useState<'worker' | 'manager'>('worker');
  const [unitBusy, setUnitBusy] = useState(false);
  const [managerId, setManagerId] = useState('');
  const [workerId, setWorkerId] = useState('');
  const [delegateProjectId, setDelegateProjectId] = useState('');
  const [directive, setDirective] = useState('');
  const [delegateBusy, setDelegateBusy] = useState(false);
  const [fundingProjectId, setFundingProjectId] = useState('');
  const [fundingAmount, setFundingAmount] = useState('');
  const [fundingPurpose, setFundingPurpose] = useState('');
  const [fundingSource, setFundingSource] = useState('');
  const [fundingBusy, setFundingBusy] = useState(false);
  const [scoutBusy, setScoutBusy] = useState(false);
  const [selectedProjectId, setSelectedProjectId] = useState('');
  const [ownerNote, setOwnerNote] = useState('');
  const [ownerBusy, setOwnerBusy] = useState(false);

  const loadFactory = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setFactory(await api.getCustomerFactory());
    } catch (err: any) {
      setFactory(null);
      const msg = String(err?.message || '');
      if (!/401|not authenticated|customer/i.test(msg)) setError(msg || 'Could not load your Factory.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadFactory(); }, [loadFactory]);
  useEffect(() => {
    if (!factory) return;
    const timer = window.setInterval(() => { void loadFactory(); }, 8000);
    return () => window.clearInterval(timer);
  }, [factory, loadFactory]);

  const submitAuth = async (event: React.FormEvent) => {
    event.preventDefault();
    setAuthBusy(true);
    setError('');
    try {
      if (authMode === 'register') await api.registerCustomer(email, password);
      else await api.loginCustomer(email, password);
      await loadFactory();
    } catch (err: any) {
      setError(err?.message || 'Sign in failed.');
    } finally {
      setAuthBusy(false);
    }
  };

  const launchMission = async () => {
    if (mission.trim().length < 8) return;
    setMissionBusy(true);
    setError('');
    setNotice('');
    try {
      const result = await api.createCustomerFactoryMission(mission.trim());
      setNotice(`Mission accepted. ${result.department_label} mobilized its five research scouts, manager, and Ultron review.`);
      setMission('');
      await loadFactory();
    } catch (err: any) {
      setError(err?.message || 'Could not launch mission.');
    } finally {
      setMissionBusy(false);
    }
  };

  const createUnit = async () => {
    if (unitPrompt.trim().length < 3) return;
    setUnitBusy(true);
    setError('');
    try {
      const unit = await api.createCustomerFactoryPersonnel({ description: unitPrompt.trim(), role_class: unitRole });
      setNotice(`${unit.label || 'AI unit'} created in your Factory.`);
      setUnitPrompt('');
      await loadFactory();
    } catch (err: any) {
      setError(err?.message || 'Could not create AI unit.');
    } finally {
      setUnitBusy(false);
    }
  };

  const delegateTask = async () => {
    if (!managerId || !workerId || !delegateProjectId || !directive.trim()) return;
    setDelegateBusy(true);
    setError('');
    try {
      const result = await api.delegateCustomerFactoryManagerTask(managerId, {
        worker_id: workerId,
        product_id: delegateProjectId,
        directive: directive.trim(),
      });
      setNotice(`Manager added a new task to ${result.worker_label || 'the worker'}.`);
      setDirective('');
      await loadFactory();
    } catch (err: any) {
      setError(err?.message || 'Could not delegate task.');
    } finally {
      setDelegateBusy(false);
    }
  };

  const requestFunding = async () => {
    const project = (factory?.projects || []).find((item) => item.product_id === fundingProjectId);
    const amount = Number(fundingAmount);
    if (!project || !Number.isFinite(amount) || amount <= 0 || fundingPurpose.trim().length < 3) return;
    setFundingBusy(true);
    setError('');
    try {
      const result = await api.requestCustomerFactoryFunding({
        product_id: project.product_id,
        department: project.department || 'general',
        amount_usd: amount,
        purpose: fundingPurpose.trim(),
        source_preference: fundingSource || undefined,
      });
      setNotice(`Funding request ${result.request?.id || ''} sent to the separate Funding Utility. Your Factory cannot authorize it.`);
      setFundingAmount('');
      setFundingPurpose('');
      await loadFactory();
    } catch (err: any) {
      setError(err?.message || 'Could not submit funding request.');
    } finally {
      setFundingBusy(false);
    }
  };

  const scoutFunding = async () => {
    if (!fundingProjectId) return;
    setScoutBusy(true);
    setError('');
    try {
      const result = await api.scoutCustomerFactoryFunding(fundingProjectId);
      setNotice(`Funding scouts found ${result.opportunities_found || 0} public opportunities and added them to the Funding Utility.`);
      await loadFactory();
    } catch (err: any) {
      setError(err?.message || 'Funding scouts could not complete the search.');
    } finally {
      setScoutBusy(false);
    }
  };

  const recordOwnerDecision = async (action: 'accept_package' | 'request_revision' | 'archive') => {
    if (!selectedProject) return;
    setOwnerBusy(true);
    setError('');
    try {
      await api.recordCustomerFactoryOwnerDecision(selectedProject.product_id, { action, note: ownerNote.trim() || undefined });
      setNotice(action === 'accept_package' ? 'Owner decision recorded: package accepted for the next non-financial stage.' : action === 'request_revision' ? 'Owner requested revision. Select a manager below to issue the follow-up order.' : 'Mission archived.');
      if (action === 'request_revision') {
        setDelegateProjectId(selectedProject.product_id);
        setDirective(ownerNote.trim() || 'Review this mission package, challenge the weakest assumptions, and assign evidence-backed follow-up work.');
      }
      setOwnerNote('');
      await loadFactory();
    } catch (err: any) {
      setError(err?.message || 'Could not record owner decision.');
    } finally {
      setOwnerBusy(false);
    }
  };

  const projects = factory?.projects || [];
  const managers = (factory?.workforce || []).filter((unit) => unit.role_class === 'manager');
  const workers = (factory?.workforce || []).filter((unit) => unit.role_class === 'worker');
  const selectedProject = projects.find((project) => project.product_id === selectedProjectId) || projects[0];
  const selectedManager = managers.find((unit) => unit.id === managerId) || managers[0];
  const eligibleWorkers = useMemo(
    () => workers.filter((unit) => !unit.supervisor_id || unit.supervisor_id === selectedManager?.id),
    [workers, selectedManager?.id],
  );

  useEffect(() => {
    if (!selectedProjectId && projects[0]?.product_id) setSelectedProjectId(projects[0].product_id);
  }, [projects, selectedProjectId]);

  useEffect(() => {
    if (!managerId && managers[0]?.id) setManagerId(managers[0].id);
  }, [managerId, managers]);

  useEffect(() => {
    if (!eligibleWorkers.some((unit) => unit.id === workerId)) setWorkerId(eligibleWorkers[0]?.id || '');
  }, [managerId, workerId, workers, eligibleWorkers]);
  const activeTasks = useMemo(
    () => projects.reduce((sum, p) => sum + Number(p.active_task_count || 0), 0),
    [projects],
  );

  if (loading && !factory) {
    return <main className="grid min-h-screen place-items-center bg-[#02060b] text-cyan-200"><div className="flex items-center gap-2"><Loader2 className="h-5 w-5 animate-spin" />Initializing Factory…</div></main>;
  }

  if (!factory) {
    return (
      <main className="min-h-screen bg-[radial-gradient(circle_at_top,#102337_0,#030810_42%,#010409_100%)] px-4 py-12 text-white">
        <div className="mx-auto max-w-md">
          <div className="mb-8 text-center">
            <div className="mx-auto grid h-16 w-16 place-items-center rounded-2xl border border-cyan-300/25 bg-cyan-400/10"><Orbit className="h-8 w-8 text-cyan-200" /></div>
            <h1 className="mt-5 text-3xl font-black">ENTER YOUR FACTORY</h1>
            <p className="mt-2 text-sm text-slate-400">Your AI workforce, missions and project data stay isolated to your account.</p>
          </div>
          <GlassCard className="p-5">
            <div className="mb-4 flex rounded-lg border border-white/10 bg-black/30 p-1">
              {(['login', 'register'] as const).map((mode) => <button key={mode} type="button" onClick={() => setAuthMode(mode)} className={`flex-1 rounded-md px-3 py-2 text-xs font-black uppercase ${authMode === mode ? 'bg-cyan-400/15 text-cyan-100' : 'text-slate-500'}`}>{mode === 'login' ? 'Sign in' : 'Create account'}</button>)}
            </div>
            <form onSubmit={submitAuth} className="space-y-3">
              <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" className="w-full rounded-lg border border-white/10 bg-black/45 px-3 py-3 text-sm outline-none focus:border-cyan-400/50" />
              <input type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password" className="w-full rounded-lg border border-white/10 bg-black/45 px-3 py-3 text-sm outline-none focus:border-cyan-400/50" />
              <button disabled={authBusy} className="flex w-full items-center justify-center gap-2 rounded-lg border border-cyan-300/30 bg-cyan-400/15 px-3 py-3 text-xs font-black uppercase text-cyan-100 disabled:opacity-50">{authBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <LockKeyhole className="h-4 w-4" />}{authMode === 'login' ? 'Enter Factory' : 'Create My Factory'}</button>
            </form>
            {error ? <p className="mt-3 text-sm text-red-300">{error}</p> : null}
          </GlassCard>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,#0b1c2c_0,#02070d_48%,#010409_100%)] px-3 py-5 text-white md:px-6">
      <div className="mx-auto max-w-7xl">
        <header className="mb-4 flex items-center gap-3 rounded-xl border border-cyan-300/15 bg-black/25 px-4 py-3">
          <div className="grid h-10 w-10 place-items-center rounded-lg border border-cyan-300/20 bg-cyan-400/10"><Orbit className="h-5 w-5 text-cyan-200" /></div>
          <div><p className="text-[9px] font-black uppercase tracking-[.24em] text-cyan-300/70">Personal AI Operations World</p><h1 className="text-lg font-black">MY FACTORY</h1></div>
          <div className="ml-auto flex items-center gap-2 text-[8px] font-bold uppercase text-slate-500"><ShieldCheck className="h-4 w-4 text-emerald-300" />Tenant isolated</div>
        </header>

        <div className="mb-4 grid gap-2 sm:grid-cols-4">
          <GlassCard className="p-3"><p className="text-[7px] uppercase text-slate-600">Departments</p><p className="mt-1 text-xl font-black text-cyan-100">{factory.organization.department_count}</p></GlassCard>
          <GlassCard className="p-3"><p className="text-[7px] uppercase text-slate-600">Research workforce</p><p className="mt-1 text-xl font-black text-violet-100">{factory.organization.research_agent_count}</p></GlassCard>
          <GlassCard className="p-3"><p className="text-[7px] uppercase text-slate-600">Projects</p><p className="mt-1 text-xl font-black text-amber-100">{projects.length}</p></GlassCard>
          <GlassCard className="p-3"><p className="text-[7px] uppercase text-slate-600">Active tasks</p><p className="mt-1 text-xl font-black text-emerald-100">{activeTasks}</p></GlassCard>
        </div>

        {selectedProject ? <GlassCard className="mb-4 overflow-hidden border-cyan-300/20 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <Activity className="h-4 w-4 text-emerald-300" />
            <p className="text-xs font-black uppercase tracking-[.18em] text-cyan-100">Factory Floor Live</p>
            <span className="rounded border border-emerald-400/20 bg-emerald-400/8 px-2 py-1 text-[7px] font-black uppercase text-emerald-200">Auto-refresh 8s</span>
            <select value={selectedProject.product_id} onChange={(e) => setSelectedProjectId(e.target.value)} className="ml-auto max-w-sm rounded border border-white/10 bg-black/45 px-2 py-1.5 text-[8px]">{projects.map((project) => <option key={project.product_id} value={project.product_id}>{project.label.slice(0, 65)}</option>)}</select>
          </div>
          <p className="mt-2 line-clamp-2 text-[11px] text-slate-300">{selectedProject.label}</p>
          <div className="mt-4 grid grid-cols-5 gap-2">
            {[
              { label: 'Research', done: Boolean(selectedProject.manager_review), active: (selectedProject.active_task_count || 0) > 0 && !selectedProject.manager_review },
              { label: 'Manager', done: Boolean(selectedProject.manager_review), active: Boolean(selectedProject.manager_review) && !selectedProject.ultron_audit },
              { label: 'Ultron', done: Boolean(selectedProject.ultron_audit), active: Boolean(selectedProject.manager_review) && !selectedProject.ultron_audit },
              { label: 'Decision', done: Boolean(selectedProject.decision_ready), active: Boolean(selectedProject.ultron_audit) && !selectedProject.owner_decision },
              { label: 'Owner', done: Boolean(selectedProject.owner_decision), active: Boolean(selectedProject.decision_ready) && !selectedProject.owner_decision },
            ].map((stage, index) => <div key={stage.label} className={`relative rounded-lg border p-2 text-center ${stage.done ? 'border-emerald-400/25 bg-emerald-400/8' : stage.active ? 'border-cyan-300/30 bg-cyan-400/10' : 'border-white/8 bg-black/20'}`}>
              {stage.active ? <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 animate-pulse rounded-full bg-cyan-300" /> : null}
              <div className="mx-auto grid h-7 w-7 place-items-center rounded-full border border-white/10 bg-black/30">{stage.done ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-300" /> : stage.active ? <Loader2 className="h-3.5 w-3.5 animate-spin text-cyan-300" /> : <CircleDot className="h-3.5 w-3.5 text-slate-600" />}</div>
              <p className="mt-1 text-[7px] font-black uppercase text-slate-300">{index + 1}. {stage.label}</p>
            </div>)}
          </div>
          <div className="mt-3 flex flex-wrap gap-2 text-[8px] text-slate-500">
            <span>{selectedProject.task_summary?.completed || 0} completed</span><span>•</span><span>{selectedProject.task_summary?.running || 0} running</span><span>•</span><span>{selectedProject.task_summary?.pending || 0} queued</span>
          </div>
        </GlassCard> : null}

        {selectedProject?.decision_ready ? <div className="mb-4 grid gap-4 xl:grid-cols-[1.05fr_.95fr]">
          <GlassCard className="border-amber-300/20 p-4">
            <div className="flex items-center gap-2"><Crown className="h-4 w-4 text-amber-300" /><p className="text-xs font-black uppercase tracking-[.16em] text-amber-100">Owner Decision Workspace</p><span className="ml-auto rounded border border-emerald-400/20 bg-emerald-400/8 px-2 py-1 text-[7px] font-black uppercase text-emerald-200">Package ready</span></div>
            <p className="mt-2 text-[10px] text-slate-400">Review the manager and Ultron package, record your decision, or route the mission back to a manager for more evidence. These actions do not authorize or move money.</p>
            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
              <div className="rounded-lg border border-white/8 bg-black/25 p-2"><p className="text-[6px] uppercase text-slate-600">Manager confidence</p><p className="mt-1 text-lg font-black text-cyan-100">{Math.round(selectedProject.manager_review?.confidence || 0)}%</p></div>
              <div className="rounded-lg border border-white/8 bg-black/25 p-2"><p className="text-[6px] uppercase text-slate-600">Primary risk</p><p className="mt-1 text-lg font-black text-rose-100">{Math.round(selectedProject.primary_risk?.risk_score_0_100 || 0)}</p></div>
              <div className="rounded-lg border border-white/8 bg-black/25 p-2"><p className="text-[6px] uppercase text-slate-600">Ultron risk</p><p className="mt-1 text-lg font-black text-violet-100">{Math.round(selectedProject.ultron_audit?.secondary_risk?.secondary_risk_score_0_100 || 0)}</p></div>
              <div className="rounded-lg border border-white/8 bg-black/25 p-2"><p className="text-[6px] uppercase text-slate-600">Evidence</p><p className="mt-1 text-lg font-black text-emerald-100">{selectedProject.ultron_audit?.secondary_risk?.evidence_items || 0}</p></div>
            </div>
            <div className="mt-3 rounded-lg border border-violet-400/15 bg-violet-400/6 p-3"><p className="text-[7px] font-black uppercase text-violet-200">Ultron recommendation</p><p className="mt-1 text-sm font-black uppercase tracking-wide text-violet-50">{String(selectedProject.ultron_audit?.recommendation || 'review').replace(/_/g, ' ')}</p>{(selectedProject.ultron_audit?.challenges || []).map((challenge) => <p key={challenge} className="mt-1 text-[8px] text-slate-400">• {challenge}</p>)}</div>
            <div className="mt-3 rounded-lg border border-green-400/15 bg-green-400/5 p-3"><div className="flex items-center gap-2"><WalletCards className="h-3.5 w-3.5 text-green-300" /><p className="text-[7px] font-black uppercase text-green-200">Funding status</p><span className="ml-auto text-[7px] text-slate-500">AI authority: request only</span></div>{(selectedProject.funding_requests || []).length ? (selectedProject.funding_requests || []).slice(0, 3).map((request) => <div key={request.id} className="mt-2 flex items-center gap-2 text-[8px]"><span className="rounded border border-white/10 bg-black/30 px-2 py-1 font-bold text-green-100">${Number(request.amount_usd || 0).toLocaleString()}</span><span className="truncate text-slate-400">{request.purpose || 'Funding request'}</span><span className="ml-auto shrink-0 uppercase text-slate-500">{String(request.status || 'requested').replace(/_/g, ' ')}</span></div>) : <p className="mt-2 text-[8px] text-slate-600">No capital request attached to this mission.</p>}</div>
            <textarea value={ownerNote} onChange={(e) => setOwnerNote(e.target.value)} rows={2} placeholder="Owner note or revision instruction…" className="mt-3 w-full resize-none rounded-lg border border-white/10 bg-black/45 px-3 py-2 text-[10px] outline-none placeholder:text-slate-700 focus:border-amber-300/40" />
            <div className="mt-2 flex flex-wrap gap-2">
              <button type="button" disabled={ownerBusy} onClick={() => void recordOwnerDecision('accept_package')} className="rounded border border-emerald-400/25 bg-emerald-400/10 px-3 py-2 text-[8px] font-black uppercase text-emerald-100 disabled:opacity-40">Accept package</button>
              <button type="button" disabled={ownerBusy} onClick={() => void recordOwnerDecision('request_revision')} className="rounded border border-amber-400/25 bg-amber-400/10 px-3 py-2 text-[8px] font-black uppercase text-amber-100 disabled:opacity-40">Request revision</button>
              <button type="button" disabled={ownerBusy} onClick={() => void recordOwnerDecision('archive')} className="rounded border border-white/10 bg-white/5 px-3 py-2 text-[8px] font-black uppercase text-slate-400 disabled:opacity-40">Archive</button>
              <a href={`/api/customer/factory/reports/${encodeURIComponent(selectedProject.product_id)}.pdf`} className="ml-auto rounded border border-sky-400/20 bg-sky-400/8 px-3 py-2 text-[8px] font-black uppercase text-sky-200">Open decision PDF</a>
            </div>
            {selectedProject.owner_decision ? <p className="mt-2 text-[8px] text-emerald-300">Latest owner action: {String(selectedProject.owner_decision.action || '').replace(/_/g, ' ')}{selectedProject.owner_decision.note ? ` — ${selectedProject.owner_decision.note}` : ''}</p> : null}
          </GlassCard>

          <GlassCard className="border-sky-300/15 p-4">
            <div className="flex items-center gap-2"><Clock3 className="h-4 w-4 text-sky-300" /><p className="text-xs font-black uppercase tracking-[.16em] text-sky-100">Mission History · Audit Replay</p></div>
            <p className="mt-1 text-[9px] text-slate-500">Persistent task, manager, Ultron and owner events for this mission.</p>
            <div className="mt-3 max-h-72 space-y-2 overflow-y-auto pr-1">
              {(selectedProject.timeline || []).length ? [...(selectedProject.timeline || [])].reverse().map((event) => <div key={event.id} className="flex gap-2 rounded-lg border border-white/8 bg-black/20 p-2">
                <div className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full border border-sky-400/15 bg-sky-400/5">{event.kind === 'owner_decision' ? <Crown className="h-3 w-3 text-amber-300" /> : event.kind === 'ultron_review' ? <Orbit className="h-3 w-3 text-violet-300" /> : event.status === 'completed' ? <CheckCircle2 className="h-3 w-3 text-emerald-300" /> : event.status === 'running' ? <Loader2 className="h-3 w-3 animate-spin text-cyan-300" /> : <Clock3 className="h-3 w-3 text-slate-500" />}</div>
                <div className="min-w-0 flex-1"><div className="flex items-center gap-2"><p className="truncate text-[8px] font-bold text-slate-200">{event.actor || 'Factory AI'}</p><span className="ml-auto text-[6px] uppercase text-slate-600">{event.timestamp ? new Date(event.timestamp * 1000).toLocaleString() : ''}</span></div><p className="mt-0.5 text-[8px] text-slate-400">{event.label || event.kind}</p>{event.evidence_count ? <p className="mt-0.5 text-[7px] text-emerald-300">{event.evidence_count} evidence items</p> : null}</div>
              </div>) : <p className="text-[9px] text-slate-600">No persisted mission events yet.</p>}
            </div>
          </GlassCard>
        </div> : null}

        <GlassCard className="mb-4 border-cyan-400/20 p-4">
          <div className="flex items-start gap-3">
            <Sparkles className="mt-1 h-5 w-5 shrink-0 text-cyan-300" />
            <div className="flex-1">
              <p className="text-xs font-black uppercase tracking-[.18em] text-cyan-100">Give the Factory a mission</p>
              <p className="mt-1 text-[10px] text-slate-400">Describe the outcome. The system chooses a department, deploys Need, Money, Competition, AI Advantage and Feasibility scouts, then routes the evidence through its manager and Ultron before production.</p>
              <textarea value={mission} onChange={(e) => setMission(e.target.value)} rows={3} placeholder="Example: Build a system that helps independent roofers find high-value leads and prepare a marketing campaign…" className="mt-3 w-full resize-none rounded-lg border border-white/10 bg-black/45 px-3 py-3 text-sm outline-none placeholder:text-slate-700 focus:border-cyan-400/45" />
              <button type="button" disabled={missionBusy || mission.trim().length < 8} onClick={() => void launchMission()} className="mt-2 flex items-center gap-2 rounded-lg border border-cyan-300/30 bg-cyan-400/15 px-4 py-2.5 text-[9px] font-black uppercase text-cyan-100 disabled:opacity-40">{missionBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}Launch Mission</button>
              {notice ? <p className="mt-2 text-sm text-emerald-300">{notice}</p> : null}
              {error ? <p className="mt-2 text-sm text-red-300">{error}</p> : null}
            </div>
          </div>
        </GlassCard>

        <div className="mb-4 grid gap-4 lg:grid-cols-2">
          <GlassCard className="border-violet-400/20 p-4">
            <div className="flex items-center gap-2"><Bot className="h-4 w-4 text-violet-300" /><p className="text-xs font-black uppercase text-violet-100">Create an AI unit</p><span className="ml-auto text-[8px] text-slate-600">{(factory.workforce || []).length} custom</span></div>
            <div className="mt-3 flex gap-2">
              {(['worker', 'manager'] as const).map((role) => <button key={role} type="button" onClick={() => setUnitRole(role)} className={`rounded border px-2 py-1 text-[8px] font-black uppercase ${unitRole === role ? 'border-violet-300/35 bg-violet-400/15 text-violet-100' : 'border-white/10 bg-white/5 text-slate-500'}`}>{role}</button>)}
            </div>
            <textarea value={unitPrompt} onChange={(e) => setUnitPrompt(e.target.value)} rows={2} placeholder={unitRole === 'manager' ? 'Example: A manager that oversees my competitor research workers…' : 'Example: An AI that researches competitor pricing and positioning…'} className="mt-2 w-full resize-none rounded-lg border border-white/10 bg-black/45 px-3 py-2 text-[10px] outline-none placeholder:text-slate-700 focus:border-violet-400/40" />
            <button type="button" disabled={unitBusy || unitPrompt.trim().length < 3} onClick={() => void createUnit()} className="mt-2 flex items-center gap-2 rounded border border-violet-400/25 bg-violet-400/10 px-3 py-2 text-[8px] font-black uppercase text-violet-100 disabled:opacity-40">{unitBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Bot className="h-3.5 w-3.5" />}Create {unitRole}</button>
            {(factory.workforce || []).length ? <div className="mt-3 grid gap-1.5 sm:grid-cols-2">{(factory.workforce || []).map((unit) => <button key={unit.id} type="button" onClick={() => { if (unit.role_class === 'manager') setManagerId(unit.id); else if (unit.supervisor_id) { setManagerId(unit.supervisor_id); setWorkerId(unit.id); } }} className={`rounded border px-2 py-2 text-left transition ${unit.role_class === 'manager' && managerId === unit.id ? 'border-emerald-300/35 bg-emerald-400/10' : workerId === unit.id ? 'border-cyan-300/30 bg-cyan-400/8' : 'border-white/10 bg-black/25 hover:border-white/20'}`}><span className="flex items-center gap-1.5 text-[8px] font-black text-slate-200">{unit.role_class === 'manager' ? <Crown className="h-3 w-3 text-amber-300" /> : <Bot className="h-3 w-3 text-violet-300" />}{unit.label}</span><span className="mt-1 block text-[6px] uppercase text-slate-600">{unit.role_class}{unit.supervisor_label ? ` · reports to ${unit.supervisor_label}` : ''}</span></button>)}</div> : null}
          </GlassCard>

          <GlassCard className="border-emerald-400/20 p-4">
            <div className="flex items-center gap-2"><Network className="h-4 w-4 text-emerald-300" /><p className="text-xs font-black uppercase text-emerald-100">Manager Command Console</p></div>
            <p className="mt-1 text-[9px] text-slate-500">Click a manager, choose a mission and subordinate, then issue a new order. The task enters the subordinate’s real queue and appears in mission replay.</p>
            {managers.length ? <div className="mt-3 grid gap-2 sm:grid-cols-2">{managers.map((unit) => <button key={unit.id} type="button" onClick={() => setManagerId(unit.id)} className={`group rounded-lg border p-2.5 text-left transition ${managerId === unit.id ? 'border-emerald-300/40 bg-emerald-400/12' : 'border-white/8 bg-black/25 hover:border-emerald-400/20'}`}>
              <div className="flex items-center gap-2"><Crown className={`h-3.5 w-3.5 ${managerId === unit.id ? 'text-emerald-300' : 'text-slate-600'}`} /><p className="truncate text-[9px] font-black text-slate-200">{unit.label}</p><ChevronRight className="ml-auto h-3 w-3 text-slate-700 group-hover:text-emerald-300" /></div>
              <p className="mt-1 line-clamp-2 text-[7px] text-slate-600">{unit.description || 'AI manager'}</p>
            </button>)}</div> : <p className="mt-3 text-[9px] text-slate-600">Create a manager first, then click it here to issue commands.</p>}
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <select value={workerId} onChange={(e) => setWorkerId(e.target.value)} className="rounded border border-white/10 bg-black/45 px-2 py-2 text-[9px]"><option value="">Subordinate…</option>{eligibleWorkers.map((unit) => <option key={unit.id} value={unit.id}>{unit.label}</option>)}</select>
              <select value={delegateProjectId} onChange={(e) => setDelegateProjectId(e.target.value)} className="rounded border border-white/10 bg-black/45 px-2 py-2 text-[9px]"><option value="">Mission…</option>{projects.map((project) => <option key={project.product_id} value={project.product_id}>{project.label.slice(0, 45)}</option>)}</select>
            </div>
            <textarea value={directive} onChange={(e) => setDirective(e.target.value)} rows={3} placeholder="Tell this manager what new work its subordinate should perform…" className="mt-2 w-full resize-none rounded-lg border border-white/10 bg-black/45 px-3 py-2 text-[10px] outline-none placeholder:text-slate-700 focus:border-emerald-400/40" />
            <button type="button" disabled={delegateBusy || !managerId || !workerId || !delegateProjectId || !directive.trim()} onClick={() => void delegateTask()} className="mt-2 flex items-center gap-2 rounded border border-emerald-400/25 bg-emerald-400/10 px-3 py-2 text-[8px] font-black uppercase text-emerald-100 disabled:opacity-40">{delegateBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}Issue manager order</button>
          </GlassCard>
        </div>

        <div className="grid gap-4 xl:grid-cols-[1.25fr_.75fr]">
          <GlassCard className="p-4">
            <div className="mb-3 flex items-center gap-2"><Building2 className="h-4 w-4 text-cyan-300" /><p className="text-xs font-black uppercase text-cyan-100">15 Department Network</p></div>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {factory.organization.departments.map((department) => (
                <div key={department.slug} className="rounded-lg border border-white/8 bg-black/25 p-2.5">
                  <div className="flex items-center gap-2"><Network className="h-3.5 w-3.5 text-violet-300" /><p className="truncate text-[10px] font-bold">{department.label}</p></div>
                  <div className="mt-2 flex flex-wrap gap-1">{factory.organization.research_lenses.map((lens) => <span key={lens.slug} className="rounded border border-cyan-400/12 bg-cyan-400/5 px-1.5 py-0.5 text-[6px] uppercase text-cyan-200/75">{lens.label}</span>)}</div>
                </div>
              ))}
            </div>
          </GlassCard>

          <div className="space-y-4">
            <GlassCard className="border-violet-400/20 p-4">
              <div className="flex items-center gap-2"><Bot className="h-4 w-4 text-violet-300" /><p className="text-xs font-black uppercase text-violet-100">Command Chain</p></div>
              {['You · Factory owner', 'Ultron · Independent review', 'Factory Manager · Coordination', 'Department Manager · Evidence challenge', '5 Research Scouts · Mission work'].map((label, i) => <div key={label} className="mt-2 flex items-center gap-2"><div className="grid h-7 w-7 place-items-center rounded-full border border-violet-400/20 bg-violet-400/8 text-[8px] font-black text-violet-200">{i + 1}</div><p className="text-[9px] text-slate-300">{label}</p></div>)}
            </GlassCard>
            <GlassCard className="border-green-400/20 p-4">
              <div className="flex items-center gap-2"><WalletCards className="h-4 w-4 text-green-300" /><p className="text-xs font-black uppercase text-green-100">Funding Utility</p></div>
              <p className="mt-2 text-[9px] text-slate-400">Separate from your Factory. AI can request funding; it cannot authorize or move money.</p>
              <div className="mt-3 grid grid-cols-2 gap-2"><div className="rounded border border-white/8 bg-black/25 p-2"><p className="text-[6px] uppercase text-slate-600">Requests</p><p className="text-base font-black">{factory.funding?.request_count || 0}</p></div><div className="rounded border border-white/8 bg-black/25 p-2"><p className="text-[6px] uppercase text-slate-600">Funding leads</p><p className="text-base font-black text-green-200">{factory.funding?.funding_opportunities?.length || 0}</p></div></div>
              <select value={fundingProjectId} onChange={(e) => setFundingProjectId(e.target.value)} className="mt-3 w-full rounded border border-white/10 bg-black/45 px-2 py-2 text-[9px]"><option value="">Choose project for request…</option>{projects.map((project) => <option key={project.product_id} value={project.product_id}>{project.label.slice(0, 48)}</option>)}</select>
              <button type="button" disabled={scoutBusy || !fundingProjectId} onClick={() => void scoutFunding()} className="mt-2 w-full rounded border border-violet-400/20 bg-violet-400/8 px-2 py-1.5 text-[7px] font-black uppercase text-violet-100 disabled:opacity-40">{scoutBusy ? 'Scouts searching…' : 'Run funding scouts'}</button>
              <select value={fundingSource} onChange={(e) => setFundingSource(e.target.value)} className="mt-2 w-full rounded border border-white/10 bg-black/45 px-2 py-2 text-[9px]"><option value="">Funding source not yet selected…</option>{(factory.funding?.funding_opportunities || []).filter((opportunity) => opportunity.status === 'received').map((opportunity) => <option key={opportunity.id} value={opportunity.id}>{opportunity.title || opportunity.id}</option>)}</select>
              <div className="mt-2 grid grid-cols-[100px_1fr] gap-2"><input value={fundingAmount} onChange={(e) => setFundingAmount(e.target.value)} inputMode="decimal" placeholder="USD amount" className="rounded border border-white/10 bg-black/45 px-2 py-2 text-[9px]" /><input value={fundingPurpose} onChange={(e) => setFundingPurpose(e.target.value)} placeholder="Purpose for capital…" className="rounded border border-white/10 bg-black/45 px-2 py-2 text-[9px]" /></div>
              <button type="button" disabled={fundingBusy || !fundingProjectId || Number(fundingAmount) <= 0 || fundingPurpose.trim().length < 3} onClick={() => void requestFunding()} className="mt-2 w-full rounded border border-green-400/25 bg-green-400/10 px-2 py-2 text-[8px] font-black uppercase text-green-100 disabled:opacity-40">{fundingBusy ? 'Sending…' : 'Request funding'}</button>
            </GlassCard>
          </div>
        </div>

        <GlassCard className="mt-4 p-4">
          <div className="mb-3 flex items-center gap-2"><Crown className="h-4 w-4 text-amber-300" /><p className="text-xs font-black uppercase text-amber-100">Mission Board</p><span className="ml-auto text-[7px] uppercase text-slate-600">Select a mission for command view</span></div>
          {projects.length ? <div className="grid gap-2 md:grid-cols-2">{projects.map((project) => <button type="button" onClick={() => setSelectedProjectId(project.product_id)} key={project.product_id} className={`rounded-lg border p-3 text-left transition ${selectedProject?.product_id === project.product_id ? 'border-amber-300/30 bg-amber-300/7' : 'border-white/8 bg-black/25 hover:border-white/15'}`}>
            <div className="flex items-start gap-2"><p className="line-clamp-2 flex-1 text-[11px] font-semibold">{project.label}</p><ChevronRight className="h-3.5 w-3.5 text-slate-600" /></div>
            <div className="mt-2 flex flex-wrap gap-1"><span className="rounded border border-cyan-400/15 bg-cyan-400/5 px-1.5 py-0.5 text-[7px] uppercase text-cyan-200">{String(project.state || 'queued').replace(/_/g, ' ')}</span><span className="rounded border border-violet-400/15 bg-violet-400/5 px-1.5 py-0.5 text-[7px] uppercase text-violet-200">{project.active_task_count || 0} active</span>{project.decision_ready ? <span className="rounded border border-amber-300/20 bg-amber-300/8 px-1.5 py-0.5 text-[7px] uppercase text-amber-100">Decision ready</span> : null}</div>
            {project.owner_decision ? <p className="mt-2 text-[7px] font-black uppercase text-emerald-300">Owner: {String(project.owner_decision.action || '').replace(/_/g, ' ')}</p> : null}
          </button>)}</div> : <p className="text-sm text-slate-500">No missions yet. Give the Factory its first mission above.</p>}
        </GlassCard>

      </div>
    </main>
  );
}
