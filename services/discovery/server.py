"""Project-local stdio MCP. No gateway registration or configuration changes."""
from mcp.server.mcpserver import MCPServer
from pubster import discovery as d
mcp=MCPServer('Pubster public repository discovery')
@mcp.tool()
def discover_adjacent(seed: str, public_objective: str) -> dict:
    """Discover public repositories. Objective is sent to GitHub; never supply private text."""
    return d.discover(seed,public_objective)
@mcp.tool()
def find_implementations(repository: str, term: str) -> list:
    """Find public code path evidence; never executes or downloads implementations."""
    client=d.Client(); repo=client.public(repository)
    return d.implementations(client,repo['full_name'],term)
@mcp.tool()
def compare_repos(repositories: list[str], public_objective: str) -> list:
    """Compare at most four public repositories using transparent metadata scores."""
    if not 1<=len(repositories)<=4 or len(public_objective)>160: raise ValueError('Bound exceeded')
    client=d.Client()
    return [d.summary(client.public(r),public_objective) for r in repositories]
@mcp.tool()
def integration_plan(repository: str) -> dict:
    """Return pinned manifest evidence and explicit review steps, not compatibility claims."""
    client=d.Client(); repo=client.public(repository)
    return {'repository':repo['full_name'],**d.inspect(client,repo),'status':'REVIEW_REQUIRED','steps':['Review license and attribution obligations','Inspect pinned manifests and supported runtime versions','Audit relevant code and dependencies','Prototype in an isolated project-local environment','Test compatibility before approving an integration'],'automatically_installed':False}
if __name__=='__main__': mcp.run(transport='stdio')
