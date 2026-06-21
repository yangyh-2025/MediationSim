import React, { useState } from 'react';
import {
  Card, Form, Input, InputNumber, Slider, Switch, Checkbox,
  Button, Table, Tag, Space, message, Popconfirm, Row, Col, Typography,
} from 'antd';
import {
  PlusOutlined, PlayCircleOutlined, PauseCircleOutlined,
  SyncOutlined, DeleteOutlined, LoadingOutlined,
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  listExperiments, createExperiment,
  startExperiment, pauseExperiment, resumeExperiment, deleteExperiment,
} from '../api/client';
import { ALL_CONDITIONS } from '../types';
import type { ExperimentRecord } from '../types';
import dayjs from 'dayjs';

const { Title, Text } = Typography;

const STATUS_CONFIG: Record<string, { color: string; label: string }> = {
  draft: { color: 'default', label: '草稿' },
  running: { color: 'processing', label: '运行中' },
  paused: { color: 'warning', label: '暂停' },
  completed: { color: 'success', label: '已完成' },
  failed: { color: 'error', label: '失败' },
};

const ConfigPage: React.FC = () => {
  const queryClient = useQueryClient();
  const [form] = Form.useForm();
  const [createLoading, setCreateLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({});

  const { data: experiments, isLoading } = useQuery({
    queryKey: ['experiments'],
    queryFn: listExperiments,
    refetchInterval: 2000,
    staleTime: 0,            // always consider stale → refetch on mount/focus
    refetchOnWindowFocus: true,
  });

  // ── Mutations (no optimistic updates — wait for real backend response) ──

  const startMut = useMutation({
    mutationFn: startExperiment,
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['experiments'] }),
  });

  const pauseMut = useMutation({
    mutationFn: pauseExperiment,
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['experiments'] }),
  });

  const resumeMut = useMutation({
    mutationFn: resumeExperiment,
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['experiments'] }),
  });

  const deleteMut = useMutation({
    mutationFn: deleteExperiment,
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['experiments'] }),
  });

  // ── Action handlers with loading per button ──

  const doAction = async (
    id: string,
    action: 'start' | 'pause' | 'resume' | 'delete',
    fn: (id: string) => Promise<any>,
    okMsg: string,
  ) => {
    setActionLoading((prev) => ({ ...prev, [`${action}-${id}`]: true }));
    try {
      await fn(id);
      message.success(okMsg);
    } catch {
      message.error(`${okMsg}失败`);
    } finally {
      setActionLoading((prev) => ({ ...prev, [`${action}-${id}`]: false }));
    }
  };

  const handleCreate = async (values: {
    name: string; temperature: number; max_tokens: number;
    max_rounds: number; runs_per_condition: number;
    side_payment_enabled: boolean; conditions: string[];
  }) => {
    setCreateLoading(true);
    try {
      await createExperiment({
        name: values.name, temperature: values.temperature,
        max_tokens: values.max_tokens, max_rounds: values.max_rounds,
        runs_per_condition: values.runs_per_condition,
        side_payment_enabled: values.side_payment_enabled,
        conditions: values.conditions,
      });
      message.success('实验创建成功');
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['experiments'] });
    } catch {
      message.error('创建失败');
    } finally {
      setCreateLoading(false);
    }
  };

  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name', ellipsis: true },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (s: string) => {
        const cfg = STATUS_CONFIG[s] || { color: 'default', label: s };
        return <Tag color={cfg.color}>{cfg.label}</Tag>;
      },
    },
    { title: '总运行数', dataIndex: 'total_runs', key: 'total_runs', width: 90 },
    {
      title: '已完成', dataIndex: 'completed_runs', key: 'completed_runs', width: 90,
      render: (v: number, r: ExperimentRecord) => `${v} / ${r.total_runs}`,
    },
    {
      title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 160,
      render: (v: string) => v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-',
    },
    {
      title: '操作', key: 'actions', width: 280,
      render: (_: unknown, record: ExperimentRecord) => (
        <Space size="small">
          {record.status === 'draft' && (
            <Button type="link" size="small" icon={
              actionLoading[`start-${record.id}`] ? <LoadingOutlined /> : <PlayCircleOutlined />
            } loading={actionLoading[`start-${record.id}`]}
              onClick={() => doAction(record.id, 'start', startMut.mutateAsync, '实验已启动')}>
              启动
            </Button>
          )}
          {record.status === 'running' && (
            <Button type="link" size="small" icon={
              actionLoading[`pause-${record.id}`] ? <LoadingOutlined /> : <PauseCircleOutlined />
            } loading={actionLoading[`pause-${record.id}`]}
              onClick={() => doAction(record.id, 'pause', pauseMut.mutateAsync, '实验已暂停')}>
              暂停
            </Button>
          )}
          {record.status === 'paused' && (
            <Button type="link" size="small" icon={
              actionLoading[`resume-${record.id}`] ? <LoadingOutlined /> : <SyncOutlined />
            } loading={actionLoading[`resume-${record.id}`]}
              onClick={() => doAction(record.id, 'resume', resumeMut.mutateAsync, '实验已恢复')}>
              恢复
            </Button>
          )}
          <Popconfirm title="确定删除此实验？"
            onConfirm={() => doAction(record.id, 'delete', deleteMut.mutateAsync, '实验已删除')}>
            <Button type="link" size="small" danger icon={<DeleteOutlined />}
              loading={actionLoading[`delete-${record.id}`]}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={10}>
          <Card title={<span><PlusOutlined style={{ marginRight: 8 }} />创建新实验</span>}>
            <Form form={form} layout="vertical" onFinish={handleCreate}
              initialValues={{
                temperature: 0.7, max_tokens: 2048, max_rounds: 8,
                runs_per_condition: 10, side_payment_enabled: true,
                conditions: ALL_CONDITIONS.map((c) => c.code),
              }}>
              <Form.Item label="实验名称" name="name"
                rules={[{ required: true, message: '请输入实验名称' }]}>
                <Input placeholder="例如：主实验-偏见效应检验" />
              </Form.Item>
              <Form.Item label="温度 (Temperature)" name="temperature">
                <Slider min={0} max={1.5} step={0.05}
                  marks={{ 0: '0', 0.5: '0.5', 1: '1.0', 1.5: '1.5' }} />
              </Form.Item>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item label="最大 Token 数" name="max_tokens">
                    <InputNumber min={256} max={8192} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="最大谈判轮数" name="max_rounds">
                    <InputNumber min={1} max={50} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item label="每组运行次数" name="runs_per_condition">
                    <InputNumber min={1} max={100} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="附带支付" name="side_payment_enabled" valuePropName="checked">
                    <Switch />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item label="实验条件" name="conditions"
                rules={[{ required: true, message: '至少选择一个条件' }]}>
                <Checkbox.Group>
                  <Row gutter={[12, 8]}>
                    {ALL_CONDITIONS.map((c) => (
                      <Col span={8} key={c.code}>
                        <Checkbox value={c.code}>
                          {c.code}
                          <Text type="secondary" style={{ fontSize: 11, marginLeft: 4 }}>{c.label}</Text>
                        </Checkbox>
                      </Col>
                    ))}
                  </Row>
                </Checkbox.Group>
              </Form.Item>
              <Form.Item>
                <Button type="primary" htmlType="submit" loading={createLoading} block>
                  创建实验
                </Button>
              </Form.Item>
            </Form>
          </Card>
        </Col>
        <Col xs={24} lg={14}>
          <Card title="已有实验">
            <Table dataSource={experiments || []} columns={columns} rowKey="id"
              size="small" loading={isLoading}
              locale={{ emptyText: '暂无实验，请先创建' }}
              pagination={{ pageSize: 10 }} />
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default ConfigPage;
