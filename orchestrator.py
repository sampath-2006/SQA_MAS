import os
import json
import asyncio
import aiosqlite
from agents.code_analysis import CodeAnalysisAgent
from agents.regression import RegressionTestingAgent
from agents.validation import ValidationAgent
from agents.sanity import SanityTestingAgent
from agents.reporting import ReportingAgent

class SQAOrchestrator:
    def __init__(self, target_dir: str):
        self.target_dir = os.path.abspath(target_dir)
        # Store DB in the tool directory, not the target repo
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.db_path = os.path.join(script_dir, "sqa_state.db")
        
        self.agents = [
            CodeAnalysisAgent(),
            RegressionTestingAgent(),
            ValidationAgent(),
            SanityTestingAgent(),
        ]
        self.reporting_agent = ReportingAgent()
        
    async def setup_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''CREATE TABLE IF NOT EXISTS run_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                target_dir TEXT,
                status TEXT,
                metrics TEXT
            )''')
            await db.execute('''CREATE TABLE IF NOT EXISTS issues (
                id TEXT PRIMARY KEY,
                run_id INTEGER,
                agent TEXT,
                file_path TEXT,
                line_number INTEGER,
                severity TEXT,
                impact_analysis TEXT,
                description TEXT,
                suggested_fix TEXT
            )''')
            await db.commit()

    async def run_pipeline(self):
        print(f"\nStarting ASYNC SQA-MAS Pipeline for: {self.target_dir}\n")
        
        await self.setup_db()
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("INSERT INTO run_state (target_dir, status, metrics) VALUES (?, ?, ?)", 
                                      (self.target_dir, "RUNNING", "{}"))
            run_id = cursor.lastrowid
            await db.commit()

        # Run primary agents concurrently using asyncio.gather
        tasks = []
        for agent in self.agents:
            tasks.append(agent.run(self.target_dir, self.db_path, run_id))
            
        # This executes Agent 1-4 perfectly in parallel
        await asyncio.gather(*tasks)

        # Run reporting agent sequentially at the end
        print("\n--- Running Agent: ReportingAgent ---")
        await self.reporting_agent.run(self.target_dir, self.db_path, run_id)
        
        print(f"\nPipeline finished. State saved to {self.db_path}")
