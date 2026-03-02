"""Sheet type detection based on sheet name."""

from app.domain.schemas.analytics import SheetType


def detect_sheet_type(sheet_name: str) -> SheetType:
    """
    Detect sheet type from sheet name (case-insensitive).

    Args:
        sheet_name: The name of the sheet to detect type for.

    Returns:
        SheetType: The detected sheet type. Defaults to ORDERS if no match.

    Examples:
        >>> detect_sheet_type("Orders")
        SheetType.ORDERS
        >>> detect_sheet_type("order_items")
        SheetType.ORDER_ITEMS
        >>> detect_sheet_type("CUSTOMERS")
        SheetType.CUSTOMERS
        >>> detect_sheet_type("unknown")
        SheetType.ORDERS  # Default
    """
    name_lower = sheet_name.lower().strip()

    if name_lower == "orders":
        return SheetType.ORDERS
    elif name_lower == "order_items":
        return SheetType.ORDER_ITEMS
    elif name_lower == "customers":
        return SheetType.CUSTOMERS
    elif name_lower == "products":
        return SheetType.PRODUCTS
    else:
        return SheetType.ORDERS  # Default to orders if no match
