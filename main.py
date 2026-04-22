"""
Main CLI Entry Point - Command-line interface for agent generation.
"""
from __future__ import annotations
import argparse
import asyncio
import sys
import json
from pathlib import Path
from typing import Optional
import structlog

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer(colors=True)
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


def print_banner():
    """Print the CLI banner."""
    banner = """
+====================================================================+
|                    AGENT GENERATION ENGINE v5                      |
|              ReAct-based Autonomous Code Generator                 |
+====================================================================+
"""
    print(banner)


def print_checkpoint(checkpoint) -> None:
    """Print checkpoint information."""
    print("\n" + "=" * 60)
    print(f"[CHECKPOINT] {checkpoint.title}")
    print("=" * 60)
    print(f"Type: {checkpoint.type.value}")
    print(f"Description: {checkpoint.description}")
    print("-" * 60)
    
    if checkpoint.data:
        for key, value in checkpoint.data.items():
            if isinstance(value, dict):
                print(f"\n{key}:")
                for k, v in value.items():
                    if isinstance(v, str) and len(v) > 100:
                        print(f"  {k}: {v[:100]}...")
                    elif isinstance(v, list):
                        print(f"  {k}: [{len(v)} items]")
                    else:
                        print(f"  {k}: {v}")
            elif isinstance(value, list):
                print(f"\n{key}: [{len(value)} items]")
                for item in value[:5]:
                    if isinstance(item, dict):
                        print(f"  - {item.get('filename', item.get('name', str(item)[:50]))}")
                    else:
                        print(f"  - {str(item)[:50]}")
            else:
                print(f"{key}: {value}")
    
    print("-" * 60)


def prompt_for_action(checkpoint) -> str:
    """Prompt user for action on checkpoint."""
    print("\nActions:")
    print("  [a] Approve and continue")
    print("  [r] Reject and abort")
    print("  [s] Skip (auto-approve)")
    print("  [v] View full details")
    
    while True:
        choice = input("\nYour choice (a/r/s/v): ").strip().lower()
        
        if choice == 'a':
            return "approve"
        elif choice == 'r':
            return "reject"
        elif choice == 's':
            return "skip"
        elif choice == 'v':
            print("\nFull checkpoint data:")
            print(json.dumps(checkpoint.data, indent=2, default=str))
            continue
        else:
            print("Invalid choice. Please enter a, r, s, or v.")


async def run_generation(
    user_input: str,
    output_path: Optional[str] = None,
    interactive: bool = True,
    verbose: bool = False,
):
    """Run the agent generation process."""
    from agents.react_orchestrator import ReactOrchestrator, GenerationConfig
    
    print(f"\n>>> Starting generation...")
    print(f"[OUTPUT] {output_path or './output'}")
    print(f"[INTERACTIVE] {interactive}")
    print("-" * 60)
    
    # Set up checkpoint handler for interactive mode
    checkpoint_callback = None
    if interactive:
        def handle_checkpoint(checkpoint):
            print_checkpoint(checkpoint)
            if checkpoint.requires_approval:
                action = prompt_for_action(checkpoint)
                if action == "approve" or action == "skip":
                    checkpoint.approve()
                elif action == "reject":
                    checkpoint.reject("Rejected by user")
        
        checkpoint_callback = handle_checkpoint
    
    config = GenerationConfig(
        output_path=output_path,
        interactive=interactive,
        sandbox=True,
    )
    
    orchestrator = ReactOrchestrator(config)
    
    # Set up checkpoint callback
    if checkpoint_callback:
        orchestrator.checkpoint_manager.on_checkpoint = checkpoint_callback
    
    result = await orchestrator.generate(user_input)
    
    print("\n" + "=" * 60)
    if result.success:
        print("[SUCCESS] GENERATION COMPLETE")
        print("=" * 60)
        print(f"Workflow ID: {result.workflow_id}")
        print(f"Output Path: {result.output_path}")
        print(f"Files Generated: {len(result.files)}")
        print("\nFiles:")
        for f in result.files:
            print(f"  - {f['filename']}")
    else:
        print("[FAILED] GENERATION FAILED")
        print("=" * 60)
        print(f"Error: {result.error}")
    
    return result


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Agent Generation Engine - Generate AI agents from natural language",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive generation (recommended)
  python main.py generate "Build a REST API for user management"
  
  # Non-interactive (auto-approve all checkpoints)
  python main.py generate "Build a web scraper" --auto
  
  # Specify output directory
  python main.py generate "Build a CLI tool" -o ./my_agent
  
  # Start API server
  python main.py server --port 8000
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Generate command
    gen_parser = subparsers.add_parser("generate", help="Generate an agent from description")
    gen_parser.add_argument("description", nargs="?", help="Agent description")
    gen_parser.add_argument("-o", "--output", help="Output directory")
    gen_parser.add_argument("--auto", action="store_true", help="Non-interactive mode (auto-approve)")
    gen_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    
    # Server command
    server_parser = subparsers.add_parser("server", help="Start the API server")
    server_parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    server_parser.add_argument("--port", type=int, default=8000, help="Port to bind")
    server_parser.add_argument("--reload", action="store_true", help="Auto-reload on changes")
    
    # Tools command
    tools_parser = subparsers.add_parser("tools", help="List available tools")
    
    args = parser.parse_args()
    
    print_banner()
    
    if args.command == "generate":
        description = args.description
        
        # If no description provided, prompt for it
        if not description:
            print("Enter your agent description (press Enter twice to finish):")
            lines = []
            while True:
                line = input()
                if line == "":
                    if lines:
                        break
                    continue
                lines.append(line)
            description = "\n".join(lines)
        
        if not description.strip():
            print("Error: No description provided")
            sys.exit(1)
        
        print(f"\n[INPUT] {description[:100]}{'...' if len(description) > 100 else ''}")
        
        asyncio.run(run_generation(
            description,
            output_path=args.output,
            interactive=not args.auto,
            verbose=args.verbose,
        ))
    
    elif args.command == "server":
        print(f"[SERVER] Starting on {args.host}:{args.port}...")
        import uvicorn
        uvicorn.run(
            "api.main:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
    
    elif args.command == "tools":
        from tools.registry import get_tool_registry
        
        registry = get_tool_registry()
        print("\n[TOOLS] Available Tools:\n")
        
        for category, tools in registry.get_tools_by_category().items():
            print(f"\n{category.upper()}:")
            for tool_name in tools:
                tool = registry.get(tool_name)
                if tool:
                    approval = " [requires approval]" if tool.requires_approval else ""
                    print(f"  - {tool.name}: {tool.description[:60]}{approval}")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
