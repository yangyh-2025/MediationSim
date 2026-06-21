import React from 'react';
import { Card, Statistic, Row, Col, Tag, Typography } from 'antd';
import { CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons';
import type { HypothesisResult } from '../types';

const { Text, Paragraph } = Typography;

interface HypothesisCardProps {
  hypothesis: HypothesisResult;
  onReRun?: () => void;
  loading?: boolean;
}

const HypothesisCard: React.FC<HypothesisCardProps> = ({ hypothesis, onReRun, loading }) => {
  const isSignificant = hypothesis.significant;

  return (
    <Card
      title={
        <span>
          {hypothesis.hypothesis_label}
          <Tag
            color={isSignificant ? 'success' : 'error'}
            style={{ marginLeft: 8 }}
          >
            {isSignificant ? '显著' : '不显著'}
          </Tag>
        </span>
      }
      loading={loading}
      style={{
        borderLeft: `4px solid ${isSignificant ? '#52c41a' : '#ff4d4f'}`,
      }}
      extra={
        onReRun && (
          <a onClick={onReRun} style={{ fontSize: 13 }}>
            重新分析
          </a>
        )
      }
    >
      <Row gutter={[16, 12]}>
        <Col span={8}>
          <Statistic
            title="检验方法"
            value={hypothesis.test_name}
            valueStyle={{ fontSize: 16 }}
          />
        </Col>
        <Col span={8}>
          <Statistic
            title="统计量"
            value={hypothesis.statistic}
            precision={4}
            valueStyle={{ fontSize: 16 }}
          />
        </Col>
        <Col span={8}>
          <Statistic
            title="p 值"
            value={hypothesis.p_value}
            precision={4}
            valueStyle={{
              fontSize: 16,
              color: isSignificant ? '#52c41a' : '#ff4d4f',
            }}
            prefix={
              isSignificant ? (
                <CheckCircleOutlined />
              ) : (
                <CloseCircleOutlined />
              )
            }
          />
        </Col>
        <Col span={8}>
          <Statistic
            title="效应量"
            value={hypothesis.effect_size}
            precision={3}
            suffix={hypothesis.effect_size_label}
            valueStyle={{ fontSize: 16 }}
          />
        </Col>
        <Col span={8}>
          <Statistic
            title="置信区间 (95%)"
            value={`[${hypothesis.ci_lower.toFixed(3)}, ${hypothesis.ci_upper.toFixed(3)}]`}
            valueStyle={{ fontSize: 14 }}
          />
        </Col>
        <Col span={8}>
          <Statistic
            title="显著性水平 α"
            value={hypothesis.alpha}
            precision={2}
            valueStyle={{ fontSize: 16 }}
          />
        </Col>
      </Row>
      <Paragraph style={{ marginTop: 12, marginBottom: 0 }}>
        <Text type="secondary">解释：</Text>
        <Text>{hypothesis.interpretation}</Text>
      </Paragraph>
    </Card>
  );
};

export default HypothesisCard;
