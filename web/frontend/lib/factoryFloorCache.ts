/**
 * Factory Floor snapshot — instant paint from dashboard cache, then lazy live refresh.
 */

import {
  createEmptyDashboardData,
  readAdminMetricsCache,
  writeAdminMetricsCache,
} from '@/lib/adminMetricsCache';

export type FactoryFloorNode = {
  id: string;
  kind?: 'agent' | 'product';
  label: string;
  status: string;
  prompt_line?: string;
  provider?: string;
  model?: string;
  latency_ms?: number | null;
  cost_usd?: number;
  product_id?: string | null;
  product_state?: string | null;
  current_task_id?: string | null;
  assigned_agent?: string | null;
  circuit_tripped?: boolean;
  role_class?: 'worker' | 'manager' | 'overseer' | 'package';
  division?: string;
  authority?: string;
  package_state?: string;
  package_progress?: number;
  next_destination?: string;
  pipeline_paused?: boolean;
  factory_priority?: 'normal' | 'high' | 'critical' | 'low' | string;
  ecosystem?: string;
  last_agent?: string | null;
  completed_agents?: string[];
  completed_states?: string[];
  permissions?: string[];
  capability?: string;
  custom_personnel?: boolean;
  virtual_personnel?: boolean;
  ecosystem_label?: string;
  ecosystem_accent?: string;
  ecosystem_manager_id?: string;
  ecosystem_manager_label?: string;
  approval_rules?: string[];
  routing_mode?: string;
  route_status?: string;
  current_stage?: string;
  current_owner?: string | null;
  next_stage?: string | null;
  next_owner?: string | null;
  next_state?: string | null;
  waiting_on?: string | null;
  crossing_division?: boolean;
  inbox_count?: number;
  manager_inbox?: Array<{ id: string; kind: string; manager_id?: string; product_id?: string | null; task_id?: string | null; worker_id?: string | null; title?: string; summary?: string; status?: string; actions?: string[]; severity?: string; created_at?: number | null }>;
  assignment_task_id?: string | null;
  reports_to?: string | null;
  reports_to_label?: string | null;
  assignment_directive?: string | null;
  supervisor_id?: string | null;
  supervisor_label?: string | null;
  subordinate_ids?: string[];
  queued_task_count?: number;
  task_queue?: Array<{
    task_id?: string | null;
    product_id?: string | null;
    product_title?: string | null;
    directive?: string | null;
    status?: string | null;
    priority?: number | null;
    reports_to?: string | null;
    reports_to_label?: string | null;
    manager_delegated?: boolean;
    delegated_by?: string | null;
    delegated_by_label?: string | null;
    created_at?: number | null;
  }>;
};

export type AiMarketFloorEvent = {
  type?: string;
  product_id?: string;
  capability_id?: string;
  price_usd?: number;
  latency_ms?: number;
  success?: boolean;
  time?: number;
};

export type FactoryFloorPayload = {
  nodes?: FactoryFloorNode[];
  edges?: Array<{
    from: string;
    to: string;
    kind?: string;
    signal_kind?: string;
    product_id?: string | null;
    product_label?: string | null;
    product_state?: string | null;
    source_label?: string;
    target_label?: string;
    last_approved_agent?: string | null;
    last_approved_label?: string | null;
    data_summary?: string;
    request_id?: string;
    original_agent?: string | null;
    origin_chain?: string[];
    completed_states?: string[];
    active?: boolean;
    status?: string;
    created_at?: number | null;
    appearance?: { style?: string; color?: string; accent?: string };
    assignment_directive?: string | null;
    reports_to?: string | null;
    report_task_id?: string | null;
    report_status?: string | null;
    report_result_summary?: string | null;
    manager_feedback?: string | null;
    route_status?: string | null;
    current_stage?: string | null;
    next_stage?: string | null;
    next_owner?: string | null;
    ecosystem?: string | null;
    manager_id?: string | null;
    movement_source?: string | null;
    event_id?: string | null;
    event_type?: string | null;
    event_time?: number | null;
  }>;
  hot_edges?: Array<{ from: string; to: string; pulse_id?: string }>;
  running_count?: number;
  open_circuits?: string[];
  alerts?: Array<{
    id: string;
    severity: 'warning' | 'stop' | string;
    origin_division?: string;
    origin_agent?: string | null;
    product_id?: string | null;
    package_label?: string | null;
    approvals_completed?: string[];
    next_required_action?: string;
    objective?: string;
    action_type?: string;
    recommended_action?: string;
    manager_id?: string;
    ecosystem?: string;
    age_seconds?: number;
    retry_count?: number;
  }>;
  updated_at?: number;
  ai_market?: { events?: AiMarketFloorEvent[]; total_usd_1h?: number };
  ecosystems?: Array<{ id: string; label: string; accent: string; manager_label: string; approval_rules: string[]; description: string }>;
  manager_inboxes?: Record<string, Array<{ id: string; kind: string; manager_id?: string; product_id?: string | null; task_id?: string | null; worker_id?: string | null; title?: string; summary?: string; status?: string; actions?: string[]; severity?: string; created_at?: number | null }>>;
  recent_events?: Array<{ id?: string; type?: string; time?: number; product_id?: string | null; source?: string | null; target?: string | null; task_id?: string | null; status?: string | null; ecosystem?: string | null; manager_id?: string | null; summary?: string }>;
  empire_architecture?: {
    department_count?: number;
    research_agents_per_department?: number;
    research_agent_count?: number;
    ultron_id?: string;
    factory_manager_id?: string;
    departments?: Array<{ slug: string; label: string }>;
    research_lenses?: Array<{ slug: string; label: string; mission?: string }>;
    funding_utility?: {
      separate_from_factory?: boolean;
      ai_authority?: string;
      roles?: Array<{ id: string; label: string; mission?: string }>;
    };
  };
  funding_utility?: {
    request_count?: number;
    owner_approval_count?: number;
    verification_required_count?: number;
    status_counts?: Record<string, number>;
    owner_approval_requests?: Array<{ id: string; amount_usd?: number; department?: string; product_id?: string | null; purpose?: string; band?: string; status?: string }>;
    verification_requests?: Array<{ id: string; amount_usd?: number; department?: string; product_id?: string | null; purpose?: string; band?: string; status?: string }>;
    capital_routes?: Array<{ id?: string; request_id?: string; source?: string; destination?: string; amount_usd?: number; status?: string; restrictions?: string[] }>;
    preapproved_budgets?: Array<{ id: string; department?: string | null; product_id?: string | null; ceiling_usd?: number; used_usd?: number; active?: boolean }>;
    funding_opportunities?: Array<{ id: string; title?: string; status?: string; opportunity_type?: string; amount_estimate_usd?: number | null }>;
    opportunity_status_counts?: Record<string, number>;
    opportunity_lifecycle?: string[];
    ai_financial_authority?: string;
  };
};

function isFactoryFloorPayload(x: unknown): x is FactoryFloorPayload {
  if (!x || typeof x !== 'object') return false;
  const nodes = (x as FactoryFloorPayload).nodes;
  return Array.isArray(nodes) && nodes.length > 0;
}

export function readFactoryFloorCache(): FactoryFloorPayload | null {
  const fromDash = readAdminMetricsCache()?.factory_floor;
  if (isFactoryFloorPayload(fromDash)) return fromDash;
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem('aicom_factory_floor_v1');
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { data?: unknown };
    return isFactoryFloorPayload(parsed.data) ? parsed.data : null;
  } catch {
    return null;
  }
}

export function writeFactoryFloorCache(floor: FactoryFloorPayload): void {
  if (!isFactoryFloorPayload(floor)) return;
  try {
    localStorage.setItem(
      'aicom_factory_floor_v1',
      JSON.stringify({ ts: Date.now(), data: floor }),
    );
  } catch {
    /* quota */
  }
  const prev = readAdminMetricsCache() ?? createEmptyDashboardData();
  writeAdminMetricsCache({ ...prev, factory_floor: floor });
}
