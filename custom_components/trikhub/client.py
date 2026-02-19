"""TrikHub API client."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .const import (
    API_CONTENT,
    API_EXECUTE,
    API_HEALTH,
    API_TOOLS,
    API_TRIKS,
    API_TRIKS_INSTALL,
    API_TRIKS_RELOAD,
)

_LOGGER = logging.getLogger(__name__)


class TrikHubClientError(Exception):
    """Base exception for TrikHub client errors."""


class TrikHubConnectionError(TrikHubClientError):
    """Connection error to TrikHub server."""


class TrikHubAuthError(TrikHubClientError):
    """Authentication error with TrikHub server."""


class TrikHubClient:
    """HTTP client for TrikHub server."""

    def __init__(
        self,
        base_url: str,
        auth_token: str | None = None,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        """Initialize the TrikHub client.

        Args:
            base_url: The base URL of the TrikHub server.
            auth_token: Optional bearer token for authentication.
            session: Optional aiohttp session to use.
        """
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self._session = session
        self._owned_session = False

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session."""
        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._owned_session = True
        return self._session

    async def close(self) -> None:
        """Close the client session if we own it."""
        if self._owned_session and self._session:
            await self._session.close()
            self._session = None

    def _get_headers(self) -> dict[str, str]:
        """Get headers for API requests."""
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers

    async def _request(
        self,
        method: str,
        endpoint: str,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request to the TrikHub server.

        Args:
            method: HTTP method (GET, POST, DELETE).
            endpoint: API endpoint path.
            json_data: Optional JSON body for POST requests.

        Returns:
            Response data as a dictionary.

        Raises:
            TrikHubConnectionError: If connection fails.
            TrikHubAuthError: If authentication fails.
            TrikHubClientError: For other API errors.
        """
        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()

        try:
            async with session.request(
                method, url, headers=headers, json=json_data, timeout=30
            ) as response:
                if response.status == 401:
                    raise TrikHubAuthError("Authentication failed")
                if response.status == 403:
                    raise TrikHubAuthError("Access forbidden")

                data = await response.json()

                if response.status >= 400:
                    error_msg = data.get("error", f"HTTP {response.status}")
                    raise TrikHubClientError(error_msg)

                return data

        except aiohttp.ClientConnectorError as err:
            raise TrikHubConnectionError(
                f"Failed to connect to TrikHub server: {err}"
            ) from err
        except aiohttp.ClientError as err:
            raise TrikHubClientError(f"Request failed: {err}") from err

    async def health_check(self) -> dict[str, Any]:
        """Check if the TrikHub server is healthy.

        Returns:
            Health check response data.
        """
        return await self._request("GET", API_HEALTH)

    async def get_tools(self) -> list[dict[str, Any]]:
        """Fetch available tools from TrikHub server.

        Returns:
            List of tool definitions with name, description, and inputSchema.
        """
        data = await self._request("GET", API_TOOLS)
        return data.get("tools", [])

    async def get_triks(self) -> list[dict[str, Any]]:
        """Fetch information about available triks.

        Returns:
            List of trik info with id, name, description, and tools.
        """
        data = await self._request("GET", API_TOOLS)
        return data.get("triks", [])

    async def execute(
        self,
        tool: str,
        input_data: dict[str, Any],
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute a trik tool.

        Args:
            tool: Tool name in format 'trikId:actionName'.
            input_data: Input parameters matching the tool's inputSchema.
            session_id: Optional session ID for multi-turn interactions.

        Returns:
            Execution result with response data.
        """
        payload: dict[str, Any] = {"tool": tool, "input": input_data}
        if session_id:
            payload["sessionId"] = session_id

        return await self._request("POST", API_EXECUTE, payload)

    async def get_content(self, ref: str) -> dict[str, Any] | None:
        """Fetch passthrough content by reference.

        One-time delivery - content is deleted after retrieval.

        Args:
            ref: Content reference ID from execute response.

        Returns:
            Content data with content, contentType, and metadata, or None if not found.
        """
        try:
            return await self._request("GET", f"{API_CONTENT}/{ref}")
        except TrikHubClientError:
            return None

    async def list_installed_triks(self) -> list[dict[str, Any]]:
        """List all installed triks.

        Returns:
            List of installed trik info with name and version.
        """
        data = await self._request("GET", API_TRIKS)
        return data.get("triks", [])

    async def install_trik(self, package: str) -> dict[str, Any]:
        """Install a trik from the registry.

        Args:
            package: Package name (e.g., '@molefas/trik-article-search').

        Returns:
            Installation result.
        """
        return await self._request("POST", API_TRIKS_INSTALL, {"package": package})

    async def uninstall_trik(self, name: str) -> dict[str, Any]:
        """Uninstall a trik.

        Args:
            name: Trik name to uninstall.

        Returns:
            Uninstallation result.
        """
        # URL encode the name for path parameter
        encoded_name = name.replace("@", "%40").replace("/", "%2F")
        return await self._request("DELETE", f"{API_TRIKS}/{encoded_name}")

    async def reload_triks(self) -> dict[str, Any]:
        """Reload all triks.

        Returns:
            Reload result with count of loaded triks.
        """
        return await self._request("POST", API_TRIKS_RELOAD)

    def convert_tool_to_llm_format(
        self, tool: dict[str, Any]
    ) -> dict[str, Any]:
        """Convert a TrikHub tool definition to LLM tool format.

        Args:
            tool: TrikHub tool definition.

        Returns:
            Tool definition in LLM-compatible format.
        """
        return {
            "type": "function",
            "function": {
                "name": f"trik_{tool['name'].replace(':', '_')}",
                "description": tool.get("description", ""),
                "parameters": tool.get("inputSchema", {"type": "object", "properties": {}}),
            },
        }
