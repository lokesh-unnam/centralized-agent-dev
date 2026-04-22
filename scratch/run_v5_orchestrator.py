import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
import sys

# Add engine to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.react_orchestrator import ReactOrchestrator

async def main():
    load_dotenv()
    
    # Use a relative path or local file for the recipe
    recipe_path = Path("recipe_account_research.md")
    if not recipe_path.exists():
        # Fallback to raw string if file not found
        raw_input = "Create an Account Research Agent that uses Google Search and LinkedIn to find company data."
    else:
        raw_input = recipe_path.read_text(encoding="utf-8")
    
    print("--- INITIATING v5 PRODUCTION PIPELINE ---")
    orchestrator = ReactOrchestrator()
    
    try:
        result = await orchestrator.generate(raw_input)
        
        print("\n--- GENERATION SUCCESSFUL ---")
        print(f"Workflow ID: {result['workflow_id']}")
        print(f"Final Score: {result['final_score']}")
        print(f"Output Path: {result['path']}")
        print("\nFiles Generated:")
        for f in result.get("files", []):
            print(f" - {f}")
            
    except Exception as e:
        print(f"\n--- GENERATION FAILED ---")
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
