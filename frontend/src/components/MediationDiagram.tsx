import React from 'react';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { GraphChart } from 'echarts/charts';
import {
  TooltipComponent,
  TitleComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import type { MediationAnalysisResult } from '../types';

echarts.use([GraphChart, TooltipComponent, TitleComponent, CanvasRenderer]);

interface MediationDiagramProps {
  mediation: MediationAnalysisResult;
  height?: number;
}

const MediationDiagram: React.FC<MediationDiagramProps> = ({ mediation, height = 350 }) => {
  const indirectPath = mediation.paths.find((p) => p.path === 'indirect') || {
    coefficient: mediation.indirect_effect,
    p_value: mediation.indirect_effect_p,
    ci_lower: mediation.indirect_effect_ci[0],
    ci_upper: mediation.indirect_effect_ci[1],
  };
  const directPath = mediation.paths.find((p) => p.path === 'direct') || {
    coefficient: mediation.direct_effect,
    p_value: 0,
    ci_lower: 0,
    ci_upper: 0,
  };
  const totalPath = mediation.paths.find((p) => p.path === 'total') || {
    coefficient: mediation.total_effect,
    p_value: 0,
    ci_lower: 0,
    ci_upper: 0,
  };

  const sigStyle = (pVal: number) => (pVal < 0.05 ? ' (*)' : '');

  const option: echarts.EChartsCoreOption = {
    title: {
      text: '中介效应路径图',
      left: 'center',
      textStyle: { fontSize: 14, fontWeight: 500 },
    },
    tooltip: {
      formatter: (params: unknown) => {
        const d = params as { data: { name: string; value?: string; detail?: string } };
        if (d.data.detail) return d.data.detail;
        return d.data.name;
      },
    },
    animation: true,
    series: [
      {
        type: 'graph',
        layout: 'force',
        force: {
          repulsion: 400,
          edgeLength: [180, 220],
          gravity: 0.1,
        },
        roam: false,
        draggable: false,
        symbolSize: 60,
        lineStyle: {
          color: '#aaa',
          curveness: 0.2,
          width: 2,
        },
        edgeSymbol: ['none', 'arrow'],
        edgeSymbolSize: 10,
        label: {
          show: true,
          position: 'inside',
          fontSize: 13,
          fontWeight: 500,
          formatter: '{b}',
        },
        data: [
          {
            name: 'X\n调停者偏见',
            x: 100,
            y: 200,
            itemStyle: { color: '#1677ff' },
            label: { color: '#fff' },
          },
          {
            name: 'M\n附带支付',
            x: 300,
            y: 200,
            itemStyle: { color: '#52c41a' },
            label: { color: '#fff' },
          },
          {
            name: 'Y\n协议达成',
            x: 500,
            y: 200,
            itemStyle: { color: '#fa8c16' },
            label: { color: '#fff' },
          },
        ],
        edges: [
          {
            source: 'X\n调停者偏见',
            target: 'M\n附带支付',
            label: {
              show: true,
              formatter: `a: ${indirectPath.coefficient.toFixed(3)}${sigStyle(indirectPath.p_value)}`,
              fontSize: 11,
              position: 'middle',
              distance: 8,
            },
            lineStyle: { color: '#1677ff', width: 2 },
          },
          {
            source: 'M\n附带支付',
            target: 'Y\n协议达成',
            label: {
              show: true,
              formatter: `b: ${mediation.paths.find((p) => p.path === 'b')?.coefficient.toFixed(3) || '—'}${sigStyle(mediation.paths.find((p) => p.path === 'b')?.p_value || 1)}`,
              fontSize: 11,
              position: 'middle',
              distance: 8,
            },
            lineStyle: { color: '#52c41a', width: 2 },
          },
          {
            source: 'X\n调停者偏见',
            target: 'Y\n协议达成',
            label: {
              show: true,
              formatter: `c': ${directPath.coefficient.toFixed(3)}${sigStyle(directPath.p_value)}`,
              fontSize: 11,
              position: 'middle',
              distance: -10,
            },
            lineStyle: {
              color: '#ff4d4f',
              width: 1.5,
              type: 'dashed',
              curveness: -0.3,
            },
          },
        ],
      },
    ],
  };

  return (
    <div>
      <ReactEChartsCore
        echarts={echarts}
        option={option}
        style={{ height, width: '100%' }}
        notMerge
        lazyUpdate
      />
      <div
        style={{
          textAlign: 'center',
          fontSize: 12,
          color: '#888',
          marginTop: 8,
        }}
      >
        间接效应 a×b = {mediation.indirect_effect.toFixed(4)}，95% CI [
        {mediation.indirect_effect_ci[0].toFixed(4)},{' '}
        {mediation.indirect_effect_ci[1].toFixed(4)}]，p = {mediation.indirect_effect_p.toFixed(4)}
        &nbsp;&nbsp;|&nbsp;&nbsp;中介比例 = {(mediation.proportion_mediated * 100).toFixed(1)}%
        &nbsp;&nbsp;|&nbsp;&nbsp;总效应 = {mediation.total_effect.toFixed(4)}
      </div>
    </div>
  );
};

export default MediationDiagram;
