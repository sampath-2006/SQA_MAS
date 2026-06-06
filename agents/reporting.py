import os
import json
import aiosqlite
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from agents.base import BaseSQAAgent

class ReportingAgent(BaseSQAAgent):
    """Agent 5: Generates final reports from State Store data."""
    
    async def run(self, target_dir: str, db_path: str, run_id: int):
        print("  - Querying database for all issues and metrics...")
        
        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT timestamp, metrics FROM run_state WHERE id = ?", (run_id,)) as cursor:
                res = await cursor.fetchone()
            
            timestamp = res[0]
            metrics = json.loads(res[1]) if res[1] else {}
            
            async with db.execute(
                "SELECT agent, file_path, line_number, severity, impact_analysis, description, suggested_fix FROM issues WHERE run_id = ?",
                (run_id,)
            ) as cursor:
                issue_rows = await cursor.fetchall()
            
        issues = []
        for row in issue_rows:
            issues.append({
                "agent": row[0],
                "file_path": row[1],
                "line_number": row[2],
                "severity": row[3],
                "impact_analysis": row[4],
                "description": row[5],
                "suggested_fix": row[6]
            })
            
        critical_issues = [i for i in issues if i["severity"] in ("CRITICAL", "HIGH")]
        other_issues = [i for i in issues if i["severity"] in ("MEDIUM", "LOW")]
        
        score = 100
        score -= len(critical_issues) * 15
        score -= len(other_issues) * 5
        score += metrics.get("test_coverage_pct", 0) * 0.2
        score -= metrics.get("complexity_avg", 0) * 1.5
        
        quality_score = max(0, min(100, round(score)))
        
        if len(critical_issues) > 0:
            release_status = "Not Ready"
            status = "FAILED"
        elif len(other_issues) > 5 or quality_score < 70:
            release_status = "Ready with Warnings"
            status = "PASSED_WITH_WARNINGS"
        else:
            release_status = "Ready"
            status = "PASSED"

        print(f"  - Generating Markdown report (Score: {quality_score}, Status: {release_status})...")
        
        template_dir = Path(__file__).parent.parent / "templates"
        env = Environment(loader=FileSystemLoader(str(template_dir)))
        template = env.get_template("report_template.md.j2")
        
        report_content = template.render(
            target_dir=target_dir,
            timestamp=timestamp,
            status=status,
            metrics=metrics,
            quality_score=quality_score,
            release_status=release_status,
            critical_issues=critical_issues,
            other_issues=other_issues
        )
        
        report_path = Path(target_dir) / "sqa_report.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_content)
            
        print(f"  - Report successfully written to {report_path}")
