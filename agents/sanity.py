import os
import subprocess
import time
import uuid
import asyncio
from pathlib import Path
from agents.base import BaseSQAAgent
from utils.sandbox import Sandbox
from utils.llm import query_llm_json

class SanityTestingAgent(BaseSQAAgent):
    """Agent 4: Checks if the application boots up successfully."""
    
    async def run(self, target_dir: str, db_path: str, run_id: int):
        print("  - Running sanity checks (boot sequence)...")
        target_path = Path(target_dir)
        
        entry_points = ["main.py", "app.py", "run.py", "server.py"]
        entry_file = None
        for ep in entry_points:
            if (target_path / ep).exists():
                entry_file = ep
                break
                
        if not entry_file:
            print("    - No standard entry point found. Skipping boot sanity check.")
            return
            
        print(f"    - Found entry point '{entry_file}'. Attempting to boot in Docker sandbox...")
        
        with Sandbox(target_dir) as sandbox:
            # Run the command asynchronously so we can time out
            # We don't use sandbox.run_command here because we want to run it in background and poll it
            # The docker API allows creating an exec object and streaming
            
            try:
                # We start the entry file in the background of the container
                exec_id = sandbox.container.client.api.exec_create(
                    sandbox.container.id,
                    f"python {entry_file}",
                    workdir="/app"
                )
                
                # Start the execution
                sandbox.container.client.api.exec_start(exec_id, detach=True)
                
                # Give it 3 seconds to fail
                await asyncio.sleep(3)
                
                exec_info = sandbox.container.client.api.exec_inspect(exec_id)
                exit_code = exec_info.get("ExitCode")
                
                if exit_code is not None and exit_code != 0:
                    print("    - CRITICAL: Application crashed during boot sequence!")
                    # In detached mode we can't easily capture output from exec_start without blocking.
                    # Since it crashed, we will run it again synchronously to capture the crash logs
                    result = sandbox.run_command(f"python {entry_file}")
                    await self._diagnose_boot_crash(entry_file, result['stdout'], db_path, run_id)
                else:
                    print("    - Application successfully survived initial boot sequence in Docker.")
                    
            except Exception as e:
                print(f"    - Sandbox boot testing failed: {e}")
                    
    async def _diagnose_boot_crash(self, entry_file: str, stderr: str, db_path: str, run_id: int):
        truncated_stderr = stderr[-3000:]
        prompt = (
            f"The application crashed immediately upon running `{entry_file}`.\n\n"
            f"Here is the stderr log:\n```\n{truncated_stderr}\n```\n\n"
            f"Analyze the traceback to determine why it failed to start. "
            f"Provide a JSON with two keys: 'impact_analysis' (explain the root cause) and 'suggested_fix' (how to resolve it)."
        )
        
        schema = {
            "type": "object",
            "properties": {
                "impact_analysis": {"type": "string"},
                "suggested_fix": {"type": "string"}
            },
            "required": ["impact_analysis", "suggested_fix"]
        }
        
        llm_insight = await query_llm_json(prompt, schema)
        
        issue = {
            "id": str(uuid.uuid4()),
            "file_path": entry_file,
            "line_number": None,
            "severity": "CRITICAL",
            "impact_analysis": llm_insight.get("impact_analysis", "Application fails to start (Boot Crash)."),
            "description": "Fatal error during application startup.",
            "suggested_fix": llm_insight.get("suggested_fix", "Review boot logs and fix fatal exceptions.")
        }
        await self.write_issue(db_path, run_id, issue)
