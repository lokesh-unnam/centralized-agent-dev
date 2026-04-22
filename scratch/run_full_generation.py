import os
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# Add engine to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.state import build_initial_state

async def main():
    load_dotenv()
    
    spec_path = r"C:\Users\LokeshUnnam\Downloads\Agent_Account_Research (2).md"
    with open(spec_path, "r", encoding="utf-8") as f:
        spec_content = f.read()
    
    # Initialize state
    state = build_initial_state("account_research_agent")
    state["user_input"] = f"Generate a full working agent system based on this specification:\n\n{spec_content}"
    
    print(f"--- STARTING FULL GENERATION PIPELINE FOR: {state['meta']['workflow_name']} ---")
    
    from orchestrator.graph import compile_graph
    app = compile_graph()
    
    async for event in app.astream(state):
        for node_name, node_state in event.items():
            print(f"\n>> COMPLETED NODE: {node_name}")
            if node_name == "error" and node_state.get("error"):
                print(f"Error encountered: {node_state['error']}")
                return
            
            if node_name == "planner":
                print("Plan generated successfully.")
            elif node_name == "code_generation":
                print(f"Code files generated: {[f['filename'] for f in node_state['artifacts']['code_files']]}")
            elif node_name == "critic":
                eval_data = node_state.get("evaluation", {})
                print(f"Evaluation: Accuracy {eval_data.get('accuracy', 0)*100:.1f}%")
            elif node_name == "finalization":
                print("Pipeline completed successfully!")
                
    # Final check of files
    print("\n--- GENERATION SUMMARY ---")
    if "artifacts" in state and "code_files" in state["artifacts"]:
        output_dir = Path("output") / state["meta"]["workflow_name"]
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for file_data in state["artifacts"]["code_files"]:
            file_path = output_dir / file_data["filename"]
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(file_data["content"])
            print(f"Saved: {file_path}")
    else:
        # If we used astream, we need to get the final state from the last event
        # This is a bit tricky with astream, but I'll add logic to capture it
        pass

if __name__ == "__main__":
    # Update main to return the final state
    async def run_and_save():
        load_dotenv()
        spec_path = r"C:\Users\LokeshUnnam\Downloads\Agent_Account_Research (2).md"
        with open(spec_path, "r", encoding="utf-8") as f:
            spec_content = f.read()
        
        state = build_initial_state("account_research_agent")
        state["user_input"] = f"Generate a full working agent system based on this specification:\n\n{spec_content}"
        
        from orchestrator.graph import compile_graph
        app = compile_graph()
        
        final_state = state
        async for event in app.astream(state):
            for node_name, node_state in event.items():
                print(f"\n>> COMPLETED NODE: {node_name}")
                final_state = node_state
        
        print("\n--- SAVING ARTIFACTS ---")
        artifacts = final_state.get("artifacts", {})
        code_files = artifacts.get("code_files", [])
        if code_files:
            output_dir = Path("output") / "account_research_agent_v8"
            output_dir.mkdir(parents=True, exist_ok=True)
            for f_data in code_files:
                f_path = output_dir / f_data["filename"]
                with open(f_path, "w", encoding="utf-8") as f:
                    f.write(f_data["content"])
                print(f"Saved: {f_path}")
        else:
            print("No artifacts found in final state.")

    asyncio.run(run_and_save())
