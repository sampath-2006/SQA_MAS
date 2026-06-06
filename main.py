import click
import asyncio
from pathlib import Path
from orchestrator import SQAOrchestrator

@click.group()
def cli():
    """SQA-MAS: Autonomous Software Quality Assurance Multi-Agent System"""
    pass

@cli.command()
@click.argument('target_dir', type=click.Path(exists=True))
def scan(target_dir):
    """Run the complete SQA-MAS pipeline on a target directory."""
    orchestrator = SQAOrchestrator(target_dir)
    asyncio.run(orchestrator.run_pipeline())

if __name__ == '__main__':
    cli()
