"""Execution engine primitives for backtest runs."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.schemas.backtest import (
    BacktestBar,
    BacktestEquityCurvePoint,
    BacktestRunRequest,
    BacktestTradeLogEntry,
)
from app.services.backtest.templates import BacktestSignal


@dataclass
class _OpenPosition:
    """One active long position tracked by the execution engine."""

    entry_time: str
    entry_price: float
    shares: int
    invested_capital: float


@dataclass(frozen=True)
class BacktestEngineResult:
    """Structured execution output produced before metrics assembly."""

    trade_log: list[BacktestTradeLogEntry]
    equity_curve: list[BacktestEquityCurvePoint]


class BacktestEngine:
    """Run one deterministic backtest execution."""

    def run(
        self,
        request: BacktestRunRequest,
        bars: list[BacktestBar],
        signals: list[BacktestSignal],
    ) -> BacktestEngineResult:
        """Execute one backtest over canonical daily bars and strategy signals."""
        if not bars:
            return BacktestEngineResult(trade_log=[], equity_curve=[])

        cash = float(request.initial_capital)
        position: _OpenPosition | None = None
        trade_log: list[BacktestTradeLogEntry] = []
        equity_curve: list[BacktestEquityCurvePoint] = []
        peak_equity = cash
        signals_by_fill_index = self._group_signals_by_fill_index(bars, signals)

        for bar_index, bar in enumerate(bars):
            for signal in signals_by_fill_index.get(bar_index, []):
                cash, position, closed_trade = self._apply_signal_fill(
                    bar=bar,
                    signal=signal,
                    cash=cash,
                    position=position,
                )
                if closed_trade is not None:
                    trade_log.append(closed_trade)

            market_value = 0.0 if position is None else position.shares * bar.close
            equity = cash + market_value
            peak_equity = max(peak_equity, equity)
            drawdown_pct = self._calculate_drawdown_pct(equity, peak_equity)
            equity_curve.append(
                BacktestEquityCurvePoint(
                    time=bar.time,
                    cash=cash,
                    market_value=market_value,
                    equity=equity,
                    drawdown_pct=drawdown_pct,
                    position_size=0 if position is None else position.shares,
                )
            )

        if position is not None:
            trade_log.append(self._close_position_at_end_of_window(position, bars[-1]))
            final_equity = equity_curve[-1].equity
            peak_equity = max(peak_equity, final_equity)
            equity_curve[-1] = BacktestEquityCurvePoint(
                time=bars[-1].time,
                cash=final_equity,
                market_value=0.0,
                equity=final_equity,
                drawdown_pct=self._calculate_drawdown_pct(final_equity, peak_equity),
                position_size=0,
            )

        return BacktestEngineResult(
            trade_log=trade_log,
            equity_curve=equity_curve,
        )

    @staticmethod
    def _group_signals_by_fill_index(
        bars: list[BacktestBar],
        signals: list[BacktestSignal],
    ) -> dict[int, list[BacktestSignal]]:
        """Group signals by the next bar index where they should be filled."""
        fills: dict[int, list[BacktestSignal]] = {}
        last_index = len(bars) - 1
        for signal in signals:
            fill_index = signal.bar_index + 1
            if fill_index > last_index:
                continue
            fills.setdefault(fill_index, []).append(signal)
        return fills

    @staticmethod
    def _apply_signal_fill(
        *,
        bar: BacktestBar,
        signal: BacktestSignal,
        cash: float,
        position: _OpenPosition | None,
    ) -> tuple[float, _OpenPosition | None, BacktestTradeLogEntry | None]:
        """Apply one next-open fill to the current portfolio state."""
        if signal.action == "buy":
            if position is not None:
                return cash, position, None
            shares = int(cash // bar.open)
            if shares <= 0:
                return cash, position, None
            invested_capital = shares * bar.open
            return (
                cash - invested_capital,
                _OpenPosition(
                    entry_time=bar.time,
                    entry_price=bar.open,
                    shares=shares,
                    invested_capital=invested_capital,
                ),
                None,
            )

        if position is None:
            return cash, position, None
        exit_value = position.shares * bar.open
        return (
            cash + exit_value,
            None,
            BacktestTradeLogEntry(
                entry_time=position.entry_time,
                entry_price=position.entry_price,
                exit_time=bar.time,
                exit_price=bar.open,
                shares=position.shares,
                invested_capital=position.invested_capital,
                pnl=exit_value - position.invested_capital,
                pnl_pct=BacktestEngine._calculate_pnl_pct(
                    exit_value,
                    position.invested_capital,
                ),
                exit_reason=signal.reason,
            ),
        )

    @staticmethod
    def _close_position_at_end_of_window(
        position: _OpenPosition,
        final_bar: BacktestBar,
    ) -> BacktestTradeLogEntry:
        """Force-close one open position on the final available close."""
        exit_value = position.shares * final_bar.close
        return BacktestTradeLogEntry(
            entry_time=position.entry_time,
            entry_price=position.entry_price,
            exit_time=final_bar.time,
            exit_price=final_bar.close,
            shares=position.shares,
            invested_capital=position.invested_capital,
            pnl=exit_value - position.invested_capital,
            pnl_pct=BacktestEngine._calculate_pnl_pct(
                exit_value,
                position.invested_capital,
            ),
            exit_reason="end_of_window",
        )

    @staticmethod
    def _calculate_pnl_pct(
        exit_value: float,
        invested_capital: float,
    ) -> float:
        """Convert one realized trade result into percent return."""
        if invested_capital <= 0:
            return 0.0
        return ((exit_value - invested_capital) / invested_capital) * 100

    @staticmethod
    def _calculate_drawdown_pct(equity: float, peak_equity: float) -> float:
        """Calculate drawdown percentage from the running peak equity."""
        if peak_equity <= 0:
            return 0.0
        return ((peak_equity - equity) / peak_equity) * 100
