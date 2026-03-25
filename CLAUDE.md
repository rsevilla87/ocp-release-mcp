# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is an MCP (Model Context Protocol) server that exposes OpenShift release information tools. It wraps the OpenShift release API (`amd64.ocp.releases.ci.openshift.org/api/v1`) using the `mcp` Python SDK with `FastMCP`.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install mcp httpx
```

## Running

```bash
python server.py
```

Or via the MCP SDK:
```bash
mcp run server.py
```

## Architecture

Single-file server (`server.py`) with three MCP tools:
- `get_release` - fetch details for a specific release version
- `list_tags` - list tags in a release stream
- `compare_releases` - diff two payloads in a stream

All tools are async and use `httpx` for HTTP requests against the OpenShift release API.

## Key Concepts

- **Release streams**: version channels like `4.22.0-0.nightly`, `4-stable`, `4-dev-preview`, `4.18.0-0.ci`
- **Release versions/tags**: specific builds like `4.22.0-0.nightly-2026-03-23-022245`
- Python 3.13, dependencies: `mcp`, `httpx`
