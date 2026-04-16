"""Result-building helpers for backtest runs."""

from __future__ import annotations

from app.domain.schemas.backtest import (
    BacktestPerformanceMetrics,
    BacktestRunRequest,
    BacktestRunResponse,
    BacktestSummaryMetrics,
    BacktestTradeLogEntry,
)
from app.services.backtest.engine import BacktestEngineResult


class BacktestMetricsBuilder:
    """Build structured metrics for completed backtests."""

    def build_response(
        self,
        request: BacktestRunRequest,
        result: BacktestEngineResult,
    ) -> BacktestRunResponse:
        """Assemble the stable run response from execution outputs."""
        ending_equity = (
            result.equity_curve[-1].equity
            if result.equity_curve
            else float(request.initial_capital)
        )
        return BacktestRunResponse(
            summary_metrics=BacktestSummaryMetrics(
                symbol=request.symbol,
                template_id=request.template_id,
                timeframe=request.timeframe,
                date_from=request.date_from,
                date_to=request.date_to,
                initial_capital=request.initial_capital,
                ending_equity=ending_equity,
                total_trades=len(result.trade_log),
            ),
            performance_metrics=self._build_performance_metrics(request, result),
            trade_log=result.trade_log,
            equity_curve=result.equity_curve,
        )

    def _build_performance_metrics(
        self,
        request: BacktestRunRequest,
        result: BacktestEngineResult,
    ) -> BacktestPerformanceMetrics:
        """Compute one stable set of performance metrics from completed trades."""
        ending_equity = (
            result.equity_curve[-1].equity
            if result.equity_curve
            else float(request.initial_capital)
        )
        total_return_pct = self._calculate_total_return_pct(
            request.initial_capital,
            ending_equity,
        )
        annualized_return_pct = self._calculate_annualized_return_pct(
            request=request,
            ending_equity=ending_equity,
        )
        return BacktestPerformanceMetrics(
            total_return_pct=total_return_pct,
            annualized_return_pct=annualized_return_pct,
            max_drawdown_pct=max(
                (point.drawdown_pct for point in result.equity_curve),
                default=0.0,
            ),
            win_rate_pct=self._calculate_win_rate_pct(result.trade_log),
            profit_factor=self._calculate_profit_factor(result.trade_log),
            avg_win_pct=self._calculate_average_win_pct(result.trade_log),
            avg_loss_pct=self._calculate_average_loss_pct(result.trade_log),
            expectancy=self._calculate_expectancy(result.trade_log),
        )

    @staticmethod
    def _calculate_total_return_pct(
        initial_capital: int,
        ending_equity: float,
    ) -> float:
        """Calculate total return percentage for the run."""
        if initial_capital <= 0:
            return 0.0
        return ((ending_equity - initial_capital) / initial_capital) * 100

    @staticmethod
    def _calculate_annualized_return_pct(
        *,
        request: BacktestRunRequest,
        ending_equity: float,
    ) -> float:
        """Annualize total return over the request date range."""
        if request.initial_capital <= 0:
            return 0.0
        elapsed_days = max((request.date_to - request.date_from).days, 1)
        growth_factor = ending_equity / request.initial_capital
        return ((growth_factor ** (365 / elapsed_days)) - 1) * 100

    @staticmethod
    def _calculate_win_rate_pct(trade_log: list[BacktestTradeLogEntry]) -> float:
        """Calculate percentage of completed trades with positive PnL."""
        if not trade_log:
            return 0.0
        wins = sum(1 for trade in trade_log if trade.pnl > 0)
        return (wins / len(trade_log)) * 100

    @staticmethod
    def _calculate_profit_factor(trade_log: list[BacktestTradeLogEntry]) -> float:
        """Calculate gross-profit-to-gross-loss ratio for completed trades."""
        gross_profit = sum(trade.pnl for trade in trade_log if trade.pnl > 0)
        gross_loss = abs(sum(trade.pnl for trade in trade_log if trade.pnl < 0))
        if gross_loss == 0:
            return 0.0 if gross_profit == 0 else gross_profit
        return gross_profit / gross_loss

    @staticmethod
    def _calculate_average_win_pct(trade_log: list[BacktestTradeLogEntry]) -> float:
        """Calculate average percent return across winning trades."""
        wins = [trade.pnl_pct for trade in trade_log if trade.pnl > 0]
        if not wins:
            return 0.0
        return sum(wins) / len(wins)

    @staticmethod
    def _calculate_average_loss_pct(trade_log: list[BacktestTradeLogEntry]) -> float:
        """Calculate average percent return across losing trades."""
        losses = [trade.pnl_pct for trade in trade_log if trade.pnl < 0]
        if not losses:
            return 0.0
        return sum(losses) / len(losses)

    @staticmethod
    def _calculate_expectancy(trade_log: list[BacktestTradeLogEntry]) -> float:
        """Calculate average PnL percent per completed trade."""
        if not trade_log:
            return 0.0
        return sum(trade.pnl_pct for trade in trade_log) / len(trade_log)
