# GenesisBot V2 — Hackathon Game Agent

GenesisBot V2 is a high-performance, modular Python-based game-playing agent designed for competitive hackathons.

> **Status — Phase 1: Foundation Complete**  
> This phase establishes the architectural foundation: typed domain models (Pydantic), abstract game adapter interfaces, environment configuration, standard-library JSONL logging, and automated test suites. Full game loops, live API adapters, and the Streamlit dashboard will be implemented in subsequent phases once the official competition specifications are released.

---

## Technical Stack

- **Python**: 3.11+
- **Data Validation & Modeling**: [Pydantic](https://docs.pydantic.dev/) v2
- **Environment Management**: [python-dotenv](https://github.com/theskumar/python-dotenv)
- **HTTP Transport**: [requests](https://requests.readthedocs.io/)
- **Testing**: [pytest](https://docs.pytest.org/)
- **Observability**: Standard-library JSONL structured logging
- **Dashboard (Phase 2+)**: [Streamlit](https://streamlit.io/)

---

## Project Structure

```text
GenesisBot/
├── .env.example              # Template for environment variables (do not commit secrets)
├── .gitignore                # Git exclusions (caches, .env, virtualenvs, logs)
├── config.py                 # Pydantic-validated application configuration
├── requirements.txt          # Project dependencies
├── README.md                 # Project documentation and quickstart
├── core/
│   ├── __init__.py           # Package exports
│   ├── models.py             # Pydantic models: GameState, ProposedAction, LayaDecision, etc.
│   └── logger.py             # Standard-library JSONL audit logger
├── game/
│   ├── __init__.py           # Package exports
│   └── base_adapter.py       # Abstract port for game environment adapters
├── docs/
│   ├── ARCHITECTURE.md       # Architectural overview, Mermaid diagram, and design patterns
│   └── HACKATHON_INTEGRATION.md # Guide for connecting official APIs / SDKs
└── tests/
    ├── __init__.py
    ├── test_models.py        # Unit tests for domain models
    ├── test_config.py        # Unit tests for configuration loading
    ├── test_adapter.py       # Unit tests for BaseGameAdapter contracts
    └── test_logger.py        # Unit tests for JSONL logging
```

---

## Quickstart & Setup Instructions

### 1. Prerequisites

Ensure Python 3.11 or newer is installed:

```bash
python --version
```

### 2. Set Up Virtual Environment

Create and activate an isolated virtual environment:

```bash
# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Linux / macOS
python -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

Install the foundation dependencies:

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create your local `.env` configuration file from the provided example:

```bash
cp .env.example .env
```

Edit `.env` to configure your local settings. Note that official competition endpoints and credentials should only be entered once released by tournament organizers.

### 5. Run the Automated Tests

Verify the project foundation by running `pytest`:

```bash
python -m pytest -v
```

---

## Domain Models Overview

All models reside in `core/models.py` and are implemented with Pydantic:

- **`SessionInfo`**: Tracks match/session identifiers, lifecycle status, and metadata.
- **`GameState`**: Encapsulates internal turn number, active status, scores, and an unmapped `raw_state` dictionary for forward compatibility.
- **`ProposedAction`**: Represents an action candidate (action type, parameters, priority, reasoning).
- **`LayaDecision`**: Encapsulates the chosen action and rationale produced by the Laya decision engine.
- **`ActionSubmissionResult`**: Standardized outcome envelope (success status, HTTP code, latency, message, raw response).

---

## Security Guidelines

- **Never commit `.env` or API credentials** to source control. The `.gitignore` is preconfigured to ignore `.env*` (except `.env.example`).
- Keep test credentials and mock tokens in memory or ephemeral test fixtures only.

---

## Next Steps (Phase 2)

- [ ] Implement the official game adapter once the competition schema and API/SDK are published.
- [ ] Implement the Laya strategic decision engine and candidate action evaluators.
- [ ] Implement the Streamlit live dashboard for match monitoring.
