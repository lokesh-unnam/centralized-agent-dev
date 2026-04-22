"""
Terminal Tools - Execute shell commands, run Python, manage packages.
"""
from __future__ import annotations
import subprocess
import sys
import os
from pathlib import Path
from typing import Optional
import tempfile

from tools.base import BaseTool, ToolResult, ToolResultStatus, ToolParameter


class ExecuteCommandTool(BaseTool):
    """Execute a shell command."""
    
    name = "execute_command"
    description = "Execute a shell command in the workspace directory. Use for running scripts, tools, etc."
    parameters = [
        ToolParameter(name="command", type="string", description="The command to execute"),
        ToolParameter(name="timeout", type="integer", description="Timeout in seconds", required=False, default=60),
    ]
    requires_approval = True  # Shell commands need approval
    sandbox_safe = False
    
    def execute(self, command: str, timeout: int = 60) -> ToolResult:
        try:
            cwd = self.workspace_path or os.getcwd()
            
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"}
            )
            
            output = result.stdout
            if result.stderr:
                output += f"\n[STDERR]\n{result.stderr}"
            
            if result.returncode == 0:
                return ToolResult(
                    status=ToolResultStatus.SUCCESS,
                    output=output.strip() or "(no output)",
                    metadata={"return_code": result.returncode, "command": command}
                )
            else:
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error=f"Command failed with code {result.returncode}",
                    output=output.strip(),
                    metadata={"return_code": result.returncode, "command": command}
                )
                
        except subprocess.TimeoutExpired:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"Command timed out after {timeout} seconds"
            )
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=str(e))


class RunPythonTool(BaseTool):
    """Execute Python code."""
    
    name = "run_python"
    description = "Execute Python code and return the output. Good for testing snippets or running scripts."
    parameters = [
        ToolParameter(name="code", type="string", description="Python code to execute"),
        ToolParameter(name="timeout", type="integer", description="Timeout in seconds", required=False, default=30),
    ]
    requires_approval = False
    sandbox_safe = True
    
    def execute(self, code: str, timeout: int = 30) -> ToolResult:
        try:
            # Write code to temp file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                f.write(code)
                temp_path = f.name
            
            try:
                cwd = self.workspace_path or os.getcwd()
                
                result = subprocess.run(
                    [sys.executable, temp_path],
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env={**os.environ, "PYTHONPATH": cwd, "PYTHONIOENCODING": "utf-8"}
                )
                
                output = result.stdout
                if result.stderr:
                    output += f"\n[STDERR]\n{result.stderr}"
                
                if result.returncode == 0:
                    return ToolResult(
                        status=ToolResultStatus.SUCCESS,
                        output=output.strip() or "(no output)",
                        metadata={"return_code": result.returncode}
                    )
                else:
                    return ToolResult(
                        status=ToolResultStatus.ERROR,
                        error=f"Python execution failed",
                        output=output.strip(),
                        metadata={"return_code": result.returncode}
                    )
            finally:
                os.unlink(temp_path)
                
        except subprocess.TimeoutExpired:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"Python execution timed out after {timeout} seconds"
            )
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=str(e))


class RunPythonFileTool(BaseTool):
    """Execute a Python file."""
    
    name = "run_python_file"
    description = "Execute a Python file from the workspace."
    parameters = [
        ToolParameter(name="path", type="string", description="Path to Python file"),
        ToolParameter(name="args", type="string", description="Command line arguments", required=False, default=""),
        ToolParameter(name="timeout", type="integer", description="Timeout in seconds", required=False, default=60),
    ]
    requires_approval = False
    sandbox_safe = True
    
    def execute(self, path: str, args: str = "", timeout: int = 60) -> ToolResult:
        try:
            if self.workspace_path:
                full_path = Path(self.workspace_path) / path
                cwd = self.workspace_path
            else:
                full_path = Path(path)
                cwd = str(full_path.parent)
            
            if not full_path.exists():
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error=f"File not found: {path}"
                )
            
            cmd = [sys.executable, str(full_path)]
            if args:
                cmd.extend(args.split())
            
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "PYTHONPATH": cwd, "PYTHONIOENCODING": "utf-8"}
            )
            
            output = result.stdout
            if result.stderr:
                output += f"\n[STDERR]\n{result.stderr}"
            
            if result.returncode == 0:
                return ToolResult(
                    status=ToolResultStatus.SUCCESS,
                    output=output.strip() or "(no output)",
                    metadata={"return_code": result.returncode, "file": path}
                )
            else:
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error=f"Script failed with code {result.returncode}",
                    output=output.strip(),
                    metadata={"return_code": result.returncode, "file": path}
                )
                
        except subprocess.TimeoutExpired:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"Script timed out after {timeout} seconds"
            )
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=str(e))


class InstallPackageTool(BaseTool):
    """Install a Python package using pip."""
    
    name = "install_package"
    description = "Install a Python package using pip."
    parameters = [
        ToolParameter(name="package", type="string", description="Package name (e.g., 'requests' or 'requests==2.28.0')"),
    ]
    requires_approval = True
    sandbox_safe = True
    
    def execute(self, package: str) -> ToolResult:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", package, "--quiet"],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                return ToolResult(
                    status=ToolResultStatus.SUCCESS,
                    output=f"Successfully installed {package}",
                    metadata={"package": package}
                )
            else:
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error=f"Failed to install {package}: {result.stderr}",
                    metadata={"package": package}
                )
                
        except subprocess.TimeoutExpired:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"Installation timed out"
            )
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=str(e))


class RunTestsTool(BaseTool):
    """Run pytest tests."""
    
    name = "run_tests"
    description = "Run pytest tests in the workspace. Returns test results and failures."
    parameters = [
        ToolParameter(name="path", type="string", description="Test file or directory path", required=False, default="."),
        ToolParameter(name="verbose", type="boolean", description="Verbose output", required=False, default=True),
        ToolParameter(name="timeout", type="integer", description="Timeout in seconds", required=False, default=120),
    ]
    requires_approval = False
    sandbox_safe = True
    
    def execute(self, path: str = ".", verbose: bool = True, timeout: int = 120) -> ToolResult:
        try:
            cwd = self.workspace_path or os.getcwd()
            
            cmd = [sys.executable, "-m", "pytest", path]
            if verbose:
                cmd.append("-v")
            cmd.append("--tb=short")
            
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "PYTHONPATH": cwd, "PYTHONIOENCODING": "utf-8"}
            )
            
            output = result.stdout
            if result.stderr:
                output += f"\n[STDERR]\n{result.stderr}"
            
            # Parse test results
            passed = "passed" in output.lower()
            failed = "failed" in output.lower() or "error" in output.lower()
            
            if result.returncode == 0:
                return ToolResult(
                    status=ToolResultStatus.SUCCESS,
                    output=output.strip(),
                    metadata={"all_passed": True, "return_code": result.returncode}
                )
            else:
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error="Some tests failed",
                    output=output.strip(),
                    metadata={"all_passed": False, "return_code": result.returncode}
                )
                
        except subprocess.TimeoutExpired:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"Tests timed out after {timeout} seconds"
            )
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=str(e))


def get_terminal_tools(workspace_path: Optional[str] = None) -> list[BaseTool]:
    """Get all terminal tools configured for a workspace."""
    return [
        ExecuteCommandTool(workspace_path),
        RunPythonTool(workspace_path),
        RunPythonFileTool(workspace_path),
        InstallPackageTool(workspace_path),
        RunTestsTool(workspace_path),
    ]
