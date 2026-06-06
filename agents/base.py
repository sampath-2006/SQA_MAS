import json
import aiosqlite

class BaseSQAAgent:
    """Abstract Base Class for all SQA-MAS Agents."""
    
    async def run(self, target_dir: str, db_path: str, run_id: int):
        """Main entry point for the agent logic."""
        raise NotImplementedError("Each agent must implement its own run() method.")
        
    async def write_issue(self, db_path: str, run_id: int, issue: dict):
        """Helper to safely write an issue to the state database asynchronously."""
        agent_name = self.__class__.__name__
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                """INSERT INTO issues 
                   (id, run_id, agent, file_path, line_number, severity, impact_analysis, description, suggested_fix) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    issue["id"],
                    run_id,
                    agent_name,
                    issue["file_path"],
                    issue.get("line_number"),
                    issue["severity"],
                    issue["impact_analysis"],
                    issue["description"],
                    issue["suggested_fix"]
                )
            )
            await db.commit()
            
    async def update_metrics(self, db_path: str, run_id: int, new_metrics: dict):
        """Helper to update the metrics JSON asynchronously."""
        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT metrics FROM run_state WHERE id = ?", (run_id,)) as cursor:
                row = await cursor.fetchone()
                
            if row:
                metrics = json.loads(row[0]) if row[0] else {}
                metrics.update(new_metrics)
                await db.execute("UPDATE run_state SET metrics = ? WHERE id = ?", (json.dumps(metrics), run_id))
                await db.commit()
