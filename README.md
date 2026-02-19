# TrikHub Home Assistant Addons

Home Assistant addon and integration for the TrikHub AI skill ecosystem. Extend your Home Assistant voice assistant with third-party AI skills (Triks).

This entire repo is basically a basic wrapper allowing users to easily expand their conversation agents with Skills. Trikhub allows then the creation and sharing of these Open Souce skill sith the community.

A more direct "hands-on" implementation of Trikhub is possible (and better) within in Agents.
More information about us on [Trikhub.com](https://trikhub.com)

## Quick Start

### 1. Install the Addon

1. Open Home Assistant
2. Go to **Settings** > **Add-ons** > **Add-on Store**
3. Click the menu (three dots) > **Repositories**
4. Add: `https://github.com/molefas/trikhub-ha-addons`
5. Find "TrikHub Server" and click **Install**
6. Start the addon

### 2. Install the Integration

Easily install through HACS:
[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Molefas&repository=trikhub-ha-addons&category=Integration)

Or copy the integration manually to your HA config:

```bash
# From your local machine
scp -r custom_components/trikhub root@homeassistant.local:/config/custom_components/
```

Then restart Home Assistant.

### 3. Configure the Integration

1. Go to **Settings** > **Devices & Services** > **Add Integration**
2. Search for "TrikHub"
3. Enter the server URL: `http://local-trikhub:3000`
   - To find your addon's IP, check the addon logs for "Server listening at http://X.X.X.X:3000"
4. Configure your LLM provider (OpenAI, Anthropic, or Ollama)

### 4. Set Up Voice Assistant

1. Go to **Settings** > **Voice Assistants**
2. Click **Add Assistant** or edit an existing one
3. Set **Conversation Agent** to "TrikHub"
4. Save

### 5. Install Triks

Use the HA service to install Triks. You can find and create these in the [Registry](https://trikhub.com).
I've created very basic examples to demo the tool:
1. [Article Search Demo](https://trikhub.com/skills/molefas/trik-article-search)
2. [Notes Demo](https://trikhub.com/skills/molefas/trik-demo-notes)

To install these or other Triks:

1. Go to **Developer Tools** > **Services**
2. Select `trikhub.install_trik`
3. Enter the package name, e.g., `@molefas/trik-demo-notes`
4. Click **Call Service**

Or via API:
```bash
curl -X POST http://<addon-ip>:3000/api/v1/triks/install \
  -H "Content-Type: application/json" \
  -d '{"package": "@molefas/trik-demo-notes"}'
```

### 6. Use It!

Open **Assist** and talk to your assistant. It will now have access to your installed Triks as tools.

---

## Features

- **JavaScript and Python Triks** - Both runtimes are supported
- **LangGraph Agent** - Sophisticated agentic loop with tool calling
- **Multiple LLM Providers** - OpenAI, Anthropic, Ollama
- **HA Services** - Install, uninstall, and execute Triks from automations
- **Passthrough Content** - Triks can deliver content directly to users

## Architecture

```
User Voice/Text → Assist Pipeline → TrikHub Integration
                                           │
                                    ┌──────┴──────┐
                                    │  LangGraph  │
                                    │    Agent    │
                                    │             │
                                    │ ┌─────────┐ │
                                    │ │  Agent  │ │ ← LLM (OpenAI/Anthropic/Ollama)
                                    │ │  Node   │ │
                                    │ └────┬────┘ │
                                    │      │      │
                                    │ ┌────▼────┐ │
                                    │ │ToolNode │ │ ← Executes Trik tools
                                    │ └─────────┘ │
                                    └──────┬──────┘
                                           │
                                    TrikHub Server API
                                           │
                              ┌────────────┴────────────┐
                              │                         │
                        JS Triks                  Python Triks
                     (Node.js runtime)         (Python worker)
```

## API Reference

The TrikHub Server exposes these endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/health` | GET | Health check |
| `/api/v1/tools` | GET | List available tools from all Triks |
| `/api/v1/triks` | GET | List installed Triks |
| `/api/v1/triks/install` | POST | Install a Trik |
| `/api/v1/triks/:name` | DELETE | Uninstall a Trik |
| `/api/v1/execute` | POST | Execute a tool |
| `/api/v1/triks/reload` | POST | Reload all Triks |

### Example: Execute a Tool

```bash
curl -X POST http://<addon-ip>:3000/api/v1/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "@molefas/article-search:search",
    "input": {"query": "home automation"}
  }'
```

## HA Services

| Service | Description | Parameters |
|---------|-------------|------------|
| `trikhub.install_trik` | Install a Trik | `package`: Package name |
| `trikhub.uninstall_trik` | Uninstall a Trik | `name`: Trik name |
| `trikhub.execute_trik` | Execute a tool | `tool`: Tool name, `input`: Parameters |

## Supported LLM Providers

| Provider | Models | API Key |
|----------|--------|---------|
| OpenAI | `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo` | OpenAI API key |
| Anthropic | `claude-sonnet-4-20250514`, `claude-3-5-sonnet`, `claude-3-haiku` | Anthropic API key |
| Ollama | `llama3`, `mistral`, `mixtral`, etc. | Ollama server URL |

## Troubleshooting

### "Cannot connect to TrikHub server"

1. Make sure the addon is running (check addon logs)
2. Find the correct IP from addon logs: look for "Server listening at http://X.X.X.X:3000"
3. Try the IP directly: `http://172.30.33.X:3000`
4. The hostname `local-trikhub` should also work

### "Authentication failed" when connecting

If you get 401 errors, you might be hitting a proxy instead of the addon directly. Use the addon's internal IP address from the logs.

### Trik install fails

1. Check addon logs for the actual error
2. Make sure the package name is correct (e.g., `@scope/trik-name`)
3. Try installing via CLI inside the container:
   ```bash
   docker exec addon_local_trikhub trik install @scope/trik-name
   ```

### No tools loaded

1. Verify Triks are installed: `curl http://<addon-ip>:3000/api/v1/triks`
2. Check if tools are exposed: `curl http://<addon-ip>:3000/api/v1/tools`
3. Check addon logs for loading errors
4. Try reloading: `curl -X POST http://<addon-ip>:3000/api/v1/triks/reload`

### Integration not appearing

1. Make sure files are in `/config/custom_components/trikhub/`
2. Restart Home Assistant completely
3. Check HA logs for import errors

### LLM errors

1. Verify your API key is correct
2. Check the model name matches your provider
3. For Ollama, ensure the server is running and the model is pulled

## Disclaimer
This project is in its infancy and many more updates, features, fixes and improvements are planned. Any help in the right direction is greatly appreciated. Check the [Trikhub repository](https://github.com/Molefas/trikhub) for more info.

## Links

- [TrikHub Website](https://trikhub.com)
- [TrikHub Documentation](https://trikhub.com/docs)
- [Browse Triks Registry](https://trikhub.com/triks)
- [Report Issues](https://github.com/molefas/trikhub-ha-addons/issues)

## License

MIT
