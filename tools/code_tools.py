"""
Code Tools - Lint, format, typecheck, analyze code.
"""
from __future__ import annotations
import subprocess
import sys
import os
import ast
import re
from pathlib import Path
from typing import Optional

from tools.base import BaseTool, ToolResult, ToolResultStatus, ToolParameter


class LintCodeTool(BaseTool):
    """Lint Python code using ruff or flake8."""
    
    name = "lint_code"
    description = "Run linter on Python files to check for errors and style issues."
    parameters = [
        ToolParameter(name="path", type="string", description="File or directory to lint", required=False, default="."),
        ToolParameter(name="fix", type="boolean", description="Auto-fix issues if possible", required=False, default=False),
    ]
    requires_approval = False
    sandbox_safe = True
    
    def execute(self, path: str = ".", fix: bool = False) -> ToolResult:
        try:
            cwd = self.workspace_path or os.getcwd()
            full_path = Path(cwd) / path if self.workspace_path else Path(path)
            
            # Try ruff first, then flake8
            linters = [
                ([sys.executable, "-m", "ruff", "check", str(full_path)] + (["--fix"] if fix else []), "ruff"),
                ([sys.executable, "-m", "flake8", str(full_path)], "flake8"),
            ]
            
            for cmd, linter_name in linters:
                try:
                    result = subprocess.run(
                        cmd,
                        cwd=cwd,
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                    
                    output = result.stdout + result.stderr
                    
                    if result.returncode == 0:
                        return ToolResult(
                            status=ToolResultStatus.SUCCESS,
                            output=f"No lint errors found ({linter_name})",
                            metadata={"linter": linter_name, "path": path}
                        )
                    else:
                        # Parse errors
                        errors = self._parse_lint_errors(output)
                        return ToolResult(
                            status=ToolResultStatus.ERROR,
                            error=f"Found {len(errors)} lint issues",
                            output=output.strip(),
                            metadata={"linter": linter_name, "errors": errors, "path": path}
                        )
                except FileNotFoundError:
                    continue
            
            # Fallback to basic syntax check
            return self._basic_syntax_check(full_path)
            
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=str(e))
    
    def _parse_lint_errors(self, output: str) -> list[dict]:
        """Parse lint output into structured errors."""
        errors = []
        for line in output.splitlines():
            # Pattern: file.py:10:5: E501 line too long
            match = re.match(r"(.+?):(\d+):(\d+):\s*(\w+)\s+(.*)", line)
            if match:
                errors.append({
                    "file": match.group(1),
                    "line": int(match.group(2)),
                    "column": int(match.group(3)),
                    "code": match.group(4),
                    "message": match.group(5),
                })
        return errors
    
    def _basic_syntax_check(self, path: Path) -> ToolResult:
        """Basic Python syntax check using ast."""
        errors = []
        
        if path.is_file():
            files = [path]
        else:
            files = list(path.rglob("*.py"))
        
        for file in files:
            try:
                content = file.read_text(encoding="utf-8")
                ast.parse(content)
            except SyntaxError as e:
                errors.append({
                    "file": str(file),
                    "line": e.lineno,
                    "message": str(e.msg),
                })
        
        if errors:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"Found {len(errors)} syntax errors",
                output="\n".join(f"{e['file']}:{e['line']}: {e['message']}" for e in errors),
                metadata={"errors": errors}
            )
        
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output="No syntax errors found (basic check)",
            metadata={"checker": "ast"}
        )


class TypeCheckTool(BaseTool):
    """Type check Python code using mypy or pyright."""
    
    name = "type_check"
    description = "Run type checker on Python files to find type errors."
    parameters = [
        ToolParameter(name="path", type="string", description="File or directory to check", required=False, default="."),
    ]
    requires_approval = False
    sandbox_safe = True
    
    def execute(self, path: str = ".") -> ToolResult:
        try:
            cwd = self.workspace_path or os.getcwd()
            full_path = Path(cwd) / path if self.workspace_path else Path(path)
            
            # Try mypy
            result = subprocess.run(
                [sys.executable, "-m", "mypy", str(full_path), "--ignore-missing-imports"],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            output = result.stdout + result.stderr
            
            if result.returncode == 0 or "Success" in output:
                return ToolResult(
                    status=ToolResultStatus.SUCCESS,
                    output="No type errors found",
                    metadata={"checker": "mypy", "path": path}
                )
            else:
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error="Type errors found",
                    output=output.strip(),
                    metadata={"checker": "mypy", "path": path}
                )
                
        except FileNotFoundError:
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output="Type checker not available (mypy not installed)",
                metadata={"checker": "none"}
            )
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=str(e))


class FormatCodeTool(BaseTool):
    """Format Python code using black or ruff."""
    
    name = "format_code"
    description = "Format Python code to follow style guidelines."
    parameters = [
        ToolParameter(name="path", type="string", description="File or directory to format", required=False, default="."),
    ]
    requires_approval = False
    sandbox_safe = True
    
    def execute(self, path: str = ".") -> ToolResult:
        try:
            cwd = self.workspace_path or os.getcwd()
            full_path = Path(cwd) / path if self.workspace_path else Path(path)
            
            # Try ruff format first, then black
            formatters = [
                ([sys.executable, "-m", "ruff", "format", str(full_path)], "ruff"),
                ([sys.executable, "-m", "black", str(full_path)], "black"),
            ]
            
            for cmd, formatter_name in formatters:
                try:
                    result = subprocess.run(
                        cmd,
                        cwd=cwd,
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                    
                    if result.returncode == 0:
                        return ToolResult(
                            status=ToolResultStatus.SUCCESS,
                            output=f"Code formatted successfully ({formatter_name})",
                            metadata={"formatter": formatter_name, "path": path}
                        )
                except FileNotFoundError:
                    continue
            
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output="No formatter available (ruff/black not installed)",
                metadata={"formatter": "none"}
            )
                
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=str(e))


class AnalyzeCodeTool(BaseTool):
    """Analyze Python code structure and extract information."""
    
    name = "analyze_code"
    description = "Analyze Python code to extract classes, functions, imports, and dependencies."
    parameters = [
        ToolParameter(name="path", type="string", description="File to analyze"),
    ]
    requires_approval = False
    sandbox_safe = True
    
    def execute(self, path: str) -> ToolResult:
        try:
            if self.workspace_path:
                full_path = Path(self.workspace_path) / path
            else:
                full_path = Path(path)
            
            if not full_path.exists():
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error=f"File not found: {path}"
                )
            
            content = full_path.read_text(encoding="utf-8")
            
            try:
                tree = ast.parse(content)
            except SyntaxError as e:
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error=f"Syntax error: {e.msg} at line {e.lineno}"
                )
            
            analysis = {
                "imports": [],
                "classes": [],
                "functions": [],
                "global_vars": [],
            }
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        analysis["imports"].append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    for alias in node.names:
                        analysis["imports"].append(f"{module}.{alias.name}")
                elif isinstance(node, ast.ClassDef):
                    methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                    analysis["classes"].append({
                        "name": node.name,
                        "methods": methods,
                        "line": node.lineno,
                    })
                elif isinstance(node, ast.FunctionDef) and isinstance(node, ast.FunctionDef):
                    # Only top-level functions
                    if any(isinstance(parent, ast.Module) for parent in ast.walk(tree)):
                        args = [arg.arg for arg in node.args.args]
                        analysis["functions"].append({
                            "name": node.name,
                            "args": args,
                            "line": node.lineno,
                        })
            
            # Deduplicate
            analysis["imports"] = list(set(analysis["imports"]))
            
            summary = (
                f"Imports: {len(analysis['imports'])}, "
                f"Classes: {len(analysis['classes'])}, "
                f"Functions: {len(analysis['functions'])}"
            )
            
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=summary,
                metadata=analysis
            )
            
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=str(e))


class SearchCodeTool(BaseTool):
    """Search for patterns in code files."""
    
    name = "search_code"
    description = "Search for a pattern in code files. Returns matching lines with context."
    parameters = [
        ToolParameter(name="pattern", type="string", description="Search pattern (regex supported)"),
        ToolParameter(name="path", type="string", description="Directory to search", required=False, default="."),
        ToolParameter(name="file_pattern", type="string", description="File glob pattern", required=False, default="*.py"),
    ]
    requires_approval = False
    sandbox_safe = True
    
    def execute(self, pattern: str, path: str = ".", file_pattern: str = "*.py") -> ToolResult:
        try:
            if self.workspace_path:
                full_path = Path(self.workspace_path) / path
            else:
                full_path = Path(path)
            
            if not full_path.exists():
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error=f"Path not found: {path}"
                )
            
            matches = []
            regex = re.compile(pattern, re.IGNORECASE)
            
            files = full_path.rglob(file_pattern) if full_path.is_dir() else [full_path]
            
            for file in files:
                if file.is_file():
                    try:
                        content = file.read_text(encoding="utf-8")
                        for i, line in enumerate(content.splitlines(), 1):
                            if regex.search(line):
                                matches.append({
                                    "file": str(file.relative_to(full_path) if full_path.is_dir() else file.name),
                                    "line": i,
                                    "content": line.strip()[:200],
                                })
                    except Exception:
                        continue
            
            if matches:
                output = "\n".join(
                    f"{m['file']}:{m['line']}: {m['content']}" 
                    for m in matches[:50]  # Limit results
                )
                return ToolResult(
                    status=ToolResultStatus.SUCCESS,
                    output=output,
                    metadata={"matches": matches[:50], "total": len(matches)}
                )
            else:
                return ToolResult(
                    status=ToolResultStatus.SUCCESS,
                    output=f"No matches found for pattern: {pattern}",
                    metadata={"matches": [], "total": 0}
                )
                
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=str(e))


def get_code_tools(workspace_path: Optional[str] = None) -> list[BaseTool]:
    """Get all code tools configured for a workspace."""
    return [
        LintCodeTool(workspace_path),
        TypeCheckTool(workspace_path),
        FormatCodeTool(workspace_path),
        AnalyzeCodeTool(workspace_path),
        SearchCodeTool(workspace_path),
    ]
