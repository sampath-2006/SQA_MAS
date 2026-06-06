import json
import uuid
import os
from pathlib import Path
from agents.base import BaseSQAAgent
from utils.sandbox import Sandbox
from utils.llm import query_llm_json

class RegressionTestingAgent(BaseSQAAgent):
    """Agent 2: Executes tests, computes coverage, and diagnoses failures."""
    
    async def run(self, target_dir: str, db_path: str, run_id: int):
        print("  - Initializing isolated Docker sandbox for testing...")
        
        with Sandbox(target_dir) as sandbox:
            sandbox.run_command("pip install pytest coverage")
            
            print("  - Executing test suite...")
            result = sandbox.run_command("coverage run -m pytest")
            
            if result['returncode'] != 0 and result['returncode'] != 5:
                print("  - Test failures detected. Running diagnostic analysis...")
                await self._diagnose_failures(result['stdout'], target_dir, db_path, run_id)
            elif result['returncode'] == 5:
                print("  - No tests found in the repository.")
            else:
                print("  - All tests passed successfully.")
                
            await self._process_coverage(sandbox, db_path, run_id)
            
    async def _diagnose_failures(self, pytest_output: str, target_dir: str, db_path: str, run_id: int):
        truncated_output = pytest_output[-3000:]
        
        prompt = (
            f"The following pytest output contains test failures.\n\n"
            f"Output:\n{truncated_output}\n\n"
            f"Analyze the traceback and provide a JSON with three keys: "
            f"'failed_test_name', 'impact_analysis' (explain why it failed), and 'suggested_fix'."
        )
        schema = {
            "type": "object",
            "properties": {
                "failed_test_name": {"type": "string"},
                "impact_analysis": {"type": "string"},
                "suggested_fix": {"type": "string"}
            },
            "required": ["failed_test_name", "impact_analysis", "suggested_fix"]
        }
        
        llm_insight = await query_llm_json(prompt, schema)
        
        issue = {
            "id": str(uuid.uuid4()),
            "file_path": "tests",
            "line_number": None,
            "severity": "HIGH",
            "impact_analysis": llm_insight.get("impact_analysis", "Test execution failed."),
            "description": f"Test Failure: {llm_insight.get('failed_test_name', 'Unknown Test')}",
            "suggested_fix": llm_insight.get("suggested_fix", "Review test logs.")
        }
        await self.write_issue(db_path, run_id, issue)

    async def _process_coverage(self, sandbox: Sandbox, db_path: str, run_id: int):
        print("  - Processing coverage metrics...")
        sandbox.run_command("coverage json -o coverage.json")
        cov_file = Path(sandbox.target_dir) / "coverage.json"
        
        if cov_file.exists():
            try:
                with open(cov_file, 'r') as f:
                    cov_data = json.load(f)
                
                percent_covered = cov_data.get("totals", {}).get("percent_covered", 0.0)
                await self.update_metrics(db_path, run_id, {"test_coverage_pct": round(percent_covered, 2)})
                print(f"  - Total Coverage: {percent_covered:.2f}%")
                
                os.remove(cov_file)
            except Exception as e:
                print(f"  - Failed to parse coverage.json: {e}")
        else:
            print("  - Coverage report could not be generated.")
