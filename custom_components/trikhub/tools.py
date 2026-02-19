"""
Tool loading for TrikHub LangGraph agent.

Creates LangChain tools from TrikHub server API for use with LangGraph.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, create_model

from .client import TrikHubClient, TrikHubClientError

_LOGGER = logging.getLogger(__name__)


# =============================================================================
# JSON Schema to Pydantic Conversion
# =============================================================================


def _get_python_type(schema: dict[str, Any]) -> type:
    """
    Convert a JSON Schema type to a Python type.

    Args:
        schema: JSON Schema dictionary

    Returns:
        Corresponding Python type
    """
    schema_type = schema.get("type")

    # Handle enum
    if "enum" in schema:
        enum_values = tuple(schema["enum"])
        return Literal[enum_values]  # type: ignore

    # Handle basic types
    if schema_type == "string":
        return str
    elif schema_type == "number":
        return float
    elif schema_type == "integer":
        return int
    elif schema_type == "boolean":
        return bool
    elif schema_type == "null":
        return type(None)
    elif schema_type == "array":
        items_schema = schema.get("items", {})
        item_type = _get_python_type(items_schema)
        return list[item_type]  # type: ignore
    elif schema_type == "object":
        return dict[str, Any]
    else:
        return Any  # type: ignore


def json_schema_to_pydantic(
    schema: dict[str, Any],
    model_name: str = "DynamicModel",
) -> type[BaseModel]:
    """
    Convert a JSON Schema to a Pydantic model.

    Args:
        schema: JSON Schema dictionary (must be an object schema)
        model_name: Name for the generated Pydantic model

    Returns:
        A dynamically created Pydantic model class
    """
    if schema.get("type") != "object":
        # For non-object schemas, wrap in a simple model
        return create_model(model_name, value=(_get_python_type(schema), ...))

    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    field_definitions: dict[str, Any] = {}

    for prop_name, prop_schema in properties.items():
        python_type = _get_python_type(prop_schema)
        description = prop_schema.get("description", "")

        if prop_name in required:
            # Required field
            field_definitions[prop_name] = (
                python_type,
                Field(description=description) if description else ...,
            )
        else:
            # Optional field (also nullable for OpenAI compatibility)
            field_definitions[prop_name] = (
                python_type | None,
                Field(default=None, description=description) if description else None,
            )

    return create_model(model_name, **field_definitions)


# =============================================================================
# Tool Name Conversion
# =============================================================================


def _to_tool_name(gateway_name: str) -> str:
    """
    Convert a gateway tool name to a LangChain-compatible tool name.

    LangChain tool names must be valid Python identifiers.
    Example: "@molefas/article-search:list" -> "molefas_article_search__list"
    """
    return (
        gateway_name.replace("@", "")
        .replace("/", "_")
        .replace("-", "_")
        .replace(":", "__")
    )


def _from_tool_name(langchain_name: str) -> str:
    """
    Convert a LangChain tool name back to gateway format.

    Example: "molefas_article_search__list" -> "article-search:list"
    (Note: We lose the @ prefix, but it's not needed for execution)
    """
    # Split on __ to get trik_id and action
    parts = langchain_name.split("__")
    if len(parts) == 2:
        trik_id = parts[0].replace("_", "-")
        action = parts[1]
        return f"{trik_id}:{action}"
    return langchain_name.replace("_", "-")


@dataclass
class PassthroughContent:
    """Content delivered directly to the user (passthrough mode)."""

    content_type: str
    content: str  # The actual content to display to the user
    metadata: dict[str, Any] | None = None


@dataclass
class TrikToolsResult:
    """Result from loading tools from TrikHub server."""

    tools: list[StructuredTool] = field(default_factory=list)
    tool_schemas: dict[str, dict[str, Any]] = field(default_factory=dict)
    loaded_triks: list[str] = field(default_factory=list)
    sessions: dict[str, str] = field(default_factory=dict)  # trik_id -> session_id


def _normalize_input(input_data: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize input data to match expected schema types.

    Handles common LLM mistakes like passing a string when an array is expected,
    or passing null/None values.
    """
    if schema.get("type") != "object":
        return input_data

    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    result = dict(input_data)

    # Remove None values for optional fields (LLM often sends null for optional params)
    keys_to_remove = []
    for key, value in result.items():
        if value is None and key not in required:
            keys_to_remove.append(key)
    for key in keys_to_remove:
        del result[key]
        _LOGGER.debug("[Normalize] Removed null optional field: %s", key)

    for key, prop_schema in properties.items():
        if key not in result:
            continue

        value = result[key]
        expected_type = prop_schema.get("type")

        # Skip if value is None (will be handled by server validation)
        if value is None:
            continue

        # Coerce string to array if schema expects array
        if expected_type == "array":
            if isinstance(value, str):
                _LOGGER.debug("[Normalize] Coercing %s from string to array", key)
                result[key] = [value]
            elif isinstance(value, dict):
                # LLM sometimes passes object, wrap in array
                _LOGGER.debug("[Normalize] Coercing %s from object to array", key)
                result[key] = [value]
            elif not isinstance(value, list):
                # Wrap any non-list value in an array
                _LOGGER.debug("[Normalize] Coercing %s from %s to array", key, type(value).__name__)
                result[key] = [value]

        # Coerce to string if schema expects string
        elif expected_type == "string":
            if isinstance(value, list) and len(value) > 0:
                _LOGGER.debug("[Normalize] Coercing %s from array to string", key)
                result[key] = str(value[0])
            elif isinstance(value, list) and len(value) == 0:
                # Empty array, remove the field
                del result[key]
                _LOGGER.debug("[Normalize] Removed empty array field: %s", key)
            elif not isinstance(value, str):
                _LOGGER.debug("[Normalize] Coercing %s from %s to string", key, type(value).__name__)
                result[key] = str(value)

    _LOGGER.debug("[Normalize] Result: %s", result)
    return result


def _create_tool_function(
    client: TrikHubClient,
    tool_name: str,
    trik_id: str,
    sessions: dict[str, str],
    input_schema: dict[str, Any] | None = None,
    on_passthrough: Callable[[PassthroughContent], None] | None = None,
    debug: bool = False,
) -> Callable[..., str]:
    """
    Create a tool function that calls the TrikHub server.

    Args:
        client: TrikHub API client
        tool_name: Tool name in format 'trikId:actionName'
        trik_id: The trik identifier (for session tracking)
        sessions: Shared session storage dict (trik_id -> session_id)
        input_schema: JSON Schema for input (used for normalization)
        on_passthrough: Callback for passthrough content
        debug: Enable debug logging

    Returns:
        Async function that executes the tool
    """

    async def tool_func(**kwargs: Any) -> str:
        """Execute the tool via TrikHub server."""
        # Log raw input for debugging
        _LOGGER.debug("[Tool] %s raw input: %s", tool_name, kwargs)

        # Normalize input to handle LLM mistakes (e.g., string instead of array)
        normalized_kwargs = _normalize_input(kwargs, input_schema or {})

        # Get existing session ID for this trik
        session_id = sessions.get(trik_id)

        _LOGGER.debug("[Tool] %s: input=%s, session=%s", tool_name, normalized_kwargs, session_id)

        try:
            result = await client.execute(tool_name, normalized_kwargs, session_id=session_id)

            # Store session ID from response for future calls
            if result.get("sessionId"):
                sessions[trik_id] = result["sessionId"]
                if debug:
                    _LOGGER.debug("[Tool] Session tracked for %s: %s", trik_id, result["sessionId"])

            # Check for errors - server returns responseMode for success, error field for failures
            if result.get("error"):
                error = result.get("error", "Unknown error")
                _LOGGER.warning(
                    "[Tool] Error from server for %s: %s (sent: %s)",
                    tool_name, error, normalized_kwargs
                )
                return json.dumps({"success": False, "error": error})

            # Handle passthrough mode - fetch content and deliver to user
            if result.get("responseMode") == "passthrough":
                content_ref = result.get("userContentRef")
                content_type = result.get("contentType", "text/plain")

                if content_ref:
                    # Fetch the actual content from the server
                    content_result = await client.get_content(content_ref)

                    # Content endpoint returns {content: {...}, receipt: {...}}
                    if content_result and content_result.get("content"):
                        content_data = content_result.get("content", {})

                        # Deliver to user via callback
                        if on_passthrough:
                            on_passthrough(
                                PassthroughContent(
                                    content_type=content_data.get("contentType", content_type),
                                    content=content_data.get("content", ""),
                                    metadata=content_data.get("metadata"),
                                )
                            )

                        if debug:
                            _LOGGER.debug(
                                "[Tool] Delivered passthrough content: %s (%d chars)",
                                content_type,
                                len(content_data.get("content", "")),
                            )
                    else:
                        _LOGGER.warning(
                            "[Tool] Failed to fetch passthrough content for ref: %s",
                            content_ref,
                        )

                # Tell agent content was delivered (agent never sees the actual content)
                return json.dumps(
                    {"success": True, "delivered": "Content delivered directly to user"}
                )

            # Handle template mode
            if result.get("responseMode") == "template":
                response = result.get("response", "")

                if debug:
                    _LOGGER.debug("[Tool] Template response: %s", response[:100])

                return json.dumps({"success": True, "response": response})

            # Fallback: return the raw result
            return json.dumps(result)

        except TrikHubClientError as err:
            _LOGGER.error("Tool execution failed: %s", err)
            return json.dumps({"success": False, "error": str(err)})

    return tool_func


async def load_trik_tools(
    client: TrikHubClient,
    on_passthrough: Callable[[PassthroughContent], None] | None = None,
    debug: bool = False,
) -> TrikToolsResult:
    """
    Load tools from the TrikHub server and convert them to LangChain tools.

    Args:
        client: TrikHub API client
        on_passthrough: Callback for passthrough content
        debug: Enable debug logging

    Returns:
        TrikToolsResult with LangChain tools and metadata
    """
    try:
        # Fetch tools from the server
        server_tools = await client.get_tools()
        triks = await client.get_triks()

        tools: list[StructuredTool] = []
        tool_schemas: dict[str, dict[str, Any]] = {}
        loaded_triks: list[str] = [trik.get("id", "") for trik in triks]
        sessions: dict[str, str] = {}  # Shared session storage for all tools

        if debug:
            _LOGGER.debug(
                "[LangChainAdapter] Creating %d tools from server", len(server_tools)
            )

        for tool_def in server_tools:
            tool_name = tool_def.get("name", "")
            description = tool_def.get("description", "No description")
            input_schema = tool_def.get("inputSchema", {})

            if not tool_name:
                continue

            # Extract trik ID from tool name (format: "trik-id:action-name")
            trik_id = tool_name.split(":")[0] if ":" in tool_name else tool_name

            # Create a LangChain-safe function name
            langchain_name = _to_tool_name(tool_name)

            # Store the schema for reference
            tool_schemas[langchain_name] = {
                "original_name": tool_name,
                "schema": input_schema,
            }

            # Create the tool function with session tracking
            tool_func = _create_tool_function(
                client, tool_name, trik_id, sessions, input_schema, on_passthrough, debug
            )

            # Convert JSON Schema to Pydantic model for proper argument handling
            try:
                pydantic_model = json_schema_to_pydantic(
                    input_schema, model_name=f"{langchain_name}_Input"
                )
            except Exception as err:
                _LOGGER.warning(
                    "Failed to create Pydantic model for %s: %s, using raw kwargs",
                    tool_name,
                    err,
                )
                pydantic_model = None

            # Create the StructuredTool
            tool = StructuredTool.from_function(
                coroutine=tool_func,
                name=langchain_name,
                description=description,
                args_schema=pydantic_model,
            )

            tools.append(tool)

            if debug:
                _LOGGER.debug("  - %s -> %s", tool_name, langchain_name)

        _LOGGER.info("Loaded %d tools from %d triks", len(tools), len(loaded_triks))

        return TrikToolsResult(
            tools=tools,
            tool_schemas=tool_schemas,
            loaded_triks=loaded_triks,
            sessions=sessions,
        )

    except TrikHubClientError as err:
        _LOGGER.error("Failed to load tools from TrikHub server: %s", err)
        return TrikToolsResult()


def create_dynamic_tool(
    client: TrikHubClient,
    name: str,
    description: str,
    input_schema: dict[str, Any],
    sessions: dict[str, str] | None = None,
    on_passthrough: Callable[[PassthroughContent], None] | None = None,
    debug: bool = False,
) -> StructuredTool:
    """
    Create a single dynamic LangChain tool for a TrikHub tool.

    Args:
        client: TrikHub API client
        name: Tool name (trikId:actionName format)
        description: Tool description
        input_schema: JSON Schema for input
        sessions: Optional shared session storage dict
        on_passthrough: Callback for passthrough content
        debug: Enable debug logging

    Returns:
        LangChain StructuredTool
    """
    langchain_name = _to_tool_name(name)
    trik_id = name.split(":")[0] if ":" in name else name
    sessions = sessions or {}
    tool_func = _create_tool_function(
        client, name, trik_id, sessions, input_schema, on_passthrough, debug
    )

    # Convert JSON Schema to Pydantic model
    try:
        pydantic_model = json_schema_to_pydantic(
            input_schema, model_name=f"{langchain_name}_Input"
        )
    except Exception:
        pydantic_model = None

    return StructuredTool.from_function(
        coroutine=tool_func,
        name=langchain_name,
        description=description,
        args_schema=pydantic_model,
    )
