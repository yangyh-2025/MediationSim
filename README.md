<p align="center">
  <h1 align="center">🌐 偏见调停中的 AI 模拟研究</h1>
  <p align="center"><i>MediationSim — 基于 LLM 多智能体系统的国际冲突调停仿真实验平台</i></p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.115+-green.svg" alt="FastAPI">
  <img src="https://img.shields.io/badge/React-18+-61dafb.svg" alt="React">
  <img src="https://img.shields.io/badge/TypeScript-5.x-3178c6.svg" alt="TypeScript">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License">
  <img src="https://img.shields.io/badge/experiment-active-orange.svg" alt="Status">
</p>

---

## 📖 研究概述

1978 年的**戴维营协议**呈现了一个经典调停理论难以解释的现象：美国以公认的亲以色列偏见立场出面调停，却成功促成了埃以和平条约。Kim（2025）在博弈论框架下证明，**偏见调停者**可以通过**附带支付机制**（side payment）弥补信任缺失，在特定条件下取得优于中立调停者的协议促成效率。

本项目以戴维营协议为经验锚点，构建了基于**大语言模型的多智能体模拟系统**，通过**纯提示工程**控制强方、弱方、调停者和国内观众四类智能体的行为边界与效用函数，系统性地检验偏见调停有效性假说及其附带支付中介机制。

### 实验设计

| 维度 | 设计 |
|------|------|
| 实验类型 | 2×3 全因子组间实验 + 1 组戴维营参照组 |
| 实验条件 | 7 条件 × 30 次 = 210 次独立谈判模拟 |
| 因子 A | 实力不对称度（高 AR=3:1 / 低 AR=1.5:1） |
| 因子 B | 调停者类型（亲强 b=+0.7 / 中立 b=0 / 亲弱 b=-0.7） |
| 参照条件 | CD：戴维营参照组（AR=2:1, b=+0.7） |

### 四项核心假设

| 假设 | 内容 | 主检验方法 | 效应量 |
|------|------|-----------|--------|
| **H1** | 偏见主效应：高不对称下亲强调停者协议率高于中立 | 独立 t 检验 + Logistic 回归 | Cohen's d |
| **H2** | 协议质量：偏见调停产生的协议公正性差、持久性弱 | ANOVA + Kaplan-Meier + Cox PH | η², HR |
| **H3** | 中介效应：附带支付是偏见→协议的关键中介变量 | Bootstrap 5000 次 | 间接效应 CI |
| **H4** | 调节效应：不对称度调节偏见与协议的关系 | 双因素 ANOVA | η²_p |

---

## 🏗️ 系统架构

```
┌──────────────────────────────────────────────────────────┐
│                     Frontend (React + TS)                 │
│   ConfigPage │ MonitorPage │ ResultsPage │ AnalysisPage  │
└───────────────────────┬──────────────────────────────────┘
                        │ REST API
┌───────────────────────┴──────────────────────────────────┐
│                   Backend (FastAPI)                       │
│  ┌──────────┬──────────┬──────────┬──────────────────┐   │
│  │  Agents  │  Engine  │  LLM     │  Analysis        │   │
│  │  ·强方    │  ·8步流程 │  ·DeepSeek│  ·t检验/ANOVA   │   │
│  │  ·弱方    │  ·状态机 │  ·缓存优化│  ·生存分析       │   │
│  │  ·调停者  │  ·调度器 │  ·容错解析│  ·Bootstrap中介 │   │
│  │  ·国内观众│          │          │  ·Cox PH模型     │   │
│  │  ·评估者  │          │          │                  │   │
│  └──────────┴──────────┴──────────┴──────────────────┘   │
│                         │                                 │
│                    SQLite + JSONL                          │
└──────────────────────────────────────────────────────────┘
```

### 谈判流程（8 步状态机）

```
Step1 初始化 → Step2 立场声明 → Step3 调停提案 →
Step4 国内观众评估 → Step5 回应与反提案 →
Step6 协议判定 → Step7 迭代控制 → Step8 评估记录
                                              │
                                    (若未达成且轮次 < 8)
                                        返回 Step3
```

### 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 后端框架 | FastAPI + Uvicorn | 异步高性能 API |
| 前端 | React 18 + TypeScript + Vite | 现代化 SPA |
| UI 组件 | Ant Design 5 | 表单/表格/卡片 |
| 图表 | ECharts | 生存曲线/箱线图 |
| LLM | DeepSeek V4 Flash（OpenAI 兼容接口） | 多智能体推理 |
| 数据库 | SQLite + JSONL | 结构化 + 全量日志 |
| 统计分析 | SciPy + statsmodels + lifelines | 完整假设检验管线 |

---

## 🚀 快速开始

### 1. 环境准备

```bash
# Python 3.10+ 环境
cd "项目目录"
pip install -r backend/requirements.txt

# Node.js 18+ 前端环境
cd frontend
npm install
```

### 2. 配置 API 密钥

```bash
cp .env.example .env
# 编辑 .env 填入你的 API 密钥：
#   OPENAI_API_KEY=sk-your-key
#   OPENAI_BASE_URL=https://api.openai.com/v1
```

### 3. 启动系统

```bash
# 一键启动（后端 + 自动打开浏览器）
python run.py
```

或者分别启动：

```bash
# 终端 1：后端
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# 终端 2：前端
cd frontend && npm run dev
```

浏览器访问 `http://localhost:5173`（前端）或 `http://localhost:8000/docs`（API 文档）。

### 4. 运行实验

参见 `docs/07-实验操作手册.md`，完整的 4 阶段实验流程：

| 阶段 | 运行次数 | 目的 | 预计耗时 |
|------|----------|------|----------|
| Phase 1 预实验 | 7×3=21 | 参数校准 | ~10-15 分钟 |
| Phase 2 主实验 | 7×10=70 | H1 + H4 检验 | ~20-40 分钟 |
| Phase 3 中介检验 | 3×10=30 | H3 检验 | ~10-20 分钟 |
| Phase 4 持久性 | 达成案例追加 | H2 检验 | ~10-15 分钟 |

---

## 📁 项目结构

```
Skill模拟仿真/
├── backend/
│   ├── agents/           # 5 类 LLM 智能体
│   │   ├── strong_party.py
│   │   ├── weak_party.py
│   │   ├── mediator.py
│   │   ├── domestic_audience.py
│   │   └── evaluator.py
│   ├── engine/           # 谈判引擎 + 实验调度
│   │   ├── negotiation.py
│   │   ├── scheduler.py
│   │   └── orchestrator.py
│   ├── llm/              # LLM 客户端（缓存/容错/日志）
│   │   ├── client.py
│   │   └── logger.py
│   ├── analysis/         # 统计分析模块
│   │   ├── hypothesis_tests.py  # H1-H4 检验
│   │   ├── survival.py          # 生存分析
│   │   └── mediation.py         # Bootstrap 中介
│   ├── prompts/          # 7 个智能体提示词模板
│   ├── models/           # Pydantic 数据模型
│   ├── db/               # 数据库 + 查询
│   ├── tests/            # 65 个单元/集成测试
│   ├── main.py           # FastAPI 入口
│   └── config.py         # 全局配置
├── frontend/
│   └── src/
│       ├── pages/        # 4 个页面
│       └── components/   # 图表/卡片/表格组件
├── docs/                 # 完整文档集（8 份）
├── data/                 # 运行时数据（数据库/日志）
├── run.py                # 一键启动入口
└── pyproject.toml
```

---

## 📊 评估体系

独立的 **评估智能体** 从 6 个维度监控实验质量并驱动参数迭代：

| 维度 | 关键指标 | 检测方法 |
|------|----------|----------|
| 外部效度 | 权力/权利话语占比、破裂率 | 文本模式匹配 + 统计检验 |
| 内部一致性 | 让步率组间差异、提案方向一致性 | t 检验 + 相关系数 |
| 行为合理性 | 让步幅度递减趋势、附带支付-僵局关联 | 时间序列检验 |
| 策略多样性 | 基尼系数 SD、轮次 CV、策略熵 | 描述统计 |
| 随机充分性 | 同条件协议分布 vs 二项分布 | 拟合优度检验 |
| 操作检查 | 提案偏向性、资源差异 | 独立 t 检验 |

三层评估迭代：快速迭代（每 10 次）→ 中期迭代（每 30 次）→ 全局迭代（条件切换前）。

---

## 📚 文档

| 文档 | 内容 |
|------|------|
| `docs/outline.md` | 完整研究提纲 |
| `docs/01-系统设计文档.md` | 系统架构设计 |
| `docs/02-API接口文档.md` | API 接口规范 |
| `docs/03-数据字典.md` | 数据库 Schema |
| `docs/04-实验执行手册.md` | 实验流程指南 |
| `docs/05-交付检查清单.md` | 交付验收标准 |
| `docs/06-测试报告.md` | 65 项测试结果 |
| `docs/07-实验操作手册.md` | 用户操作指南 |
| `docs/08-预实验报告.md` | 预实验分析与优化 |

---

## 🔬 方法论特点

- **纯提示工程**：不训练模型、不微调，仅通过精心设计的提示词控制智能体行为
- **历史锚点校准**：从戴维营案例提取参数（AR≈2:1, b≈+0.7, 附带支付≈GDP 的 2%）作为参照条件
- **容错解析**：支持 DeepSeek 非原生结构化输出环境，自带 JSON 截断修复和 Schema 消歧
- **前缀缓存优化**：为 DeepSeek V4 的 prompt caching 设计字节对齐的消息结构，降低约 40% 成本
- **模块化架构**：智能体/引擎/分析/评估四大模块独立可替换，便于迁移至其他 LLM 或研究问题

---

## ⚙️ 关键配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_rounds` | 8 | 单次模拟最大谈判轮次 |
| `runs_per_condition` | 10 | 每条件运行次数 |
| `max_tokens` | 2048 | 每次调用最大 tokens |
| `temperature` | 0.7 | LLM 温度参数 |
| `side_payment_budget_pct` | 2.0 | 边支付预算（GDP 占比 %） |
| `llm_concurrency` | 50 | LLM 调用全局并发上限 |
| `alpha` | 0.05 | 统计显著性水平 |

---

## 📄 引用

> Kim (2025). Biased Mediators, Credible Commitments, and the Camp David Accords.
>
> 阎学通. 《国际关系研究实用方法》.

```bibtex
@software{MediationSim2026,
  author = {Yang, Yuhang},
  title = {MediationSim: LLM Multi-Agent Simulation of Biased Mediation in International Conflicts},
  year = {2026},
  url = {https://github.com/yangyh-2025/MediationSim}
}
```

---

<p align="center">
  <sub>Built with ❤️ using FastAPI + React + DeepSeek V4</sub>
</p>
