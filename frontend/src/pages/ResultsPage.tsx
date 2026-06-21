import React, { useState, useMemo } from 'react';
import {
  Card,
  Select,
  Row,
  Col,
  Table,
  Button,
  Empty,
  Spin,
  Typography,
  Tabs,
} from 'antd';
import { ReloadOutlined, BarChartOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { BarChart, BoxplotChart } from 'echarts/charts';
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
  DatasetComponent,
  TransformComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { getStatistics, runStatistics, listExperiments } from '../api/client';
import { ALL_CONDITIONS } from '../types';
import HypothesisCard from '../components/HypothesisCard';
import type { ExperimentRecord, ConditionSummary, HypothesisResult } from '../types';

echarts.use([
  BarChart,
  BoxplotChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
  DatasetComponent,
  TransformComponent,
  CanvasRenderer,
]);

const { Title, Text } = Typography;

const CHART_COLORS = ['#1677ff', '#52c41a', '#fa8c16', '#722ed1', '#eb2f96', '#13c2c2', '#f5222d'];

const ResultsPage: React.FC = () => {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | undefined>(undefined);

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

  const { data: statistics, isLoading } = useQuery({
    queryKey: ['statistics', selectedId],
    queryFn: () => getStatistics(selectedId!),
    enabled: !!selectedId,
  });

  const runStatsMut = useMutation({
    mutationFn: () => runStatistics(selectedId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['statistics', selectedId] });
    },
  });

  const agreementBarOption = useMemo(() => {
    if (!statistics?.condition_summaries) return {};
    const summaries = statistics.condition_summaries;
    const highConditions = summaries.filter((s) => {
      const cfg = ALL_CONDITIONS.find((c) => c.code === s.condition_code);
      return cfg?.bias_level === 'high';
    });
    const lowConditions = summaries.filter((s) => {
      const cfg = ALL_CONDITIONS.find((c) => c.code === s.condition_code);
      return cfg?.bias_level === 'low';
    });

    return {
      title: { text: '协议达成率（按条件分组）', left: 'center', textStyle: { fontSize: 14 } },
      tooltip: { trigger: 'axis' },
      legend: { data: ['高不对称', '低不对称'], bottom: 0 },
      grid: { left: 60, right: 30, top: 50, bottom: 40 },
      xAxis: {
        type: 'category',
        data: ['亲强', '中立', '亲弱', '戴维营'],
      },
      yAxis: {
        type: 'value',
        name: '协议率 (%)',
        axisLabel: { formatter: '{value}%' },
      },
      series: [
        {
          name: '高不对称',
          type: 'bar',
          data: highConditions.map((s) => +(s.agreement_rate * 100).toFixed(1)),
          itemStyle: { color: '#ff4d4f' },
        },
        {
          name: '低不对称',
          type: 'bar',
          data: lowConditions.map((s) => +(s.agreement_rate * 100).toFixed(1)),
          itemStyle: { color: '#1677ff' },
        },
      ],
    };
  }, [statistics]);

  const giniBoxOption = useMemo(() => {
    if (!statistics?.condition_summaries) return {};
    const summaries = statistics.condition_summaries;
    return {
      title: { text: '基尼系数分布（按条件）', left: 'center', textStyle: { fontSize: 14 } },
      tooltip: { trigger: 'axis' },
      grid: { left: 60, right: 30, top: 50, bottom: 40 },
      xAxis: {
        type: 'category',
        data: summaries.map((s) => s.condition_code),
      },
      yAxis: {
        type: 'value',
        name: '基尼系数',
        min: 0,
        max: 1,
      },
      series: [
        {
          name: '平均基尼系数',
          type: 'bar',
          data: summaries.map((s, idx) => ({
            value: +s.mean_gini.toFixed(4),
            itemStyle: { color: CHART_COLORS[idx % CHART_COLORS.length] },
          })),
        },
      ],
    };
  }, [statistics]);

  const sidePaymentBarOption = useMemo(() => {
    if (!statistics?.condition_summaries) return {};
    const summaries = statistics.condition_summaries;
    return {
      title: { text: '附带支付使用情况（按条件）', left: 'center', textStyle: { fontSize: 14 } },
      tooltip: { trigger: 'axis' },
      grid: { left: 60, right: 30, top: 50, bottom: 40 },
      xAxis: {
        type: 'category',
        data: summaries.map((s) => s.condition_code),
      },
      yAxis: {
        type: 'value',
        name: '平均附带支付金额',
      },
      series: [
        {
          name: '平均附带支付',
          type: 'bar',
          data: summaries.map((s, idx) => ({
            value: +s.mean_side_payment.toFixed(2),
            itemStyle: { color: CHART_COLORS[idx % CHART_COLORS.length] },
          })),
        },
      ],
    };
  }, [statistics]);

  const summaryColumns = [
    { title: '条件', dataIndex: 'condition_code', key: 'condition_code', width: 80 },
    {
      title: '运行数',
      dataIndex: 'runs',
      key: 'runs',
      width: 80,
    },
    {
      title: '协议率 (%)',
      dataIndex: 'agreement_rate',
      key: 'agreement_rate',
      width: 100,
      render: (v: number) => (v * 100).toFixed(1),
    },
    {
      title: '平均基尼系数',
      dataIndex: 'mean_gini',
      key: 'mean_gini',
      width: 120,
      render: (v: number) => v?.toFixed(4),
    },
    {
      title: '平均轮数',
      dataIndex: 'mean_rounds',
      key: 'mean_rounds',
      width: 100,
      render: (v: number) => v?.toFixed(1),
    },
    {
      title: '平均附带支付',
      dataIndex: 'mean_side_payment',
      key: 'mean_side_payment',
      width: 120,
      render: (v: number) => v?.toFixed(2),
    },
  ];

  if (!completedExperiments.length) {
    return (
      <Empty
        description="暂无已完成的实验"
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
              onChange={setSelectedId}
              options={completedExperiments.map((e: ExperimentRecord) => ({
                value: e.id,
                label: `${e.name} - ${e.completed_runs}/${e.total_runs} 已完成`,
              }))}
            />
          </Col>
          <Col>
            <Button
              icon={<ReloadOutlined />}
              onClick={() => runStatsMut.mutate()}
              loading={runStatsMut.isPending}
              disabled={!selectedId}
            >
              重新分析
            </Button>
          </Col>
        </Row>
      </Card>

      {selectedId && (isLoading ? (
        <Spin style={{ display: 'block', margin: '60px auto' }} />
      ) : statistics ? (
        <>
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            {statistics.hypotheses?.map((hyp: HypothesisResult) => (
              <Col xs={24} lg={12} key={hyp.hypothesis_id}>
                <HypothesisCard
                  hypothesis={hyp}
                  onReRun={() => runStatsMut.mutate()}
                />
              </Col>
            )) || (
              <Col span={24}>
                <Empty description="暂无假设检验结果" />
              </Col>
            )}
          </Row>

          <Card title="条件汇总" style={{ marginBottom: 16 }}>
            <Table
              dataSource={statistics.condition_summaries || []}
              columns={summaryColumns}
              rowKey="condition_code"
              size="middle"
              pagination={false}
            />
          </Card>

          <Tabs
            defaultActiveKey="agreement"
            items={[
              {
                key: 'agreement',
                label: '协议达成率（分组柱状图）',
                children: (
                  <ReactEChartsCore
                    echarts={echarts}
                    option={agreementBarOption}
                    style={{ height: 400 }}
                    notMerge
                    lazyUpdate
                  />
                ),
              },
              {
                key: 'gini',
                label: '基尼系数分布',
                children: (
                  <ReactEChartsCore
                    echarts={echarts}
                    option={giniBoxOption}
                    style={{ height: 400 }}
                    notMerge
                    lazyUpdate
                  />
                ),
              },
              {
                key: 'side_payment',
                label: '附带支付使用情况',
                children: (
                  <ReactEChartsCore
                    echarts={echarts}
                    option={sidePaymentBarOption}
                    style={{ height: 400 }}
                    notMerge
                    lazyUpdate
                  />
                ),
              },
            ]}
          />
        </>
      ) : (
        <Empty description="未找到统计数据" style={{ marginTop: 60 }} />
      ))}
    </div>
  );
};

export default ResultsPage;
