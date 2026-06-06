import os
import json
import uuid
import ast
from pathlib import Path
from openapi_spec_validator import validate_spec
from agents.base import BaseSQAAgent
from utils.llm import query_llm_json

class ValidationAgent(BaseSQAAgent):
    """Agent 3: Validates logic, schemas, and API contracts."""
    
    async def run(self, target_dir: str, db_path: str, run_id: int):
        print("  - Running logic validation and schema checking...")
        target_path = Path(target_dir)
        
        await self._validate_openapi_spec(target_path, db_path, run_id)
        await self._cross_check_business_logic(target_path, db_path, run_id)

    async def _validate_openapi_spec(self, target_path: Path, db_path: str, run_id: int):
        print("    - Searching for OpenAPI specifications...")
        spec_files = list(target_path.rglob("openapi.json")) + list(target_path.rglob("swagger.json"))
        
        for spec_file in spec_files:
            try:
                with open(spec_file, 'r') as f:
                    spec_dict = json.load(f)
                validate_spec(spec_dict)
                print(f"    - Valid OpenAPI spec found: {spec_file.name}")
            except Exception as e:
                print(f"    - Invalid OpenAPI spec found: {spec_file.name}")
                issue = {
                    "id": str(uuid.uuid4()),
                    "file_path": str(spec_file.relative_to(target_path)),
                    "line_number": None,
                    "severity": "HIGH",
                    "impact_analysis": "Invalid API contract will break client integrations.",
                    "description": f"OpenAPI Spec validation failed: {str(e)}",
                    "suggested_fix": "Review OpenAPI documentation syntax and correct the schema definition."
                }
                await self.write_issue(db_path, run_id, issue)

    async def _cross_check_business_logic(self, target_path: Path, db_path: str, run_id: int):
        print("    - Cross-checking code against business rules in README.md...")
        readme_path = target_path / "README.md"
        
        if not readme_path.exists():
            print("    - No README.md found to extract business rules from.")
            return

        with open(readme_path, 'r') as f:
            readme_content = f.read()

        py_files = list(target_path.glob("*.py"))
        if not py_files:
            return
            
        code_file = next((f for f in py_files if not f.name.startswith('test_')), py_files[0])
        
        with open(code_file, 'r') as f:
            source = f.read()
            
        # Try AST extraction for more focused analysis
        chunks = []
        try:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    chunks.append(ast.get_source_segment(source, node))
        except:
            chunks = [source[:3000]]
            
        code_content = "\n\n".join(chunks[:3]) # Limit to 3 chunks to save tokens
        readme_content = readme_content[:2000]

        prompt = (
            f"Here is a README document containing business rules for an application:\n"
            f"```markdown\n{readme_content}\n```\n\n"
            f"Here is the source code implementation:\n"
            f"```python\n{code_content}\n```\n\n"
            f"Analyze both. Are there any edge cases or business rules in the README that the code fails to implement correctly? "
            f"If so, provide a JSON with three keys: 'rule_violation_found' (boolean), 'impact_analysis' (string explaining the problem), and 'suggested_fix' (string). "
            f"If there are no violations, set 'rule_violation_found' to false."
        )
        
        schema = {
            "type": "object",
            "properties": {
                "rule_violation_found": {"type": "boolean"},
                "impact_analysis": {"type": "string"},
                "suggested_fix": {"type": "string"}
            },
            "required": ["rule_violation_found", "impact_analysis", "suggested_fix"]
        }
        
        llm_insight = await query_llm_json(prompt, schema)
        
        if llm_insight.get("rule_violation_found", False):
            issue = {
                "id": str(uuid.uuid4()),
                "file_path": str(code_file.relative_to(target_path)),
                "line_number": None,
                "severity": "MEDIUM",
                "impact_analysis": llm_insight.get("impact_analysis", "Business logic mismatch between docs and code."),
                "description": "Business logic mismatch detected.",
                "suggested_fix": llm_insight.get("suggested_fix", "Update code to reflect documentation.")
            }
            await self.write_issue(db_path, run_id, issue)
