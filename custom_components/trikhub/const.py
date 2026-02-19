"""Constants for TrikHub integration."""

DOMAIN = "trikhub"

# Configuration keys
CONF_SERVER_URL = "server_url"
CONF_AUTH_TOKEN = "auth_token"
CONF_LLM_PROVIDER = "llm_provider"
CONF_LLM_API_KEY = "llm_api_key"
CONF_LLM_MODEL = "llm_model"

# Default values
DEFAULT_SERVER_URL = "http://addon_local_trikhub:3000"
DEFAULT_LLM_MODEL = "gpt-4o-mini"

# LLM Providers
LLM_PROVIDER_OPENAI = "openai"
LLM_PROVIDER_ANTHROPIC = "anthropic"
LLM_PROVIDER_OLLAMA = "ollama"

LLM_PROVIDERS = [
    LLM_PROVIDER_OPENAI,
    LLM_PROVIDER_ANTHROPIC,
    LLM_PROVIDER_OLLAMA,
]

# API endpoints
API_HEALTH = "/api/v1/health"
API_TOOLS = "/api/v1/tools"
API_EXECUTE = "/api/v1/execute"
API_CONTENT = "/api/v1/content"
API_TRIKS = "/api/v1/triks"
API_TRIKS_INSTALL = "/api/v1/triks/install"
API_TRIKS_RELOAD = "/api/v1/triks/reload"

# Service names
SERVICE_EXECUTE_TRIK = "execute_trik"
SERVICE_INSTALL_TRIK = "install_trik"
SERVICE_UNINSTALL_TRIK = "uninstall_trik"

# Attributes
ATTR_TOOL = "tool"
ATTR_INPUT = "input"
ATTR_PACKAGE = "package"
ATTR_NAME = "name"
