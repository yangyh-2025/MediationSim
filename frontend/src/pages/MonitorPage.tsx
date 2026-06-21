import React, { useState, useMemo } from 'react';
import {
  Card, Select, Progress, Row, Col, Statistic, Table, Tag, Typography,
  Empty, Spin, Badge, Tooltip,
} from 'antd';
import {
  CheckCircleOutlined, CloseCircleOutlined, LoadingOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import {
  getExperiment, listEvaluations, listRuns,
  getStatistics, listExperiments,
} from '../api/client';
import { ALL_CONDITIONS } from '../types';
import type { ExperimentRecord, ConditionSummary, RunResult } from '../types';
import dayjs from 'dayjs';

const { Title, Text } = Typography;

// ── Helpers ───────────────────────────────────────────

const CONDITION_LABEL: Record<string, string> = Object.fromEntries(
  ALL_CONDITIONS.map((c) => [c.code, c.label]),
);

const CONDITION_COLOR: Record<string, string> = {
  'H-PS': '#ff4d4f', 'H-N': '#fa8c16', 'H-PW': '#faad14',
  'L-PS': '#1677ff', 'L-N': '#13c2c2', 'L-PW': '#52c41a',
  CD: '#722ed1',
};

// ── Component ─────────────────────────────────────────

const MonitorPage: React.FC = () => {
  const [selectedId, setSelectedId] = useState<string | undefined>(undefined);

  const { data: experiments } = useQuery({
    queryKey: ['experiments'],
    queryFn: listExperiments,
    refetchInterval: 3000,
  });

  const activeExperiments = useMemo(
    () => (experiments || []).filter((e) =>
      ['draft','running','completed','failed'].includes(e.status)),
    [experiments],
  );

  // Main experiment detail
  const { data: experiment, isLoading: expLoading } = useQuery({
    queryKey: ['experiment', selectedId],
    queryFn: () => getExperiment(selectedId!),
    enabled: !!selectedId,
  });

  // Condition summary for aggregate numbers
  const { data: statistics } = useQuery({
    queryKey: ['statistics', selectedId],
    queryFn: () => getStatistics(selectedId!),
    enabled: !!selectedId,
    refetchInterval: 2000,
  });

  // Live runs — the key real-time data
  const { data: runs } = useQuery<RunResult[]>({
    queryKey: ['runs', selectedId],
    queryFn: () => listRuns(selectedId!),
    enabled: !!selectedId,
    refetchInterval: 1500,
  });

  if (!activeExperiments.length) {
    return <Empty description="暂无运行中或已完成的实验" style={{ marginTop: 80 }} />;
  }

  const progressPct = experiment
    ? Math.round((experiment.completed_runs / Math.max(experiment.total_runs, 1)) * 100)
    : 0;

  // ── Build per-condition stats from live runs ──
  interface CondStats {
    total: number;
    running: number;
    completed: number;
    failed: number;
    agreements: number;
    maxRound: number;
  }
  const condStatsMap: Record<string, CondStats> = {};

  // Condition order
  const conditionCodes = experiment?.conditions.length
    ? experiment.conditions
    : Object.keys(CONDITION_LABEL);

  for (const code of conditionCodes) {
    condStatsMap[code] = { total: 0, running: 0, completed: 0, failed: 0, agreements: 0, maxRound: 0 };
  }

  if (runs) {
    for (const r of runs) {
      const s = condStatsMap[r.condition_code];
      if (!s) continue;
      s.total++;
      if (r.status === 'running') { s.running++; s.maxRound = Math.max(s.maxRound, r.total_rounds); }
      else if (r.status === 'completed') { s.completed++; if (r.agreement_reached) s.agreements++; }
      else if (r.status === 'failed') s.failed++;
    }
  }

  // ── Summary condition data ──
  const summaryMap: Record<string, ConditionSummary> = {};
  if (statistics?.condition_summaries) {
    for (const cs of statistics.condition_summaries) {
      summaryMap[cs.condition_code] = cs;
    }
  }

  // ── Runs table columns ──
  const runColumns = [
    { title: '#', dataIndex: 'run_index', key: 'idx', width: 45 },
    {
      title: '条件', dataIndex: 'condition_code', key: 'code', width: 70,
      render: (c: string) => <Tag color={CONDITION_COLOR[c] || 'default'}>{c}</Tag>,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 80,
      render: (s: string) => {
        if (s === 'running') return <Badge status="processing" text="运行中" />;
        if (s === 'completed') return <Badge status="success" text="完成" />;
        if (s === 'failed') return <Badge status="error" text="失败" />;
        return <Badge status="default" text={s} />;
      },
    },
    {
      title: '轮次', dataIndex: 'total_rounds', key: 'rounds', width: 60,
      render: (v: number, r: RunResult) => (
        <span>{v}{r.status === 'running' ? <LoadingOutlined style={{marginLeft:4,fontSize:11}} /> : ''}</span>
      ),
    },
    {
      title: '协议', dataIndex: 'agreement_reached', key: 'agree', width: 60,
      render: (v: boolean, r: RunResult) =>
        r.status !== 'completed' ? <Text type="secondary">—</Text>
        : v ? <Tag color="success" style={{margin:0}}>达成</Tag>
        : <Tag color="error" style={{margin:0}}>未达成</Tag>,
    },
    {
      title: '耗时', dataIndex: 'duration_ms', key: 'dur', width: 80,
      render: (v: number) => v ? `${(v/1000).toFixed(1)}s` : '—',
    },
  ];

  return (
    <div>
      {/* ── Selector ── */}
      <Card size="small" style={{ marginBottom: 12 }}>
        <Row gutter={16} align="middle">
          <Col><Text strong>实验：</Text></Col>
          <Col flex="auto">
            <Select style={{ width: 420 }} placeholder="选择要监控的实验" value={selectedId}
              onChange={setSelectedId}
              options={activeExperiments.map((e) => ({
                value: e.id,
                label: `${e.name} [${e.status}] ${e.completed_runs}/${e.total_runs}`,
              }))} />
          </Col>
          <Col>
            <Text type="secondary">自动刷新 1.5s</Text>
          </Col>
        </Row>
      </Card>

      {!selectedId ? (
        <Empty description="请选择一个实验" style={{ marginTop: 60 }} />
      ) : expLoading ? (
        <Spin style={{ display: 'block', margin: '60px auto' }} />
      ) : experiment ? (
        <>
          {/* ── Overall progress bar ── */}
          <Card size="small" style={{ marginBottom: 12 }}>
            <Row gutter={16} align="middle">
              <Col flex="auto">
                <Progress percent={progressPct}
                  status={experiment.status === 'completed' ? 'success'
                    : experiment.status === 'failed' ? 'exception' : 'active'}
                  format={() => `${experiment.completed_runs} / ${experiment.total_runs}`} />
              </Col>
              <Col>
                <Tag color={experiment.status === 'running' ? 'processing'
                  : experiment.status === 'completed' ? 'success'
                  : experiment.status === 'failed' ? 'error'
                  : 'default'}>
                  {experiment.status === 'draft' ? '草稿'
                    : experiment.status === 'running' ? '运行中'
                    : experiment.status === 'completed' ? '已完成'
                    : experiment.status === 'failed' ? '失败' : experiment.status}
                </Tag>
              </Col>
            </Row>
          </Card>

          {/* ── Per-condition cards ── */}
          <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
            {conditionCodes.map((code) => {
              const cs = condStatsMap[code];
              const sm = summaryMap[code];
              const condCfg = ALL_CONDITIONS.find((c) => c.code === code);
              const activeCount = cs.completed + cs.running + cs.failed;
              const runTotal = experiment.runs_per_condition;
              return (
                <Col xs={12} sm={8} md={6} lg={Math.ceil(24/conditionCodes.length)} key={code}>
                  <Card size="small"
                    title={<span>{code}<Text type="secondary" style={{fontSize:11,marginLeft:4}}>{CONDITION_LABEL[code]}</Text></span>}
                    style={{ borderTop: `3px solid ${CONDITION_COLOR[code] || '#d9d9d9'}` }}>
                    <Row gutter={8}>
                      <Col span={8}>
                        <Statistic title="状态" value={activeCount} suffix={`/${runTotal}`}
                          valueStyle={{fontSize:16}} />
                      </Col>
                      <Col span={5}>
                        <Statistic title={<Badge status="processing" text="运行" />} value={cs.running} valueStyle={{fontSize:14,color:'#1677ff'}} />
                      </Col>
                      <Col span={5}>
                        <Statistic title={<Badge status="success" text="完成" />} value={cs.completed} valueStyle={{fontSize:14,color:'#52c41a'}} />
                      </Col>
                      <Col span={6}>
                        <Statistic title={<Badge status="error" text="失败" />} value={cs.failed} valueStyle={{fontSize:14,color:'#ff4d4f'}} />
                      </Col>
                    </Row>
                    {cs.running > 0 && (
                      <Row style={{ marginTop: 6 }}>
                        <Col span={24}>
                          <Text type="secondary" style={{ fontSize: 11 }}>
                            <LoadingOutlined spin /> 进行中: 当前最高第 {cs.maxRound} 轮
                          </Text>
                        </Col>
                      </Row>
                    )}
                  </Card>
                </Col>
              );
            })}
          </Row>

          {/* ── Live runs table ── */}
          <Card size="small" title={
            <span>实时运行记录<Text type="secondary" style={{fontSize:12,marginLeft:8}}>自动刷新 1.5s</Text></span>
          }>
            <Table dataSource={runs || []} columns={runColumns} rowKey="id"
              size="small" pagination={{ pageSize: 20, showSizeChanger: false }}
              locale={{ emptyText: '暂无运行记录' }}
              sortDirections={['descend','ascend']}
              rowClassName={(r: RunResult) =>
                r.status === 'running' ? 'ant-table-row-running' : ''} />
          </Card>
        </>
      ) : (
        <Empty description="未找到实验数据" style={{ marginTop: 60 }} />
      )}
    </div>
  );
};

export default MonitorPage;
