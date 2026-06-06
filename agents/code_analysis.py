import json
import uuid
import ast
import subprocess
from pathlib import Path
from agents.base import BaseSQAAgent
from utils.llm import query_llm_json

class CodeAnalysisAgent(BaseSQAAgent):
    """Agent 1: Statical complexity and security scanning."""
    
    async def run(self, target_dir: str, db_path: str, run_id: int):
        print("  - Running Radon for complexity...")
        await self._run_radon(target_dir, db_path, run_id)
        
        print("  - Running Bandit for static security analysis...")
        await self._run_bandit(target_dir, db_path, run_id)

    async def _run_radon(self, target_dir: str, db_path: str, run_id: int):
        try:
            # -j for json output, -s for summary
            result = subprocess.run(["radon", "cc", "-j", target_dir], capture_output=True, text=True)
            data = json.loads(result.stdout)
            
            total_complexity = 0
            count = 0
            
            for file_path, blocks in data.items():
                for block in blocks:
                    # Radon outputs classes, functions, methods
                    complexity = block.get('complexity', 0)
                    total_complexity += complexity
                    count += 1
                    
                    if complexity > 10: # Threshold for high complexity
                        # Extract just the function via AST instead of truncating
                        chunk = self._extract_ast_chunk(file_path, block.get('lineno'))
                        
                        prompt = (
                            f"The following code chunk has a high cyclomatic complexity of {complexity}.\n\n"
                            f"```python\n{chunk}\n```\n\n"
                            f"Provide a JSON with two keys: 'impact_analysis' (explain why this is bad) and 'suggested_fix' (how to refactor it)."
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
                            "file_path": file_path,
                            "line_number": block.get('lineno'),
                            "severity": "MEDIUM",
                            "impact_analysis": llm_insight.get("impact_analysis", "High cyclomatic complexity."),
                            "description": f"Complexity is {complexity} (Threshold: 10)",
                            "suggested_fix": llm_insight.get("suggested_fix", "Refactor to reduce complexity.")
                        }
                        await self.write_issue(db_path, run_id, issue)
            
            avg = total_complexity / count if count > 0 else 0
            await self.update_metrics(db_path, run_id, {"complexity_avg": avg})
            
        except Exception as e:
            print(f"    - Radon failed: {e}")

    async def _run_bandit(self, target_dir: str, db_path: str, run_id: int):
        try:
            result = subprocess.run(["bandit", "-r", target_dir, "-f", "json"], capture_output=True, text=True)
            # Bandit exit code 1 means issues found, 0 means clean
            data = json.loads(result.stdout)
            
            for result in data.get("results", []):
                severity_map = {"HIGH": "HIGH", "MEDIUM": "MEDIUM", "LOW": "LOW"}
                severity = severity_map.get(result.get("issue_severity"), "LOW")
                
                # Fetch exact lines instead of full file
                code_snippet = result.get("code", "")
                
                prompt = (
                    f"Bandit found a {severity} security issue: '{result.get('issue_text')}'.\n\n"
                    f"Code snippet:\n```python\n{code_snippet}\n```\n\n"
                    f"Provide a JSON with two keys: 'impact_analysis' (explain the security risk) and 'suggested_fix'."
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
                    "file_path": result.get("filename"),
                    "line_number": result.get("line_number"),
                    "severity": severity,
                    "impact_analysis": llm_insight.get("impact_analysis", "Security vulnerability detected."),
                    "description": result.get("issue_text"),
                    "suggested_fix": llm_insight.get("suggested_fix", "Fix the vulnerability.")
                }
                await self.write_issue(db_path, run_id, issue)
                
        except Exception as e:
            print(f"    - Bandit failed: {e}")

    def _extract_ast_chunk(self, file_path: str, lineno: int) -> str:
        """Uses AST to extract just the function/class containing the line number."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()
            tree = ast.parse(source)
            
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    # Check if the node encompasses the line number
                    if hasattr(node, 'lineno') and hasattr(node, 'end_lineno'):
                        if node.lineno <= lineno <= node.end_lineno:
                            return ast.get_source_segment(source, node)
                            
            return "Could not extract specific AST node."
        except Exception:
            return "AST parsing failed."
