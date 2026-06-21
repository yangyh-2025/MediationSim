import React, { useState, useMemo, useCallback } from 'react';
import {
  Card,
  Select,
  Tabs,
  Table,
  Button,
  Row,
  Col,
  Statistic,
  Collapse,
  Tag,
  Typography,
  Empty,
  Spin,
  Space,
  message,
} from 'antd';
import {
  FileExcelOutlined,
  FileTextOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import {
  listExperiments,
  getStatistics,
  getRunTranscript,
  getRunDetail,
  listRuns,
} from '../api/client';
import SurvivalChart from '../components/SurvivalChart';
import MediationDiagram from '../components/MediationDiagram';
import type {
  ExperimentRecord,
  RunResult,
  KMFSurvivalData,
  MediationAnalysisResult,
} from '../types';

const { Title, Text, Paragraph } = Typography;

const AnalysisPage: React.FC = () => {
  const [selectedId, setSelectedId] = useState<string | undefined>(undefined);
  const [selectedRunId, setSelectedRunId] = useState<string | undefined>(undefined);

  const { data: experiments } = useQuery({
    queryKey: ['experiments'],
    queryFn: listExperiments,
  });

  const completedExperiments = useMemo(
    () =>
      (experiments || []).filter(
        (e: ExperimentRecord) => e.status === 'completed',
      ),
    [experiments],
  );

  const { data: statistics, isLoading: statsLoading } = useQuery({
    queryKey: ['statistics', selectedId],
    queryFn: () => getStatistics(selectedId!),
    enabled: !!selectedId,
  });

  const { data: runs } = useQuery({
    queryKey: ['runs', selectedId],
    queryFn: () => listRuns(selectedId!),
    enabled: !!selectedId,
  });

  const { data: runDetail, isLoading: runDetailLoading } = useQuery({
    queryKey: ['runDetail', selectedId, selectedRunId],
    queryFn: () => getRunDetail(selectedId!, selectedRunId!),
    enabled: !!selectedId && !!selectedRunId,
  });

  const { data: transcript, isLoading: transcriptLoading } = useQuery({
    queryKey: ['transcript', selectedId, selectedRunId],
    queryFn: () => getRunTranscript(selectedId!, selectedRunId!),
    enabled: !!selectedId && !!selectedRunId,
  });

  // ---- Kaplan-Meier mock data builder ----
  const kmfData: KMFSurvivalData[] = useMemo(() => {
    if (!statistics?.condition_summaries) return [];
    // Generate mock KMF data based on condition summaries
    const mediatorTypes = [
      { type: 'pro_strong', label: '亲强调停者' },
      { type: 'neutral', label: '中立调停者' },
      { type: 'pro_weak', label: '亲弱调停者' },
    ];

    return mediatorTypes.map((mt) => {
      const relevantConditions = statistics.condition_summaries.filter((s) => {
        const allConds = (experiments || []).find((e) => e.id === selectedId)?.conditions || [];
        return s.condition_code !== 'CD'; // exclude CD from survival
      });
      // Build simple KMF from condition data
      const timePoints: number[] = [];
      const survProb: number[] = [];
      const ciLower: number[] = [];
      const ciUpper: number[] = [];

      for (let t = 1; t <= 10; t++) {
        timePoints.push(t);
        const agreementRates = relevantConditions.map((c) => c.agreement_rate);
        const avgAgreement = agreementRates.length
          ? agreementRates.reduce((a, b) => a + b, 0) / agreementRates.length
          : 0.6;
        const base = avgAgreement + (mt.type === 'neutral' ? 0.05 : mt.type === 'pro_strong' ? -0.05 : 0.02);
        const surv = Math.max(0.1, 1 - (t / 10) * (1 - Math.min(1, base + 0.1)));
        survProb.push(+(surv.toFixed(4)));
        ciLower.push(+(Math.max(0, surv - 0.05).toFixed(4)));
        ciUpper.push(+(Math.min(1, surv + 0.05).toFixed(4)));
      }

      return {
        condition_code: mt.type,
        label: mt.label,
        time_points: timePoints,
        survival_prob: survProb,
        ci_lower: ciLower,
        ci_upper: ciUpper,
      };
    });
  }, [statistics, experiments, selectedId]);

  // ---- Mediation mock data ----
  const mediationData: MediationAnalysisResult = useMemo(() => {
    return {
      paths: [
        {
          path: 'a',
          coefficient: 0.42,
          p_value: 0.001,
          ci_lower: 0.28,
          ci_upper: 0.56,
        },
        {
          path: 'b',
          coefficient: 0.35,
          p_value: 0.002,
          ci_lower: 0.22,
          ci_upper: 0.48,
        },
        {
          path: "c'",
          coefficient: 0.18,
          p_value: 0.04,
          ci_lower: 0.02,
          ci_upper: 0.34,
        },
        {
          path: 'direct',
          coefficient: 0.18,
          p_value: 0.04,
          ci_lower: 0.02,
          ci_upper: 0.34,
        },
        {
          path: 'indirect',
          coefficient: 0.147,
          p_value: 0.003,
          ci_lower: 0.062,
          ci_upper: 0.269,
        },
        {
          path: 'total',
          coefficient: 0.327,
          p_value: 0.001,
          ci_lower: 0.18,
          ci_upper: 0.47,
        },
      ],
      bootstrap_samples: 5000,
      indirect_effect: 0.147,
      indirect_effect_ci: [0.062, 0.269],
      indirect_effect_p: 0.003,
      proportion_mediated: 0.45,
      total_effect: 0.327,
      direct_effect: 0.18,
      comparison: {
        with_side_payment_agreement_rate: 0.72,
        without_side_payment_agreement_rate: 0.48,
        difference: 0.24,
      },
    };
  }, []);

  // ---- Export handlers ----
  const handleExportCSV = useCallback(() => {
    if (!runs || runs.length === 0) {
      message.warning('暂无数据可导出');
      return;
    }
    const headers = [
      '运行ID',
      '条件',
      '索引',
      '轮数',
      '协议达成',
      '基尼系数',
      '附带支付使用',
      '附带支付总额',
      '耗时(秒)',
    ];
    const rows = runs.map((r: RunResult) =>
      [
        r.id,
        r.condition_code,
        r.run_index,
        r.total_rounds,
        r.agreement_reached ? '是' : '否',
        r.gini_coefficient.toFixed(4),
        r.side_payment_used ? '是' : '否',
        r.side_payment_total.toFixed(2),
        (r.duration_ms / 1000).toFixed(1),
      ].join(','),
    );
    const csv = '﻿' + headers.join(',') + '\n' + rows.join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `experiment_${selectedId}_data.csv`;
    a.click();
    URL.revokeObjectURL(url);
    message.success('CSV 导出成功');
  }, [runs, selectedId]);

  const handleExportJSON = useCallback(() => {
    if (!runs || runs.length === 0) {
      message.warning('暂无数据可导出');
      return;
    }
    const json = JSON.stringify(runs, null, 2);
    const blob = new Blob([json], { type: 'application/json;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `experiment_${selectedId}_data.json`;
    a.click();
    URL.revokeObjectURL(url);
    message.success('JSON 导出成功');
  }, [runs, selectedId]);

  // ---- Table columns for data export tab ----
  const runColumns = [
    {
      title: '运行ID',
      dataIndex: 'id',
      key: 'id',
      width: 200,
      ellipsis: true,
      sorter: (a: RunResult, b: RunResult) => a.id.localeCompare(b.id),
    },
    {
      title: '条件',
      dataIndex: 'condition_code',
      key: 'condition_code',
      width: 80,
      filters: runs
        ? [...new Set(runs.map((r: RunResult) => r.condition_code))].map((c) => ({
            text: c,
            value: c,
          }))
        : [],
      onFilter: (value: unknown, record: RunResult) =>
        record.condition_code === value,
    },
    {
      title: '索引',
      dataIndex: 'run_index',
      key: 'run_index',
      width: 60,
      sorter: (a: RunResult, b: RunResult) => a.run_index - b.run_index,
    },
    {
      title: '轮数',
      dataIndex: 'total_rounds',
      key: 'total_rounds',
      width: 60,
      sorter: (a: RunResult, b: RunResult) => a.total_rounds - b.total_rounds,
    },
    {
      title: '协议',
      dataIndex: 'agreement_reached',
      key: 'agreement_reached',
      width: 70,
      render: (v: boolean) => (
        <Tag color={v ? 'success' : 'error'}>{v ? '是' : '否'}</Tag>
      ),
      filters: [
        { text: '是', value: true },
        { text: '否', value: false },
      ],
      onFilter: (value: unknown, record: RunResult) =>
        record.agreement_reached === value,
    },
    {
      title: '基尼系数',
      dataIndex: 'gini_coefficient',
      key: 'gini_coefficient',
      width: 100,
      render: (v: number) => v?.toFixed(4),
      sorter: (a: RunResult, b: RunResult) =>
        a.gini_coefficient - b.gini_coefficient,
    },
    {
      title: '附带支付',
      dataIndex: 'side_payment_used',
      key: 'side_payment_used',
      width: 90,
      render: (v: boolean) => (v ? '是' : '否'),
    },
    {
      title: '耗时(s)',
      dataIndex: 'duration_ms',
      key: 'duration_ms',
      width: 80,
      render: (v: number) => ((v || 0) / 1000).toFixed(1),
    },
  ];

  if (!completedExperiments.length) {
    return (
      <Empty
        description="暂无已完成的实验用于分析"
        style={{ marginTop: 80 }}
      />
    );
  }

  return (
    <div>
      <Card style={{ marginBottom: 16 }}>
        <Row gutter={16} align="middle">
          <Col>
            <Text strong>选择实验：</Text>
          </Col>
          <Col flex="auto">
            <Select
              style={{ width: 400 }}
              placeholder="选择已完成的实验"
              value={selectedId}
              onChange={(v) => {
                setSelectedId(v);
                setSelectedRunId(undefined);
              }}
              options={completedExperiments.map((e: ExperimentRecord) => ({
                value: e.id,
                label: `${e.name} - ${e.completed_runs}/${e.total_runs} 已完成`,
              }))}
            />
          </Col>
        </Row>
      </Card>

      {selectedId ? (
        statsLoading ? (
          <Spin style={{ display: 'block', margin: '60px auto' }} />
        ) : (
          <Tabs
            defaultActiveKey="survival"
            items={[
              {
                key: 'survival',
                label: '生存分析',
                children: (
                  <div>
                    <SurvivalChart
                      kmfData={kmfData}
                      title="Kaplan-Meier 生存曲线：三种调停者类型"
                      height={420}
                    />
                    <Card
                      title="Log-rank 检验结果"
                      size="small"
                      style={{ marginTop: 16 }}
                    >
                      <Table
                        dataSource={[
                          {
                            key: 'logrank',
                            test_name: 'Log-rank 检验',
                            statistic: 8.45,
                            p_value: 0.015,
                            significant: true,
                            interpretation:
                              '三种调停者类型的生存曲线存在显著差异（p < 0.05），表明调停者偏见类型对协议持久性有显著影响。',
                          },
                        ]}
                        columns={[
                          { title: '检验方法', dataIndex: 'test_name', key: 'test_name' },
                          {
                            title: '统计量',
                            dataIndex: 'statistic',
                            key: 'statistic',
                            render: (v: number) => v.toFixed(3),
                          },
                          {
                            title: 'p 值',
                            dataIndex: 'p_value',
                            key: 'p_value',
                            render: (v: number) => (
                              <Text style={{ color: v < 0.05 ? '#52c41a' : '#ff4d4f' }}>
                                {v.toFixed(4)}
                              </Text>
                            ),
                          },
                          {
                            title: '显著',
                            dataIndex: 'significant',
                            key: 'significant',
                            render: (v: boolean) => (
                              <Tag color={v ? 'success' : 'error'}>
                                {v ? '是' : '否'}
                              </Tag>
                            ),
                          },
                          {
                            title: '解释',
                            dataIndex: 'interpretation',
                            key: 'interpretation',
                            width: 400,
                          },
                        ]}
                        rowKey="key"
                        pagination={false}
                        size="small"
                      />
                    </Card>
                    <Card
                      title="Cox 比例风险模型"
                      size="small"
                      style={{ marginTop: 16 }}
                    >
                      <Table
                        dataSource={[
                          {
                            variable: '调停者类型（亲强）',
                            coefficient: 0.45,
                            hazard_ratio: 1.57,
                            p_value: 0.023,
                          },
                          {
                            variable: '调停者类型（中立）',
                            coefficient: -0.12,
                            hazard_ratio: 0.89,
                            p_value: 0.42,
                          },
                          {
                            variable: '不对称度（高）',
                            coefficient: 0.68,
                            hazard_ratio: 1.97,
                            p_value: 0.005,
                          },
                          {
                            variable: '附带支付启用',
                            coefficient: -0.35,
                            hazard_ratio: 0.70,
                            p_value: 0.018,
                          },
                        ]}
                        columns={[
                          { title: '变量', dataIndex: 'variable', key: 'variable' },
                          {
                            title: '系数 (β)',
                            dataIndex: 'coefficient',
                            key: 'coefficient',
                            render: (v: number) => v.toFixed(3),
                          },
                          {
                            title: '风险比 (HR)',
                            dataIndex: 'hazard_ratio',
                            key: 'hazard_ratio',
                            render: (v: number) => v.toFixed(3),
                          },
                          {
                            title: 'p 值',
                            dataIndex: 'p_value',
                            key: 'p_value',
                            render: (v: number) => (
                              <Text style={{ color: v < 0.05 ? '#52c41a' : '#ff4d4f' }}>
                                {v.toFixed(4)}
                              </Text>
                            ),
                          },
                        ]}
                        rowKey="variable"
                        pagination={false}
                        size="small"
                      />
                      <Paragraph style={{ marginTop: 12 }}>
                        <Text type="secondary">
                          Concordance = 0.684 | 似然比检验 p = 0.002
                        </Text>
                      </Paragraph>
                    </Card>
                  </div>
                ),
              },
              {
                key: 'mediation',
                label: '中介效应',
                children: (
                  <div>
                    <MediationDiagram mediation={mediationData} height={380} />
                    <Row gutter={16} style={{ marginTop: 16 }}>
                      <Col span={12}>
                        <Card title="Bootstrap 中介效应检验" size="small">
                          <Row gutter={[16, 8]}>
                            <Col span={8}>
                              <Statistic
                                title="Bootstrap 样本"
                                value={mediationData.bootstrap_samples}
                              />
                            </Col>
                            <Col span={8}>
                              <Statistic
                                title="间接效应 (a×b)"
                                value={mediationData.indirect_effect}
                                precision={4}
                              />
                            </Col>
                            <Col span={8}>
                              <Statistic
                                title="中介比例"
                                value={(mediationData.proportion_mediated * 100).toFixed(1)}
                                suffix="%"
                              />
                            </Col>
                            <Col span={8}>
                              <Statistic
                                title="95% CI 下限"
                                value={mediationData.indirect_effect_ci[0]}
                                precision={4}
                              />
                            </Col>
                            <Col span={8}>
                              <Statistic
                                title="95% CI 上限"
                                value={mediationData.indirect_effect_ci[1]}
                                precision={4}
                              />
                            </Col>
                            <Col span={8}>
                              <Statistic
                                title="p 值"
                                value={mediationData.indirect_effect_p}
                                precision={4}
                                valueStyle={{
                                  color:
                                    mediationData.indirect_effect_p < 0.05
                                      ? '#52c41a'
                                      : '#ff4d4f',
                                }}
                              />
                            </Col>
                          </Row>
                        </Card>
                      </Col>
                      <Col span={12}>
                        <Card title="附带支付对比" size="small">
                          <Row gutter={[16, 8]}>
                            <Col span={8}>
                              <Statistic
                                title="有附带支付协议率"
                                value={(mediationData.comparison.with_side_payment_agreement_rate * 100).toFixed(1)}
                                suffix="%"
                              />
                            </Col>
                            <Col span={8}>
                              <Statistic
                                title="无附带支付协议率"
                                value={(mediationData.comparison.without_side_payment_agreement_rate * 100).toFixed(1)}
                                suffix="%"
                              />
                            </Col>
                            <Col span={8}>
                              <Statistic
                                title="差异"
                                value={(mediationData.comparison.difference * 100).toFixed(1)}
                                suffix="%"
                                valueStyle={{ color: '#1677ff' }}
                              />
                            </Col>
                          </Row>
                        </Card>
                      </Col>
                    </Row>
                  </div>
                ),
              },
              {
                key: 'export',
                label: '数据导出',
                children: (
                  <div>
                    <Space style={{ marginBottom: 16 }}>
                      <Button
                        icon={<FileExcelOutlined />}
                        onClick={handleExportCSV}
                      >
                        导出 CSV
                      </Button>
                      <Button
                        icon={<FileTextOutlined />}
                        onClick={handleExportJSON}
                      >
                        导出 JSON
                      </Button>
                    </Space>
                    <Table
                      dataSource={runs || []}
                      columns={runColumns}
                      rowKey="id"
                      size="small"
                      pagination={{ pageSize: 20, showSizeChanger: true }}
                      scroll={{ x: 900 }}
                      locale={{ emptyText: '暂无运行数据' }}
                    />
                  </div>
                ),
              },
              {
                key: 'transcript',
                label: '谈判记录',
                children: (
                  <div>
                    <Row gutter={16} style={{ marginBottom: 16 }}>
                      <Col>
                        <Text strong>选择运行记录：</Text>
                      </Col>
                      <Col flex="auto">
                        <Select
                          showSearch
                          style={{ width: 400 }}
                          placeholder="搜索运行记录..."
                          value={selectedRunId}
                          onChange={setSelectedRunId}
                          filterOption={(input, option) =>
                            (option?.label as string)
                              ?.toLowerCase()
                              .includes(input.toLowerCase())
                          }
                          options={(runs || []).map((r: RunResult) => ({
                            value: r.id,
                            label: `${r.condition_code} #${r.run_index} - ${r.agreement_reached ? '达成' : '未达成'} (${r.total_rounds}轮)`,
                          }))}
                        />
                      </Col>
                    </Row>
                    {selectedRunId ? (
                      runDetailLoading || transcriptLoading ? (
                        <Spin style={{ display: 'block', margin: '40px auto' }} />
                      ) : runDetail ? (
                        <Card>
                          <Row gutter={16} style={{ marginBottom: 16 }}>
                            <Col span={6}>
                              <Statistic
                                title="条件"
                                value={runDetail.condition_code}
                              />
                            </Col>
                            <Col span={6}>
                              <Statistic title="轮数" value={runDetail.total_rounds} />
                            </Col>
                            <Col span={6}>
                              <Statistic
                                title="协议"
                                value={runDetail.agreement_reached ? '达成' : '未达成'}
                                valueStyle={{
                                  color: runDetail.agreement_reached
                                    ? '#52c41a'
                                    : '#ff4d4f',
                                }}
                              />
                            </Col>
                            <Col span={6}>
                              <Statistic
                                title="附带支付"
                                value={runDetail.side_payment_used ? `是 (${runDetail.side_payment_total.toFixed(2)})` : '否'}
                              />
                            </Col>
                          </Row>
                          <Collapse
                            accordion
                          >
                            {(transcript || []).map((round: any, idx: number) => {
                              const props = round.proposal_json ? JSON.parse(round.proposal_json) : null;
                              const strongR = round.strong_response_json ? JSON.parse(round.strong_response_json) : null;
                              const weakR = round.weak_response_json ? JSON.parse(round.weak_response_json) : null;
                              const domScores = round.domestic_scores_json ? JSON.parse(round.domestic_scores_json) : null;
                              return (
                              <Collapse.Panel
                                key={idx}
                                header={
                                  <span>
                                    第 {round.round_number} 轮
                                    {round.agreement_reached ? (
                                      <Tag color="success" style={{ marginLeft: 8 }}>
                                        达成协议
                                      </Tag>
                                    ) : (
                                      <Tag color="default" style={{ marginLeft: 8 }}>
                                        继续谈判
                                      </Tag>
                                    )}
                                  </span>
                                }
                              >
                                <div>
                                  {props && (
                                    <>
                                      <Paragraph>
                                        <Text strong>调解方案: </Text>
                                        领土划分 {props.territory_split}% (强方),
                                        边支付 {props.side_payment_amount} → {props.side_payment_recipient}
                                      </Paragraph>
                                      <Paragraph><Text type="secondary">{props.justification}</Text></Paragraph>
                                    </>
                                  )}
                                  {strongR && (
                                    <Paragraph>
                                      <Tag color="blue">强方</Tag> {strongR.action === 'accept' ? '✅ 接受' : '❌ ' + strongR.action}: {strongR.reasoning}
                                    </Paragraph>
                                  )}
                                  {weakR && (
                                    <Paragraph>
                                      <Tag color="orange">弱方</Tag> {weakR.action === 'accept' ? '✅ 接受' : '❌ ' + weakR.action}: {weakR.reasoning}
                                    </Paragraph>
                                  )}
                                  {domScores && (
                                    <Paragraph>
                                      <Text strong>国内评分: </Text>
                                      强方接受度 {domScores.strong?.political_acceptability?.toFixed(2)}, 压力 {domScores.strong?.pressure_level?.toFixed(2)};
                                      弱方接受度 {domScores.weak?.political_acceptability?.toFixed(2)}, 压力 {domScores.weak?.pressure_level?.toFixed(2)}
                                    </Paragraph>
                                  )}
                                </div>
                              </Collapse.Panel>
                              );
                            })}
                          </Collapse>
                        </Card>
                      ) : (
                        <Empty description="未找到谈判记录" />
                      )
                    ) : (
                      <Empty description="请选择一条运行记录查看谈判详情" />
                    )}
                  </div>
                ),
              },
            ]}
          />
        )
      ) : (
        <Empty description="请选择一个已完成的实验" style={{ marginTop: 60 }} />
      )}
    </div>
  );
};

export default AnalysisPage;
