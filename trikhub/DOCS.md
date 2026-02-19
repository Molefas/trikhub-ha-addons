# TrikHub Server

The TrikHub Server addon runs the TrikHub AI skill ecosystem in Home Assistant, allowing you to install and use third-party AI capabilities (Triks) within your smart home.

## About TrikHub

TrikHub is an open-source framework for AI agents to safely use third-party skills. Each skill (called a "Trik") is a self-contained capability that can be:

- **Installed** from the TrikHub registry
- **Executed** via REST API
- **Managed** through the REST API

Triks provide secure, type-safe integrations with external services while protecting against prompt injection attacks.

## Installation

1. Add this repository to your Home Assistant addon store
2. Install the "TrikHub Server" addon
3. Configure the addon options (see below)
4. Start the addon

## Configuration

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `AUTH_TOKEN` | Bearer token for API authentication (leave empty to disable) | (empty) |
| `REGISTRY_URL` | TrikHub registry URL | `https://api.trikhub.com` |
| `LOG_LEVEL` | Logging verbosity | `info` |
| `LINT_ON_LOAD` | Validate Triks for security on load | `true` |

### Example Configuration

```yaml
AUTH_TOKEN: "your-secret-token"
REGISTRY_URL: "https://api.trikhub.com"
LOG_LEVEL: "info"
LINT_ON_LOAD: true
```

## API Access

The addon exposes a REST API on port 3000 (internal network only). Access via HTTP:

- **API Documentation**: `http://<addon-ip>:3000/docs` (Swagger UI)
- **Health Check**: `GET /api/v1/health`

## API Endpoints

The addon exposes a REST API on port 3000 (internal only):

### Discovery

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/health` | GET | Health check |
| `/api/v1/tools` | GET | List available tools |

### Execution

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/execute` | POST | Execute a Trik action |
| `/api/v1/content/:ref` | GET | Retrieve passthrough content |

### Trik Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/triks` | GET | List installed Triks |
| `/api/v1/triks/install` | POST | Install a Trik |
| `/api/v1/triks/:name` | DELETE | Uninstall a Trik |
| `/api/v1/triks/reload` | POST | Reload all Triks |

## Installing Triks

### Via Services

- Navigate to Developer Tools > Actions
- Search for "Trikhub"
- See the Install / Uninstall / Execute actions

Make sure that when installing / uninstalling you add the entire trik name `(@org/repo)`

### Via API

```bash
curl -X POST http://homeassistant.local:3000/api/v1/triks/install \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-token" \
  -d '{"package": "@org/repo"}'
```

### Via Terminal (SSH)

```bash
docker exec addon_trikhub trik install @org/repo
```

## Integration with Home Assistant

For full integration with Home Assistant's Assist voice pipeline, install the TrikHub custom integration:

1. **Install via HACS**: Search for "TrikHub" in HACS integrations
2. **Configure the integration**: Enter the addon URL (`http://addon_local_trikhub:3000`)
3. **Select TrikHub** as your conversation agent in Assist settings

The integration provides:

- **Conversation Agent**: Use Triks via voice commands
- **HA Services**: Call Triks from automations

## Data Persistence

The addon stores data in `/data` which persists across restarts:

- `/data/skills/` - Installed Trik packages
- `/data/.trikhub/config.json` - Trik installation registry
- `/data/.trikhub/storage/` - Trik persistent storage (SQLite)

## Troubleshooting

### Addon won't start

1. Check the addon logs for error messages
2. Ensure no other service is using port 3000
3. Verify your configuration is valid YAML

### Triks won't install

1. Check network connectivity to the TrikHub registry
2. Verify the Trik package name is correct
3. Check addon logs for installation errors

### API returns 401 Unauthorized

If you've configured `AUTH_TOKEN`, ensure you're sending the correct Bearer token in the `Authorization` header.

## Support

- [TrikHub Documentation](https://trikhub.com/docs)
- [Report Issues](https://github.com/Molefas/trikhub-ha-addons/issues)

## License

MIT
