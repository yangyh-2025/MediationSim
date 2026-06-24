"""
Phase 4 persistence analysis engine:追加执行期, survival tracking.

对已达成协议的案例追加 5 轮无调停者执行期，记录协议何时破裂（或存活至结束）。
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid

from backend.llm.client import LLMClient
from backend.models.schemas import NegotiationContext, AgentResponse, DomesticScore, Proposal
from backend.db.database import Database
from backend.config import config


class PersistenceEngine:
    """Run execution-phase rounds for agreement cases, producing survival data."""

    EXECUTION_ROUNDS: int = 5

    def __init__(self, db: Database) -> None:
        self.db = db
        self._llm = LLMClient()

    @staticmethod
    def _mediator_type(code: str) -> str:
        if code in ("H-PS", "L-PS"):
            return "pro_strong"
        elif code in ("H-N", "L-N"):
            return "neutral"
        elif code in ("H-PW", "L-PW"):
            return "pro_weak"
        return "other"

    @staticmethod
    def _asymmetry_level(code: str) -> str:
        return "high" if code.startswith("H-") else "low"

    # ── Execution round prompt ──────────────────────────

    _EVAL_PROMPT = """你是一个谈判智能体，正在评估已达成协议的执行情况。

谈判阶段已结束，你与对方达成了协议。现在进入执行阶段——没有调停者，双方需要独立决定是否继续遵守协议。

## 协议条款
- 领土划分（强方占比）: {territory_split}%
- 边支付金额: {side_payment}
- 边支付接收方: {recipient}
- 资源分配: {resources}

## 当前状态
- 执行第 {exec_round}/{total_rounds} 轮
- 你的当前效用: {utility:.2f}
- 初始效用: {initial_utility:.2f}
- 国内政治接受度: {acceptability:.2f}
- 国内政治压力: {pressure:.2f}

## 评估指导

你需要决定是 **accept**（继续遵守协议）还是 **reject**（破裂/退出协议）。

考量因素：
1. 协议条款对你是否仍然有利？
2. 国内政治压力是否迫使你重新考虑？
3. 破裂协议的代价（关系恶化、国际声誉损失、重新进入僵局）是否大于继续遵守的代价？
4. 已执行的轮次越长，破裂的合法性成本越高。

输出 AgentResponse，action 只能是 accept 或 reject。"""

    async def _evaluate_party(
        self,
        party_name: str,
        context: NegotiationContext,
        proposal: Proposal,
        domestic: DomesticScore,
        exec_round: int,
    ) -> AgentResponse:
        """Ask one party whether they still uphold the agreement."""
        system_prompt = (
            f"你是谈判中的{party_name}。你的任务是评估已达成协议的执行情况，"
            f"决定是否继续遵守协议。请严格按 JSON Schema 输出。"
        )
        s = AgentResponse.model_json_schema()
        schema_str = json.dumps(s, ensure_ascii=False, indent=2)
        system_prompt += f"\n\n## 输出要求\n请严格按以下 JSON Schema 输出：\n```\n{schema_str}\n```"

        resources_str = json.dumps(proposal.resource_allocation, ensure_ascii=False) if proposal.resource_allocation else "无"

        utility = (
            context.strong_current_utility if party_name == "强方"
            else context.weak_current_utility
        )
        initial_utility = (
            context.strong_initial_utility if party_name == "强方"
            else context.weak_initial_utility
        )

        user_msg = self._EVAL_PROMPT.format(
            territory_split=proposal.territory_split,
            side_payment=proposal.side_payment_amount,
            recipient=proposal.side_payment_recipient,
            resources=resources_str,
            exec_round=exec_round,
            total_rounds=self.EXECUTION_ROUNDS,
            utility=utility,
            initial_utility=initial_utility,
            acceptability=domestic.political_acceptability,
            pressure=domestic.pressure_level,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ]

        result = await self._llm.chat(messages, response_schema=AgentResponse)
        assert isinstance(result, AgentResponse)
        return result

    # ── Main runner ─────────────────────────────────────

    async def run_for_experiment(self, experiment_id: str) -> list[dict]:
        """Run persistence analysis for all agreement cases in an experiment."""
        rows = await self.db.fetch_all(
            "SELECT * FROM runs WHERE experiment_id = ? AND status = 'completed' AND agreement_reached = 1",
            (experiment_id,),
        )
        if not rows:
            return []

        from backend.agents.domestic_audience import DomesticAudience

        audience = DomesticAudience(self._llm)
        results: list[dict] = []

        sem = asyncio.Semaphore(config.max_concurrent_runs)

        async def _process_one(run_row: dict) -> dict | None:
            async with sem:
                return await self._run_one(run_row, audience, experiment_id)

        tasks = [_process_one(r) for r in rows]
        all_results = await asyncio.gather(*tasks)
        for r in all_results:
            if r:
                results.append(r)

        # Persist to DB
        for r in results:
            await self._save_result(experiment_id, r)

        return results

    async def _run_one(self, run_row: dict, audience, experiment_id: str) -> dict | None:
        code = run_row["condition_code"]
        mt = self._mediator_type(code)
        al = self._asymmetry_level(code)

        # Parse run result to get final proposal
        try:
            result_json = json.loads(run_row.get("result_json", "{}"))
        except (json.JSONDecodeError, TypeError):
            return None

        final_proposal_raw = result_json.get("final_proposal")
        if not final_proposal_raw:
            return None

        proposal = Proposal.model_validate(final_proposal_raw)

        # Build minimal context for execution phase
        cond = config.get_condition(code)
        context = NegotiationContext(
            condition_code=code,
            ar=cond["ar"],
            mediator_bias=cond["bias"],
            round_number=0,
        )
        # Set utility from final state
        context.strong_current_utility = result_json.get("strong_current_utility", 300.0)
        context.weak_current_utility = result_json.get("weak_current_utility", 100.0)

        start = time.time()
        agreement_gini = run_row.get("agreement_gini") or 0.0
        side_payment = run_row.get("side_payment_used", 0.0)

        survival = 0
        event = 1  # broke
        broke = False

        for exec_rnd in range(1, self.EXECUTION_ROUNDS + 1):
            # Domestic audience evaluates the situation (no new proposal)
            dom_strong = await audience.act(context, proposal, "strong")
            dom_weak = await audience.act(context, proposal, "weak")

            strong_resp = await self._evaluate_party("强方", context, proposal, dom_strong, exec_rnd)
            weak_resp = await self._evaluate_party("弱方", context, proposal, dom_weak, exec_rnd)

            if strong_resp.action == "reject" or weak_resp.action == "reject":
                survival = exec_rnd
                broke = True
                break
            survival = exec_rnd

        if not broke:
            event = 0  # censored — survived all rounds

        elapsed = time.time() - start

        return {
            "id": str(uuid.uuid4()),
            "experiment_id": experiment_id,
            "run_id": run_row["id"],
            "condition_code": code,
            "mediator_type": mt,
            "asymmetry_level": al,
            "negotiation_rounds": run_row.get("rounds_completed", 0),
            "agreement_gini": agreement_gini,
            "survival_rounds": survival,
            "event": event,
            "side_payment_total": side_payment,
            "duration_seconds": round(elapsed, 2),
        }

    async def _save_result(self, experiment_id: str, result: dict) -> None:
        await self.db.execute(
            """INSERT OR REPLACE INTO persistence_results
               (id, experiment_id, run_id, condition_code, mediator_type, asymmetry_level,
                negotiation_rounds, agreement_gini, survival_rounds, event,
                side_payment_total, duration_seconds)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result["id"], experiment_id, result["run_id"], result["condition_code"],
                result["mediator_type"], result["asymmetry_level"],
                result["negotiation_rounds"], result["agreement_gini"],
                result["survival_rounds"], result["event"],
                result["side_payment_total"], result["duration_seconds"],
            ),
        )
        await self.db._conn.commit()

    async def get_results(self, experiment_id: str) -> list[dict]:
        return await self.db.fetch_all(
            "SELECT * FROM persistence_results WHERE experiment_id = ? ORDER BY condition_code",
            (experiment_id,),
        )

    async def get_kmf_data(self, experiment_id: str) -> list[dict]:
        """Build KMF survival data grouped by mediator_type."""
        rows = await self.get_results(experiment_id)
        if not rows:
            return []

        from lifelines import KaplanMeierFitter
        import numpy as np

        groups: dict[str, list[dict]] = {}
        for r in rows:
            mt = r["mediator_type"]
            if mt not in groups:
                groups[mt] = []
            groups[mt].append(r)

        label_map = {
            "pro_strong": "亲强调停者",
            "neutral": "中立调停者",
            "pro_weak": "亲弱调停者",
        }

        kmf_data = []
        for mt, group_rows in groups.items():
            durations = np.array([r["survival_rounds"] for r in group_rows], dtype=float)
            events = np.array([r["event"] for r in group_rows], dtype=int)

            kmf = KaplanMeierFitter()
            kmf.fit(durations, events, label=mt)

            # Build time points across all possible rounds
            max_t = int(max(durations)) if len(durations) > 0 else 5
            time_points = list(range(1, max_t + 1))
            surv = []
            ci_lower = []
            ci_upper = []
            for t in time_points:
                s = kmf.survival_function_at_times([t]).values
                surv.append(round(float(s[0]), 4) if len(s) > 0 else 1.0)
                try:
                    ci = kmf.confidence_interval_at_times([t])
                    ci_lower.append(round(float(ci.iloc[0, 0]), 4))
                    ci_upper.append(round(float(ci.iloc[0, 1]), 4))
                except Exception:
                    ci_lower.append(round(max(0, surv[-1] - 0.05), 4))
                    ci_upper.append(round(min(1, surv[-1] + 0.05), 4))

            kmf_data.append({
                "condition_code": mt,
                "label": label_map.get(mt, mt),
                "time_points": time_points,
                "survival_prob": surv,
                "ci_lower": ci_lower,
                "ci_upper": ci_upper,
            })

        return kmf_data

    async def get_logrank_and_cox(self, experiment_id: str) -> dict:
        """Run log-rank test and Cox PH model."""
        rows = await self.get_results(experiment_id)
        if not rows or len(set(r["mediator_type"] for r in rows)) < 2:
            return {
                "log_rank": None,
                "cox": None,
            }

        import numpy as np
        import pandas as pd

        df = pd.DataFrame(rows)

        # Log-rank
        from lifelines.statistics import logrank_test, multivariate_logrank_test

        results = {}
        try:
            lr_result = multivariate_logrank_test(
                df["survival_rounds"].values,
                df["mediator_type"].values,
                df["event"].values,
            )
            results["log_rank"] = {
                "test_name": "Log-rank 检验",
                "statistic": round(float(lr_result.test_statistic), 3),
                "p_value": round(float(lr_result.p_value), 4),
                "significant": float(lr_result.p_value) < 0.05,
                "interpretation": (
                    f"三种调停者类型的生存曲线{'存在显著' if float(lr_result.p_value) < 0.05 else '无显著'}差异"
                    f"（p={'<' if float(lr_result.p_value) < 0.05 else '='} {lr_result.p_value:.4f}），"
                    f"表明调停者偏见类型对协议持久性{'有显著' if float(lr_result.p_value) < 0.05 else '无显著'}影响。"
                ),
            }
        except Exception:
            results["log_rank"] = None

        # Cox PH
        try:
            from lifelines import CoxPHFitter

            df_cox = pd.get_dummies(df, columns=["mediator_type"], drop_first=False)
            cov_cols = [c for c in df_cox.columns if c.startswith("mediator_type_") and c != "mediator_type_neutral"]

            if cov_cols:
                cph = CoxPHFitter()
                cph.fit(df_cox[["survival_rounds", "event"] + cov_cols],
                        duration_col="survival_rounds", event_col="event")

                cox_vars = []
                for cov in cov_cols:
                    label = cov.replace("mediator_type_", "")
                    cox_vars.append({
                        "variable": f"调停者类型（{label}）",
                        "coefficient": round(float(cph.summary_.loc[cov, "coef"]), 3),
                        "hazard_ratio": round(float(cph.summary_.loc[cov, "exp(coef)"]), 3),
                        "p_value": round(float(cph.summary_.loc[cov, "p"]), 4),
                    })

                results["cox"] = {
                    "variables": cox_vars,
                    "concordance": round(float(cph.concordance_index_), 3),
                }
        except Exception:
            results["cox"] = None

        return results
