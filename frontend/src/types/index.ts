// ============================================================
// 偏见调停多智能体模拟系统 - TypeScript 类型定义
// ============================================================

// ---- API 通用响应 ----
export interface APIResponse<T = unknown> {
  code: number;
  message: string;
  data: T;
}

// ---- 实验配置 ----
export interface ExperimentCondition {
  code: string;
  label: string;
  bias_level: 'high' | 'low';
  mediator_type: 'pro_strong' | 'neutral' | 'pro_weak';
}

export const ALL_CONDITIONS: ExperimentCondition[] = [
  { code: 'H-PS', label: '高不对称+亲强', bias_level: 'high', mediator_type: 'pro_strong' },
  { code: 'H-N', label: '高不对称+中立', bias_level: 'high', mediator_type: 'neutral' },
  { code: 'H-PW', label: '高不对称+亲弱', bias_level: 'high', mediator_type: 'pro_weak' },
  { code: 'L-PS', label: '低不对称+亲强', bias_level: 'low', mediator_type: 'pro_strong' },
  { code: 'L-N', label: '低不对称+中立', bias_level: 'low', mediator_type: 'neutral' },
  { code: 'L-PW', label: '低不对称+亲弱', bias_level: 'low', mediator_type: 'pro_weak' },
  { code: 'CD', label: '戴维营参照组', bias_level: 'low', mediator_type: 'neutral' },
];

export interface ExperimentConfigIn {
  name: string;
  conditions: string[];
  runs_per_condition: number;
  max_rounds: number;
  temperature: number;
  max_tokens: number;
  side_payment_enabled: boolean;
}

export type ExperimentStatus = 'draft' | 'running' | 'paused' | 'completed' | 'failed';

export interface ExperimentRecord {
  id: string;
  name: string;
  status: ExperimentStatus;
  conditions: string[];
  runs_per_condition: number;
  max_rounds: number;
  temperature: number;
  max_tokens: number;
  side_payment_enabled: boolean;
  total_runs: number;
  completed_runs: number;
  created_at: string;
  updated_at: string;
}

// ---- 条件进度 ----
export interface ConditionProgress {
  condition_code: string;
  total: number;
  completed: number;
  agreement_rate: number;
  avg_rounds: number;
  status: string;
}

// ---- 运行结果 ----
export interface Proposal {
  round: number;
  content: string;
  from_party: string;
  to_party: string;
  side_payment_amount: number; // 运行结果中的侧支付金额（仅适用时）
}

export interface AgentResponse {
  round: number;
  agent_name: string;
  accept: boolean;
  reasoning: string;
}

export interface DomesticScore {
  round: number;
  agent_name: string;
  score: number;
  dimension: string;
}

export interface RoundRecord {
  round: number;
  proposal: Proposal;
  responses: AgentResponse[];
  domestic_scores: DomesticScore[];
  side_payment_made?: boolean;
  side_payment_amount?: number;
  agreement_reached: boolean;
  round_duration_ms: number;
}

export interface RunResult {
  id: string;
  experiment_id: string;
  condition_code: string;
  run_index: number;
  status: 'pending' | 'running' | 'completed' | 'failed';
  rounds: RoundRecord[];
  total_rounds: number;
  agreement_reached: boolean;
  gini_coefficient: number;
  side_payment_used: boolean;
  side_payment_total: number;
  duration_ms: number;
  mediator_type: string;
  bias_level: string;
  error_message?: string;
}

// ---- 评估 ----
export interface EvaluationDimension {
  name: string;
  score: number;
  weight: number;
  description: string;
}

export interface EvaluationReport {
  id: string;
  experiment_id: string;
  batch_label: string;
  overall_score: number;
  dimensions: EvaluationDimension[];
  run_count: number;
  summary: string;
  created_at: string;
}

// ---- 假设检验 ----
export interface HypothesisResult {
  hypothesis_id: string;
  hypothesis_label: string;
  test_name: string;
  statistic: number;
  p_value: number;
  significant: boolean;
  alpha: number;
  effect_size: number;
  effect_size_label: string;
  ci_lower: number;
  ci_upper: number;
  interpretation: string;
  details?: Record<string, unknown>;
}

// ---- 统计汇总 ----
export interface ConditionSummary {
  condition_code: string;
  total: number;
  running: number;
  completed: number;
  failed: number;
  agreements: number;
  agreement_rate: number;
  mean_gini: number;
  mean_rounds: number;
  mean_side_payment: number;
}

export interface ExperimentStatistics {
  experiment_id: string;
  n_total: number;
  overall_agreement_rate: number;
  hypotheses: HypothesisResult[];
  condition_summaries: ConditionSummary[];
  computed_at?: string;
}

// ---- 生存分析 ----
export interface KMFSurvivalData {
  condition_code: string;
  label: string;
  time_points: number[];
  survival_prob: number[];
  ci_lower: number[];
  ci_upper: number[];
}

export interface SurvivalAnalysisResult {
  kmf_data: KMFSurvivalData[];
  log_rank_test: {
    test_name: string;
    statistic: number;
    p_value: number;
    significant: boolean;
    interpretation: string;
  };
  cox_model?: {
    variables: { name: string; coefficient: number; hazard_ratio: number; p_value: number }[];
    concordance: number;
  };
}

// ---- 中介效应 ----
export interface MediationPath {
  path: string;
  coefficient: number;
  p_value: number;
  ci_lower: number;
  ci_upper: number;
}

export interface MediationAnalysisResult {
  paths: MediationPath[];
  bootstrap_samples: number;
  indirect_effect: number;
  indirect_effect_ci: [number, number];
  indirect_effect_p: number;
  proportion_mediated: number;
  total_effect: number;
  direct_effect: number;
  comparison: {
    with_side_payment_agreement_rate: number;
    without_side_payment_agreement_rate: number;
    difference: number;
  };
}

// ---- API 函数参数类型 ----
export interface CreateExperimentParams {
  name: string;
  conditions: string[];
  runs_per_condition: number;
  max_rounds: number;
  temperature: number;
  max_tokens: number;
  side_payment_enabled: boolean;
}
