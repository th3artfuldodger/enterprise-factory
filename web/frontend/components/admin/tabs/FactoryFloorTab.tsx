'use client';

import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Panel,
  Handle,
  Position,
  MarkerType,
  BaseEdge,
  getBezierPath,
  type Edge,
  type EdgeProps,
  type Node,
  useEdgesState,
  useNodesState,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { motion } from 'framer-motion';
import { AlertTriangle, ArrowLeftCircle, GitBranch, History, Loader2, Package, Pause, Play, Plus, Radio, Send, ShieldAlert, ShieldCheck, Skull, Sparkles, UserCog, UserPlus, Zap, X } from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import api from '@/lib/api';
import toast from 'react-hot-toast';
import {
  readFactoryFloorCache,
  writeFactoryFloorCache,
  type FactoryFloorNode,
  type FactoryFloorPayload,
} from '@/lib/factoryFloorCache';
import { connectAdminMetricsStream } from '@/lib/connectAdminMetricsStream';
import { loadAdminDashboardFull } from '@/lib/loadAdminDashboardLayers';
import { type AdminLocale, t } from '@/lib/adminI18n';

const STATUS_COLOR: Record<string, string> = {
  running: '#22d3ee',
  thinking: '#a78bfa',
  idle: '#475569',
};

function ZoneNode({
  data,
}: {
  data: { label: string; subtitle?: string; accent: string };
}) {
  const isCommand = data.label === 'COMMAND CORE';
  const isConveyor = data.label === 'PROJECT CONVEYOR';
  return (
    <div className="pointer-events-none relative h-full w-full [perspective:900px]">
      <div
        className="absolute inset-x-2 bottom-2 top-8 overflow-hidden border"
        style={{
          borderColor: `${data.accent}66`,
          background: `linear-gradient(145deg, ${data.accent}16, rgba(2,6,12,.95) 58%)`,
          clipPath: 'polygon(7% 0,100% 0,93% 100%,0 100%)',
          boxShadow: `inset 0 0 75px ${data.accent}18, 0 22px 40px rgba(0,0,0,.45)`,
        }}
      >
        <div className="absolute inset-0 opacity-40" style={{ backgroundImage: `linear-gradient(${data.accent}18 1px, transparent 1px), linear-gradient(90deg, ${data.accent}18 1px, transparent 1px)`, backgroundSize: '28px 28px' }} />
        <div className="absolute left-4 right-4 top-4 h-px" style={{ background: `linear-gradient(90deg, transparent, ${data.accent}, transparent)` }} />
        <div className="absolute bottom-3 left-5 right-5 flex gap-2 opacity-60">
          {Array.from({ length: 7 }).map((_, i) => <span key={i} className="h-1 flex-1 bg-black/70" style={{ borderTop: `1px solid ${data.accent}55` }} />)}
        </div>
        {isConveyor ? (
          <div className="absolute bottom-10 left-8 right-8 h-14 overflow-hidden border border-amber-400/25 bg-black/45">
            <motion.div className="absolute inset-y-0 -left-24 w-[140%] opacity-65" style={{ backgroundImage: 'repeating-linear-gradient(115deg, rgba(251,191,36,.06) 0 18px, rgba(251,191,36,.35) 18px 28px, rgba(2,6,12,.85) 28px 48px)' }} animate={{ x: [0, 48] }} transition={{ duration: 1.8, repeat: Infinity, ease: 'linear' }} />
            <div className="absolute inset-x-0 top-1/2 h-px bg-amber-300/35 shadow-[0_0_8px_rgba(251,191,36,.35)]" />
            {Array.from({ length: 8 }).map((_, i) => (
              <motion.span key={i} className="absolute top-2 h-2 w-2 rounded-sm bg-amber-300/70 shadow-[0_0_8px_rgba(251,191,36,.6)]" style={{ left: `${8 + i * 12}%` }} animate={{ x: [0, 46, 0], opacity: [.35, 1, .35] }} transition={{ duration: 2.6 + (i % 3) * .35, repeat: Infinity, ease: 'easeInOut', delay: i * .12 }} />
            ))}
          </div>
        ) : null}
      </div>

      {isCommand ? (
        <motion.div animate={{ y: [0, -4, 0], scale: [1, 1.018, 1] }} transition={{ duration: 3.2, repeat: Infinity, ease: 'easeInOut' }} className="absolute bottom-5 right-6 top-2 w-[132px] overflow-hidden border border-cyan-300/45 bg-[#02070c]/90 shadow-[0_0_40px_rgba(34,211,238,.24)]" style={{ clipPath: 'polygon(12% 0,100% 0,100% 88%,88% 100%,0 100%,0 12%)' }}>
          <motion.img src="/ultron-command.webp" alt="Ultron command overseer" className="h-full w-full object-cover object-top" animate={{ filter: ['brightness(.78) saturate(1.05)', 'brightness(1.12) saturate(1.38)', 'brightness(.78) saturate(1.05)'], scale: [1.03, 1.075, 1.03] }} transition={{ duration: 2.8, repeat: Infinity, ease: 'easeInOut' }} />
          <motion.div className="absolute inset-x-0 h-[2px] bg-cyan-200/80 shadow-[0_0_12px_rgba(103,232,249,.9)]" animate={{ top: ['8%', '92%', '8%'] }} transition={{ duration: 3.6, repeat: Infinity, ease: 'linear' }} />
          <div className="absolute inset-0 opacity-30" style={{ backgroundImage: 'repeating-linear-gradient(0deg, transparent 0 3px, rgba(103,232,249,.16) 3px 4px)' }} />
          <motion.div className="absolute inset-2 border border-cyan-300/35" animate={{ opacity: [.28, .9, .28] }} transition={{ duration: 1.8, repeat: Infinity }} />
          <div className="absolute inset-0 bg-gradient-to-t from-[#02070c] via-transparent to-cyan-950/20" />
          <div className="absolute bottom-2 left-2 text-[7px] font-black uppercase tracking-[.24em] text-cyan-200">ULTRON · COMMAND AI</div>
        </motion.div>
      ) : (
        <>
          <motion.div animate={{ y: [0, -3, 0] }} transition={{ duration: 2.6, repeat: Infinity, ease: 'easeInOut' }} className="absolute bottom-7 left-8 h-12 w-12 border" style={{ borderColor: `${data.accent}55`, background: `linear-gradient(135deg, ${data.accent}28, #071018)`, boxShadow: `0 0 18px ${data.accent}1f` }}>
            <motion.div className="absolute inset-2 border" style={{ borderColor: `${data.accent}55` }} animate={{ rotate: [0, 360] }} transition={{ duration: 8, repeat: Infinity, ease: 'linear' }} />
          </motion.div>
          <div className="absolute bottom-7 left-24 h-8 w-20 overflow-hidden border" style={{ borderColor: `${data.accent}45`, background: '#071018' }}>
            <motion.div className="absolute inset-y-0 w-8" style={{ background: `linear-gradient(90deg, transparent, ${data.accent}55, transparent)` }} animate={{ x: [-36, 90] }} transition={{ duration: 2.2, repeat: Infinity, ease: 'linear' }} />
          </div>
          <motion.div animate={{ opacity: [.35, 1, .35], scaleY: [.9, 1.08, .9] }} transition={{ duration: 1.7, repeat: Infinity }} className="absolute bottom-8 right-10 h-16 w-5 border" style={{ borderColor: `${data.accent}45`, background: `linear-gradient(to top, #05090d, ${data.accent}22)`, transformOrigin: 'bottom' }} />
        </>
      )}

      <div className="absolute left-5 top-1 rounded-sm border border-white/5 bg-black/85 px-3 py-2 shadow-xl">
        <p className="text-[9px] font-black uppercase tracking-[0.25em]" style={{ color: `${data.accent}ee` }}>{data.label}</p>
        {data.subtitle ? <p className="mt-0.5 text-[7px] uppercase tracking-[.12em] text-slate-600">{data.subtitle}</p> : null}
      </div>
    </div>
  );
}

function AgentNode({ data }: { data: FactoryFloorNode & { shake?: boolean } }) {
  const color = STATUS_COLOR[data.status] || STATUS_COLOR.idle;
  const active = data.status === 'running' || data.status === 'thinking';
  const route = (data as FactoryFloorNode & { route?: RoutePoint[] }).route || [];
  const movement = data.circuit_tripped || data.shake
    ? { x: [0, -4, 4, -3, 3, 0] }
    : active && data.role_class === 'manager' && route.length > 1
      ? { x: route.map((p) => p.x), y: route.map((p) => p.y), rotate: [0, 1, 0, -1, 0] }
      : active && data.role_class === 'worker'
        ? { x: [0, 9, -6, 14, 24, 24, 10, 0], y: [0, -5, 4, -4, 3, 3, -2, 0], rotate: [0, .5, 0, -.5, 0, 0, .3, 0] }
        : active
          ? { x: [0, 7, -5, 4, 0], y: [0, -4, 1, -3, 0], rotate: [0, .5, 0, -.5, 0] }
          : { y: [0, -1.5, 0] };

  return (
    <motion.div animate={movement} whileHover={{ scale: 1.08, y: -3 }} transition={data.circuit_tripped || data.shake ? { duration: .28 } : { duration: active ? (data.role_class === 'manager' ? 11 : data.role_class === 'worker' ? 8.5 : 3.1) : 4.2, repeat: Infinity, ease: 'easeInOut', times: data.role_class === 'worker' && active ? [0,.14,.28,.44,.58,.7,.84,1] : undefined }} className="relative w-[130px] cursor-pointer select-none">
      <Handle type="target" position={Position.Left} className="!opacity-0" />
      <Handle type="source" position={Position.Right} className="!opacity-0" />
      <div className="relative mx-auto h-[78px] w-[78px]">
        {data.role_class === 'manager' && data.circuit_tripped ? (
          <motion.div className="absolute -right-5 -top-3 z-20 flex h-7 w-7 items-center justify-center rounded-md border border-amber-300/70 bg-amber-950/95 shadow-[0_0_18px_rgba(245,158,11,.55)]" animate={{ scale: [1, 1.18, 1], rotate: [-3, 3, -3] }} transition={{ duration: .9, repeat: Infinity }}>
            <AlertTriangle className="h-4 w-4 text-amber-300" />
          </motion.div>
        ) : null}
        <div className="absolute bottom-0 left-1/2 h-5 w-20 -translate-x-1/2 rounded-[50%] border" style={{ borderColor: `${color}55`, background: `radial-gradient(ellipse, ${color}30, rgba(0,0,0,.9) 68%)`, boxShadow: active ? `0 0 26px ${color}35` : undefined }} />
        <div className="absolute bottom-3 left-1/2 h-14 w-12 -translate-x-1/2 border bg-[#091018]" style={{ borderColor: data.circuit_tripped ? '#ef4444' : `${color}88`, clipPath: data.role_class === 'manager' ? 'polygon(18% 0,82% 0,100% 24%,88% 100%,12% 100%,0 24%)' : 'polygon(28% 0,72% 0,100% 28%,80% 100%,20% 100%,0 28%)', boxShadow: active ? `0 0 22px ${color}44` : '0 10px 20px rgba(0,0,0,.55)' }}>
          <div className="absolute left-1/2 top-1 h-5 w-7 -translate-x-1/2 rounded-[55%_55%_45%_45%] border" style={{ borderColor: `${color}aa`, background: data.role_class === 'manager' ? 'linear-gradient(180deg,#24344b,#0a111a)' : 'linear-gradient(180deg,#1d3b31,#08140f)' }}>
            <span className="absolute left-1 top-2 h-1.5 w-1.5 rounded-full" style={{ background: color, boxShadow: `0 0 6px ${color}` }} />
            <span className="absolute right-1 top-2 h-1.5 w-1.5 rounded-full" style={{ background: color, boxShadow: `0 0 6px ${color}` }} />
          </div>
          <div className="absolute bottom-2 left-2 right-2 flex justify-between"><span className="h-2 w-1 bg-slate-700" /><span className="h-2 w-1 bg-slate-700" /></div>
          {data.role_class === 'manager' ? <span className="absolute -right-2 top-5 h-3 w-3 rotate-45 border border-violet-300 bg-violet-500/60 shadow-[0_0_9px_rgba(167,139,250,.7)]" /> : null}
        </div>
        {active ? (<>
          <span className="absolute inset-3 animate-ping rounded-full opacity-20" style={{ background: color }} />
          {data.role_class === 'worker' ? (
            <motion.div className="absolute -right-1 bottom-2 flex h-5 w-5 items-center justify-center rounded border border-amber-300/70 bg-amber-950/90 shadow-[0_0_12px_rgba(245,158,11,.5)]" animate={{ y: [0, -2, 0, -1, 0], rotate: [-2, 2, -2, 1, -2], opacity: [1,1,1,.15,1] }} transition={{ duration: 8.5, repeat: Infinity, times: [0,.38,.57,.7,1] }}>
              <Package className="h-3 w-3 text-amber-300" />
            </motion.div>
          ) : null}
          <motion.span className="absolute left-1/2 top-0 h-2 w-2 -translate-x-1/2 rotate-45" style={{ background: color, boxShadow: `0 0 12px ${color}` }} animate={{ y: [0, -11, -22], opacity: [0, 1, 0], scale: [.5, 1, .2] }} transition={{ duration: 1.25, repeat: Infinity, ease: 'easeOut' }} />
          <motion.span className="absolute left-[28%] top-2 h-1.5 w-1.5 rounded-full" style={{ background: color, boxShadow: `0 0 10px ${color}` }} animate={{ x: [0, -8, -14], y: [0, -7, -16], opacity: [0, 1, 0] }} transition={{ duration: 1.7, repeat: Infinity, delay: .35 }} />
        </>) : null}
      </div>
      <div className="relative -mt-1 border bg-[#050a10]/96 px-2 py-2 text-center shadow-xl" style={{ borderColor: `${color}55`, clipPath: 'polygon(7% 0,93% 0,100% 25%,100% 100%,0 100%,0 25%)' }}>
        <p className="truncate text-[9px] font-black uppercase tracking-[.12em] text-white">{data.label}</p>
        <p className="mt-0.5 text-[6px] font-bold uppercase tracking-[.16em] text-slate-500">{data.role_class || 'worker'} · {data.division || 'general'}</p>
        <div className="mt-1 flex items-center justify-center gap-1.5"><span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color, boxShadow: active ? `0 0 7px ${color}` : undefined }} /><span className="text-[7px] font-bold uppercase tracking-widest" style={{ color }}>{data.status}</span></div>
      </div>
    </motion.div>
  );
}

function StrandEdge(props: EdgeProps) {
  const [edgePath] = getBezierPath({
    sourceX: props.sourceX,
    sourceY: props.sourceY,
    sourcePosition: props.sourcePosition,
    targetX: props.targetX,
    targetY: props.targetY,
    targetPosition: props.targetPosition,
  });
  const data = (props.data || {}) as Record<string, any>;
  const appearance = (data.appearance || {}) as { style?: string; color?: string; accent?: string };
  const styleName = String(appearance.style || 'polka');
  const color = String(appearance.color || '#22d3ee');
  const accent = String(appearance.accent || '#f8fafc');
  const selected = Boolean(props.selected);
  const width = selected ? 4.8 : styleName === 'red_laser' ? 3.4 : 2.7;
  const dash = styleName === 'polka' ? '1 10'
    : styleName === 'green_dots' ? '2 8'
      : styleName === 'violet_wave' ? '12 5 2 5'
        : styleName === 'blue_scan' ? '18 8'
          : styleName === 'pink_pulse' ? '5 5'
            : styleName === 'gold_comet' ? '16 12'
              : undefined;

  return (
    <g>
      <BaseEdge
        path={edgePath}
        markerEnd={props.markerEnd}
        interactionWidth={26}
        style={{
          stroke: color,
          strokeWidth: width,
          strokeDasharray: dash,
          strokeLinecap: 'round',
          opacity: 0.98,
          filter: `drop-shadow(0 0 ${selected ? 10 : 5}px ${color})`,
        }}
      />
      {styleName === 'red_laser' ? (
        <path d={edgePath} fill="none" stroke={accent} strokeWidth={1.1} opacity={0.9}>
          <animate attributeName="opacity" values=".2;1;.35;1;.2" dur="1.25s" repeatCount="indefinite" />
        </path>
      ) : null}
      {styleName === 'orange_butterfly' ? (
        <g>
          <text fontSize="15" fill={accent} style={{ filter: `drop-shadow(0 0 5px ${color})` }}>🦋
            <animateMotion dur="3.8s" repeatCount="indefinite" rotate="auto" path={edgePath} />
          </text>
        </g>
      ) : null}
      {styleName === 'gold_comet' ? (
        <circle r="4" fill={accent} style={{ filter: `drop-shadow(0 0 7px ${color})` }}>
          <animateMotion dur="2.7s" repeatCount="indefinite" path={edgePath} />
        </circle>
      ) : null}
      {styleName === 'polka' || styleName === 'green_dots' ? (
        <circle r={styleName === 'polka' ? 3.3 : 2.6} fill={accent} opacity=".95">
          <animateMotion dur={styleName === 'polka' ? '4.6s' : '3.4s'} repeatCount="indefinite" path={edgePath} />
        </circle>
      ) : null}
      {styleName === 'blue_scan' ? (
        <circle r="3.4" fill={accent}>
          <animateMotion dur="2.2s" repeatCount="indefinite" path={edgePath} />
          <animate attributeName="opacity" values="0;1;0" dur="1.1s" repeatCount="indefinite" />
        </circle>
      ) : null}
    </g>
  );
}

function ProductNode({ data, selected }: { data: FactoryFloorNode; selected?: boolean }) {
  const active = data.status === 'running';
  const state = String(data.product_state || 'IDEA').replace(/_/g, ' ');

  return (
    <motion.div
      whileHover={{ scale: 1.055 }}
      className={`relative w-[185px] cursor-pointer select-none ${selected ? 'drop-shadow-[0_0_14px_rgba(251,191,36,.85)]' : ''}`}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!h-1 !w-1 !border-0 !bg-amber-300 !opacity-0"
      />

      <Handle
        type="source"
        position={Position.Right}
        className="!h-1 !w-1 !border-0 !bg-amber-300 !opacity-0"
      />

      <div
        className={`overflow-hidden rounded-lg border bg-[#151108]/95 shadow-2xl ${selected ? 'border-amber-200' : 'border-amber-400/60'}`}
        style={{
          boxShadow: active
            ? '0 0 30px rgba(251,191,36,.26)'
            : '0 14px 34px rgba(0,0,0,.48)',
        }}
      >
        <div className="flex items-center gap-2.5 p-2.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded border border-amber-400/30 bg-amber-300/10">
            <Package className="h-5 w-5 text-amber-300" />
          </div>

          <div className="min-w-0">
            <p className="text-[7px] font-black uppercase tracking-[0.22em] text-amber-300/70">
              PROJECT
            </p>

            <p className="line-clamp-2 text-[9px] font-semibold leading-tight text-white">
              {data.label}
            </p>
          </div>
        </div>

        <div className="border-t border-amber-300/10 bg-black/25 px-2.5 py-1.5">
          <p className="text-[8px] font-bold uppercase tracking-wide text-amber-200">
            {state}
          </p>

          <p className="mt-0.5 truncate text-[8px] text-slate-600">
            {data.assigned_agent
              ? `Assigned → ${data.assigned_agent}`
              : 'Awaiting assignment'}
          </p>
          <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-slate-900">
            <motion.div className="h-full bg-amber-400" initial={false} animate={{ width: `${Math.max(4, Math.min(100, data.package_progress || 0))}%` }} transition={{ duration: .45 }} />
          </div>
          <p className="mt-1 text-[6px] uppercase tracking-[.12em] text-amber-200/60">{String(data.package_state || 'ready_for_manager').replace(/_/g, ' ')} → {String(data.next_destination || 'manager_review').replace(/_/g, ' ')}</p>
        </div>
      </div>
    </motion.div>
  );
}

type RoutePoint = { x: number; y: number };

function TransferPackageNode({ data, selected }: { data: FactoryFloorNode & { route?: RoutePoint[]; routeTimes?: number[]; routeLabels?: string[] }; selected?: boolean }) {
  const route = data.route || [];
  const xs = route.length ? route.map((p) => p.x) : [0, 0];
  const ys = route.length ? route.map((p) => p.y) : [0, 0];
  const times = data.routeTimes?.length === route.length ? data.routeTimes : undefined;
  const labels = data.routeLabels || [];

  return (
    <motion.div
      className={`relative h-8 w-8 cursor-pointer ${selected ? 'drop-shadow-[0_0_12px_rgba(251,191,36,1)]' : ''}`}
      animate={{ x: xs, y: ys, scale: [1, 1.08, 1] }}
      transition={{ x: { duration: 11, repeat: Infinity, ease: 'easeInOut', times }, y: { duration: 11, repeat: Infinity, ease: 'easeInOut', times }, scale: { duration: 1.1, repeat: Infinity } }}
    >
      <div className={`absolute inset-0 rotate-45 border bg-amber-950/90 shadow-[0_0_18px_rgba(245,158,11,.65)] ${selected ? 'border-white' : 'border-amber-300/80'}`} />
      <Package className="absolute inset-0 m-auto h-4 w-4 text-amber-200" />
      <motion.span className="absolute -right-3 top-1/2 h-1 w-3 -translate-y-1/2 bg-amber-300" animate={{ opacity: [.2, 1, .2], scaleX: [.5, 1.4, .5] }} transition={{ duration: .55, repeat: Infinity }} />
      {(labels.length ? labels : ['PACKAGE HANDOFF']).map((label, index) => {
        const windows = [
          [0,.04,.2,.24,1],
          [0,.2,.3,.38,1],
          [0,.48,.58,.66,1],
          [0,.72,.82,.92,1],
        ][Math.min(index, 3)];
        return (
          <motion.div key={label} className="absolute -left-8 -top-7 whitespace-nowrap rounded border border-amber-300/25 bg-black/85 px-1.5 py-0.5 text-[6px] font-black uppercase tracking-[.12em] text-amber-200" animate={{ opacity: [0, 1, 1, 0, 0] }} transition={{ duration: 11, repeat: Infinity, ease: 'linear', times: windows }}>
            {label}
          </motion.div>
        );
      })}
    </motion.div>
  );
}

const nodeTypes = {
  zone: ZoneNode,
  agent: AgentNode,
  product: ProductNode,
  transfer: TransferPackageNode,
};

const edgeTypes = { strand: StrandEdge };

type LivePhase = 'cached' | 'fetching' | 'live' | 'error';

function applyFloorPayload(floor: FactoryFloorPayload | null | undefined): FactoryFloorPayload | null {
  if (!floor?.nodes?.length) return null;
  writeFactoryFloorCache(floor);
  return floor;
}

function useFactoryFloorLive(
  onFloor: (floor: FactoryFloorPayload) => void,
  onPhase: (phase: LivePhase) => void,
  hasCachedFloor: boolean,
) {
  useEffect(() => {
    let cancelled = false;

    const applyMetrics = (payload: Record<string, unknown>) => {
      const ff = applyFloorPayload(payload.factory_floor as FactoryFloorPayload | undefined);
      if (ff) {
        onFloor(ff);
        onPhase('live');
        return true;
      }
      return false;
    };

    onPhase(hasCachedFloor ? 'cached' : 'fetching');

    void loadAdminDashboardFull().then((full) => {
      if (cancelled || !full) return;
      applyMetrics(full as unknown as Record<string, unknown>);
    });

    const disconnect = connectAdminMetricsStream({
      onOpen: () => {
        if (!cancelled) onPhase('live');
      },
      onMessage: (data) => {
        if (data && typeof data === 'object') {
          applyMetrics(data as Record<string, unknown>);
        }
      },
      onError: () => {
        if (!cancelled) onPhase(hasCachedFloor ? 'cached' : 'error');
      },
    });

    return () => {
      cancelled = true;
      disconnect();
    };
  }, [onFloor, onPhase, hasCachedFloor]);
}

export function FactoryFloorTab({ locale }: { locale: AdminLocale }) {
  const bootRef = useRef(readFactoryFloorCache());
  const hadCacheOnMount = bootRef.current != null;

  const [floor, setFloor] = useState<FactoryFloorPayload | null>(() => bootRef.current);
  const [livePhase, setLivePhase] = useState<LivePhase>(() => (hadCacheOnMount ? 'cached' : 'fetching'));
  const [selectedEntity, setSelectedEntity] =
    useState<FactoryFloorNode | null>(null);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [expandedAlert, setExpandedAlert] = useState<string | null>(null);
  const [alertNotes, setAlertNotes] = useState<Record<string, string>>({});
  const [selectedEdge, setSelectedEdge] = useState<Edge | null>(null);
  const [confirmTerminateId, setConfirmTerminateId] = useState<string | null>(null);
  const [quickTool, setQuickTool] = useState<'closed' | 'new-project' | 'command-selected' | 'personnel' | 'assign-personnel' | 'auto-staff' | 'manager-delegate'>('closed');
  const [quickPrompt, setQuickPrompt] = useState('');
  const [quickBusy, setQuickBusy] = useState(false);
  const [quickProductId, setQuickProductId] = useState('');
  const [quickWorkerId, setQuickWorkerId] = useState('');
  const [replayData, setReplayData] = useState<any | null>(null);
  const [replayIndex, setReplayIndex] = useState(0);
  const [replayLoading, setReplayLoading] = useState(false);

  useLayoutEffect(() => {
    const cached = readFactoryFloorCache();
    if (cached) {
      setFloor(cached);
      setLivePhase('cached');
    }
  }, []);

  const onFloor = useCallback((next: FactoryFloorPayload) => {
    setFloor(next);
  }, []);

  const onPhase = useCallback((phase: LivePhase) => {
    setLivePhase((prev) => {
      if (prev === 'live' && phase === 'fetching') return prev;
      return phase;
    });
  }, []);

  useFactoryFloorLive(onFloor, onPhase, hadCacheOnMount);

  const { flowNodes, flowEdges } = useMemo(() => {
    const items = floor?.nodes || [];

    const agents = items.filter((item) => item.kind !== 'product');
    const products = items.filter((item) => item.kind === 'product');

    const zoneNodes: Node[] = [
      {
        id: 'zone-command',
        type: 'zone',
        position: { x: 330, y: -245 },
        data: {
          label: 'COMMAND CORE',
          subtitle: 'Factory oversight / orchestration',
          accent: '#a78bfa',
        },
        style: { width: 390, height: 175 },
        selectable: false,
        draggable: false,
        zIndex: -10,
      },

      {
        id: 'zone-research',
        type: 'zone',
        position: { x: 0, y: 0 },
        data: {
          label: 'RESEARCH BAY',
          subtitle: 'Discovery / market intelligence',
          accent: '#22d3ee',
        },
        style: { width: 500, height: 325 },
        selectable: false,
        draggable: false,
        zIndex: -10,
      },

      {
        id: 'zone-management',
        type: 'zone',
        position: { x: 550, y: 0 },
        data: {
          label: 'MANAGER COMMAND',
          subtitle: 'Planning / routing / architecture',
          accent: '#818cf8',
        },
        style: { width: 500, height: 325 },
        selectable: false,
        draggable: false,
        zIndex: -10,
      },

      {
        id: 'zone-production',
        type: 'zone',
        position: { x: 0, y: 380 },
        data: {
          label: 'PRODUCTION BAY',
          subtitle: 'Design / development / QA / infrastructure',
          accent: '#34d399',
        },
        style: { width: 760, height: 350 },
        selectable: false,
        draggable: false,
        zIndex: -10,
      },

      {
        id: 'zone-funding',
        type: 'zone',
        position: { x: 810, y: 380 },
        data: {
          label: 'FUNDING / REVIEW',
          subtitle: 'Commercial review / escalation',
          accent: '#f59e0b',
        },
        style: { width: 240, height: 350 },
        selectable: false,
        draggable: false,
        zIndex: -10,
      },

      {
        id: 'zone-projects',
        type: 'zone',
        position: { x: 0, y: 785 },
        data: {
          label: 'PROJECT CONVEYOR',
          subtitle: 'Persistent products / live work items',
          accent: '#fbbf24',
        },
        style: { width: 1050, height: 250 },
        selectable: false,
        draggable: false,
        zIndex: -10,
      },
    ];

    const ecosystemLayout = [
      { id: 'health', x: 1120, y: 0 },
      { id: 'science', x: 1405, y: 0 },
      { id: 'commerce', x: 1120, y: 235 },
      { id: 'weapons', x: 1405, y: 235 },
      { id: 'general', x: 1260, y: 470 },
    ];
    for (const eco of ecosystemLayout) {
      const meta = (floor?.ecosystems || []).find((row) => row.id === eco.id);
      if (!meta) continue;
      zoneNodes.push({
        id: `zone-ecosystem-${eco.id}`,
        type: 'zone',
        position: { x: eco.x, y: eco.y },
        data: {
          label: meta.label,
          subtitle: `${meta.manager_label} · ${meta.description}`,
          accent: meta.accent,
        },
        style: { width: 250, height: 190 },
        selectable: false,
        draggable: false,
        zIndex: -10,
      });
    }

    const stationPositions: Record<
      string,
      { x: number; y: number }
    > = {
      external_agent: { x: 450, y: -165 },

      analyst: { x: 55, y: 100 },
      marketing: { x: 200, y: 100 },
      methodologist: { x: 345, y: 100 },
      evolution_analyst: { x: 130, y: 215 },

      pm: { x: 610, y: 100 },
      architect: { x: 790, y: 100 },

      designer: { x: 55, y: 485 },
      developer: { x: 225, y: 485 },
      qa: { x: 395, y: 485 },
      security: { x: 140, y: 620 },
      devops: { x: 315, y: 620 },

      sales: { x: 855, y: 495 },
    };
    for (const eco of ecosystemLayout) {
      stationPositions[`ecosystem-manager:${eco.id}`] = { x: eco.x + 55, y: eco.y + 82 };
    }

    const managerRoutes: Record<string, RoutePoint[]> = {
      pm: [{ x: 0, y: 0 }, { x: -65, y: 35 }, { x: -135, y: 120 }, { x: -135, y: 120 }, { x: -20, y: 310 }, { x: -20, y: 310 }, { x: 0, y: 0 }],
      architect: [{ x: 0, y: 0 }, { x: 45, y: 55 }, { x: 75, y: 175 }, { x: 75, y: 175 }, { x: 10, y: 300 }, { x: 10, y: 300 }, { x: 0, y: 0 }],
      sales: [{ x: 0, y: 0 }, { x: -25, y: -55 }, { x: -75, y: -115 }, { x: -75, y: -115 }, { x: -115, y: 260 }, { x: -115, y: 260 }, { x: 0, y: 0 }],
    };

    const agentNodes: Node[] = agents.map((agent, index) => ({
      id: agent.id,
      type: 'agent',
      position:
        stationPositions[agent.id] || {
          x: 600 + (index % 3) * 155,
          y: 200 + Math.floor(index / 3) * 105,
        },
      data: {
        ...agent,
        shake: agent.circuit_tripped,
        route: agent.role_class === 'manager' ? (managerRoutes[agent.id] || [{ x: 0, y: 0 }, { x: 35, y: 25 }, { x: 0, y: 0 }]) : undefined,
      },
      zIndex: 5,
    }));

    const productNodes: Node[] = products.map((product, index) => ({
      id: product.id,
      type: 'product',
      position: {
        x: 55 + (index % 4) * 245,
        y: 870 + Math.floor(index / 4) * 125,
      },
      data: product,
      zIndex: 6,
    }));

    const transferNodes: Node[] = products
      .filter((product) => product.status === 'running' && product.assigned_agent)
      .map((product, index) => {
        const source = stationPositions[String(product.assigned_agent)] || { x: 120, y: 120 };
        const assigned = agents.find((agent) => agent.id === product.assigned_agent);
        const managerTarget = assigned?.role_class === 'manager'
          ? source
          : (String(assigned?.division || '') === 'production' ? { x: 610, y: 160 } : { x: 610, y: 115 });
        const conveyorTarget = { x: 470, y: 845 };
        const finalTarget = String(product.next_destination || '').includes('fund') || assigned?.role_class === 'manager'
          ? { x: 875, y: 515 }
          : { x: 720, y: 185 };
        const rel = (target: RoutePoint): RoutePoint => ({ x: target.x - source.x, y: target.y - source.y });
        const route: RoutePoint[] = [
          { x: 0, y: 0 },
          rel(managerTarget),
          rel(managerTarget),
          rel(conveyorTarget),
          rel(conveyorTarget),
          rel(finalTarget),
          rel(finalTarget),
          { x: 0, y: 0 },
        ];
        return {
          id: `transfer:${product.id}`,
          type: 'transfer',
          position: { x: source.x + 56 + (index % 2) * 6, y: source.y + 18 },
          data: {
            ...product,
            route,
            routeTimes: [0,.22,.33,.52,.62,.78,.88,1],
            routeLabels: ['PACKAGE HANDOFF','MANAGER REVIEW','CONVEYOR TRANSFER','APPROVAL ROUTE'],
          },
          selectable: true,
          draggable: false,
          zIndex: 9,
        };
      });

    const hot = new Set(
      (floor?.hot_edges || []).map(
        (edge) => `${edge.from}->${edge.to}`,
      ),
    );

    const classifySignal = (from: string, to: string, explicitKind?: string) => {
      const pair = `${from}->${to}`.toLowerCase();
      const kind = String(explicitKind || '').toLowerCase();

      if (kind === 'funding' || pair.includes('sales') || pair.includes('fund') || pair.includes('review')) {
        return {
          color: '#22c55e',
          glow: 'rgba(34,197,94,.62)',
          dash: '3 7',
          width: 2.1,
          label: 'FUNDING',
        };
      }

      if (kind === 'production' || pair.includes('product:') || pair.includes('developer') || pair.includes('designer') || pair.includes('qa')) {
        return {
          color: '#f59e0b',
          glow: 'rgba(245,158,11,.58)',
          dash: '10 5 2 5',
          width: 2.2,
          label: 'PRODUCTION',
        };
      }

      if (pair.includes('security') || pair.includes('circuit')) {
        return {
          color: '#ef4444',
          glow: 'rgba(239,68,68,.6)',
          dash: '2 4',
          width: 2.2,
          label: 'ALERT',
        };
      }

      if (pair.includes('pm') || pair.includes('architect')) {
        return {
          color: '#a78bfa',
          glow: 'rgba(167,139,250,.56)',
          dash: '7 5',
          width: 2.0,
          label: 'COMMAND',
        };
      }

      return {
        color: '#22d3ee',
        glow: 'rgba(34,211,238,.55)',
        dash: '6 7',
        width: 1.9,
        label: 'DATA',
      };
    };

    const flowEdges: Edge[] = (floor?.edges || []).map(
      (edge, idx) => {
        const active = edge.active !== false || hot.has(`${edge.from}->${edge.to}`);
        const signal = classifySignal(edge.from, edge.to, edge.signal_kind);
        const strandId = String((edge as any).id || edge.request_id || `strand-${edge.from}-${edge.to}-${idx}`);
        const appearance = edge.appearance || { style: 'polka', color: signal.color, accent: '#f8fafc' };

        return {
          id: strandId,
          type: 'strand',
          source: edge.from,
          target: edge.to,
          animated: false,
          interactionWidth: 26,
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: appearance.color || signal.color,
            width: 17,
            height: 17,
          },
          data: { signalType: signal.label, active, ...edge, appearance },
          zIndex: active ? 5 : 2,
        };
      },
    );

    return {
      flowNodes: [
        ...zoneNodes,
        ...agentNodes,
        ...productNodes,
        ...transferNodes,
      ],
      flowEdges,
    };
  }, [floor]);

  const [nodes, setNodes, onNodesChange] = useNodesState(flowNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(flowEdges);

  useEffect(() => {
    setNodes(flowNodes);
    setEdges(flowEdges);
  }, [flowNodes, flowEdges, setNodes, setEdges]);

  const syncing = livePhase === 'cached' || livePhase === 'fetching';
  const connectionLabel =
    livePhase === 'live'
      ? t(locale, 'wow.factoryFloorLive')
      : livePhase === 'error'
        ? hadCacheOnMount
          ? t(locale, 'wow.factoryFloorStale')
          : t(locale, 'wow.factoryFloorLoadFailed')
        : livePhase === 'cached'
          ? t(locale, 'wow.factoryFloorStale')
          : t(locale, 'wow.factoryFloorSyncing');

  const refreshFloor = useCallback(async (keepProductId?: string) => {
    const refreshed = await loadAdminDashboardFull();
    const ff = refreshed?.factory_floor as FactoryFloorPayload | undefined;
    if (ff?.nodes?.length) {
      setFloor(ff);
      if (keepProductId) {
        const updated = ff.nodes.find((node) => node.product_id === keepProductId && node.kind === 'product');
        if (updated) setSelectedEntity(updated);
      }
    }
  }, []);

  const controlProject = useCallback(async (productId: string, action: 'pause' | 'resume' | 'set_priority' | 'terminate', priority?: 'normal' | 'high' | 'critical' | 'low') => {
    const key = `project:${productId}:${action}:${priority || ''}`;
    setActionBusy(key);
    try {
      await api.controlFactoryFloorProduct(productId, {
        action,
        priority,
        reason: action === 'terminate' ? 'Stopped by operator from Factory Floor' : undefined,
      });
      toast.success(
        action === 'pause' ? 'Project paused'
          : action === 'resume' ? 'Project resumed'
            : action === 'terminate' ? 'Project stopped; history and files preserved'
              : `Priority set to ${priority}`,
      );
      setConfirmTerminateId(null);
      await refreshFloor(productId);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Project command failed');
    } finally {
      setActionBusy(null);
    }
  }, [refreshFloor]);

  const controlPersonnel = useCallback(async (agentId: string, body: { action: 'promote' | 'demote' | 'set_division' | 'set_ecosystem' | 'grant_permission' | 'revoke_permission' | 'rename' | 'retire' | 'restore'; division?: string; ecosystem?: string; permission?: string; label?: string }) => {
    const key = `personnel:${agentId}:${body.action}`;
    setActionBusy(key);
    try {
      await api.updateFactoryFloorPersonnel(agentId, body);
      const refreshed = await loadAdminDashboardFull();
      const ff = refreshed?.factory_floor as FactoryFloorPayload | undefined;
      if (ff?.nodes?.length) {
        setFloor(ff);
        const updated = ff.nodes.find((node) => node.id === agentId);
        setSelectedEntity(updated || null);
      }
      toast.success(body.action === 'promote' ? 'AI promoted to manager' : body.action === 'demote' ? 'AI returned to worker role' : body.action === 'retire' ? 'AI unit retired' : 'AI permissions updated');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Personnel change failed');
    } finally {
      setActionBusy(null);
    }
  }, []);

  const reviewAssignmentReport = useCallback(async (taskId: string, action: 'accept' | 'send_back' | 'escalate' | 'incorporate') => {
    let feedback = '';
    if (action === 'send_back') {
      const note = window.prompt('What should this AI improve on the next pass?');
      if (note === null) return;
      feedback = note.trim();
    } else if (action === 'escalate') {
      const note = window.prompt('Optional note for Command AI:');
      if (note === null) return;
      feedback = note.trim();
    }
    const key = `assignment-report:${taskId}:${action}`;
    setActionBusy(key);
    try {
      await api.reviewFactoryAssignmentReport(taskId, { action, feedback });
      toast.success(
        action === 'accept' ? 'Manager accepted the report'
          : action === 'send_back' ? 'Sent back for another pass'
            : action === 'escalate' ? 'Report escalated to Command AI'
              : 'Report incorporated into the project record',
      );
      setSelectedEdge(null);
      await refreshFloor();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Report action failed');
    } finally {
      setActionBusy(null);
    }
  }, [refreshFloor]);

  const openProjectReplay = useCallback(async (productId: string) => {
    setReplayLoading(true);
    try {
      const timeline = await api.getReplayTimeline(productId);
      setReplayData(timeline);
      const frames = timeline?.frames || [];
      setReplayIndex(Math.max(0, frames.length - 1));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not load project history');
    } finally {
      setReplayLoading(false);
    }
  }, []);

  const runQuickFactoryCommand = useCallback(async () => {
    const prompt = quickPrompt.trim();
    if (!prompt) return;
    setQuickBusy(true);
    try {
      if (quickTool === 'new-project') {
        const created = await api.createAdminProduct({
          idea: prompt,
          production_mode: true,
          interface_locale: locale,
          content_locale: locale,
        });
        toast.success('New project created on the Factory Floor');
        setQuickPrompt('');
        await refreshFloor(created.product_id);
        return;
      }

      if (quickTool === 'personnel') {
        const created = await api.createFactoryFloorPersonnel({ description: prompt });
        const refreshed = await loadAdminDashboardFull();
        const ff = refreshed?.factory_floor as FactoryFloorPayload | undefined;
        if (ff?.nodes?.length) {
          setFloor(ff);
          const unit = ff.nodes.find((node) => node.id === created.id);
          if (unit) setSelectedEntity(unit);
        }
        toast.success(created.role_class === 'manager' ? 'Manager created and placed on the floor' : 'Worker created and placed on the floor');
        setQuickPrompt('');
        return;
      }

      if (quickTool === 'auto-staff') {
        const pid = quickProductId || String(selectedEntity?.product_id || '');
        if (!pid) {
          toast.error('Choose a project first');
          return;
        }
        const assigned = await api.assignFactoryFloorPersonnel('auto', { product_id: pid, directive: prompt });
        toast.success(`Automatically assigned to ${assigned.agent_label || assigned.agent_id}`);
        setQuickPrompt('');
        await refreshFloor(pid);
        return;
      }

      if (quickTool === 'manager-delegate') {
        if (!selectedEntity || selectedEntity.role_class !== 'manager') {
          toast.error('Select an AI manager first');
          return;
        }
        if (!quickWorkerId) {
          toast.error('Choose a subordinate AI worker');
          return;
        }
        if (!quickProductId) {
          toast.error('Choose a project for this task');
          return;
        }
        const delegated = await api.delegateFactoryFloorManagerTask(selectedEntity.id, {
          worker_id: quickWorkerId,
          product_id: quickProductId,
          directive: prompt,
        });
        toast.success(`${selectedEntity.label} added a task to ${delegated.subordinate_label || delegated.subordinate_id}`);
        setQuickPrompt('');
        const refreshed = await loadAdminDashboardFull();
        const ff = refreshed?.factory_floor as FactoryFloorPayload | undefined;
        if (ff?.nodes?.length) {
          setFloor(ff);
          const updatedManager = ff.nodes.find((node) => node.id === selectedEntity.id);
          if (updatedManager) setSelectedEntity(updatedManager);
        }
        return;
      }

      if (quickTool === 'assign-personnel') {
        if (!selectedEntity || selectedEntity.kind === 'product' || selectedEntity.role_class === 'package') {
          toast.error('Select an AI unit first');
          return;
        }
        if (!quickProductId) {
          toast.error('Choose a project for this assignment');
          return;
        }
        const managers = (floor?.nodes || []).filter((node) => node.role_class === 'manager' && node.kind !== 'product');
        const sameDivision = managers.find((node) => node.division === selectedEntity.division && node.id !== selectedEntity.id);
        const fallbackManager = managers.find((node) => node.id === 'pm') || managers.find((node) => node.id !== selectedEntity.id);
        const managerId = selectedEntity.role_class === 'manager' ? undefined : (sameDivision?.id || fallbackManager?.id);
        await api.assignFactoryFloorPersonnel(selectedEntity.id, {
          product_id: quickProductId,
          directive: prompt,
          manager_id: managerId,
        });
        toast.success(`Task assigned to ${selectedEntity.label}`);
        setQuickPrompt('');
        await refreshFloor(quickProductId);
        return;
      }

      if (quickTool === 'command-selected') {
        if (!selectedEntity) {
          toast.error('Select a project first');
          return;
        }
        const pid = String(selectedEntity.product_id || '');
        if (!pid || !(selectedEntity.kind === 'product' || selectedEntity.role_class === 'package')) {
          toast.error('Quick commands currently apply to project packages');
          return;
        }
        const command = prompt.toLowerCase();
        if (/\b(pause|hold|freeze)\b/.test(command)) {
          await controlProject(pid, 'pause');
        } else if (/\b(resume|continue|restart)\b/.test(command)) {
          await controlProject(pid, 'resume');
        } else if (/\b(critical|urgent|highest|top priority)\b/.test(command)) {
          await controlProject(pid, 'set_priority', 'critical');
        } else if (/\b(high|important|upgrade|promote)\b/.test(command)) {
          await controlProject(pid, 'set_priority', 'high');
        } else if (/\b(normal|standard|regular)\b/.test(command)) {
          await controlProject(pid, 'set_priority', 'normal');
        } else if (/\b(stop|kill|cancel|terminate)\b/.test(command)) {
          setConfirmTerminateId(pid);
          toast('Confirm Stop Project in the project panel');
        } else {
          toast.error('For now use: pause, resume, high priority, critical, normal, or stop');
          return;
        }
        setQuickPrompt('');
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Factory command failed');
    } finally {
      setQuickBusy(false);
    }
  }, [quickPrompt, quickTool, quickProductId, quickWorkerId, locale, refreshFloor, selectedEntity, controlProject, floor]);

  const resolveHumanReview = useCallback(async (alertId: string, productId: string, action: 'approve' | 'reject') => {
    setActionBusy(`${alertId}:${action}`);
    try {
      if (action === 'approve') {
        const note = (alertNotes[alertId] || '').trim();
        await api.postPipelineHumanReviewApprove(productId, { note });
        toast.success('Approved — package released to the next stage');
      } else {
        const notes = (alertNotes[alertId] || '').trim();
        if (notes.length < 8) {
          setExpandedAlert(alertId);
          toast.error('Add at least 8 characters of rework instructions');
          return;
        }
        await api.postPipelineHumanReviewReject(productId, notes);
        toast.success('Sent back — developer rework queued');
      }
      setExpandedAlert(null);
      setAlertNotes((prev) => ({ ...prev, [alertId]: '' }));
      await refreshFloor(productId);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Factory action failed');
    } finally {
      setActionBusy(null);
    }
  }, [alertNotes, refreshFloor]);

  const verifyFundingRequest = useCallback(async (requestId: string, passed: boolean) => {
    const key = `funding:verify:${requestId}`;
    setActionBusy(key);
    try {
      await api.verifyEmpireFundingRequest(requestId, {
        verifier_id: 'funding:verifier',
        passed,
        evidence: { reviewed_from: 'factory_floor', reviewed_at: Date.now() },
        note: passed ? 'Funding Utility verification passed by operator review.' : 'Funding Utility verification rejected by operator review.',
      });
      toast.success(passed ? 'Funding verification passed' : 'Funding verification rejected');
      await refreshFloor();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Funding verification failed');
    } finally {
      setActionBusy(null);
    }
  }, [refreshFloor]);

  const decideFundingRequest = useCallback(async (
    request: { id: string; amount_usd?: number; purpose?: string; department?: string; product_id?: string | null },
    approved: boolean,
  ) => {
    const key = `funding:owner:${request.id}`;
    setActionBusy(key);
    try {
      const amount = Number(request.amount_usd || 0);
      if (approved && amount >= 5000) {
        const risk = window.prompt('Risk meter 0-100 for this capital decision:', '50');
        if (risk == null) return;
        const roiLow = window.prompt('Expected ROI low end (%):', '0');
        if (roiLow == null) return;
        const roiHigh = window.prompt('Expected ROI high end (%):', '20');
        if (roiHigh == null) return;
        const breakEven = window.prompt('Break-even estimate in months:', '12');
        if (breakEven == null) return;
        const confidence = window.prompt('Confidence 0-100:', '60');
        if (confidence == null) return;
        const marketEvidence = window.prompt('Summarize the market evidence supporting this spend:');
        if (!marketEvidence) return;
        const capitalEfficiency = window.prompt('Summarize why this is capital-efficient versus a cheaper path:');
        if (!capitalEfficiency) return;
        const audit = window.prompt('Independent audit summary / strongest challenge:');
        if (!audit) return;
        const alternatives = window.prompt('Cheaper alternatives considered (separate with semicolons):');
        if (!alternatives) return;
        const rationale = window.prompt('Plain-language 1-2 sentence owner rationale:');
        if (!rationale) return;
        await api.saveEmpireFundingDecisionCard(request.id, {
          roi_low_pct: Number(roiLow),
          roi_high_pct: Number(roiHigh),
          break_even_months: Number(breakEven),
          maximum_loss_usd: amount,
          confidence: Number(confidence),
          risk_score: Number(risk),
          market_evidence_summary: marketEvidence,
          capital_efficiency_summary: capitalEfficiency,
          independent_audit_summary: audit,
          cheaper_alternatives: alternatives.split(';').map((x) => x.trim()).filter(Boolean),
          plain_language_rationale: rationale,
        });
      }
      const note = window.prompt(approved ? 'Optional owner approval note:' : 'Reason for rejecting this request:') || '';
      await api.decideEmpireFundingRequest(request.id, approved, note);
      toast.success(approved ? 'Capital request authorized by owner' : 'Capital request rejected');
      await refreshFloor(request.product_id || undefined);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Owner funding decision failed');
    } finally {
      setActionBusy(null);
    }
  }, [refreshFloor]);

  const advanceFundingOpportunity = useCallback(async (opportunity: { id: string; status?: string }) => {
    const order = ['found', 'eligible', 'application_ready', 'submitted', 'awarded', 'received'];
    const current = String(opportunity.status || 'found');
    const index = order.indexOf(current);
    if (index < 0 || index >= order.length - 1) return;
    const next = order[index + 1];
    setActionBusy(`funding:opportunity:${opportunity.id}`);
    try {
      await api.advanceEmpireFundingOpportunity(opportunity.id, next, {
        reviewed_from: 'factory_floor',
        reviewed_at: Date.now(),
      });
      toast.success(`Funding opportunity advanced to ${next.replace(/_/g, ' ')}`);
      await refreshFloor();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not advance funding opportunity');
    } finally {
      setActionBusy(null);
    }
  }, [refreshFloor]);

  const createFundingBudget = useCallback(async () => {
    const ceilingRaw = window.prompt('Preapproved budget ceiling (USD):');
    if (!ceilingRaw) return;
    const ceiling = Number(ceilingRaw);
    if (!Number.isFinite(ceiling) || ceiling <= 0) {
      toast.error('Enter a positive budget amount');
      return;
    }
    const department = window.prompt('Department scope (optional; leave blank for workspace-wide):') || undefined;
    const productId = window.prompt('Project ID scope (optional; leave blank for any project):') || undefined;
    const note = window.prompt('Budget note / permitted purpose:') || '';
    setActionBusy('funding:create-budget');
    try {
      await api.createEmpireFundingBudget({
        ceiling_usd: ceiling,
        department,
        product_id: productId,
        note,
      });
      toast.success('Owner preapproved budget created');
      await refreshFloor();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not create funding budget');
    } finally {
      setActionBusy(null);
    }
  }, [refreshFloor]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-white flex items-center gap-2">
            <Zap className="h-5 w-5 text-cyan-400" />
            {t(locale, 'tab.factoryFloor')}
          </h2>
          <p className="text-xs text-gray-500 mt-1">{t(locale, 'wow.factoryFloorIntro')}</p>
        </div>
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <Radio
            className={`h-3.5 w-3.5 ${
              livePhase === 'live' ? 'text-emerald-400' : livePhase === 'error' ? 'text-rose-400' : 'text-amber-400'
            }`}
          />
          {connectionLabel}
          {floor?.running_count != null ? <span>· {floor.running_count} active</span> : null}
        </div>
      </div>

      {syncing && floor ? (
        <p className="flex items-center gap-2 text-xs text-indigo-200/80" aria-live="polite">
          <Loader2 className="h-3.5 w-3.5 animate-spin shrink-0" />
          {hadCacheOnMount ? t(locale, 'wow.factoryFloorCachedSync') : t(locale, 'wow.factoryFloorFirstLoad')}
        </p>
      ) : null}

      {!floor ? (
        <div className="flex h-64 items-center justify-center text-gray-500">
          <Loader2 className="h-6 w-6 animate-spin text-indigo-400 mr-2" />
          {t(locale, 'common.loading')}
        </div>
      ) : (
        <GlassCard
          className={`h-[min(72vh,720px)] p-0 overflow-hidden border-indigo-500/20 transition-opacity ${
            syncing ? 'opacity-95' : 'opacity-100'
          }`}
        >
          <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          nodesDraggable={false}
          nodesConnectable={false}
          minZoom={0.16}
          maxZoom={2.0}
          onNodeClick={(_, node) => {
            if (!String(node.id).startsWith('zone-')) {
              setSelectedEdge(null);
              setSelectedEntity(node.data as FactoryFloorNode);
            }
          }}
          onEdgeClick={(_, edge) => {
            setSelectedEntity(null);
            setSelectedEdge(edge);
          }}
          onPaneClick={() => { setSelectedEntity(null); setSelectedEdge(null); }}
          fitView
          fitViewOptions={{ padding: 0.14, minZoom: 0.16, maxZoom: 0.72 }}
          proOptions={{ hideAttribution: true }}
          style={{
            background:
              'radial-gradient(circle at 50% 38%, rgba(8,24,38,.28), rgba(1,4,8,.995) 64%), linear-gradient(180deg,#02050a 0%,#050a10 52%,#020408 100%)',
          }}
        >
          <div className="pointer-events-none absolute inset-0 overflow-hidden">
            <div className="absolute inset-0 bg-[#010309]" />

            <div className="absolute inset-x-0 top-0 h-[36%] overflow-hidden">
              <div className="absolute inset-0 opacity-90" style={{ backgroundImage: 'radial-gradient(circle at 12% 18%,rgba(255,255,255,.95) 0 1px,transparent 1.4px),radial-gradient(circle at 31% 64%,rgba(103,232,249,.8) 0 1px,transparent 1.5px),radial-gradient(circle at 52% 26%,rgba(255,255,255,.75) 0 1px,transparent 1.4px),radial-gradient(circle at 72% 58%,rgba(147,197,253,.85) 0 1px,transparent 1.4px),radial-gradient(circle at 88% 22%,rgba(255,255,255,.9) 0 1px,transparent 1.3px)', backgroundSize: '170px 130px,210px 160px,250px 190px,300px 220px,360px 260px' }} />
              <motion.div className="absolute -left-[8%] top-[8%] h-[72%] w-[42%] rounded-full opacity-45 blur-3xl" style={{ background: 'radial-gradient(circle,rgba(34,211,238,.22),rgba(59,130,246,.08) 42%,transparent 72%)' }} animate={{ x: [0,18,-7,0], y:[0,-8,6,0] }} transition={{ duration: 18, repeat: Infinity, ease:'easeInOut' }} />
              <motion.div className="absolute right-[2%] top-[8%] h-[240px] w-[240px] rounded-full border border-cyan-200/10 opacity-70" style={{ background: 'radial-gradient(circle at 35% 30%,rgba(148,163,184,.28),rgba(14,116,144,.18) 38%,rgba(2,6,23,.95) 72%)', boxShadow:'inset -22px -16px 50px rgba(0,0,0,.7),0 0 45px rgba(34,211,238,.08)' }} animate={{ rotate:360 }} transition={{ duration:120, repeat:Infinity, ease:'linear' }} />
              <div className="absolute bottom-0 left-0 right-0 h-[58%] bg-gradient-to-b from-transparent via-[#02070d]/35 to-[#05080c]" />
            </div>

            <div className="absolute left-0 right-0 top-[24%] h-[16%] border-y border-cyan-300/10 bg-gradient-to-b from-[#111922]/90 via-[#071018]/96 to-[#03070b]/95 shadow-[0_18px_35px_rgba(0,0,0,.65)]">
              <div className="absolute inset-x-0 top-3 flex justify-around opacity-70">
                {Array.from({ length: 13 }).map((_, i) => (
                  <motion.span key={i} className="h-1.5 w-8 rounded-sm bg-cyan-300/25 shadow-[0_0_8px_rgba(34,211,238,.25)]" animate={{ opacity:[.2,.85,.2] }} transition={{ duration:1.8+(i%4)*.45,repeat:Infinity,delay:i*.09 }} />
                ))}
              </div>
              <div className="absolute inset-x-0 bottom-0 h-4 bg-[repeating-linear-gradient(90deg,#111827_0_34px,#1f2937_34px_38px,#050a10_38px_70px)] opacity-80" />
            </div>

            <div className="absolute inset-x-[4%] bottom-[3%] top-[34%] overflow-hidden border-x border-t border-cyan-300/10 bg-gradient-to-b from-[#0c131a]/92 via-[#070c12]/96 to-[#030609]/98 shadow-[0_-18px_40px_rgba(0,0,0,.45),inset_0_0_70px_rgba(34,211,238,.035)]" style={{ clipPath:'polygon(4% 0,96% 0,100% 100%,0 100%)' }}>
              <div className="absolute inset-0 opacity-55" style={{ backgroundImage:'linear-gradient(rgba(148,163,184,.07) 1px,transparent 1px),linear-gradient(90deg,rgba(148,163,184,.07) 1px,transparent 1px)',backgroundSize:'54px 54px',transform:'perspective(600px) rotateX(58deg) scale(1.28)',transformOrigin:'50% 100%' }} />
              <div className="absolute inset-x-0 bottom-0 h-[45%] bg-[repeating-linear-gradient(90deg,rgba(255,255,255,.015)_0_1px,transparent_1px_80px),repeating-linear-gradient(0deg,rgba(34,211,238,.03)_0_1px,transparent_1px_64px)]" />
              <div className="absolute inset-y-0 left-[7%] w-px bg-cyan-300/15" />
              <div className="absolute inset-y-0 right-[7%] w-px bg-cyan-300/15" />
            </div>

            <div className="absolute left-[1%] top-[31%] bottom-[4%] w-[7%] border-r border-cyan-300/10 bg-gradient-to-r from-[#111821] via-[#0a1118] to-[#02060a] shadow-[12px_0_26px_rgba(0,0,0,.45)]">
              {Array.from({ length: 5 }).map((_,i)=><div key={i} className="mx-auto mt-8 h-14 w-5 border border-slate-600/25 bg-black/40 shadow-inner"><motion.div className="mx-auto mt-2 h-2 w-2 rounded-full bg-cyan-300/50" animate={{opacity:[.15,1,.15]}} transition={{duration:1.4+i*.28,repeat:Infinity}} /></div>)}
            </div>
            <div className="absolute right-[1%] top-[31%] bottom-[4%] w-[7%] border-l border-cyan-300/10 bg-gradient-to-l from-[#111821] via-[#0a1118] to-[#02060a] shadow-[-12px_0_26px_rgba(0,0,0,.45)]">
              {Array.from({ length: 5 }).map((_,i)=><div key={i} className="mx-auto mt-8 h-14 w-5 border border-slate-600/25 bg-black/40 shadow-inner"><motion.div className="mx-auto mt-2 h-2 w-2 rounded-full bg-amber-300/50" animate={{opacity:[.15,1,.15]}} transition={{duration:1.7+i*.24,repeat:Infinity}} /></div>)}
            </div>

            <div className="absolute left-[10%] top-[38%] h-20 w-20 rounded-full border border-cyan-300/15 bg-black/55 shadow-[0_0_26px_rgba(34,211,238,.08)]">
              <motion.div className="absolute inset-3 rounded-full border border-cyan-300/30" animate={{rotate:360}} transition={{duration:8,repeat:Infinity,ease:'linear'}} />
              <motion.div className="absolute inset-6 rounded-full bg-cyan-300/20 shadow-[0_0_18px_rgba(34,211,238,.35)]" animate={{scale:[.82,1.08,.82],opacity:[.3,.9,.3]}} transition={{duration:2.1,repeat:Infinity}} />
            </div>
            <div className="absolute right-[11%] top-[42%] h-24 w-14 border border-emerald-300/10 bg-black/55 shadow-[0_0_24px_rgba(16,185,129,.06)]">
              <motion.div className="absolute bottom-2 left-2 right-2 h-[70%] bg-gradient-to-t from-emerald-400/25 to-transparent" animate={{scaleY:[.45,1,.65,.45],opacity:[.25,.8,.45,.25]}} transition={{duration:2.8,repeat:Infinity}} style={{transformOrigin:'bottom'}} />
            </div>

            <motion.div className="absolute left-[-15%] top-[22%] h-px w-[38%] bg-gradient-to-r from-transparent via-cyan-300/70 to-transparent shadow-[0_0_14px_rgba(34,211,238,.5)]" animate={{ x: ['0vw', '120vw'] }} transition={{ duration: 8, repeat: Infinity, ease: 'linear' }} />
            <motion.div className="absolute right-[-20%] top-[61%] h-px w-[45%] bg-gradient-to-r from-transparent via-blue-400/55 to-transparent" animate={{ x: ['0vw', '-125vw'] }} transition={{ duration: 11, repeat: Infinity, ease: 'linear', delay: 1.4 }} />
            <motion.div className="absolute inset-x-0 bottom-[14%] h-16 opacity-20" style={{ backgroundImage: 'repeating-linear-gradient(90deg, transparent 0 46px, rgba(34,211,238,.32) 47px 49px, transparent 50px 92px)' }} animate={{ x: [0, 92] }} transition={{ duration: 3.8, repeat: Infinity, ease: 'linear' }} />
            <motion.div className="absolute left-1/2 top-1/2 h-[460px] w-[460px] -translate-x-1/2 -translate-y-1/2 rounded-full border border-cyan-300/10" animate={{ rotate: 360, opacity: [.12, .27, .12] }} transition={{ rotate: { duration: 28, repeat: Infinity, ease: 'linear' }, opacity: { duration: 3.2, repeat: Infinity } }} />

            <div className="absolute inset-x-0 bottom-0 h-10 bg-gradient-to-t from-black via-[#02070d]/90 to-transparent" />
            <div className="absolute inset-0 shadow-[inset_0_0_120px_rgba(0,0,0,.78)]" />
          </div>
          <Panel position="top-left">
            <div className="flex items-start gap-2">
              <div className="w-[52px] overflow-hidden rounded-xl border border-cyan-400/25 bg-[#03080e]/96 p-1.5 shadow-2xl backdrop-blur-xl">
                <button type="button" title="Create a new project" onClick={() => { setQuickTool('new-project'); setQuickPrompt(''); }} className={`mb-1 flex h-10 w-10 items-center justify-center rounded-lg border ${quickTool === 'new-project' ? 'border-cyan-300/60 bg-cyan-400/15 text-cyan-100' : 'border-white/10 bg-white/5 text-cyan-300'}`}>
                  <Plus className="h-4 w-4" />
                </button>
                <button type="button" title="Command the selected project" onClick={() => { setQuickTool('command-selected'); setQuickPrompt(''); }} className={`mb-1 flex h-10 w-10 items-center justify-center rounded-lg border ${quickTool === 'command-selected' ? 'border-violet-300/60 bg-violet-400/15 text-violet-100' : 'border-white/10 bg-white/5 text-violet-300'}`}>
                  <Sparkles className="h-4 w-4" />
                </button>
                <button type="button" title="Create an AI worker or manager" onClick={() => { setQuickTool('personnel'); setQuickPrompt(''); }} className={`mb-1 flex h-10 w-10 items-center justify-center rounded-lg border ${quickTool === 'personnel' ? 'border-emerald-300/60 bg-emerald-400/15 text-emerald-100' : 'border-white/10 bg-white/5 text-emerald-300'}`}>
                  <UserPlus className="h-4 w-4" />
                </button>
                {quickTool !== 'closed' ? (
                  <button type="button" title="Close quick command" onClick={() => { setQuickTool('closed'); setQuickPrompt(''); }} className="flex h-10 w-10 items-center justify-center rounded-lg border border-white/10 bg-white/5 text-slate-500">
                    <X className="h-4 w-4" />
                  </button>
                ) : null}
              </div>

              {quickTool !== 'closed' ? (
                <motion.div initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} className="w-[310px] rounded-xl border border-cyan-400/25 bg-[#03080e]/96 p-3 shadow-2xl backdrop-blur-xl">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-[8px] font-black uppercase tracking-[.22em] text-cyan-300/70">{quickTool === 'new-project' ? 'QUICK CREATE' : quickTool === 'personnel' ? 'AI PERSONNEL' : quickTool === 'manager-delegate' ? 'MANAGER DELEGATION' : quickTool === 'assign-personnel' ? 'ASSIGN AI TASK' : quickTool === 'auto-staff' ? 'AUTO STAFF TASK' : 'QUICK COMMAND'}</p>
                      <p className="mt-1 text-[9px] text-slate-400">{quickTool === 'new-project' ? 'Describe the project exactly as you want it.' : quickTool === 'personnel' ? 'Describe the job. The factory chooses worker vs manager, department, permissions, and icon automatically.' : quickTool === 'manager-delegate' ? selectedEntity ? `${selectedEntity.label} can add a new task to one of its AI worker subordinates.` : 'Select an AI manager first.' : quickTool === 'assign-personnel' ? selectedEntity ? `Assign work to ${selectedEntity.label}.` : 'Select an AI unit first.' : quickTool === 'auto-staff' ? 'Describe the work. The factory chooses the best available AI and its division manager.' : selectedEntity ? `Command · ${selectedEntity.label}` : 'Select a project package, then type the change.'}</p>
                    </div>
                  </div>
                  {quickTool === 'manager-delegate' ? (
                    <select value={quickWorkerId} onChange={(e) => setQuickWorkerId(e.target.value)} className="mt-3 w-full rounded-lg border border-white/10 bg-black/55 px-3 py-2 text-[9px] text-white outline-none focus:border-violet-400/40">
                      <option value="">Choose subordinate worker…</option>
                      {(floor?.nodes || [])
                        .filter((node) =>
                          node.kind !== 'product'
                          && node.role_class === 'worker'
                          && !node.virtual_personnel
                          && (!node.supervisor_id || node.supervisor_id === selectedEntity?.id)
                        )
                        .map((node) => (
                          <option key={node.id} value={node.id}>
                            {node.label}{node.supervisor_id === selectedEntity?.id ? ' · subordinate' : ' · available'}
                          </option>
                        ))}
                    </select>
                  ) : null}
                  {quickTool === 'assign-personnel' || quickTool === 'auto-staff' || quickTool === 'manager-delegate' ? (
                    <select value={quickProductId} onChange={(e) => setQuickProductId(e.target.value)} className="mt-3 w-full rounded-lg border border-white/10 bg-black/55 px-3 py-2 text-[9px] text-white outline-none focus:border-emerald-400/40">
                      <option value="">Choose project…</option>
                      {(floor?.nodes || []).filter((node) => node.kind === 'product' && node.product_id).map((node) => (
                        <option key={node.id} value={String(node.product_id)}>{node.label}</option>
                      ))}
                    </select>
                  ) : null}
                  <textarea
                    value={quickPrompt}
                    onChange={(e) => setQuickPrompt(e.target.value)}
                    onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') void runQuickFactoryCommand(); }}
                    placeholder={quickTool === 'new-project' ? 'Example: Build a simple scheduling app for local dog walkers…' : quickTool === 'personnel' ? 'Example: I need an AI to research medical-device competitors and report findings…' : quickTool === 'manager-delegate' ? 'Example: Also compare supplier pricing and add a one-page recommendation to your task list…' : quickTool === 'assign-personnel' ? 'Example: Compare the three strongest competitors, summarize pricing, and report the risks to your manager…' : quickTool === 'auto-staff' ? 'Example: research competitors, compare pricing, and summarize the strongest opportunity…' : 'Example: make this critical, pause it, resume it, or stop it…'}
                    rows={3}
                    className="mt-3 w-full resize-none rounded-lg border border-white/10 bg-black/45 px-3 py-2 text-[10px] leading-relaxed text-white outline-none placeholder:text-slate-700 focus:border-cyan-400/40"
                  />
                  <button type="button" disabled={!quickPrompt.trim() || quickBusy || ((quickTool === 'assign-personnel' || quickTool === 'auto-staff' || quickTool === 'manager-delegate') && !quickProductId) || (quickTool === 'manager-delegate' && !quickWorkerId)} onClick={() => void runQuickFactoryCommand()} className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-lg border border-cyan-300/25 bg-cyan-400/10 px-3 py-2 text-[8px] font-black uppercase tracking-[.16em] text-cyan-100 disabled:opacity-35">
                    {quickBusy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Send className="h-3 w-3" />}
                    {quickTool === 'new-project' ? 'Create On Floor' : quickTool === 'personnel' ? 'Create AI Unit' : quickTool === 'manager-delegate' ? 'Delegate To Worker' : quickTool === 'assign-personnel' ? 'Assign Task' : quickTool === 'auto-staff' ? 'Find AI & Assign' : 'Apply Command'}
                  </button>
                </motion.div>
              ) : (
                <div className="pointer-events-none rounded-xl border border-cyan-400/20 bg-[#04090f]/92 px-3 py-2 shadow-2xl backdrop-blur-xl">
                  <p className="text-[7px] font-black uppercase tracking-[.22em] text-cyan-300/65">FACTORY COMMAND</p>
                  <p className="mt-1 text-[8px] text-slate-500">+ project · ✦ selected · ◉ AI unit</p>
                </div>
              )}
            </div>
          </Panel>

          {selectedEntity ? (
            <Panel position="top-right">
              <motion.div
                initial={{ opacity: 0, x: 16 }}
                animate={{ opacity: 1, x: 0 }}
                className="w-[300px] rounded-xl border border-cyan-400/20 bg-[#04090f]/95 p-4 shadow-2xl backdrop-blur-xl"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <p className="text-[8px] font-black uppercase tracking-[0.25em] text-cyan-300/70">
                      {selectedEntity.kind === 'product' || selectedEntity.role_class === 'package' ? 'PROJECT COMMAND' : 'SELECTED ENTITY'}
                    </p>

                    <h3 className="mt-1 text-sm font-semibold leading-snug text-white">
                      {selectedEntity.label}
                    </h3>
                  </div>

                  <button
                    type="button"
                    onClick={() =>
                      setSelectedEntity(null)
                    }
                    className="rounded border border-white/10 px-2 py-1 text-[8px] font-bold text-slate-500 hover:bg-white/5 hover:text-white"
                  >
                    CLOSE
                  </button>
                </div>

                <div className="mt-4 space-y-2 border-t border-white/10 pt-3 text-[9px]">
                  <div className="flex justify-between gap-4">
                    <span className="text-slate-600">
                      CLASS
                    </span>
                    <span className="font-semibold text-white">
                      {selectedEntity.kind === 'product'
                        ? 'PROJECT'
                        : 'AI UNIT'}
                    </span>
                  </div>

                  <div className="flex justify-between gap-4">
                    <span className="text-slate-600">
                      STATUS
                    </span>
                    <span className="font-semibold uppercase text-cyan-200">
                      {selectedEntity.product_state ||
                        selectedEntity.status}
                    </span>
                  </div>

                  {selectedEntity.assigned_agent ? (
                    <div className="flex justify-between gap-4">
                      <span className="text-slate-600">
                        ASSIGNED UNIT
                      </span>
                      <span className="text-amber-200">
                        {selectedEntity.assigned_agent}
                      </span>
                    </div>
                  ) : null}

                  {selectedEntity.provider &&
                  selectedEntity.provider !== 'factory' ? (
                    <div className="flex justify-between gap-4">
                      <span className="text-slate-600">
                        PROVIDER
                      </span>
                      <span className="truncate text-white">
                        {selectedEntity.provider}
                      </span>
                    </div>
                  ) : null}

                  {selectedEntity.model &&
                  selectedEntity.model !== 'product' ? (
                    <div className="flex justify-between gap-4">
                      <span className="text-slate-600">
                        MODEL
                      </span>
                      <span className="truncate text-white">
                        {selectedEntity.model}
                      </span>
                    </div>
                  ) : null}

                  {selectedEntity.product_id ? (
                    <div className="pt-2">
                      <p className="text-[7px] font-bold uppercase tracking-wider text-slate-700">
                        PRODUCT ID
                      </p>
                      <p className="mt-1 break-all font-mono text-[8px] text-slate-500">
                        {selectedEntity.product_id}
                      </p>
                    </div>
                  ) : null}

                  {selectedEntity.assignment_task_id ? (
                    <div className="rounded border border-emerald-400/20 bg-emerald-400/5 p-2">
                      <p className="text-[7px] font-bold uppercase tracking-wider text-emerald-300/70">Active assignment</p>
                      <p className="mt-1 leading-relaxed text-emerald-50">{selectedEntity.assignment_directive || selectedEntity.prompt_line}</p>
                      {selectedEntity.reports_to_label || selectedEntity.reports_to ? <p className="mt-1 text-[7px] uppercase tracking-wider text-slate-500">Reports to · {selectedEntity.reports_to_label || selectedEntity.reports_to}</p> : null}
                    </div>
                  ) : null}

                  {selectedEntity.role_class === 'worker' && (selectedEntity.task_queue || []).length ? (
                    <div className="rounded border border-amber-400/15 bg-amber-400/5 p-2">
                      <p className="text-[7px] font-black uppercase tracking-wider text-amber-200">Task queue · {selectedEntity.queued_task_count || selectedEntity.task_queue?.length || 0}</p>
                      {(selectedEntity.task_queue || []).slice(0, 6).map((task, index) => (
                        <div key={task.task_id || index} className="mt-1.5 border-t border-white/5 pt-1.5">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-[7px] font-bold uppercase tracking-wider text-slate-400">{index === 0 && String(task.status).toLowerCase() === 'running' ? 'Now' : `#${index + 1}`} · {String(task.status || 'pending')}</span>
                            {task.manager_delegated ? <span className="text-[6px] uppercase tracking-wider text-violet-300">manager delegated</span> : null}
                          </div>
                          <p className="mt-0.5 line-clamp-2 text-[8px] leading-relaxed text-white">{task.directive || task.product_title || 'Assigned work'}</p>
                          <p className="mt-0.5 text-[6px] uppercase tracking-wider text-slate-600">{task.delegated_by_label || task.reports_to_label || task.reports_to ? `From · ${task.delegated_by_label || task.reports_to_label || task.reports_to}` : ''}{task.product_title ? ` · ${task.product_title}` : ''}</p>
                        </div>
                      ))}
                    </div>
                  ) : null}

                  {selectedEntity.prompt_line ? (
                    <div className="pt-2">
                      <p className="text-[7px] font-bold uppercase tracking-wider text-slate-700">
                        CURRENT DIRECTIVE
                      </p>
                      <p className="mt-1 max-w-[260px] leading-relaxed text-slate-300">
                        {selectedEntity.prompt_line}
                      </p>
                    </div>
                  ) : null}

                  {selectedEntity.virtual_personnel ? (
                    <div className="mt-3 space-y-3 border-t border-cyan-300/15 pt-3">
                      <div className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-cyan-300" /><span className="text-[8px] font-black uppercase tracking-wider text-cyan-100">Division Supervisor</span></div>
                      <p className="text-[8px] leading-relaxed text-slate-400">This manager supervises routing and approval policy for the {selectedEntity.ecosystem || 'general'} ecosystem.</p>
                      <div className="rounded border border-violet-400/15 bg-violet-400/5 p-2">
                        <p className="text-[7px] font-black uppercase tracking-wider text-violet-200">Manager inbox · {selectedEntity.inbox_count || 0}</p>
                        {(selectedEntity.manager_inbox || []).slice(0, 4).map((item) => (
                          <div key={item.id} className="mt-1.5 border-t border-white/5 pt-1.5">
                            <p className="truncate text-[8px] font-semibold text-white">{item.title || item.kind}</p>
                            <p className="mt-0.5 line-clamp-2 text-[7px] leading-relaxed text-slate-500">{item.summary}</p>
                            <p className="mt-0.5 text-[6px] uppercase tracking-wider text-violet-300/70">{String(item.status || item.kind).replace(/_/g, ' ')}</p>
                          </div>
                        ))}
                      </div>
                      {selectedEntity.approval_rules?.length ? (
                        <div><p className="text-[7px] font-bold uppercase tracking-wider text-slate-600">Approval rules</p><div className="mt-1.5 flex flex-wrap gap-1">{selectedEntity.approval_rules.map((rule) => <span key={rule} className="rounded border border-cyan-400/15 bg-cyan-400/5 px-1.5 py-0.5 text-[6px] uppercase tracking-wider text-cyan-200">{rule.replace(/_/g, ' ')}</span>)}</div></div>
                      ) : null}
                    </div>
                  ) : null}

                  {selectedEntity.kind !== 'product' && selectedEntity.role_class !== 'package' && !selectedEntity.virtual_personnel ? (
                    <div className="mt-3 space-y-3 border-t border-emerald-300/15 pt-3">
                      <div className="flex flex-wrap gap-1.5">
                        <span className="rounded border border-emerald-400/15 bg-emerald-400/5 px-2 py-1 text-[7px] uppercase tracking-wider text-emerald-200">{selectedEntity.role_class || 'worker'}</span>
                        <span className="rounded border border-cyan-400/15 bg-cyan-400/5 px-2 py-1 text-[7px] uppercase tracking-wider text-cyan-200">{selectedEntity.division || 'general'}</span>
                        <span className="rounded border border-violet-400/15 bg-violet-400/5 px-2 py-1 text-[7px] uppercase tracking-wider text-violet-200">{selectedEntity.authority || 'local'}</span>
                      </div>
                      {selectedEntity.permissions?.length ? (
                        <div>
                          <p className="text-[7px] font-bold uppercase tracking-wider text-slate-600">Permissions</p>
                          <div className="mt-1.5 flex flex-wrap gap-1">
                            {selectedEntity.permissions.slice(0, 8).map((permission) => <span key={permission} className="rounded border border-white/10 bg-white/5 px-1.5 py-0.5 text-[6px] uppercase tracking-wider text-slate-400">{permission.replace(/_/g, ' ')}</span>)}
                          </div>
                        </div>
                      ) : null}
                      {selectedEntity.role_class === 'manager' ? (
                        <>
                          <div className="rounded border border-violet-400/15 bg-violet-400/5 p-2">
                            <p className="text-[7px] font-black uppercase tracking-wider text-violet-200">Manager inbox · {selectedEntity.inbox_count || 0}</p>
                            {(selectedEntity.manager_inbox || []).slice(0, 3).map((item) => <div key={item.id} className="mt-1.5 border-t border-white/5 pt-1.5"><p className="truncate text-[8px] text-white">{item.title || item.kind}</p><p className="line-clamp-2 text-[7px] text-slate-500">{item.summary}</p></div>)}
                          </div>
                          <div className="rounded border border-cyan-400/15 bg-cyan-400/5 p-2">
                            <p className="text-[7px] font-black uppercase tracking-wider text-cyan-200">Subordinates · {(selectedEntity.subordinate_ids || []).length}</p>
                            {(selectedEntity.subordinate_ids || []).length ? (
                              <div className="mt-1.5 flex flex-wrap gap-1">
                                {(selectedEntity.subordinate_ids || []).map((workerId) => {
                                  const worker = (floor?.nodes || []).find((node) => node.id === workerId);
                                  return <span key={workerId} className="rounded border border-cyan-400/15 bg-black/20 px-1.5 py-0.5 text-[6px] uppercase tracking-wider text-cyan-100">{worker?.label || workerId}</span>;
                                })}
                              </div>
                            ) : (
                              <p className="mt-1 text-[7px] leading-relaxed text-slate-500">No permanent subordinates yet. The first worker you delegate to becomes part of this manager&apos;s team.</p>
                            )}
                          </div>
                          <button
                            type="button"
                            disabled={actionBusy !== null}
                            onClick={() => {
                              const nodes = floor?.nodes || [];
                              const existing = nodes.find((node) => node.role_class === 'worker' && node.supervisor_id === selectedEntity.id);
                              const available = nodes.find((node) => node.role_class === 'worker' && !node.virtual_personnel && !node.supervisor_id);
                              setQuickWorkerId(existing?.id || available?.id || '');
                              setQuickProductId(String(nodes.find((node) => node.kind === 'product')?.product_id || ''));
                              setQuickPrompt('');
                              setQuickTool('manager-delegate');
                            }}
                            className="flex w-full items-center justify-center gap-1 rounded border border-violet-400/30 bg-violet-400/10 px-2 py-2 text-[8px] font-black uppercase tracking-wider text-violet-100 disabled:opacity-35"
                          >
                            <Send className="h-3 w-3" />Delegate New Task
                          </button>
                        </>
                      ) : null}
                      <button type="button" disabled={actionBusy !== null} onClick={() => { setQuickTool('assign-personnel'); setQuickPrompt(''); setQuickProductId(String((floor?.nodes || []).find((node) => node.kind === 'product')?.product_id || '')); }} className="flex w-full items-center justify-center gap-1 rounded border border-emerald-400/30 bg-emerald-400/10 px-2 py-2 text-[8px] font-black uppercase tracking-wider text-emerald-100 disabled:opacity-35"><Send className="h-3 w-3" />Assign Project Task</button>
                      <div className="grid grid-cols-2 gap-1.5">
                        {selectedEntity.role_class === 'manager' ? (
                          <button type="button" disabled={actionBusy !== null} onClick={() => void controlPersonnel(selectedEntity.id, { action: 'demote' })} className="rounded border border-amber-400/25 bg-amber-400/10 px-2 py-2 text-[8px] font-black uppercase tracking-wider text-amber-100 disabled:opacity-35">Demote</button>
                        ) : (
                          <button type="button" disabled={actionBusy !== null} onClick={() => void controlPersonnel(selectedEntity.id, { action: 'promote' })} className="flex items-center justify-center gap-1 rounded border border-violet-400/25 bg-violet-400/10 px-2 py-2 text-[8px] font-black uppercase tracking-wider text-violet-100 disabled:opacity-35"><UserCog className="h-3 w-3" />Promote</button>
                        )}
                        <button type="button" disabled={actionBusy !== null} onClick={() => { const division = window.prompt('Move this AI to which division?', selectedEntity.division || 'research'); if (division) void controlPersonnel(selectedEntity.id, { action: 'set_division', division }); }} className="rounded border border-cyan-400/25 bg-cyan-400/10 px-2 py-2 text-[8px] font-black uppercase tracking-wider text-cyan-100 disabled:opacity-35">Move Division</button>
                        <button type="button" disabled={actionBusy !== null} onClick={() => { const permission = window.prompt('Permission to grant (example: request_cross_division_support)'); if (permission) void controlPersonnel(selectedEntity.id, { action: 'grant_permission', permission }); }} className="rounded border border-emerald-400/25 bg-emerald-400/10 px-2 py-2 text-[8px] font-black uppercase tracking-wider text-emerald-100 disabled:opacity-35">Grant Permission</button>
                        <button type="button" disabled={actionBusy !== null} onClick={() => { const label = window.prompt('New display name', selectedEntity.label); if (label) void controlPersonnel(selectedEntity.id, { action: 'rename', label }); }} className="rounded border border-white/10 bg-white/5 px-2 py-2 text-[8px] font-black uppercase tracking-wider text-slate-200 disabled:opacity-35">Rename</button>
                      </div>
                      {selectedEntity.custom_personnel ? (
                        <button type="button" disabled={actionBusy !== null} onClick={() => { if (window.confirm('Retire this AI unit from the Factory Floor?')) void controlPersonnel(selectedEntity.id, { action: 'retire' }); }} className="w-full rounded border border-red-500/20 bg-red-500/5 px-2 py-2 text-[8px] font-black uppercase tracking-wider text-red-300 disabled:opacity-35">Retire AI Unit</button>
                      ) : null}
                    </div>
                  ) : null}

                  {selectedEntity.product_id && (selectedEntity.kind === 'product' || selectedEntity.role_class === 'package') ? (
                    <div className="mt-3 space-y-3 border-t border-amber-300/15 pt-3">
                      <div className="flex flex-wrap gap-1.5">
                        <span className="rounded border border-cyan-400/15 bg-cyan-400/5 px-2 py-1 text-[7px] uppercase tracking-wider text-cyan-200">Ecosystem · {selectedEntity.ecosystem || 'general'}</span>
                        <span className="rounded border border-violet-400/15 bg-violet-400/5 px-2 py-1 text-[7px] uppercase tracking-wider text-violet-200">Priority · {selectedEntity.factory_priority || 'normal'}</span>
                      </div>
                      <div className="rounded border border-indigo-400/15 bg-indigo-400/5 p-2.5">
                        <div className="flex items-center gap-1.5"><GitBranch className="h-3 w-3 text-indigo-300" /><p className="text-[7px] font-black uppercase tracking-[.14em] text-indigo-200">Automatic routing</p></div>
                        <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[7px] uppercase tracking-wider">
                          <span className="text-slate-600">Now</span><span className="text-slate-300">{(selectedEntity.current_stage || 'general').replace(/_/g, ' ')} · {(selectedEntity.current_owner || 'waiting').replace(/_/g, ' ')}</span>
                          <span className="text-slate-600">Next</span><span className="text-cyan-200">{(selectedEntity.next_stage || 'complete').replace(/_/g, ' ')} · {(selectedEntity.next_owner || 'complete').replace(/_/g, ' ')}</span>
                          <span className="text-slate-600">Status</span><span className="text-amber-200">{(selectedEntity.route_status || 'queued').replace(/_/g, ' ')}</span>
                          <span className="text-slate-600">Supervisor</span><span className="text-violet-200">{selectedEntity.ecosystem_manager_label || 'General Division Manager'}</span>
                        </div>
                        {selectedEntity.approval_rules?.length ? <p className="mt-2 text-[7px] leading-relaxed text-slate-500">Approval policy · {selectedEntity.approval_rules.map((x) => x.replace(/_/g, ' ')).join(' → ')}</p> : null}
                      </div>
                      <button type="button" disabled={replayLoading} onClick={() => void openProjectReplay(String(selectedEntity.product_id))} className="flex w-full items-center justify-center gap-1 rounded border border-sky-400/25 bg-sky-400/10 px-2 py-2 text-[8px] font-black uppercase tracking-wider text-sky-100 disabled:opacity-35">{replayLoading ? <Loader2 className="h-3 w-3 animate-spin" /> : <History className="h-3 w-3" />}History / Replay</button>
                      <button type="button" onClick={() => { setQuickTool('auto-staff'); setQuickPrompt(''); setQuickProductId(String(selectedEntity.product_id || '')); }} className="flex w-full items-center justify-center gap-1 rounded border border-emerald-400/25 bg-emerald-400/10 px-2 py-2 text-[8px] font-black uppercase tracking-wider text-emerald-100"><Sparkles className="h-3 w-3" />Auto Staff Task</button>
                      <div className="grid grid-cols-2 gap-1.5">
                        <button type="button" disabled={actionBusy !== null || String(selectedEntity.product_state || '').toUpperCase() === 'CANCELLED'} onClick={() => void controlProject(String(selectedEntity.product_id), selectedEntity.pipeline_paused ? 'resume' : 'pause')} className="flex items-center justify-center gap-1 rounded border border-cyan-400/25 bg-cyan-400/10 px-2 py-2 text-[8px] font-black uppercase tracking-wider text-cyan-100 disabled:opacity-35">
                          {selectedEntity.pipeline_paused ? <Play className="h-3 w-3" /> : <Pause className="h-3 w-3" />} {selectedEntity.pipeline_paused ? 'Resume' : 'Pause'}
                        </button>
                        <button type="button" disabled={actionBusy !== null} onClick={() => void controlProject(String(selectedEntity.product_id), 'set_priority', 'critical')} className="rounded border border-fuchsia-400/25 bg-fuchsia-400/10 px-2 py-2 text-[8px] font-black uppercase tracking-wider text-fuchsia-100 disabled:opacity-35">Critical</button>
                        <button type="button" disabled={actionBusy !== null} onClick={() => void controlProject(String(selectedEntity.product_id), 'set_priority', 'high')} className="rounded border border-amber-400/25 bg-amber-400/10 px-2 py-2 text-[8px] font-black uppercase tracking-wider text-amber-100 disabled:opacity-35">High Priority</button>
                        <button type="button" disabled={actionBusy !== null} onClick={() => void controlProject(String(selectedEntity.product_id), 'set_priority', 'normal')} className="rounded border border-white/10 bg-white/5 px-2 py-2 text-[8px] font-black uppercase tracking-wider text-slate-200 disabled:opacity-35">Normal</button>
                      </div>
                      {confirmTerminateId === selectedEntity.product_id ? (
                        <div className="rounded border border-red-500/30 bg-red-950/30 p-2">
                          <p className="text-[8px] leading-relaxed text-red-100">Stop all work on this project? Its history and files will be preserved for backtracking.</p>
                          <div className="mt-2 flex gap-1.5">
                            <button type="button" disabled={actionBusy !== null} onClick={() => void controlProject(String(selectedEntity.product_id), 'terminate')} className="flex items-center gap-1 rounded border border-red-400/40 bg-red-500/15 px-2 py-1.5 text-[8px] font-black uppercase text-red-100"><Skull className="h-3 w-3" />Confirm stop</button>
                            <button type="button" onClick={() => setConfirmTerminateId(null)} className="rounded border border-white/10 px-2 py-1.5 text-[8px] font-bold text-slate-300">Cancel</button>
                          </div>
                        </div>
                      ) : (
                        <button type="button" disabled={actionBusy !== null || String(selectedEntity.product_state || '').toUpperCase() === 'CANCELLED'} onClick={() => setConfirmTerminateId(String(selectedEntity.product_id))} className="flex w-full items-center justify-center gap-1 rounded border border-red-500/20 bg-red-500/5 px-2 py-2 text-[8px] font-black uppercase tracking-wider text-red-300 disabled:opacity-35"><Skull className="h-3 w-3" />Stop project</button>
                      )}
                    </div>
                  ) : null}
                </div>
              </motion.div>
            </Panel>
          ) : null}


          {selectedEdge ? (
            <Panel position="top-right">
              <motion.div initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} className="w-[320px] rounded-xl border border-cyan-300/30 bg-[#03080e]/96 p-4 shadow-2xl backdrop-blur-xl">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-[8px] font-black uppercase tracking-[.23em] text-cyan-300/70">DATA ROUTE</p>
                    <h3 className="mt-1 text-sm font-semibold text-white">{String((selectedEdge.data as any)?.source_label || selectedEdge.source)} → {String((selectedEdge.data as any)?.target_label || selectedEdge.target)}</h3>
                  </div>
                  <button type="button" onClick={() => setSelectedEdge(null)} className="rounded border border-white/10 px-2 py-1 text-[8px] font-bold text-slate-400">CLOSE</button>
                </div>
                <div className="mt-3 space-y-2 border-t border-white/10 pt-3 text-[9px]">
                  <div className="flex justify-between gap-4"><span className="text-slate-600">CHANNEL</span><span className="font-semibold text-cyan-200">{String((selectedEdge.data as any)?.signalType || 'DATA')}</span></div>
                  <div className="flex justify-between gap-4"><span className="text-slate-600">ACTIVITY</span><span className={(selectedEdge.data as any)?.active ? 'font-semibold text-emerald-300' : 'text-slate-400'}>{(selectedEdge.data as any)?.active ? 'LIVE / FLASHING' : 'STANDBY'}</span></div>
                  <div className="flex justify-between gap-4"><span className="text-slate-600">SOURCE</span><span className="font-semibold text-sky-200">{String((selectedEdge.data as any)?.movement_source || 'task state').replace(/_/g, ' ')}</span></div>
                  {(selectedEdge.data as any)?.event_type ? <div className="flex justify-between gap-4"><span className="text-slate-600">EVENT</span><span className="font-semibold text-violet-200">{String((selectedEdge.data as any)?.event_type).replace(/_/g, ' ')}</span></div> : null}
                  <div className="flex justify-between gap-4"><span className="text-slate-600">STRAND</span><span className="font-semibold text-slate-300">{String((selectedEdge.data as any)?.appearance?.style || 'signal').replace(/_/g, ' ')}</span></div>
                  {(selectedEdge.data as any)?.product_label ? <div className="pt-1"><p className="text-[7px] font-bold uppercase tracking-wider text-slate-600">Package</p><p className="mt-1 leading-relaxed text-amber-100">{String((selectedEdge.data as any)?.product_label)}</p></div> : null}
                  <div className="pt-1"><p className="text-[7px] font-bold uppercase tracking-wider text-slate-600">What is moving</p><p className="mt-1 leading-relaxed text-slate-300">{String((selectedEdge.data as any)?.data_summary || 'Factory workflow data between these stations.')}</p></div>
                  {((selectedEdge.data as any)?.origin_chain || []).length ? (
                    <div className="pt-1">
                      <p className="text-[7px] font-bold uppercase tracking-wider text-slate-600">Carried history</p>
                      <p className="mt-1 leading-relaxed text-slate-400">{((selectedEdge.data as any)?.origin_chain || []).map((v: string) => v.replace(/_/g, ' ')).join(' → ')}</p>
                    </div>
                  ) : null}
                  {(selectedEdge.data as any)?.report_task_id ? (
                    <div className="rounded border border-emerald-400/20 bg-emerald-400/5 p-2.5">
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-[7px] font-black uppercase tracking-[.16em] text-emerald-300/75">Manager report-back</p>
                        <span className="text-[7px] font-bold uppercase tracking-wider text-emerald-100">{String((selectedEdge.data as any)?.report_status || 'awaiting manager').replace(/_/g, ' ')}</span>
                      </div>
                      {(selectedEdge.data as any)?.assignment_directive ? <div className="mt-2"><p className="text-[7px] font-bold uppercase tracking-wider text-slate-600">Assignment</p><p className="mt-1 leading-relaxed text-slate-300">{String((selectedEdge.data as any)?.assignment_directive)}</p></div> : null}
                      {(selectedEdge.data as any)?.report_result_summary ? <div className="mt-2"><p className="text-[7px] font-bold uppercase tracking-wider text-slate-600">Returned result</p><p className="mt-1 max-h-28 overflow-auto whitespace-pre-wrap leading-relaxed text-emerald-50">{String((selectedEdge.data as any)?.report_result_summary)}</p></div> : null}
                      {(selectedEdge.data as any)?.manager_feedback ? <div className="mt-2"><p className="text-[7px] font-bold uppercase tracking-wider text-slate-600">Manager note</p><p className="mt-1 leading-relaxed text-amber-100">{String((selectedEdge.data as any)?.manager_feedback)}</p></div> : null}
                      <div className="mt-3 grid grid-cols-2 gap-1.5">
                        <button type="button" disabled={actionBusy !== null} onClick={() => void reviewAssignmentReport(String((selectedEdge.data as any)?.report_task_id), 'accept')} className="rounded border border-emerald-400/30 bg-emerald-400/10 px-2 py-2 text-[8px] font-black uppercase tracking-wider text-emerald-100 disabled:opacity-35">Accept</button>
                        <button type="button" disabled={actionBusy !== null} onClick={() => void reviewAssignmentReport(String((selectedEdge.data as any)?.report_task_id), 'incorporate')} className="rounded border border-cyan-400/30 bg-cyan-400/10 px-2 py-2 text-[8px] font-black uppercase tracking-wider text-cyan-100 disabled:opacity-35">Incorporate</button>
                        <button type="button" disabled={actionBusy !== null} onClick={() => void reviewAssignmentReport(String((selectedEdge.data as any)?.report_task_id), 'send_back')} className="rounded border border-amber-400/30 bg-amber-400/10 px-2 py-2 text-[8px] font-black uppercase tracking-wider text-amber-100 disabled:opacity-35">Send Back</button>
                        <button type="button" disabled={actionBusy !== null} onClick={() => void reviewAssignmentReport(String((selectedEdge.data as any)?.report_task_id), 'escalate')} className="rounded border border-violet-400/30 bg-violet-400/10 px-2 py-2 text-[8px] font-black uppercase tracking-wider text-violet-100 disabled:opacity-35">Escalate</button>
                      </div>
                    </div>
                  ) : null}

                  {(selectedEdge.data as any)?.last_approved_agent ? (
                    <div className="rounded border border-violet-400/15 bg-violet-400/5 p-2">
                      <p className="text-[7px] font-bold uppercase tracking-wider text-violet-300/70">Last approval / handoff</p>
                      <p className="mt-1 text-[10px] font-semibold text-violet-100">{String((selectedEdge.data as any)?.last_approved_label || (selectedEdge.data as any)?.last_approved_agent)}</p>
                      <button type="button" onClick={() => {
                        const id = String((selectedEdge.data as any)?.last_approved_agent || '');
                        const target = (floor?.nodes || []).find((node) => node.id === id);
                        if (target) { setSelectedEntity(target); setSelectedEdge(null); }
                        else toast.error('That approval unit is not currently on the floor');
                      }} className="mt-2 flex w-full items-center justify-center gap-1 rounded border border-violet-300/25 bg-violet-400/10 px-2 py-1.5 text-[8px] font-black uppercase tracking-wider text-violet-100"><ArrowLeftCircle className="h-3 w-3" />Trace to last approval</button>
                    </div>
                  ) : null}
                  {(selectedEdge.data as any)?.product_id ? (
                    <button type="button" onClick={() => {
                      const pid = String((selectedEdge.data as any)?.product_id || '');
                      const target = (floor?.nodes || []).find((node) => node.kind === 'product' && node.product_id === pid);
                      if (target) { setSelectedEntity(target); setSelectedEdge(null); }
                    }} className="w-full rounded border border-amber-300/20 bg-amber-400/10 px-2 py-1.5 text-[8px] font-black uppercase tracking-wider text-amber-100">Open package controls</button>
                  ) : null}
                </div>
              </motion.div>
            </Panel>
          ) : null}

          {replayData ? (
            <Panel position="bottom-right">
              <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="mb-20 mr-3 w-[430px] max-w-[72vw] rounded-xl border border-sky-300/25 bg-[#03080e]/97 p-4 shadow-2xl backdrop-blur-xl">
                <div className="flex items-start justify-between gap-3">
                  <div><p className="text-[8px] font-black uppercase tracking-[.22em] text-sky-300/70">PROJECT HISTORY / REPLAY</p><h3 className="mt-1 max-w-[330px] truncate text-sm font-semibold text-white">{replayData.product_title || replayData.product_id}</h3></div>
                  <button type="button" onClick={() => setReplayData(null)} className="rounded border border-white/10 px-2 py-1 text-[8px] font-bold text-slate-400">CLOSE</button>
                </div>
                {(replayData.frames || []).length ? (() => {
                  const frames = replayData.frames || [];
                  const frame = frames[Math.min(replayIndex, frames.length - 1)] || {};
                  return <div className="mt-3 space-y-3">
                    <input type="range" min={0} max={Math.max(0, frames.length - 1)} value={Math.min(replayIndex, Math.max(0, frames.length - 1))} onChange={(e) => setReplayIndex(Number(e.target.value))} className="w-full" />
                    <div className="flex justify-between text-[7px] uppercase tracking-wider text-slate-500"><span>Start</span><span>Step {replayIndex + 1} / {frames.length}</span><span>Current</span></div>
                    <div className="rounded-lg border border-white/10 bg-black/35 p-3">
                      <div className="flex items-center justify-between gap-3"><span className="text-[10px] font-semibold text-sky-100">{String(frame.agent_type || 'stage').replace(/_/g, ' ')}</span><span className="text-[7px] font-bold uppercase tracking-wider text-emerald-300">{frame.status}</span></div>
                      <div className="mt-2 grid grid-cols-2 gap-2 text-[8px]"><div><p className="text-[7px] uppercase tracking-wider text-slate-600">State</p><p className="mt-1 text-slate-300">{String(frame.state_before || '—').replace(/_/g, ' ')}</p></div><div><p className="text-[7px] uppercase tracking-wider text-slate-600">Duration</p><p className="mt-1 text-slate-300">{frame.duration_sec == null ? '—' : `${frame.duration_sec}s`}</p></div></div>
                      {frame.input_preview ? <div className="mt-2"><p className="text-[7px] uppercase tracking-wider text-slate-600">Received</p><p className="mt-1 max-h-20 overflow-auto whitespace-pre-wrap text-[8px] leading-relaxed text-slate-400">{frame.input_preview}</p></div> : null}
                      {frame.output_preview ? <div className="mt-2"><p className="text-[7px] uppercase tracking-wider text-slate-600">Produced</p><p className="mt-1 max-h-24 overflow-auto whitespace-pre-wrap text-[8px] leading-relaxed text-sky-100">{frame.output_preview}</p></div> : null}
                      {frame.error ? <p className="mt-2 text-[8px] text-red-300">{frame.error}</p> : null}
                    </div>
                    <div className="flex gap-1.5"><button type="button" onClick={() => setReplayIndex((i) => Math.max(0, i - 1))} className="flex-1 rounded border border-white/10 bg-white/5 px-2 py-1.5 text-[8px] font-bold text-slate-200">Previous</button><button type="button" onClick={() => setReplayIndex((i) => Math.min(frames.length - 1, i + 1))} className="flex-1 rounded border border-sky-300/20 bg-sky-400/10 px-2 py-1.5 text-[8px] font-bold text-sky-100">Next</button></div>
                  </div>;
                })() : <p className="mt-3 text-[9px] text-slate-500">No recorded project stages yet.</p>}
              </motion.div>
            </Panel>
          ) : null}

          <Panel position="bottom-left">
            <div className="pointer-events-none mb-7 ml-7 flex items-center gap-3 rounded-md border border-white/10 bg-[#02070c]/82 px-2.5 py-1.5 text-[7px] font-bold uppercase tracking-[.13em] text-slate-400 backdrop-blur-md">
              <span className="flex items-center gap-1"><i className="h-[2px] w-5 bg-cyan-400 shadow-[0_0_6px_rgba(34,211,238,.7)]" />Data</span>
              <span className="flex items-center gap-1"><i className="h-[2px] w-5 bg-violet-400 shadow-[0_0_6px_rgba(167,139,250,.7)]" />Command</span>
              <span className="flex items-center gap-1"><i className="h-[2px] w-5 bg-amber-400 shadow-[0_0_6px_rgba(245,158,11,.7)]" />Production</span>
              <span className="flex items-center gap-1"><i className="h-[2px] w-5 bg-green-500 shadow-[0_0_6px_rgba(34,197,94,.7)]" />Funding</span>
              <span className="flex items-center gap-1"><i className="h-[2px] w-5 bg-red-500 shadow-[0_0_6px_rgba(239,68,68,.7)]" />Alert</span>
            </div>
          </Panel>

          <Background
            color="#183044"
            gap={32}
            size={1}
          />

          <MiniMap
            nodeColor={(node) => {
              if (node.type === 'product') {
                return '#f59e0b';
              }

              if (node.type === 'zone') {
                return '#111827';
              }

              return (
                STATUS_COLOR[
                  (node.data as FactoryFloorNode)?.status
                ] || '#475569'
              );
            }}
            maskColor="rgba(2,6,23,.80)"
            style={{
              width: 108,
              height: 74,
              right: 10,
              bottom: 10,
              background: '#050a10',
              border: '1px solid rgba(34,211,238,.18)',
              borderRadius: 6,
              boxShadow: '0 6px 18px rgba(0,0,0,.35)',
            }}
          />

          <Controls
            style={{
              transform: 'scale(.62)',
              transformOrigin: 'bottom left',
              left: 8,
              bottom: 8,
            }}
          />
        </ReactFlow>
        </GlassCard>
      )}

      {floor?.empire_architecture ? (
        <div className="grid gap-3 xl:grid-cols-[1.35fr_.85fr]">
          <GlassCard className="border-cyan-500/20 p-3">
            <div className="mb-3 flex items-center gap-2">
              <UserCog className="h-4 w-4 text-cyan-300" />
              <div>
                <p className="text-xs font-semibold uppercase tracking-[.14em] text-cyan-100">Empire Organization</p>
                <p className="text-[8px] uppercase tracking-wider text-slate-500">
                  Owner → Ultron → Factory Manager → {floor.empire_architecture.department_count || 15} department managers → {floor.empire_architecture.research_agent_count || 75} research agents
                </p>
              </div>
              <span className="ml-auto rounded border border-violet-400/20 bg-violet-400/10 px-2 py-1 text-[7px] font-black uppercase tracking-wider text-violet-200">Ultron independent audit</span>
            </div>
            <div className="grid gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
              {(floor.empire_architecture.departments || []).map((department) => (
                <div key={department.slug} className="rounded-md border border-white/8 bg-black/25 p-2">
                  <p className="truncate text-[9px] font-bold text-white">{department.label}</p>
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {(floor.empire_architecture?.research_lenses || []).map((lens) => (
                      <span key={lens.slug} title={lens.mission || lens.label} className="rounded border border-cyan-400/12 bg-cyan-400/5 px-1 py-0.5 text-[6px] uppercase tracking-wider text-cyan-200/75">{lens.label}</span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </GlassCard>

          <GlassCard className="border-green-500/20 p-3">
            <div className="mb-3 flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-green-400 shadow-[0_0_12px_rgba(74,222,128,.9)]" />
              <div>
                <p className="text-xs font-semibold uppercase tracking-[.14em] text-green-100">Funding Utility · Separate System</p>
                <p className="text-[8px] uppercase tracking-wider text-slate-500">Factory AI authority · {floor.funding_utility?.ai_financial_authority || 'request only'}</p>
              </div>
              {(floor.funding_utility?.owner_approval_count || 0) > 0 ? <span className="ml-auto rounded border border-amber-400/25 bg-amber-400/10 px-2 py-1 text-[7px] font-black text-amber-200">{floor.funding_utility?.owner_approval_count} OWNER DECISION</span> : null}
            </div>
            <div className="grid grid-cols-3 gap-1.5">
              <div className="rounded border border-white/8 bg-black/25 p-2"><p className="text-[6px] uppercase tracking-wider text-slate-600">Requests</p><p className="mt-1 text-sm font-black text-white">{floor.funding_utility?.request_count || 0}</p></div>
              <div className="rounded border border-white/8 bg-black/25 p-2"><p className="text-[6px] uppercase tracking-wider text-slate-600">Budgets</p><p className="mt-1 text-sm font-black text-cyan-200">{(floor.funding_utility?.preapproved_budgets || []).filter((b) => b.active).length}</p></div>
              <div className="rounded border border-white/8 bg-black/25 p-2"><p className="text-[6px] uppercase tracking-wider text-slate-600">Funding leads</p><p className="mt-1 text-sm font-black text-violet-200">{floor.funding_utility?.funding_opportunities?.length || 0}</p></div>
            </div>
            <button type="button" disabled={actionBusy !== null} onClick={() => void createFundingBudget()} className="mt-2 w-full rounded border border-cyan-400/20 bg-cyan-400/8 px-2 py-1.5 text-[7px] font-black uppercase tracking-wider text-cyan-100 disabled:opacity-40">Create owner preapproved budget</button>

            {(floor.funding_utility?.verification_requests || []).length ? (
              <div className="mt-3 space-y-1.5">
                <p className="text-[7px] font-black uppercase tracking-[.16em] text-amber-200">Funding verifier queue</p>
                {(floor.funding_utility?.verification_requests || []).slice(0, 4).map((request) => (
                  <div key={request.id} className="rounded border border-amber-400/15 bg-amber-400/5 p-2">
                    <div className="flex items-center gap-2"><p className="min-w-0 flex-1 truncate text-[8px] text-white">{request.purpose || request.department || request.id}</p><span className="text-[8px] font-black text-amber-200">${Number(request.amount_usd || 0).toLocaleString()}</span></div>
                    <div className="mt-1.5 flex gap-1">
                      <button type="button" disabled={actionBusy !== null} onClick={() => void verifyFundingRequest(request.id, true)} className="rounded border border-emerald-400/25 bg-emerald-400/10 px-2 py-1 text-[6px] font-black uppercase text-emerald-200">Verify</button>
                      <button type="button" disabled={actionBusy !== null} onClick={() => void verifyFundingRequest(request.id, false)} className="rounded border border-red-400/20 bg-red-400/8 px-2 py-1 text-[6px] font-black uppercase text-red-200">Reject</button>
                    </div>
                  </div>
                ))}
              </div>
            ) : null}

            {(floor.funding_utility?.owner_approval_requests || []).length ? (
              <div className="mt-3 space-y-1.5">
                <p className="text-[7px] font-black uppercase tracking-[.16em] text-violet-200">Owner decision queue</p>
                {(floor.funding_utility?.owner_approval_requests || []).slice(0, 4).map((request) => (
                  <div key={request.id} className="rounded border border-violet-400/15 bg-violet-400/5 p-2">
                    <div className="flex items-center gap-2"><p className="min-w-0 flex-1 truncate text-[8px] text-white">{request.purpose || request.department || request.id}</p><span className="text-[8px] font-black text-violet-200">${Number(request.amount_usd || 0).toLocaleString()}</span></div>
                    {Number(request.amount_usd || 0) >= 5000 ? <p className="mt-1 text-[6px] uppercase tracking-wider text-amber-300">Owner locked · full decision card required</p> : null}
                    <div className="mt-1.5 flex gap-1">
                      <button type="button" disabled={actionBusy !== null} onClick={() => void decideFundingRequest(request, true)} className="rounded border border-emerald-400/25 bg-emerald-400/10 px-2 py-1 text-[6px] font-black uppercase text-emerald-200">Approve</button>
                      <button type="button" disabled={actionBusy !== null} onClick={() => void decideFundingRequest(request, false)} className="rounded border border-red-400/20 bg-red-400/8 px-2 py-1 text-[6px] font-black uppercase text-red-200">Reject</button>
                    </div>
                  </div>
                ))}
              </div>
            ) : null}

            {(floor.funding_utility?.funding_opportunities || []).length ? (
              <div className="mt-3 space-y-1.5">
                <p className="text-[7px] font-black uppercase tracking-[.16em] text-cyan-200">Funding opportunity lifecycle</p>
                {(floor.funding_utility?.funding_opportunities || []).slice(0, 4).map((opportunity) => (
                  <div key={opportunity.id} className="rounded border border-cyan-400/15 bg-cyan-400/5 p-2">
                    <div className="flex items-center gap-2"><p className="min-w-0 flex-1 truncate text-[8px] text-white">{opportunity.title || opportunity.id}</p><span className="rounded border border-white/10 px-1 py-0.5 text-[6px] uppercase text-slate-400">{String(opportunity.status || 'found').replace(/_/g, ' ')}</span></div>
                    {!['received', 'rejected'].includes(String(opportunity.status || '')) ? <button type="button" disabled={actionBusy !== null} onClick={() => void advanceFundingOpportunity(opportunity)} className="mt-1.5 rounded border border-cyan-400/20 bg-cyan-400/8 px-2 py-1 text-[6px] font-black uppercase text-cyan-100">Advance next stage</button> : null}
                  </div>
                ))}
              </div>
            ) : null}

            <div className="mt-3">
              <p className="text-[7px] font-black uppercase tracking-[.18em] text-green-300/80">Verified capital routing tube</p>
              {(floor.funding_utility?.capital_routes || []).length ? (
                <div className="mt-1.5 space-y-1.5">
                  {(floor.funding_utility?.capital_routes || []).slice(0, 4).map((route, index) => (
                    <div key={route.id || index} className="rounded border border-green-400/20 bg-green-400/5 p-2 shadow-[inset_0_0_18px_rgba(34,197,94,.04)]">
                      <div className="flex items-center gap-1.5 text-[7px] font-bold uppercase tracking-wider text-green-100">
                        <span className="truncate">{route.source || 'verified source'}</span><span className="h-[2px] flex-1 bg-green-400 shadow-[0_0_8px_rgba(74,222,128,.9)]" /><span className="truncate">{route.destination || 'factory'}</span><span className="ml-1 text-green-300">${Number(route.amount_usd || 0).toLocaleString()}</span>
                      </div>
                      {(route.restrictions || []).length ? <p className="mt-1 truncate text-[6px] text-slate-500">Restrictions · {(route.restrictions || []).join(' · ')}</p> : null}
                    </div>
                  ))}
                </div>
              ) : <p className="mt-1.5 text-[8px] text-slate-600">No authorized capital is moving. The tube only lights after verification/owner authorization.</p>}
            </div>
          </GlassCard>
        </div>
      ) : null}

      {(floor?.alerts?.length || 0) > 0 ? (
        <GlassCard className="border-amber-500/25 p-3">
          <div className="mb-2 flex items-center gap-2">
            <ShieldAlert className="h-4 w-4 text-amber-300" />
            <p className="text-xs font-semibold uppercase tracking-[.14em] text-amber-200">Command Center · Decisions & Exceptions</p>
            <span className="ml-auto rounded border border-amber-400/20 bg-amber-400/10 px-2 py-0.5 text-[9px] font-bold text-amber-200">{floor?.alerts?.length || 0} OPEN</span>
          </div>
          <div className="grid gap-2 md:grid-cols-2">
            {(floor?.alerts || []).slice(0, 6).map((alert) => (
              <div key={alert.id} className={`rounded-md border p-2.5 ${alert.severity === 'stop' ? 'border-red-500/30 bg-red-950/20' : 'border-amber-500/25 bg-amber-950/15'}`}>
                <div className="flex items-start gap-2">
                  {alert.severity === 'stop' ? <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-red-400" /> : <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />}
                  <div className="min-w-0">
                    <p className="truncate text-[10px] font-bold text-white">{alert.package_label || alert.origin_agent || 'Factory alert'}</p>
                    <p className="mt-1 text-[8px] uppercase tracking-wider text-slate-500">Origin · {alert.origin_division || 'general'}{alert.origin_agent ? ` / ${alert.origin_agent}` : ''}</p>
                    <p className="mt-1 text-[9px] text-slate-300">{String(alert.action_type || 'review').replace(/_/g, ' ')} · {String(alert.next_required_action || 'review').replace(/_/g, ' ')}</p>
                    {alert.recommended_action ? <p className="mt-1 text-[8px] leading-relaxed text-amber-100/75">{alert.recommended_action}</p> : null}
                    {(alert.approvals_completed?.length || 0) > 0 ? (
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {(alert.approvals_completed || []).slice(-4).map((step) => (
                          <span key={step} className="rounded border border-cyan-400/15 bg-cyan-400/5 px-1.5 py-0.5 text-[6px] font-bold uppercase tracking-wider text-cyan-200/70">✓ {step}</span>
                        ))}
                      </div>
                    ) : null}
                    <p className="mt-1 line-clamp-2 text-[8px] leading-relaxed text-slate-500">{alert.objective || 'Awaiting system action'}</p>
                    {alert.product_id && alert.action_type === 'human_review' ? (
                      <div className="mt-2 space-y-2">
                        <div className="flex flex-wrap gap-1.5">
                          <button
                            type="button"
                            disabled={actionBusy !== null}
                            onClick={() => void resolveHumanReview(alert.id, String(alert.product_id), 'approve')}
                            className="rounded border border-emerald-400/30 bg-emerald-400/10 px-2 py-1 text-[8px] font-black uppercase tracking-wider text-emerald-200 disabled:opacity-40"
                          >
                            {actionBusy === `${alert.id}:approve` ? 'Approving…' : 'Approve'}
                          </button>
                          <button
                            type="button"
                            disabled={actionBusy !== null}
                            onClick={() => setExpandedAlert((current) => current === alert.id ? null : alert.id)}
                            className="rounded border border-amber-400/25 bg-amber-400/10 px-2 py-1 text-[8px] font-black uppercase tracking-wider text-amber-200 disabled:opacity-40"
                          >
                            Send back
                          </button>
                        </div>
                        {expandedAlert === alert.id ? (
                          <div className="space-y-1.5">
                            <textarea
                              value={alertNotes[alert.id] || ''}
                              onChange={(event) => setAlertNotes((prev) => ({ ...prev, [alert.id]: event.target.value }))}
                              rows={2}
                              placeholder="What needs to change before this can proceed?"
                              className="w-full rounded border border-amber-400/20 bg-black/45 px-2 py-1.5 text-[9px] text-white outline-none placeholder:text-slate-600 focus:border-amber-300/50"
                            />
                            <button
                              type="button"
                              disabled={actionBusy !== null}
                              onClick={() => void resolveHumanReview(alert.id, String(alert.product_id), 'reject')}
                              className="rounded border border-red-400/25 bg-red-400/10 px-2 py-1 text-[8px] font-black uppercase tracking-wider text-red-200 disabled:opacity-40"
                            >
                              {actionBusy === `${alert.id}:reject` ? 'Routing…' : 'Confirm rework'}
                            </button>
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                    {alert.product_id && alert.action_type === 'resume_project' ? (
                      <button type="button" disabled={actionBusy !== null} onClick={() => void controlProject(String(alert.product_id), 'resume')} className="mt-2 rounded border border-emerald-400/30 bg-emerald-400/10 px-2 py-1 text-[8px] font-black uppercase tracking-wider text-emerald-200 disabled:opacity-40">Resume Project</button>
                    ) : null}
                    {alert.product_id && (alert.action_type === 'stale_task' || alert.action_type === 'blocked_task' || alert.action_type === 'rework_loop' || alert.action_type === 'routing_review') ? (
                      <button type="button" disabled={actionBusy !== null} onClick={() => void controlProject(String(alert.product_id), 'set_priority', 'critical')} className="mt-2 rounded border border-fuchsia-400/30 bg-fuchsia-400/10 px-2 py-1 text-[8px] font-black uppercase tracking-wider text-fuchsia-200 disabled:opacity-40">Make Critical</button>
                    ) : null}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </GlassCard>
      ) : null}

      {(floor?.open_circuits?.length || 0) > 0 ? (
        <p className="text-xs text-rose-400">
          Circuit open: {floor?.open_circuits?.join(', ')}
        </p>
      ) : null}

      {(floor?.ai_market?.events?.length || 0) > 0 ? (
        <GlassCard className="p-3 border-cyan-500/25">
          <p className="text-xs font-medium text-cyan-200 mb-2">
            AI Market (external agents) · ${Number(floor?.ai_market?.total_usd_1h ?? 0).toFixed(2)} recent
          </p>
          <ul className="space-y-1 max-h-32 overflow-y-auto text-[10px] text-slate-400 font-mono">
            {(floor?.ai_market?.events || []).slice(0, 8).map((ev, idx) => (
              <li key={`${ev.time}-${idx}`}>
                {ev.capability_id || ev.type} → ${Number(ev.price_usd ?? 0).toFixed(2)}
                {ev.latency_ms != null ? ` · ${ev.latency_ms}ms` : ''}
              </li>
            ))}
          </ul>
        </GlassCard>
      ) : null}
    </div>
  );
}
