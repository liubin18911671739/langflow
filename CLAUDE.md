# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Langflow is a visual flow-based framework for building LLM applications with a React frontend and FastAPI backend. It uses a component-based architecture where users can create flows by connecting different AI components.

## Development Commands

### Environment Setup
```bash
make init                    # Initialize project (install deps + build frontend)
make check_tools            # Verify uv and npm are installed
```

### Backend Development
```bash
make backend                # Start FastAPI dev server (port 7860) with hot reload
make install_backend        # Install Python dependencies via uv
uv run langflow run         # Start production server
```

### Frontend Development  
```bash
make frontend               # Start React dev server (port 3000) with Vite
make install_frontend       # Install Node.js dependencies
make build_frontend         # Build static frontend files
```

### Testing & Quality
```bash
make unit_tests             # Run backend unit tests with pytest
make integration_tests      # Run integration tests
make tests                  # Run all tests + coverage
make lint                   # Lint backend code
make format_backend         # Format Python code
make format_frontend        # Format frontend code
```

### Documentation
```bash
cd docs && yarn install && yarn start  # Serve docs on port 3001
```

## Architecture

### Backend Structure
- **Components**: `src/backend/base/langflow/components/` - Core AI components (LLMs, vector stores, etc.)
- **Graph Processing**: `src/backend/base/langflow/graph/` - Flow execution engine
- **API**: `src/backend/base/langflow/api/` - FastAPI routes
- **Services**: `src/backend/base/langflow/services/` - Business logic
- **Base Classes**: `src/backend/base/langflow/custom/` - Component base classes

### Frontend Structure  
- **Components**: `src/frontend/src/components/` - React UI components
- **Pages**: `src/frontend/src/pages/` - Route components
- **Controllers**: `src/frontend/src/controllers/` - API client logic
- **Types**: `src/frontend/src/types/` - TypeScript definitions

### Component Development
Components are Python classes inheriting from `Component` or specialized bases. They define:
- Input/output specifications
- Build method for execution logic
- Metadata for UI rendering

Add new components to appropriate subdirectory in `src/backend/base/langflow/components/` and update the `__init__.py` file.

### Development Workflow
1. Run `make backend` and `make frontend` in separate terminals for hot reload
2. Backend runs on port 7860, frontend dev server on port 3000
3. Frontend proxies API requests to backend
4. Components auto-reload when backend restarts

## Key Configuration Files
- `pyproject.toml` - Python dependencies and project config
- `src/frontend/package.json` - Node.js dependencies  
- `Makefile` - Build commands and development scripts
- `.cursor/rules/` - Development guidelines for different areas

## Testing Notes
- Unit tests: `src/backend/tests/unit/`
- Integration tests require additional setup
- Some tests may fail in parallel execution but pass individually
- Backend test database can be flaky when run with `make tests`