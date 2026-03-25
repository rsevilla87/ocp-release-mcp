import logging
import os

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
from typing import List
load_dotenv()

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("openshift-release")

mcp = FastMCP(
    "openshift-release",
    host=os.getenv("HOST", "0.0.0.0"),
    port=int(os.getenv("PORT", 8000)),
)

BASE_URL = os.getenv("BASE_URL", "https://amd64.ocp.releases.ci.openshift.org/api/v1")

class CommitInfo(BaseModel):
    """A commit info in a release payload."""
    subject: str
    pull_request_url: str

class UpdatedImage(BaseModel):
    """An updated image in a release payload."""
    name: str
    commits: List[CommitInfo] = Field(default_factory=list)

class ReleaseInfo(BaseModel):
    """Information about an OpenShift release payload."""
    version: str
    phase: str
    updated_images: List[UpdatedImage] = Field(default_factory=list)

async def _get_json(url: str) -> dict:
    logger.info("GET %s", url)
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        logger.info("Response %s from %s", resp.status_code, url)
        return resp.json()

async def _get_text(url: str) -> str:
    logger.info("GET %s", url)
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        logger.info("Response %s from %s", resp.status_code, url)
        return resp.text

@mcp.tool()
async def get_release(stream: str, version: str) -> dict:
    """Fetch detailed information about a specific OpenShift release version.

    Args:
        stream: The release stream, e.g. '4.22.0-0.nightly', '4-stable', '4-dev-preview', '4.18.0-0.ci'
        version: The full release version tag, e.g. '4.22.0-0.nightly-2026-03-23-022245'
    """
    logger.info("get_release called: stream=%s, version=%s", stream, version)
    payload = await _get_json(f"{BASE_URL}/releasestream/{stream}/release/{version}")
    release_info = ReleaseInfo(
        version=payload["name"],
        phase=payload["phase"],
    )
    if "changeLogJson" in payload and "updatedImages" in payload["changeLogJson"]:
        for image in payload["changeLogJson"]["updatedImages"]:
            updated_image = UpdatedImage(name=image["name"])
            if "commits" in image:
                updated_image.commits = [CommitInfo(subject=commit["subject"], pull_request_url=commit["pullURL"]) for commit in image["commits"]]
            release_info.updated_images.append(updated_image)
    return release_info


@mcp.tool()
async def list_tags(stream: str, phase: str) -> dict:
    """List the latest release tags for a given release stream.

    Args:
        stream: The release stream, e.g. '4.22.0-0.nightly', '4-stable', '4-dev-preview', '4.18.0-0.ci'
        phase: The release phase, e.g. 'Accepted, Accepted, Ready'
    """
    logger.info("list_tags called: stream=%s, phase=%s", stream, phase)
    if phase:
        return await _get_json(f"{BASE_URL}/releasestream/{stream}/tags?phase={phase}")
    return await _get_json(f"{BASE_URL}/releasestream/{stream}/tags")


@mcp.tool()
async def compare_releases(stream: str, payload1: str, payload2: str) -> dict:
    """Compare two payload versions within a release stream, showing differences between them.

    Args:
        stream: The release stream, e.g. '4.22.0-0.nightly'
        payload1: The target release version to compare
        payload2: The base release version to compare from
    """
    logger.info("compare_releases called: stream=%s, payload1=%s, payload2=%s", stream, payload1, payload2)
    return await _get_json(
        f"{BASE_URL}/releasestream/{stream}/release/{payload1}?from={payload2}"
    )

@mcp.tool()
async def get_pull_request_info(url: str) -> dict:
    """Get the details of a pull request from a pull request URL.

    Args:
        pull_request_url: The URL of the pull request
    """
    return await _get_text(url + ".patch")