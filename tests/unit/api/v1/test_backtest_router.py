from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
BACKTEST_ROUTER_PATH = ROOT / "app" / "api" / "v1" / "backtests" / "router.py"
API_V1_ROUTER_PATH = ROOT / "app" / "api" / "v1" / "router.py"


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _router_assignment(module: ast.Module) -> ast.Call:
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "router":
                    if isinstance(node.value, ast.Call):
                        return node.value
    raise AssertionError("router assignment was not found")


def _function_def(module: ast.Module, name: str) -> ast.AsyncFunctionDef:
    for node in module.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return node
    raise AssertionError(f"Function {name} was not found")


def _decorator_path_and_method(function_def: ast.AsyncFunctionDef) -> tuple[str, str]:
    for decorator in function_def.decorator_list:
        if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
            method = decorator.func.attr.upper()
            if decorator.args and isinstance(decorator.args[0], ast.Constant):
                return str(decorator.args[0].value), method
    raise AssertionError(f"No route decorator was found on {function_def.name}")


def _depends_targets(function_def: ast.AsyncFunctionDef) -> set[str]:
    dependency_names: set[str] = set()
    positional_args = function_def.args.args
    defaults = function_def.args.defaults
    default_offset = len(positional_args) - len(defaults)

    for index, argument in enumerate(positional_args):
        if index < default_offset:
            continue
        default = defaults[index - default_offset]
        if not isinstance(default, ast.Call):
            continue
        if isinstance(default.func, ast.Name) and default.func.id == "Depends":
            if default.args and isinstance(default.args[0], ast.Name):
                dependency_names.add(default.args[0].id)
    return dependency_names


def test_backtest_router_uses_dedicated_domain_prefix_and_tag() -> None:
    module = _parse(BACKTEST_ROUTER_PATH)
    router_call = _router_assignment(module)

    kwargs = {
        keyword.arg: keyword.value
        for keyword in router_call.keywords
        if keyword.arg is not None
    }

    assert isinstance(kwargs["prefix"], ast.Constant)
    assert kwargs["prefix"].value == "/backtests"
    assert isinstance(kwargs["tags"], ast.List)
    assert [elt.value for elt in kwargs["tags"].elts] == ["backtests"]


def test_backtest_router_declares_template_and_run_handlers() -> None:
    module = _parse(BACKTEST_ROUTER_PATH)

    templates_handler = _function_def(module, "list_backtest_templates")
    run_handler = _function_def(module, "run_backtest")

    assert _decorator_path_and_method(templates_handler) == ("/templates", "GET")
    assert _decorator_path_and_method(run_handler) == ("/run", "POST")


def test_backtest_router_wires_auth_and_service_dependencies() -> None:
    module = _parse(BACKTEST_ROUTER_PATH)

    templates_dependencies = _depends_targets(
        _function_def(module, "list_backtest_templates")
    )
    run_dependencies = _depends_targets(_function_def(module, "run_backtest"))

    expected = {
        "get_current_active_user",
        "get_current_organization_context",
        "get_backtest_service",
    }

    assert templates_dependencies == expected
    assert run_dependencies == expected


def test_backtest_router_is_registered_in_aggregate_v1_router() -> None:
    source = API_V1_ROUTER_PATH.read_text(encoding="utf-8")

    assert "from app.api.v1.backtests.router import router as backtests_router" in source
    assert "router.include_router(backtests_router)" in source
