"""Trade-agent invocation service for processable sandbox ticks."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from app.agents.implementations.sandbox_trade_agent.runtime import (
    SandboxTradeAgentRuntimeConfig,
    build_sandbox_trade_model,
    get_default_sandbox_trade_runtime_config,
    resolve_sandbox_trade_runtime_config,
)
from app.agents.implementations.sandbox_trade_agent.validation import (
    INVALID_AGENT_DECISION,
    SandboxTradeAgentDecisionOutput,
    parse_sandbox_trade_decision_output,
)
from app.domain.models.sandbox_trade_agent import (
    SandboxTradeAgentRuntimeConfig as SandboxTradeSessionRuntimeConfig,
    SandboxTradeDecision,
    SandboxTradeMarketSnapshot,
    SandboxTradePortfolioSnapshot,
    SandboxTradePosition,
    SandboxTradeSession,
    SandboxTradeSettlement,
    SandboxTradeTick,
)
from app.prompts.system.sandbox_trade_agent import (
    get_sandbox_trade_agent_system_prompt,
)
from app.repo.sandbox_trade_agent_repo import SandboxTradeTickRepository

TradeAgentInvoker = Callable[
    [SandboxTradeAgentRuntimeConfig, list[SystemMessage | HumanMessage]],
    Awaitable[SandboxTradeAgentDecisionOutput | dict[str, Any] | str],
]


class SandboxTradeAgentRuntimeService:
    """Invoke the trade agent and persist valid or rejected decisions."""

    def __init__(
        self,
        *,
        tick_repo: SandboxTradeTickRepository,
        invoker: TradeAgentInvoker | None = None,
    ) -> None:
        self.tick_repo = tick_repo
        self.invoker = invoker or _invoke_structured_trade_agent

    async def invoke_for_tick(
        self,
        *,
        session: SandboxTradeSession,
        tick: SandboxTradeTick,
        position: SandboxTradePosition,
        pending_settlements: list[SandboxTradeSettlement],
        recent_ticks: list[SandboxTradeTick] | None = None,
        latest_snapshot: SandboxTradePortfolioSnapshot | None = None,
        now: datetime | None = None,
    ) -> SandboxTradeTick:
        """Invoke the sandbox trade agent and persist its structured decision."""
        process_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if tick.market_snapshot is None:
            return await self._reject_invalid_decision(
                tick=tick,
                completed_at=process_now,
                error="processable ticks require a market snapshot",
            )

        runtime_config = self._resolve_runtime_config(session.runtime_config)
        messages = self._build_messages(
            session=session,
            tick=tick,
            market_snapshot=tick.market_snapshot,
            position=position,
            pending_settlements=pending_settlements,
            recent_ticks=recent_ticks or [],
            latest_snapshot=latest_snapshot,
        )

        try:
            raw_decision = await self.invoker(runtime_config, messages)
            decision_output = parse_sandbox_trade_decision_output(raw_decision)
            decision = decision_output.to_domain_model()
        except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return await self._reject_invalid_decision(
                tick=tick,
                completed_at=process_now,
                error=str(exc),
            )

        if tick.id is None or tick.lock_token is None:
            return tick.model_copy(update={"decision": decision})

        updated = await self.tick_repo.attach_decision(
            tick_id=tick.id,
            lock_token=tick.lock_token,
            decision=decision,
        )
        return updated or tick.model_copy(update={"decision": decision})

    def _build_messages(
        self,
        *,
        session: SandboxTradeSession,
        tick: SandboxTradeTick,
        market_snapshot: SandboxTradeMarketSnapshot,
        position: SandboxTradePosition,
        pending_settlements: list[SandboxTradeSettlement],
        recent_ticks: list[SandboxTradeTick],
        latest_snapshot: SandboxTradePortfolioSnapshot | None,
    ) -> list[SystemMessage | HumanMessage]:
        payload = {
            "session": {
                "id": session.id,
                "symbol": session.symbol,
                "initial_capital": session.initial_capital,
            },
            "tick": {
                "id": tick.id,
                "tick_at": tick.tick_at.isoformat(),
            },
            "market_snapshot": market_snapshot.model_dump(mode="json"),
            "position": position.model_dump(mode="json", exclude={"id"}),
            "pending_settlements": [
                settlement.model_dump(mode="json", exclude={"id"})
                for settlement in pending_settlements
            ],
            "recent_decisions": [
                {
                    "tick_at": recent_tick.tick_at.isoformat(),
                    "status": recent_tick.status.value,
                    "decision": (
                        None
                        if recent_tick.decision is None
                        else recent_tick.decision.model_dump(mode="json")
                    ),
                    "skip_reason": recent_tick.skip_reason,
                    "rejection_reason": recent_tick.rejection_reason,
                }
                for recent_tick in recent_ticks
            ],
            "latest_portfolio_snapshot": (
                None
                if latest_snapshot is None
                else latest_snapshot.model_dump(mode="json", exclude={"id"})
            ),
        }
        return [
            SystemMessage(content=get_sandbox_trade_agent_system_prompt()),
            HumanMessage(
                content=json.dumps(
                    payload,
                    ensure_ascii=True,
                    sort_keys=True,
                )
            ),
        ]

    async def _reject_invalid_decision(
        self,
        *,
        tick: SandboxTradeTick,
        completed_at: datetime,
        error: str,
    ) -> SandboxTradeTick:
        if tick.id is None or tick.lock_token is None:
            return tick.model_copy(
                update={
                    "rejection_reason": INVALID_AGENT_DECISION,
                    "error": error,
                    "completed_at": completed_at,
                }
            )

        updated = await self.tick_repo.mark_rejected_invalid_agent_decision(
            tick_id=tick.id,
            lock_token=tick.lock_token,
            completed_at=completed_at,
            rejection_reason=INVALID_AGENT_DECISION,
            error=error,
        )
        return updated or tick

    @staticmethod
    def _resolve_runtime_config(
        runtime_config: SandboxTradeSessionRuntimeConfig | None,
    ) -> SandboxTradeAgentRuntimeConfig:
        if runtime_config is None:
            return get_default_sandbox_trade_runtime_config()
        return resolve_sandbox_trade_runtime_config(
            provider=runtime_config.provider,
            model=runtime_config.model,
            reasoning=runtime_config.reasoning,
        )


async def _invoke_structured_trade_agent(
    runtime_config: SandboxTradeAgentRuntimeConfig,
    messages: list[SystemMessage | HumanMessage],
) -> SandboxTradeAgentDecisionOutput:
    """Invoke the configured chat model with structured decision output."""
    model = build_sandbox_trade_model(runtime_config)
    structured_model = model.with_structured_output(SandboxTradeAgentDecisionOutput)
    return await structured_model.ainvoke(messages)
