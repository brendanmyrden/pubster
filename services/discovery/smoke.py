import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
async def main():
 async with stdio_client(StdioServerParameters(command='/Volumes/SYYR/Pubster/scripts/pubster-discovery-mcp')) as (read,write):
  async with ClientSession(read,write) as session:
   await session.initialize()
   listed=await session.list_tools()
   assert len(listed.tools)==4
   result=await session.call_tool('compare_repos',{'repositories':['apple/swift-algorithms'],'public_objective':'Swift collections'})
   assert not result.is_error, result
   print('MCP initialize + four tool schemas + live compare_repos: PASS')
asyncio.run(main())
