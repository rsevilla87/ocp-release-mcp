from openshift_release_mcp.server import mcp, logger

import os


def main():
    logger.info("Starting MCP server at %s:%s", os.getenv("HOST", "0.0.0.0"), os.getenv("PORT", 8000))
    mcp.run(transport="streamable-http")
