"""
TrikHub Conversation Entity using LangGraph for Home Assistant Assist.

This module creates a LangGraph-based conversation agent that uses TrikHub
tools (Triks) alongside Home Assistant's native capabilities.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode

# Import LLM providers at module level to avoid blocking event loop
try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None  # type: ignore

try:
    from langchain_anthropic import ChatAnthropic
except ImportError:
    ChatAnthropic = None  # type: ignore

try:
    from langchain_ollama import ChatOllama
except ImportError:
    ChatOllama = None  # type: ignore

from homeassistant.components import conversation
from homeassistant.components.conversation import (
    ConversationEntity,
    ConversationEntityFeature,
    ConversationInput,
    ConversationResult,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import ulid

from .client import TrikHubClient
from .const import (
    CONF_LLM_API_KEY,
    CONF_LLM_MODEL,
    CONF_LLM_PROVIDER,
    DOMAIN,
    LLM_PROVIDER_ANTHROPIC,
    LLM_PROVIDER_OLLAMA,
    LLM_PROVIDER_OPENAI,
)
from .tools import load_trik_tools, PassthroughContent

_LOGGER = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a helpful Home Assistant AI assistant with access to various tools.

IMPORTANT RULES for TrikHub Tools:

1. **Template Mode Tools** (like "search"): These return a text response like "I found 3 articles".
   - Just relay this response to the user and STOP
   - Do NOT automatically call other tools to show more details
   - Wait for the user to ask for more information

2. **Passthrough Mode Tools** (like "list", "details"): These deliver content directly to the user.
   - Only call these when the user explicitly asks (e.g., "show me the list", "tell me about the first one")
   - When they return "Content delivered directly to user", just acknowledge briefly
   - Do NOT repeat or summarize the content

3. **One tool at a time**: After a tool succeeds, return the response to the user.
   Do not chain multiple tool calls unless the user explicitly asks for multiple things.

4. **General**: Be concise. If a tool returns an error, explain briefly what went wrong.

Available tools will be shown in your tool list."""


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TrikHub conversation entity from a config entry."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    client = data["client"]
    config = data["config"]

    async_add_entities([TrikHubConversationEntity(config_entry, client, config, hass)])


class TrikHubConversationEntity(
    ConversationEntity, conversation.AbstractConversationAgent
):
    """TrikHub conversation entity using LangGraph with Trik tools."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = ConversationEntityFeature.CONTROL

    def __init__(
        self,
        config_entry: ConfigEntry,
        client: TrikHubClient,
        config: dict[str, Any],
        hass: HomeAssistant,
    ) -> None:
        """Initialize the TrikHub conversation entity."""
        self._config_entry = config_entry
        self._client = client
        self._config = config
        self._hass = hass
        self._attr_unique_id = f"{config_entry.entry_id}_conversation"

        # LangGraph components (initialized lazily)
        self._graph: Any = None
        self._tools: list[Any] = []
        self._llm: Any = None

        # Passthrough content storage
        self._last_passthrough: PassthroughContent | None = None

        # Conversation history storage (per conversation_id)
        self._conversation_history: dict[str, list[Any]] = {}

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Return supported languages."""
        return "*"

    async def async_added_to_hass(self) -> None:
        """Initialize the graph when entity is added to Home Assistant.

        Note: The first LLM API call may trigger a "blocking call to
        load_verify_locations" warning from Home Assistant. This is caused by
        the langchain_anthropic SDK creating SSL contexts lazily during async
        calls. This is an upstream issue and doesn't affect functionality.
        """
        await super().async_added_to_hass()
        try:
            await self._initialize_graph()
        except Exception as err:
            _LOGGER.warning("Failed to pre-initialize LangGraph: %s", err)

    def _handle_passthrough(self, content: PassthroughContent) -> None:
        """Store passthrough content for retrieval."""
        self._last_passthrough = content
        _LOGGER.debug("Received passthrough content: %s", content.content_type)

    def _get_llm(self) -> Any:
        """Get the configured LLM instance."""
        provider = self._config.get(CONF_LLM_PROVIDER, LLM_PROVIDER_OPENAI)
        api_key = self._config.get(CONF_LLM_API_KEY)
        model = self._config.get(CONF_LLM_MODEL, "gpt-4o-mini")

        if provider == LLM_PROVIDER_OPENAI:
            if ChatOpenAI is None:
                raise ValueError("langchain_openai is not installed")
            return ChatOpenAI(
                model=model,
                api_key=api_key,
                temperature=0.7,
            )

        elif provider == LLM_PROVIDER_ANTHROPIC:
            if ChatAnthropic is None:
                raise ValueError("langchain_anthropic is not installed")
            return ChatAnthropic(
                model=model,
                api_key=api_key,
                temperature=0.7,
            )

        elif provider == LLM_PROVIDER_OLLAMA:
            if ChatOllama is None:
                raise ValueError("langchain_ollama is not installed")
            # For Ollama, api_key is actually the base URL
            return ChatOllama(
                model=model,
                base_url=api_key or "http://localhost:11434",
                temperature=0.7,
            )

        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

    async def _initialize_graph(self) -> None:
        """Initialize the LangGraph agent with tools."""
        _LOGGER.info("Initializing LangGraph agent...")

        # Load tools from TrikHub server
        tools_result = await load_trik_tools(
            self._client,
            on_passthrough=self._handle_passthrough,
        )
        self._tools = tools_result.tools

        if not self._tools:
            _LOGGER.warning("No tools loaded from TrikHub server")

        # Get the LLM
        self._llm = self._get_llm()

        # Bind tools to LLM
        if self._tools:
            llm_with_tools = self._llm.bind_tools(self._tools)
        else:
            llm_with_tools = self._llm

        # Create the agent node
        async def call_model(state: MessagesState) -> dict[str, Any]:
            """Call the model with the current messages."""
            messages = state["messages"]

            # Add system prompt if not present
            if not messages or not isinstance(messages[0], SystemMessage):
                messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(messages)

            response = await llm_with_tools.ainvoke(messages)
            return {"messages": [response]}

        # Create the routing function
        def should_continue(state: MessagesState) -> Literal["tools", "__end__"]:
            """Determine if we should continue to tools or end."""
            messages = state["messages"]
            last_message = messages[-1]

            if isinstance(last_message, AIMessage) and last_message.tool_calls:
                return "tools"
            return "__end__"

        # Build the graph
        workflow = StateGraph(MessagesState)

        # Add nodes
        workflow.add_node("agent", call_model)
        if self._tools:
            workflow.add_node("tools", ToolNode(self._tools))

        # Add edges
        workflow.add_edge(START, "agent")

        if self._tools:
            workflow.add_conditional_edges(
                "agent",
                should_continue,
                ["tools", END],
            )
            workflow.add_edge("tools", "agent")
        else:
            workflow.add_edge("agent", END)

        # Compile the graph
        self._graph = workflow.compile()

        _LOGGER.info(
            "LangGraph agent initialized with %d tools from %d triks",
            len(self._tools),
            len(tools_result.loaded_triks),
        )

    async def async_process(
        self, user_input: ConversationInput
    ) -> ConversationResult:
        """Process a user input using the LangGraph agent."""
        conversation_id = user_input.conversation_id or ulid.ulid()

        try:
            # Initialize graph if needed
            if self._graph is None:
                await self._initialize_graph()

            # Get or create conversation history for this conversation_id
            if conversation_id not in self._conversation_history:
                self._conversation_history[conversation_id] = []

            messages = self._conversation_history[conversation_id]

            # Add the new user message
            messages.append(HumanMessage(content=user_input.text))

            # Run the graph with full conversation history
            _LOGGER.debug(
                "Running LangGraph with %d messages, latest: %s",
                len(messages),
                user_input.text,
            )

            result = await self._graph.ainvoke(
                {"messages": messages},
                config={"configurable": {"thread_id": conversation_id}},
            )

            # Update conversation history with full result (includes tool calls, responses, etc.)
            result_messages = result.get("messages", [])
            self._conversation_history[conversation_id] = list(result_messages)

            # Extract the final response from the agent
            agent_response_text = ""

            for msg in reversed(result_messages):
                if isinstance(msg, AIMessage) and msg.content:
                    agent_response_text = msg.content
                    break

            # Build final response - passthrough content takes priority
            response_parts: list[str] = []

            # Check for passthrough content FIRST (bypasses agent, goes to user)
            if self._last_passthrough:
                _LOGGER.debug(
                    "Including passthrough content in response: %s (%d chars)",
                    self._last_passthrough.content_type,
                    len(self._last_passthrough.content),
                )
                response_parts.append(self._last_passthrough.content)
                self._last_passthrough = None  # Clear after use

            # Add agent's verbal response if meaningful
            # Skip generic "content delivered" type responses when we have passthrough
            skip_responses = {
                "Content delivered directly to user",
                "I processed your request but have no response.",
            }
            if agent_response_text and agent_response_text not in skip_responses:
                # If we have passthrough content, the agent response is supplementary
                if response_parts:
                    response_parts.append(f"\n{agent_response_text}")
                else:
                    response_parts.append(agent_response_text)

            final_response = "".join(response_parts) if response_parts else "Done."

            _LOGGER.debug("Final response: %s", final_response[:200])

            # Create the response using IntentResponse
            intent_response = intent.IntentResponse(language=user_input.language)
            intent_response.async_set_speech(final_response)

            return ConversationResult(
                response=intent_response,
                conversation_id=conversation_id,
            )

        except Exception as err:
            _LOGGER.exception("Error processing conversation: %s", err)
            intent_response = intent.IntentResponse(language=user_input.language)
            intent_response.async_set_speech(f"Error processing request: {err}")

            return ConversationResult(
                response=intent_response,
                conversation_id=conversation_id,
            )

    async def async_reload_tools(self) -> int:
        """Reload tools from the TrikHub server.

        Returns:
            Number of tools loaded.
        """
        _LOGGER.info("Reloading TrikHub tools...")

        # Reset the graph to force reinitialization
        self._graph = None
        self._tools = []
        self._llm = None

        # Reinitialize
        await self._initialize_graph()

        return len(self._tools)
