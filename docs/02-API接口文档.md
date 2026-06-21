# API 接口文档 — 偏见调停多智能体模拟系统

## 基础信息

- **Base URL:** `http://localhost:8000`
- **Content-Type:** `application/json`
- **API 文档（自动生成）:** `http://localhost:8000/docs` (Swagger UI) | `http://localhost:8000/redoc` (ReDoc)

---

## 1. 健康检查

### `GET /api/health`
```
Response: {"status": "ok", "version": "1.0.0"}
```

---

## 2. 实验管理

### `POST /api/experiments` — 创建实验
```json
// Request
{
  "name": "主实验",
  "conditions": ["H-PS","H-N","H-PW","L-PS","L-N","L-PW","CD"],
  "runs_per_condition": 30,
  "max_rounds": 10,
  "temperature": 0.7,
  "max_tokens": 3840,
  "side_payment_enabled": true,
  "max_retries": 3
}
// Response: ExperimentStatus
```

### `GET /api/experiments` — 实验列表
返回 `ExperimentStatus[]`

### `GET /api/experiments/{id}` — 实验详情
### `POST /api/experiments/{id}/start` — 启动实验（后台异步执行）
### `POST /api/experiments/{id}/pause` — 暂停
### `POST /api/experiments/{id}/resume` — 恢复
### `DELETE /api/experiments/{id}` — 删除实验及数据

---

## 3. 运行数据

### `GET /api/experiments/{id}/runs?condition_code=H-PS` — 运行列表
返回 `RunResult[]`，可按条件筛选

### `GET /api/experiments/{id}/runs/{run_id}` — 单次运行详情
### `GET /api/experiments/{id}/runs/{run_id}/transcript` — 谈判记录
返回 `RoundRecord[]`

---

## 4. 评估

### `GET /api/experiments/{id}/evaluations` — 评估报告列表
### `POST /api/experiments/{id}/evaluations/trigger` — 手动触发评估

---

## 5. 统计分析

### `GET /api/experiments/{id}/statistics` — 已缓存的分析结果
### `POST /api/experiments/{id}/statistics/run` — 运行完整统计分析
返回 `HypothesisResult[]`（H1-H4）

### `GET /api/experiments/{id}/summary` — 条件汇总
返回各条件的运行数、协议率、平均 gini、平均轮次、平均附带支付

---

## 6. LLM 调用日志

### `GET /api/experiments/{id}/logs?limit=1000&offset=0` — 分页获取全量调用日志
每条日志包含：完整提示词（messages）、原始响应（response_text）、结构化输出（parsed_output）、缓存指标、agent/condition/round/run 上下文、时间戳、耗时

### `GET /api/experiments/{id}/logs/stats` — 日志统计
返回：总调用次数、缓存命中/未命中 token 数、缓存命中率、总耗时、错误数、日志文件数

---

## 7. 核心数据模型

| 模型 | 关键字段 |
|------|----------|
| ExperimentConfigIn | name, conditions[], runs_per_condition, temperature, max_tokens, side_payment_enabled |
| ExperimentStatus | experiment_id, status(draft/running/paused/completed/failed), total_runs, completed_runs |
| RunResult | run_id, condition_code, agreement_reached, agreement_gini, side_payment_used_total, round_records[] |
| RoundRecord | round_number, mediator_proposal, strong_response, weak_response, domestic scores |
| Proposal | territory_split, resource_allocation, side_payment_amount, side_payment_recipient |
| HypothesisResult | hypothesis, test_statistic, p_value, effect_size, confidence_interval, significant |
| EvaluationReport | dimensions[6], overall_score, parameter_adjustments[] |
