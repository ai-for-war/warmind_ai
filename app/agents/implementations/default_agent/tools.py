"""Tools for the default agent."""

import re

from langchain_core.tools import tool


@tool
def calculator(expression: str) -> str:
    """Evaluate a mathematical expression safely.

    Only allows basic mathematical operations: +, -, *, /, parentheses,
    decimal points, and spaces. Returns the result or an error message.

    Args:
        expression: A mathematical expression to evaluate (e.g., "2 + 3 * 4")

    Returns:
        The result of the calculation as a string, or an error message.
    """
    # Only allow digits, basic operators, parentheses, decimal points, and spaces
    allowed_pattern = r"^[\d\+\-\*\/\.\(\)\s]+$"

    if not re.match(allowed_pattern, expression):
        return "Error: Invalid expression. Only digits and basic operators (+, -, *, /, ., (, )) are allowed."

    # Check for empty expression after stripping
    if not expression.strip():
        return "Error: Empty expression."

    try:
        # Evaluate the expression safely
        result = eval(expression, {"__builtins__": {}}, {})
        return str(result)
    except ZeroDivisionError:
        return "Error: Division by zero."
    except SyntaxError:
        return "Error: Invalid syntax in expression."
    except Exception as e:
        return f"Error: Could not evaluate expression. {str(e)}"
