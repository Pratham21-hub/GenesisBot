# Hackathon Official API Integration Guide

This guide describes how to connect GenesisBot V2 to the official competition game server once the organizers release the API documentation and/or SDK.

---

## Pre-Kickoff Checklist

When the competition organizers announce the rules, API endpoints, or SDK packages:

1. **Obtain API Documentation & Credentials**
   - Retrieve the official base URL, authentication scheme (Bearer token, API key, mTLS), and rate limits.
   - Obtain sandbox/test credentials and match session identifiers.
2. **Review Official Schemas**
   - Identify how the game server represents ticks/turns, map coordinates, units, scores, and status flags.
   - Identify the expected format for submitting actions (HTTP POST, WebSocket messages, SDK methods).
3. **Verify Dependencies**
   - Check if an official client package is distributed via PyPI or Git.
   - If a custom SDK is required, add it to `requirements.txt` with appropriate version pinning.

---

## Integration Workflow

### Step 1: Configure Local Environment

Copy `.env.example` to `.env` and configure your credentials:

```bash
cp .env.example .env
```

Set the official variables in `.env`:
```ini
GENESIS_API_BASE_URL=https://official-competition-api.example.com
GENESIS_API_KEY=your_actual_private_api_key
GENESIS_SESSION_ID=match_session_12345
GENESIS_REQUEST_TIMEOUT_SEC=3.0
```

> **Security Rule**: Never commit `.env` or push real API tokens to version control.

---

### Step 2: Implement a Concrete Game Adapter

Create a new file in `game/` (e.g. `game/official_adapter.py`) inheriting from `BaseGameAdapter`:

```python
# game/official_adapter.py
from datetime import datetime, timezone
import requests
from config import AppConfig
from core.models import ActionSubmissionResult, GameState, ProposedAction
from game.base_adapter import BaseGameAdapter

class OfficialGameAdapter(BaseGameAdapter):
    def __init__(self, config: AppConfig):
        self.config = config
        self.session = requests.Session()
        if self.config.api_key:
            self.session.headers.update({
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            })

    def read_game_state(self) -> GameState:
        url = f"{self.config.api_base_url}/sessions/{self.config.session_id}/state"
        response = self.session.get(url, timeout=self.config.request_timeout_sec)
        response.raise_for_status()
        raw = response.json()

        # Map official schema to internal GameState
        return GameState(
            turn_number=raw.get("turn", 0),
            is_active=raw.get("status") == "in_progress",
            score=raw.get("current_score"),
            time_remaining_ms=raw.get("remaining_turn_time_ms"),
            raw_state=raw,  # Preserve unmapped payload
            timestamp=datetime.now(timezone.utc),
        )

    def submit_action(self, action: ProposedAction) -> ActionSubmissionResult:
        url = f"{self.config.api_base_url}/sessions/{self.config.session_id}/action"
        
        # Translate internal ProposedAction to official wire format
        payload = {
            "type": action.action_type,
            "params": action.parameters,
        }
        
        start_time = datetime.now(timezone.utc)
        response = self.session.post(url, json=payload, timeout=self.config.request_timeout_sec)
        latency = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000.0
        
        raw_resp = response.json() if response.content else {}
        return ActionSubmissionResult(
            success=response.ok,
            response_code=response.status_code,
            message=raw_resp.get("message"),
            latency_ms=latency,
            raw_response=raw_resp,
        )

    def check_submission_result(self, result: ActionSubmissionResult) -> bool:
        return result.success and (result.response_code in (200, 201, 202))
```

---

### Step 3: Write Adapter Tests

Create automated tests in `tests/test_official_adapter.py` that mock network responses using `unittest.mock` or a requests mock library:
- Verify that `read_game_state()` parses valid server responses into `GameState`.
- Verify that network timeouts or non-200 responses are handled gracefully.
- Verify that `submit_action()` formats the official payload correctly.

---

### Step 4: Run the Bot in Dry-Run / Sandbox Mode

Before joining live matches:
1. Verify logging in `logs/bot_audit.jsonl`.
2. Inspect latency numbers to confirm compliance with turn timeout rules.
3. Validate that `GameState.raw_state` contains all expected keys from the official documentation.
