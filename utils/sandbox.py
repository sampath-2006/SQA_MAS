import os
import uuid
import docker
from pathlib import Path
from docker.models.containers import Container

class Sandbox:
    """Provides an isolated Docker container execution environment."""
    
    def __init__(self, target_dir: str):
        self.target_dir = os.path.abspath(target_dir)
        self.container_name = f"sqa_sandbox_{uuid.uuid4().hex[:8]}"
        self.client = docker.from_env()
        self.container: Container = None
        
    def __enter__(self):
        print(f"Setting up Docker sandbox '{self.container_name}'...")
        
        # Pull image if not exists
        try:
            self.client.images.get("python:3.11-slim")
        except docker.errors.ImageNotFound:
            print("  - Pulling python:3.11-slim image (this might take a moment)...")
            self.client.images.pull("python:3.11-slim")
            
        # Start a persistent detached container
        self.container = self.client.containers.run(
            "python:3.11-slim",
            command="sleep infinity",
            name=self.container_name,
            volumes={self.target_dir: {'bind': '/app', 'mode': 'rw'}},
            working_dir="/app",
            detach=True,
            remove=True # Automatically remove when stopped
        )
        
        # Install requirements if they exist
        req_file = Path(self.target_dir) / "requirements.txt"
        if req_file.exists():
            self.run_command("pip install -r requirements.txt")
            
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.container:
            print(f"Cleaning up Docker sandbox '{self.container_name}'...")
            self.container.stop(timeout=2)
            
    def run_command(self, cmd: str) -> dict:
        """Runs a shell command inside the container and returns the result."""
        # Using sh -c allows parsing pipes and multiple commands if needed
        exit_code, output = self.container.exec_run(["sh", "-c", cmd], workdir="/app")
        
        # Return a dictionary mimicking the old subprocess.CompletedProcess
        return {
            "returncode": exit_code,
            "stdout": output.decode('utf-8', errors='replace'),
            "stderr": "" # exec_run combines stdout and stderr by default
        }
