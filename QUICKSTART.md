# Agent Generation Engine v5 - Quick Start Guide

A **ReAct-based autonomous agent system** that generates working code from natural language descriptions - similar to Devin, AutoGPT, and Claude Code.

## Installation

```bash
cd engine
pip install -r requirements.txt
```

## Usage

### CLI (Recommended)

```bash
# Interactive mode - pauses for approval at key steps
python main.py generate "Build a REST API for user management"

# Auto mode - no pauses, runs to completion
python main.py generate "Build a web scraper" --auto

# Specify output directory
python main.py generate "Build a CLI tool" -o ./my_agent

# List available tools
python main.py tools

# Start API server
python main.py server
```

### Python API

```python
from agents import generate_agent_sync, ReactOrchestrator, GenerationConfig

# Simple usage
result = generate_agent_sync(
    "Build a FastAPI application with user authentication",
    output_path="./my_agent",
    interactive=False
)

print(f"Generated {len(result.files)} files")
for f in result.files:
    print(f"  - {f['filename']}")

# Advanced usage with config
config = GenerationConfig(
    output_path="./output",
    interactive=True,
    sandbox=True,
    max_iterations=5
)

orchestrator = ReactOrchestrator(config)
result = orchestrator.generate_sync("Build a CLI tool for file encryption")
```

### REST API

```bash
# Start server
python main.py server --port 8000

# Generate agent
curl -X POST http://localhost:8000/api/v2/generate \
  -H "Content-Type: application/json" \
  -d '{"user_input": "Build a web scraper for news articles"}'

# List tools
curl http://localhost:8000/api/v2/tools
```

### WebSocket (Real-time)

```javascript
const ws = new WebSocket("ws://localhost:8000/api/v2/ws/generate");

ws.send(JSON.stringify({
    type: "start",
    user_input: "Build a machine learning pipeline"
}));

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    if (data.type === "checkpoint") {
        // Show approval UI, then respond
        ws.send(JSON.stringify({
            type: "approve",
            checkpoint_id: data.checkpoint.id,
            action: "approve"
        }));
    }
};
```

## Available Tools (19 total)

### File Tools
- `create_file` - Create new files
- `read_file` - Read file contents
- `edit_file` - Edit files (search/replace)
- `write_file` - Overwrite files
- `delete_file` - Delete files (requires approval)
- `list_files` - List directory contents

### Terminal Tools
- `execute_command` - Run shell commands (requires approval)
- `run_python` - Execute Python code
- `run_python_file` - Run Python scripts
- `install_package` - pip install (requires approval)
- `run_tests` - Run pytest

### Code Tools
- `lint_code` - Check for errors (ruff/flake8)
- `type_check` - Type checking (mypy)
- `format_code` - Format code (black/ruff)
- `analyze_code` - Extract structure
- `search_code` - Search patterns

### Search Tools
- `web_search` - Search the web
- `python_docs` - Python documentation
- `package_info` - PyPI package info

## Checkpoints

Interactive mode pauses at these points:
1. **Spec Generated** - Review the parsed specification
2. **Plan Generated** - Review the implementation plan
3. **Ready to Deploy** - Review all generated files

At each checkpoint you can:
- **Approve** - Continue with current state
- **Reject** - Abort generation
- **Modify** - Provide changes
- **Skip** - Auto-approve this checkpoint

## Architecture

```
User Input
    |
    v
+-------------------+
| SpecBuilderAgent  |  <-- Converts input to structured spec
+-------------------+
    |
    v
+-------------------+
|   PlannerAgent    |  <-- Creates implementation plan
+-------------------+
    |
    v
+-------------------+
|    CoderAgent     |  <-- Generates code using tools
+-------------------+     (create_file, lint_code, etc.)
    |
    v
+-------------------+
|  DebuggerAgent    |  <-- Fixes any issues
+-------------------+
    |
    v
+-------------------+
|  ReviewerAgent    |  <-- Final review
+-------------------+
    |
    v
Output Files
```

Each agent uses the **ReAct loop**:
1. **Think** - Analyze current state
2. **Act** - Call a tool
3. **Observe** - Review result
4. Repeat until task complete

## Configuration

Environment variables (`.env`):
```bash
# Required
OPENAI_API_KEY=sk-...

# Optional
MODEL_STRONG=gpt-4o          # For complex tasks
MODEL_FAST=gpt-4o-mini       # For simple tasks
MAX_ITERATIONS=5             # Max QA iterations
```

## File Structure

```
engine/
├── agents/                 # ReAct agents
│   ├── base.py            # ReActAgent base class
│   ├── coder.py           # Code generation
│   ├── react_planner.py   # Planning
│   └── react_orchestrator.py  # Main coordinator
├── tools/                  # Tool system
│   ├── base.py            # BaseTool class
│   ├── file_tools.py      # File operations
│   ├── terminal_tools.py  # Shell execution
│   ├── code_tools.py      # Linting, analysis
│   └── search_tools.py    # Web search
├── checkpoints/            # Interactive checkpoints
├── execution/              # Sandbox environment
├── memory/                 # Context management
├── api/                    # REST/WebSocket API
├── main.py                 # CLI entry point
└── config.py              # Settings
```
