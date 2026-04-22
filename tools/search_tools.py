"""
Search Tools - Web search, documentation lookup.
"""
from __future__ import annotations
import json
import urllib.request
import urllib.parse
from typing import Optional

from tools.base import BaseTool, ToolResult, ToolResultStatus, ToolParameter


class WebSearchTool(BaseTool):
    """Search the web for information."""
    
    name = "web_search"
    description = "Search the web for documentation, examples, or information. Use for finding API docs, libraries, etc."
    parameters = [
        ToolParameter(name="query", type="string", description="Search query"),
        ToolParameter(name="num_results", type="integer", description="Number of results", required=False, default=5),
    ]
    requires_approval = False
    sandbox_safe = False  # Needs network access
    
    def execute(self, query: str, num_results: int = 5) -> ToolResult:
        try:
            # Use DuckDuckGo Instant Answer API (no API key needed)
            encoded_query = urllib.parse.quote(query)
            url = f"https://api.duckduckgo.com/?q={encoded_query}&format=json&no_html=1"
            
            req = urllib.request.Request(url, headers={"User-Agent": "AgentGenerator/1.0"})
            
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
            
            results = []
            
            # Abstract (main result)
            if data.get("Abstract"):
                results.append({
                    "title": data.get("Heading", "Result"),
                    "snippet": data["Abstract"][:500],
                    "url": data.get("AbstractURL", ""),
                })
            
            # Related topics
            for topic in data.get("RelatedTopics", [])[:num_results]:
                if isinstance(topic, dict) and "Text" in topic:
                    results.append({
                        "title": topic.get("Text", "")[:100],
                        "snippet": topic.get("Text", "")[:300],
                        "url": topic.get("FirstURL", ""),
                    })
            
            if results:
                output = "\n\n".join(
                    f"**{r['title']}**\n{r['snippet']}\n{r['url']}"
                    for r in results[:num_results]
                )
                return ToolResult(
                    status=ToolResultStatus.SUCCESS,
                    output=output,
                    metadata={"results": results, "query": query}
                )
            else:
                return ToolResult(
                    status=ToolResultStatus.SUCCESS,
                    output=f"No results found for: {query}",
                    metadata={"results": [], "query": query}
                )
                
        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"Search failed: {str(e)}"
            )


class PythonDocsTool(BaseTool):
    """Search Python documentation."""
    
    name = "python_docs"
    description = "Look up Python standard library documentation for a module or function."
    parameters = [
        ToolParameter(name="topic", type="string", description="Module or function name (e.g., 'json', 'os.path.join')"),
    ]
    requires_approval = False
    sandbox_safe = True
    
    def execute(self, topic: str) -> ToolResult:
        try:
            import pydoc
            
            # Try to get documentation
            doc = pydoc.render_doc(topic, title="%s")
            
            if doc:
                # Clean up and truncate
                doc = doc[:3000]
                return ToolResult(
                    status=ToolResultStatus.SUCCESS,
                    output=doc,
                    metadata={"topic": topic}
                )
            else:
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error=f"No documentation found for: {topic}"
                )
                
        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"Documentation lookup failed: {str(e)}"
            )


class PackageInfoTool(BaseTool):
    """Get information about a Python package from PyPI."""
    
    name = "package_info"
    description = "Get information about a Python package from PyPI (description, version, dependencies)."
    parameters = [
        ToolParameter(name="package", type="string", description="Package name on PyPI"),
    ]
    requires_approval = False
    sandbox_safe = False
    
    def execute(self, package: str) -> ToolResult:
        try:
            url = f"https://pypi.org/pypi/{package}/json"
            req = urllib.request.Request(url, headers={"User-Agent": "AgentGenerator/1.0"})
            
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
            
            info = data.get("info", {})
            
            result = {
                "name": info.get("name"),
                "version": info.get("version"),
                "summary": info.get("summary"),
                "author": info.get("author"),
                "license": info.get("license"),
                "requires_python": info.get("requires_python"),
                "homepage": info.get("home_page") or info.get("project_url"),
            }
            
            # Get dependencies
            requires = info.get("requires_dist", []) or []
            result["dependencies"] = [r.split(";")[0].strip() for r in requires[:10]]
            
            output = f"""**{result['name']}** v{result['version']}
{result['summary']}

Author: {result['author']}
License: {result['license']}
Python: {result['requires_python']}
Homepage: {result['homepage']}

Dependencies: {', '.join(result['dependencies'][:5]) or 'None'}"""
            
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=output,
                metadata=result
            )
                
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error=f"Package not found on PyPI: {package}"
                )
            raise
        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"Failed to get package info: {str(e)}"
            )


def get_search_tools(workspace_path: Optional[str] = None) -> list[BaseTool]:
    """Get all search tools."""
    return [
        WebSearchTool(workspace_path),
        PythonDocsTool(workspace_path),
        PackageInfoTool(workspace_path),
    ]
