import axios, { AxiosInstance } from 'axios';
import type {
  ExperimentConfigIn,
  ExperimentRecord,
  RunResult,
  EvaluationReport,
  ExperimentStatistics,
  ConditionSummary,
} from '../types';

const client: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

// ── Helpers ───────────────────────────────────────────

/** Parse the config_json string stored in DB into a typed object. */
function parseConfig(row: any): {
  conditions: string[];
  runs_per_condition: number;
  max_rounds: number;
  temperature: number;
  max_tokens: number;
  side_payment_enabled: boolean;
} {
  try {
    const cfg = typeof row.config_json === 'string' ? JSON.parse(row.config_json) : row;
    return {
      conditions: cfg.conditions || [],
      runs_per_condition: cfg.runs_per_condition || 10,
      max_rounds: cfg.max_rounds || 8,
      temperature: cfg.temperature ?? 0.7,
      max_tokens: cfg.max_tokens || 2048,
      side_payment_enabled: cfg.side_payment_enabled ?? true,
    };
  } catch {
    return {
      conditions: [], runs_per_condition: 10, max_rounds: 8,
      temperature: 0.7, max_tokens: 2048, side_payment_enabled: true,
    };
  }
}

/** Map a DB row to frontend ExperimentRecord. */
function toExperimentRecord(row: any): ExperimentRecord {
  const cfg = parseConfig(row);
  return {
    id: row.id || row.experiment_id,
    name: row.name,
    status: row.status,
    conditions: cfg.conditions,
    runs_per_condition: cfg.runs_per_condition,
    max_rounds: cfg.max_rounds,
    temperature: cfg.temperature,
    max_tokens: cfg.max_tokens,
    side_payment_enabled: cfg.side_payment_enabled,
    total_runs: row.total_runs ?? (cfg.conditions.length * cfg.runs_per_condition),
    completed_runs: row.completed_runs ?? 0,
    created_at: row.created_at || '',
    updated_at: row.updated_at || '',
  };
}

// ── 实验管理 ──────────────────────────────────────────

export async function createExperiment(
  data: ExperimentConfigIn,
): Promise<ExperimentRecord> {
  const res = await client.post<any>('/experiments', data);
  // POST returns ExperimentStatus shape → map to ExperimentRecord
  const d = res.data;
  const conditions = Object.keys(d.conditions_progress || {});
  const cp = conditions.length > 0 ? d.conditions_progress[conditions[0]] : null;
  return {
    id: d.experiment_id,
    name: data.name,
    status: d.status,
    conditions,
    runs_per_condition: cp?.total ?? data.runs_per_condition,
    max_rounds: data.max_rounds,
    temperature: data.temperature,
    max_tokens: data.max_tokens,
    side_payment_enabled: data.side_payment_enabled,
    total_runs: d.total_runs,
    completed_runs: d.completed_runs ?? 0,
    created_at: d.updated_at || d.created_at || '',
    updated_at: d.updated_at || '',
  };
}

export async function listExperiments(): Promise<ExperimentRecord[]> {
  const res = await client.get<any[]>('/experiments');
  return (res.data || []).map(toExperimentRecord);
}

export async function getExperiment(id: string): Promise<ExperimentRecord> {
  const res = await client.get<any>(`/experiments/${id}`);
  return toExperimentRecord(res.data);
}

export async function startExperiment(id: string): Promise<ExperimentRecord> {
  const res = await client.post<any>(`/experiments/${id}/start`);
  const d = res.data;
  return { id: d.experiment_id || id, name: '', status: 'running', conditions: [],
    runs_per_condition: 0, max_rounds: 0, temperature: 0, max_tokens: 0,
    side_payment_enabled: false, total_runs: 0, completed_runs: 0,
    created_at: '', updated_at: '' };
}

export async function pauseExperiment(id: string): Promise<ExperimentRecord> {
  const res = await client.post<any>(`/experiments/${id}/pause`);
  return { ...toExperimentRecord({ id, ...res.data }) };
}

export async function resumeExperiment(id: string): Promise<ExperimentRecord> {
  const res = await client.post<any>(`/experiments/${id}/resume`);
  return { ...toExperimentRecord({ id, ...res.data }) };
}

export async function deleteExperiment(id: string): Promise<void> {
  await client.delete(`/experiments/${id}`);
}

// ── 运行数据 ──────────────────────────────────────────

export async function listRuns(
  experimentId: string,
  conditionCode?: string,
): Promise<RunResult[]> {
  const params = conditionCode ? { condition_code: conditionCode } : {};
  const res = await client.get<any[]>(`/experiments/${experimentId}/runs`, { params });
  return (res.data || []).map((r: any) => ({
    id: r.id,
    experiment_id: r.experiment_id || experimentId,
    condition_code: r.condition_code,
    run_index: r.run_index,
    status: r.status,
    rounds: [],
    total_rounds: r.rounds_completed,
    agreement_reached: !!r.agreement_reached,
    gini_coefficient: r.agreement_gini,
    side_payment_used: r.side_payment_used > 0,
    side_payment_total: r.side_payment_used,
    duration_ms: (r.total_duration_seconds || 0) * 1000,
    mediator_type: '',
    bias_level: '',
  }));
}

export async function getRunDetail(
  experimentId: string, runId: string,
): Promise<RunResult> {
  const res = await client.get<any>(`/experiments/${experimentId}/runs/${runId}`);
  const r = res.data;
  return {
    id: r.id, experiment_id: r.experiment_id || experimentId,
    condition_code: r.condition_code, run_index: r.run_index, status: r.status,
    rounds: [], total_rounds: r.rounds_completed,
    agreement_reached: !!r.agreement_reached,
    gini_coefficient: r.agreement_gini,
    side_payment_used: r.side_payment_used > 0,
    side_payment_total: r.side_payment_used,
    duration_ms: (r.total_duration_seconds || 0) * 1000,
    mediator_type: '', bias_level: '',
  };
}

export async function getRunTranscript(
  experimentId: string, runId: string,
): Promise<any[]> {
  const res = await client.get<any[]>(`/experiments/${experimentId}/runs/${runId}/transcript`);
  return res.data || [];
}

// ── 评估 ──────────────────────────────────────────────

export async function listEvaluations(
  experimentId: string,
): Promise<EvaluationReport[]> {
  const res = await client.get<any[]>(`/experiments/${experimentId}/evaluations`);
  return (res.data || []).map((e: any, idx: number) => {
    const dims = typeof e.dimensions_json === 'string'
      ? JSON.parse(e.dimensions_json) : (e.dimensions || []);
    return {
      id: e.id || `eval-${idx}`,
      experiment_id: e.experiment_id || experimentId,
      batch_label: `${e.condition_code || '全局'} #${e.batch_start}-${e.batch_end}`,
      overall_score: (e.overall_score || 0) / 10,
      dimensions: dims.map((d: any) => ({
        name: d.name, score: d.score, weight: 1, description: '',
      })),
      run_count: (e.batch_end || 0) - (e.batch_start || 0),
      summary: '', created_at: e.created_at,
    };
  });
}

export async function triggerEvaluation(
  experimentId: string,
): Promise<EvaluationReport> {
  const res = await client.post<any>(`/experiments/${experimentId}/evaluations/trigger`);
  const e = res.data;
  const dims = e.dimensions || [];
  return {
    id: e.id || 'eval-trigger', experiment_id: e.experiment_id || experimentId,
    batch_label: '手动触发', overall_score: (e.overall_score || 0) / 10,
    dimensions: dims.map((d: any) => ({
      name: d.name, score: d.score, weight: 1, description: '',
    })),
    run_count: 0, summary: '', created_at: e.created_at || new Date().toISOString(),
  };
}

// ── 统计 ──────────────────────────────────────────────

export async function getStatistics(
  experimentId: string,
): Promise<ExperimentStatistics> {
  const res = await client.get<any[]>(`/experiments/${experimentId}/statistics`);
  const items = res.data || [];
  // Also fetch condition summary — needed by MonitorPage / ResultsPage / AnalysisPage
  const summaries = await getConditionSummary(experimentId).catch(() => [] as ConditionSummary[]);
  return {
    experiment_id: experimentId, n_total: 0, overall_agreement_rate: 0,
    hypotheses: items.map((h: any) => ({
      hypothesis_id: h.hypothesis, hypothesis_label: h.hypothesis,
      test_name: h.test_name, statistic: h.test_statistic,
      p_value: h.p_value, significant: !!h.significant,
      alpha: 0.05, effect_size: h.effect_size, effect_size_label: '',
      ci_lower: (h.confidence_interval && h.confidence_interval[0]) || 0,
      ci_upper: (h.confidence_interval && h.confidence_interval[1]) || 0,
      interpretation: h.interpretation,
    })),
    condition_summaries: summaries,
    computed_at: new Date().toISOString(),
  };
}

export async function runStatistics(
  experimentId: string,
): Promise<ExperimentStatistics> {
  const res = await client.post<any[]>(`/experiments/${experimentId}/statistics/run`);
  const items = res.data || [];
  const summaries = await getConditionSummary(experimentId).catch(() => [] as ConditionSummary[]);
  return {
    experiment_id: experimentId, n_total: 0, overall_agreement_rate: 0,
    hypotheses: items.map((h: any) => ({
      hypothesis_id: h.hypothesis, hypothesis_label: h.hypothesis,
      test_name: h.test_name, statistic: h.test_statistic,
      p_value: h.p_value, significant: !!h.significant,
      alpha: 0.05, effect_size: h.effect_size, effect_size_label: '',
      ci_lower: (h.confidence_interval && h.confidence_interval[0]) || 0,
      ci_upper: (h.confidence_interval && h.confidence_interval[1]) || 0,
      interpretation: h.interpretation,
    })),
    condition_summaries: summaries,
    computed_at: new Date().toISOString(),
  };
}

export async function getConditionSummary(
  experimentId: string,
): Promise<ConditionSummary[]> {
  const res = await client.get<any[]>(`/experiments/${experimentId}/summary`);
  return (res.data || []).map((s: any) => ({
    condition_code: s.condition_code,
    total: s.total || 0,
    running: s.running || 0,
    completed: s.completed || 0,
    failed: s.failed || 0,
    agreements: s.agreements || 0,
    agreement_rate: s.total ? (s.agreements || 0) / (s.completed || 1) : 0,
    mean_gini: s.mean_gini || 0,
    mean_rounds: s.mean_rounds || 0,
    mean_side_payment: s.mean_payment || 0,
  }));
}

export default client;
