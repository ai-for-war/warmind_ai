"""Google Sheets API Client.

Provides async interface for interacting with Google Sheets API
using service account authentication.
"""

import json
from typing import Any, Optional

import gspread
from gspread_asyncio import AsyncioGspreadClientManager
from google.oauth2.service_account import Credentials

from app.config.settings import get_settings
import os
from pathlib import Path


class GoogleSheetClientError(Exception):
    """Base exception for Google Sheet Client errors."""


class SheetNotAccessibleError(GoogleSheetClientError):
    """Raised when the service account cannot access the sheet."""


class SheetNotFoundError(GoogleSheetClientError):
    """Raised when the sheet or tab is not found."""


class GoogleSheetClient:
    """Async client for Google Sheets API.

    Uses service account authentication and gspread-asyncio
    for async operations.
    """

    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]

    def __init__(self):
        """Initialize the Google Sheet client."""
        self._manager: Optional[AsyncioGspreadClientManager] = None
        self._settings = get_settings()

    def _get_credentials(self) -> Credentials:
        """Create credentials from service account JSON.

        Supports both:
        - JSON string directly in env var
        - Path to JSON file (relative to project root or absolute)

        Returns:
            Google OAuth2 credentials with required scopes.
        """

        json_value = self._settings.GOOGLE_SERVICE_ACCOUNT_JSON

        # Check if it's a file path or JSON string
        if json_value.strip().startswith("{"):
            # It's a JSON string
            service_account_info = json.loads(json_value)
        else:
            # It's a file path - resolve relative to project root
            file_path = Path(json_value)
            if not file_path.is_absolute():
                # Get project root (where app/ folder is)
                project_root = Path(__file__).parent.parent.parent.parent
                file_path = project_root / json_value

            if not file_path.exists():
                raise FileNotFoundError(
                    f"Service account JSON file not found: {file_path}"
                )

            with open(file_path, "r", encoding="utf-8") as f:
                service_account_info = json.load(f)

        credentials = Credentials.from_service_account_info(
            service_account_info, scopes=self.SCOPES
        )
        return credentials

    def _get_manager(self) -> AsyncioGspreadClientManager:
        """Get or create the async gspread client manager.

        Returns:
            AsyncioGspreadClientManager instance.
        """
        if self._manager is None:
            self._manager = AsyncioGspreadClientManager(self._get_credentials)
        return self._manager

    async def _get_client(self) -> gspread.Client:
        """Get an authorized gspread client.

        Returns:
            Authorized gspread client.
        """
        manager = self._get_manager()
        agc = await manager.authorize()
        return agc

    async def check_access(self, sheet_id: str) -> bool:
        """Check if the service account can access a sheet.

        Args:
            sheet_id: The Google Sheet ID.

        Returns:
            True if accessible, False otherwise.
        """
        try:
            client = await self._get_client()
            await client.open_by_key(sheet_id)
            return True
        except gspread.exceptions.APIError as e:
            if e.response.status_code in (403, 404):
                return False
            raise GoogleSheetClientError(f"API error checking access: {e}") from e
        except Exception as e:
            raise GoogleSheetClientError(f"Error checking access: {e}") from e

    async def get_sheet_metadata(self, sheet_id: str) -> dict[str, Any]:
        """Get sheet metadata including title and available tabs.

        Args:
            sheet_id: The Google Sheet ID.

        Returns:
            Dictionary with 'title' and 'sheets' (list of tab names).

        Raises:
            SheetNotAccessibleError: If sheet cannot be accessed.
            GoogleSheetClientError: For other API errors.
        """
        try:
            client = await self._get_client()
            spreadsheet = await client.open_by_key(sheet_id)

            # Get all worksheet titles
            worksheets = await spreadsheet.worksheets()
            sheet_names = [ws.title for ws in worksheets]

            return {
                "title": spreadsheet.title,
                "sheets": sheet_names,
            }
        except gspread.exceptions.APIError as e:
            if e.response.status_code == 403:
                raise SheetNotAccessibleError(
                    f"Cannot access sheet. Please share with {self._settings.GOOGLE_SERVICE_ACCOUNT_EMAIL}"
                ) from e
            if e.response.status_code == 404:
                raise SheetNotFoundError(f"Sheet not found: {sheet_id}") from e
            raise GoogleSheetClientError(f"API error: {e}") from e
        except Exception as e:
            raise GoogleSheetClientError(f"Error getting metadata: {e}") from e

    async def get_sheet_values(
        self,
        sheet_id: str,
        sheet_name: str = "Sheet1",
        start_row: int = 1,
    ) -> list[list[str]]:
        """Fetch values from a sheet starting at a specific row.

        Args:
            sheet_id: The Google Sheet ID.
            sheet_name: Name of the worksheet/tab (default: "Sheet1").
            start_row: Row number to start from (1-indexed, default: 1).

        Returns:
            List of rows, where each row is a list of cell values as strings.

        Raises:
            SheetNotAccessibleError: If sheet cannot be accessed.
            SheetNotFoundError: If sheet or tab is not found.
            GoogleSheetClientError: For other API errors.
        """
        try:
            client = await self._get_client()
            spreadsheet = await client.open_by_key(sheet_id)

            try:
                worksheet = await spreadsheet.worksheet(sheet_name)
            except gspread.exceptions.WorksheetNotFound as exc:
                raise SheetNotFoundError(
                    f"Worksheet '{sheet_name}' not found in sheet"
                ) from exc

            # Get all values from the worksheet
            all_values = await worksheet.get_all_values()

            # Return rows starting from start_row (convert to 0-indexed)
            if start_row > len(all_values):
                return []

            return all_values[start_row - 1 :]

        except SheetNotFoundError:
            raise
        except gspread.exceptions.APIError as e:
            if e.response.status_code == 403:
                raise SheetNotAccessibleError(
                    f"Cannot access sheet. Please share with {self._settings.GOOGLE_SERVICE_ACCOUNT_EMAIL}"
                ) from e
            if e.response.status_code == 404:
                raise SheetNotFoundError(f"Sheet not found: {sheet_id}") from e
            raise GoogleSheetClientError(f"API error: {e}") from e
        except Exception as e:
            if isinstance(e, GoogleSheetClientError):
                raise
            raise GoogleSheetClientError(f"Error fetching values: {e}") from e

    async def get_headers(
        self,
        sheet_id: str,
        sheet_name: str = "Sheet1",
        header_row: int = 1,
    ) -> list[str]:
        """Get the header row from a sheet.

        Only fetches the specific header row, not the entire sheet.

        Args:
            sheet_id: The Google Sheet ID.
            sheet_name: Name of the worksheet/tab (default: "Sheet1").
            header_row: Row number containing headers (1-indexed, default: 1).

        Returns:
            List of header values as strings.

        Raises:
            SheetNotAccessibleError: If sheet cannot be accessed.
            SheetNotFoundError: If sheet or tab is not found.
            GoogleSheetClientError: For other API errors.
        """
        try:
            client = await self._get_client()
            spreadsheet = await client.open_by_key(sheet_id)

            try:
                worksheet = await spreadsheet.worksheet(sheet_name)
            except gspread.exceptions.WorksheetNotFound as exc:
                raise SheetNotFoundError(
                    f"Worksheet '{sheet_name}' not found in sheet"
                ) from exc

            # Fetch only the header row using row_values
            headers = await worksheet.row_values(header_row)
            return headers

        except SheetNotFoundError:
            raise
        except gspread.exceptions.APIError as e:
            if e.response.status_code == 403:
                email = self._settings.GOOGLE_SERVICE_ACCOUNT_EMAIL
                raise SheetNotAccessibleError(
                    f"Cannot access sheet. Please share with {email}"
                ) from e
            if e.response.status_code == 404:
                raise SheetNotFoundError(f"Sheet not found: {sheet_id}") from e
            raise GoogleSheetClientError(f"API error: {e}") from e
        except Exception as e:
            if isinstance(e, GoogleSheetClientError):
                raise
            raise GoogleSheetClientError(f"Error fetching headers: {e}") from e

    async def get_preview(
        self,
        sheet_id: str,
        sheet_name: str = "Sheet1",
        header_row: int = 1,
        data_start_row: int = 2,
        num_rows: int = 10,
    ) -> dict[str, Any]:
        """Get a preview of sheet data with headers.

        Only fetches the header row and the requested number of data rows,
        not the entire sheet.

        Args:
            sheet_id: The Google Sheet ID.
            sheet_name: Name of the worksheet/tab (default: "Sheet1").
            header_row: Row number containing headers (1-indexed, default: 1).
            data_start_row: Row number where data starts (1-indexed, default: 2).
            num_rows: Number of data rows to preview (default: 10, max: 50).

        Returns:
            Dictionary with 'headers', 'rows', and 'total_rows'.

        Raises:
            SheetNotAccessibleError: If sheet cannot be accessed.
            SheetNotFoundError: If sheet or tab is not found.
            GoogleSheetClientError: For other API errors.
        """
        num_rows = min(num_rows, 50)

        try:
            client = await self._get_client()
            spreadsheet = await client.open_by_key(sheet_id)

            try:
                worksheet = await spreadsheet.worksheet(sheet_name)
            except gspread.exceptions.WorksheetNotFound as exc:
                raise SheetNotFoundError(
                    f"Worksheet '{sheet_name}' not found in sheet"
                ) from exc

            # Fetch only header row
            headers = await worksheet.row_values(header_row)
            if not headers:
                return {"headers": [], "rows": [], "total_rows": 0}

            # Get total row count for total_rows calculation
            row_count = worksheet.row_count

            # Calculate end row for preview (only fetch needed rows)
            end_row = min(data_start_row + num_rows - 1, row_count)

            # Fetch only the preview range using batch_get for efficiency
            # Range format: "A{start}:{end}" fetches all columns
            if data_start_row <= row_count:
                data_range = f"{data_start_row}:{end_row}"
                data_rows = await worksheet.get_values(data_range)
            else:
                data_rows = []

            # Calculate actual total data rows (from data_start_row to end)
            total_data_rows = max(0, row_count - data_start_row + 1)

            # Convert rows to dictionaries using headers
            row_dicts = []
            for row in data_rows:
                row_dict = {
                    headers[i]: (row[i] if i < len(row) else "")
                    for i in range(len(headers))
                }
                row_dicts.append(row_dict)

            return {
                "headers": headers,
                "rows": row_dicts,
                "total_rows": total_data_rows,
            }

        except SheetNotFoundError:
            raise
        except gspread.exceptions.APIError as e:
            if e.response.status_code == 403:
                email = self._settings.GOOGLE_SERVICE_ACCOUNT_EMAIL
                raise SheetNotAccessibleError(
                    f"Cannot access sheet. Please share with {email}"
                ) from e
            if e.response.status_code == 404:
                raise SheetNotFoundError(f"Sheet not found: {sheet_id}") from e
            raise GoogleSheetClientError(f"API error: {e}") from e
        except Exception as e:
            if isinstance(e, GoogleSheetClientError):
                raise
            raise GoogleSheetClientError(f"Error fetching preview: {e}") from e
