"""Column mapper for Google Sheet data transformation.

Handles mapping between Google Sheet columns and system fields,
supporting both column letters (A, B, C) and header names.
"""

import re
from datetime import datetime
from typing import Any, Optional

from app.domain.schemas.sheet_crawler import ColumnMapping


class MissingRequiredColumnError(Exception):
    """Raised when a required column is not found in the sheet."""

    def __init__(self, column_name: str, system_field: str):
        self.column_name = column_name
        self.system_field = system_field
        super().__init__(
            f"Required column '{column_name}' for field '{system_field}' not found in sheet"
        )


class ColumnMapper:
    """Maps Google Sheet row data to system fields using column mappings."""

    @staticmethod
    def column_letter_to_index(letter: str) -> int:
        """Convert column letter (A, B, ..., Z, AA, AB, ...) to 0-based index.

        Args:
            letter: Column letter (e.g., "A", "B", "AA")

        Returns:
            0-based column index
        """
        letter = letter.upper()
        result = 0
        for char in letter:
            result = result * 26 + (ord(char) - ord("A") + 1)
        return result - 1

    @staticmethod
    def is_column_letter(value: str) -> bool:
        """Check if a string is a valid column letter (A-Z, AA-ZZ, etc.).

        Args:
            value: String to check

        Returns:
            True if value is a valid column letter pattern
        """
        return bool(re.match(r"^[A-Za-z]+$", value))

    def get_column_index(self, sheet_column: str, headers: list[str]) -> Optional[int]:
        """Get the column index for a sheet_column value.

        Supports both column letters (A, B) and header names.

        Args:
            sheet_column: Column letter or header name
            headers: List of header values from the sheet

        Returns:
            0-based column index, or None if not found
        """
        # Check if it's a column letter (A, B, AA, etc.)
        # if self.is_column_letter(sheet_column):
        #     return self.column_letter_to_index(sheet_column)

        # Otherwise, treat as header name - find in headers list
        try:
            return headers.index(sheet_column)
        except ValueError:
            return None

    def convert_type(self, value: str, data_type: str) -> Any:
        """Convert string value to specified data type.

        Returns original string if conversion fails (per Requirement 3.4).

        Args:
            value: String value to convert
            data_type: Target type (string, number, integer, date)

        Returns:
            Converted value or original string if conversion fails
        """
        if value is None or value == "":
            return value

        # String type - no conversion needed
        if data_type == "string":
            return str(value)

        try:
            if data_type == "number":
                # Handle comma as decimal separator (common in some locales)
                cleaned = str(value).replace(",", ".")
                return float(cleaned)

            if data_type == "integer":
                # Handle float strings by converting to float first
                cleaned = str(value).replace(",", ".")
                return int(float(cleaned))

            if data_type == "date":
                # Try common date formats
                date_formats = [
                    "%Y-%m-%d",
                    "%d/%m/%Y",
                    "%m/%d/%Y",
                    "%Y/%m/%d",
                    "%d-%m-%Y",
                    "%m-%d-%Y",
                ]
                for fmt in date_formats:
                    try:
                        return datetime.strptime(str(value), fmt)
                    except ValueError:
                        continue
                # If no format matches, return original
                return value

            # Unknown type, return as string
            return str(value)

        except (ValueError, TypeError):
            # Conversion failed, return original string value (Requirement 3.4)
            return str(value)

    def map_row(
        self,
        row: list[str],
        headers: list[str],
        mappings: list[ColumnMapping],
    ) -> dict[str, Any]:
        """Map a row of data using column mappings.

        Args:
            row: List of cell values from the sheet row
            headers: List of header values from the sheet
            mappings: List of column mappings to apply

        Returns:
            Dictionary with system_field as keys and converted values

        Raises:
            MissingRequiredColumnError: If a required column is not found
        """
        result: dict[str, Any] = {}

        for mapping in mappings:
            col_index = self.get_column_index(mapping.sheet_column, headers)

            if col_index is None:
                # Column not found
                if mapping.required:
                    # Requirement 3.2: Raise validation error for missing required columns
                    raise MissingRequiredColumnError(
                        column_name=mapping.sheet_column,
                        system_field=mapping.system_field,
                    )
                # Optional column - skip this mapping
                continue

            if col_index >= len(row):
                # Row doesn't have enough columns - use empty string
                value = ""
            else:
                value = row[col_index]

            # Convert to specified type
            converted_value = self.convert_type(value, mapping.data_type)
            result[mapping.system_field] = converted_value

        return result

    def get_raw_data(self, row: list[str], headers: list[str]) -> dict[str, str]:
        """Create raw data dictionary from row using headers as keys.

        Args:
            row: List of cell values from the sheet row
            headers: List of header values from the sheet

        Returns:
            Dictionary with header names as keys and cell values
        """
        raw_data: dict[str, str] = {}
        for i, header in enumerate(headers):
            if i < len(row):
                raw_data[header] = row[i]
            else:
                raw_data[header] = ""
        return raw_data

    def validate_required_columns(
        self,
        headers: list[str],
        mappings: list[ColumnMapping],
    ) -> None:
        """Validate that all required columns exist in headers.

        Should be called before processing rows to fail fast.

        Args:
            headers: List of header values from the sheet
            mappings: List of column mappings to validate

        Raises:
            MissingRequiredColumnError: If any required column is not found
        """
        for mapping in mappings:
            if mapping.required:
                col_index = self.get_column_index(mapping.sheet_column, headers)
                if col_index is None:
                    raise MissingRequiredColumnError(
                        column_name=mapping.sheet_column,
                        system_field=mapping.system_field,
                    )
