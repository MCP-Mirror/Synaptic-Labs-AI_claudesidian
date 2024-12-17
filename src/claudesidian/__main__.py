#!/usr/bin/env python
import asyncio
import sys
import logging
from pathlib import Path

from mcp.server import Server, NotificationOptions
from mcp.server.stdio import stdio_server
from claudesidian.config import Config

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('claudesidian.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("claudesidian")

def setup_tools(server: Server):
    """Set up server tools and capabilities."""
    logger.info("Setting up server tools...")
    
    # Define tools with proper schemas
    tools = [{
        "name": "read_vault",
        "description": "Read content from the vault",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to read"},
            },
            "required": ["path"]
        }
    }]
    
    # Register tools
    @server.list_tools()
    async def list_tools():
        logger.info("Tool list requested")
        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        logger.info(f"Tool called: {name} with arguments: {arguments}")
        if name == "read_vault":
            path = arguments["path"]
            # Implement your vault reading logic here
            return {"content": [{"type": "text", "text": f"Content from {path}"}]}
        else:
            raise ValueError(f"Unknown tool: {name}")

async def main():
    """Main entry point."""
    try:
        logger.info("Starting Claudesidian server...")
        
        # Load config
        config = Config.load()
        logger.info(f"Config loaded: {config}")
        
        # Initialize server without version parameter
        server = Server(name="claudesidian")
        
        # Set up tools and handlers
        setup_tools(server)
        logger.info("Server initialized")
        
        # Set up stdio transport
        logger.info("Setting up stdio transport...")
        async with stdio_server() as (read_stream, write_stream):
            logger.info("Stdio transport ready")
            
            try:
                await server.run(
                    read_stream,
                    write_stream,
                    server.create_initialization_options(
                        notification_options=NotificationOptions()
                    )
                )
            except Exception as e:
                logger.error(f"Server run error: {str(e)}", exc_info=True)
                raise
                
    except Exception as e:
        logger.error(f"Startup error: {str(e)}", exc_info=True)
        sys.exit(1)

def run():
    """Wrapper to handle keyboard interrupts."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Received exit request...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    run()