import React, { useState } from 'react';
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu, Typography } from 'antd';
import {
  SettingOutlined,
  DashboardOutlined,
  BarChartOutlined,
  FundOutlined,
  ExperimentOutlined,
} from '@ant-design/icons';
import ConfigPage from './pages/ConfigPage';
import MonitorPage from './pages/MonitorPage';
import ResultsPage from './pages/ResultsPage';
import AnalysisPage from './pages/AnalysisPage';

const { Header, Sider, Content } = Layout;
const { Title } = Typography;

const menuItems = [
  { key: '/config', icon: <SettingOutlined />, label: '实验配置' },
  { key: '/monitor', icon: <DashboardOutlined />, label: '实验监控' },
  { key: '/results', icon: <BarChartOutlined />, label: '结果总览' },
  { key: '/analysis', icon: <FundOutlined />, label: '详细分析' },
];

const App: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);

  const selectedKey =
    menuItems.find((item) => location.pathname.startsWith(item.key))?.key || '/config';

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        theme="dark"
        width={200}
      >
        <div
          style={{
            height: 48,
            margin: 12,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <ExperimentOutlined
            style={{ fontSize: collapsed ? 20 : 28, color: '#fff' }}
          />
          {!collapsed && (
            <span style={{ color: '#fff', marginLeft: 10, fontWeight: 600, whiteSpace: 'nowrap' }}>
              仿真系统
            </span>
          )}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: '#fff',
            padding: '0 24px',
            borderBottom: '1px solid #f0f0f0',
            display: 'flex',
            alignItems: 'center',
          }}
        >
          <Title level={4} style={{ margin: 0 }}>
            偏见调停多智能体模拟系统
          </Title>
        </Header>
        <Content style={{ margin: 16, padding: 24, background: '#fff', borderRadius: 8 }}>
          <Routes>
            <Route path="/config" element={<ConfigPage />} />
            <Route path="/monitor" element={<MonitorPage />} />
            <Route path="/results" element={<ResultsPage />} />
            <Route path="/analysis" element={<AnalysisPage />} />
            <Route path="/" element={<ConfigPage />} />
            <Route path="*" element={<ConfigPage />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  );
};

export default App;
