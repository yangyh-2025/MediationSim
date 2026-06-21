import React from 'react';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { LineChart } from 'echarts/charts';
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import type { KMFSurvivalData } from '../types';

echarts.use([
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
  CanvasRenderer,
]);

interface SurvivalChartProps {
  kmfData: KMFSurvivalData[];
  title?: string;
  height?: number;
}

const COLORS = ['#1677ff', '#52c41a', '#fa8c16', '#722ed1', '#eb2f96', '#13c2c2', '#f5222d'];

const SurvivalChart: React.FC<SurvivalChartProps> = ({
  kmfData,
  title = 'Kaplan-Meier 生存曲线',
  height = 400,
}) => {
  const option: echarts.EChartsCoreOption = {
    title: {
      text: title,
      left: 'center',
      textStyle: { fontSize: 14, fontWeight: 500 },
    },
    tooltip: {
      trigger: 'axis',
      formatter: (params: unknown) => {
        const items = params as Array<{
          seriesName: string;
          data: [number, number];
          color: string;
        }>;
        let html = `回合: ${items[0]?.data[0]}<br/>`;
        items.forEach((item) => {
          html += `<span style="display:inline-block;margin-right:5px;border-radius:10px;width:10px;height:10px;background-color:${item.color};"></span>`;
          html += `${item.seriesName}: ${(item.data[1] * 100).toFixed(1)}%<br/>`;
        });
        return html;
      },
    },
    legend: {
      bottom: 0,
      data: kmfData.map((d) => d.label),
    },
    grid: {
      left: 60,
      right: 40,
      top: 50,
      bottom: 40,
    },
    xAxis: {
      type: 'value',
      name: '回合数',
      nameLocation: 'middle',
      nameGap: 25,
      min: 0,
      axisLabel: { fontSize: 12 },
    },
    yAxis: {
      type: 'value',
      name: '生存概率',
      nameLocation: 'middle',
      nameGap: 45,
      min: 0,
      max: 1,
      axisLabel: {
        fontSize: 12,
        formatter: (val: number) => `${(val * 100).toFixed(0)}%`,
      },
    },
    series: kmfData.map((d, idx) => ({
      name: d.label,
      type: 'line',
      step: 'end' as const,
      data: d.time_points.map((t, i) => [t, d.survival_prob[i]]),
      color: COLORS[idx % COLORS.length],
      lineStyle: { width: 2 },
      symbol: 'none',
      markArea:
        d.ci_lower && d.ci_upper
          ? {
              silent: true,
              data: [
                [
                  {
                    xAxis: d.time_points[0],
                    yAxis: d.ci_lower[0],
                  },
                  {
                    xAxis: d.time_points[d.time_points.length - 1],
                    yAxis: d.ci_upper[d.ci_upper.length - 1],
                  },
                ],
              ],
              itemStyle: {
                color: COLORS[idx % COLORS.length],
                opacity: 0.08,
              },
            }
          : undefined,
    })),
  };

  return (
    <ReactEChartsCore
      echarts={echarts}
      option={option}
      style={{ height, width: '100%' }}
      notMerge
      lazyUpdate
    />
  );
};

export default SurvivalChart;
