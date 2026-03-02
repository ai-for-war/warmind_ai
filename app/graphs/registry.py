"""Graph registry for managing LangGraph workflows.

Provides factory functions to create and retrieve graph instances.
"""

from typing import TYPE_CHECKING, Any, Callable, Dict

from langgraph.graph.state import CompiledStateGraph

if TYPE_CHECKING:
    pass  # Type hints only, no runtime imports

# Registry of graph factories
_graph_registry: Dict[str, Callable[..., CompiledStateGraph]] = {}


def register_graph(name: str, factory: Callable[..., CompiledStateGraph]) -> None:
    """Register a graph factory function.

    Args:
        name: Unique identifier for the graph
        factory: Factory function that creates the compiled graph
    """
    _graph_registry[name] = factory


def get_graph(name: str, **kwargs: Any) -> CompiledStateGraph:
    """Get a compiled graph by name.

    Args:
        name: The registered graph name
        **kwargs: Arguments to pass to the graph factory

    Returns:
        Compiled LangGraph StateGraph

    Raises:
        KeyError: If graph name is not registered
    """
    if name not in _graph_registry:
        raise KeyError(
            f"Graph '{name}' not found. Available: {list(_graph_registry.keys())}"
        )
    return _graph_registry[name](**kwargs)


def list_graphs() -> list[str]:
    """List all registered graph names."""
    return list(_graph_registry.keys())


def get_chat_workflow(user_connections: list[dict] | None = None) -> CompiledStateGraph:
    """Get a compiled chat workflow instance.

    This is a convenience function that creates a chat workflow
    with lazy import to avoid circular dependencies.

    Args:
        user_connections: Optional list of user's sheet connections with schemas

    Returns:
        Compiled LangGraph StateGraph ready for execution
    """
    # Lazy import to avoid circular dependency
    from app.graphs.workflows.chat_workflow.graph import create_chat_workflow

    return create_chat_workflow(user_connections)


# Register built-in workflows using lazy factory
register_graph("chat_workflow", get_chat_workflow)
