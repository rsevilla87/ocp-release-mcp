import base64
import html
import os
import re
import logging
from urllib.parse import urlparse, parse_qs, unquote

import httpx, asyncio
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field
from typing import List
load_dotenv()

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "openshift-release",
    host=os.getenv("HOST", "0.0.0.0"),
    port=int(os.getenv("PORT", 8000)),
)

BASE_URL = os.getenv("BASE_URL", "https://amd64.ocp.releases.ci.openshift.org/api/v1")

class RPMInfo(BaseModel):
    """An RPM package in an RHCOS build."""
    name: str
    epoch: str
    version: str
    release: str
    architecture: str

class RPMDiff(BaseModel):
    """RPM differences between two RHCOS builds."""
    added: List[RPMInfo] = Field(default_factory=list)
    removed: List[RPMInfo] = Field(default_factory=list)
    updated: List[dict] = Field(default_factory=list, description="List of dicts with 'name', 'old' and 'new' RPMInfo")

class ComponentInfo(BaseModel):
    """A component info in a release payload."""
    name: str
    version: str
    from_version: str

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
    components: List[ComponentInfo] = Field(default_factory=list)

async def _get_json(url: str, ctx: Context) -> dict:
    await ctx.info(f"GET {url}")
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

def _get_release_info(payload: dict, release_info: ReleaseInfo) -> ReleaseInfo: 
    if "changeLogJson" in payload and "updatedImages" in payload["changeLogJson"]:
        for image in payload["changeLogJson"]["updatedImages"]:
            updated_image = UpdatedImage(name=image["name"])
            if "commits" in image:
                updated_image.commits = [CommitInfo(subject=commit["subject"], pull_request_url=commit["pullURL"]) for commit in image["commits"]]
            release_info.updated_images.append(updated_image)
    if "changeLogJson" in payload and "components" in payload["changeLogJson"]:
        for component in payload["changeLogJson"]["components"]:
            release_info.components.append(ComponentInfo(name=component["name"], version=component["version"], from_version=component.get("from", "")))
    return release_info

@mcp.tool()
async def get_release(stream: str, version: str,  ctx: Context) -> dict:
    """Fetch detailed information about a specific OpenShift release version.

    Args:
        stream: The release stream, e.g. '4.22.0-0.nightly', '4-stable', '4-dev-preview', '4.18.0-0.ci'
        version: The full release version tag, e.g. '4.22.0-0.nightly-2026-03-23-022245'
    """
    payload = await _get_json(f"{BASE_URL}/releasestream/{stream}/release/{version}", ctx)
    release_info = _get_release_info(payload, ReleaseInfo(version=payload["name"], phase=payload["phase"]))
    return release_info


@mcp.tool()
async def list_tags(stream: str, phase: str, ctx: Context) -> dict:
    """List the latest release tags for a given release stream.

    Args:
        stream: The release stream, e.g. '4.22.0-0.nightly', '4-stable', '4-dev-preview', '4.18.0-0.ci'
        phase: The release phase, e.g. 'Accepted, Accepted, Ready'
    """
    if phase:
        return await _get_json(f"{BASE_URL}/releasestream/{stream}/tags?phase={phase}", ctx)
    return await _get_json(f"{BASE_URL}/releasestream/{stream}/tags", ctx)


@mcp.tool()
async def compare_releases(stream: str, payload1: str, payload2: str, ctx: Context) -> dict:
    """Compare two payload versions within a release stream, showing differences between them.

    Args:
        stream: The release stream, e.g. '4.22.0-0.nightly'
        payload1: The target release version to compare
        payload2: The base release version to compare from
    """
    payload = await _get_json(f"{BASE_URL}/releasestream/{stream}/release/{payload1}?from={payload2}", ctx)
    release_info = _get_release_info(payload, ReleaseInfo(version=payload["name"], phase=payload["phase"]))
    return release_info

async def _fetch_rhcos_rpms(stream: str, version: str) -> List[RPMInfo]:
    """Fetch the RHCOS RPM list for a given release payload."""
    payload = await _get_json(f"{BASE_URL}/releasestream/{stream}/release/{version}")
    # Try to get versionUrl from structured changeLogJson components
    version_url = None
    if "changeLogJson" in payload and "components" in payload["changeLogJson"]:
        for component in payload["changeLogJson"]["components"]:
            if "Red Hat Enterprise Linux CoreOS" in component.get("name", ""):
                version_url = component.get("versionUrl")
                break
    # Fall back to parsing the HTML changelog for the RHCOS release browser URL
    if not version_url and "changeLog" in payload:
        changelog_html = base64.b64decode(payload["changeLog"]).decode("utf-8")
        urls = re.findall(r'https://releases-rhcos[^"\'<>\s]+', changelog_html)
        if urls:
            version_url = html.unescape(urls[-1])
    if not version_url:
        raise ValueError(f"RHCOS version URL not found in release {version}")
    parsed = urlparse(version_url)
    params = parse_qs(parsed.query)
    rhcos_stream = unquote(params["stream"][0])
    rhcos_release = params["release"][0]
    rhcos_arch = params.get("arch", ["x86_64"])[0]
    rhcos_base_url = f"{parsed.scheme}://{parsed.netloc}"
    commitmeta_url = f"{rhcos_base_url}/storage/{rhcos_stream}/builds/{rhcos_release}/{rhcos_arch}/commitmeta.json"
    commitmeta = await _get_json(commitmeta_url)
    pkglist = commitmeta.get("rpmostree.rpmdb.pkglist", [])
    return [
        RPMInfo(name=pkg[0], epoch=pkg[1], version=pkg[2], release=pkg[3], architecture=pkg[4])
        for pkg in pkglist
    ]

@mcp.tool()
async def get_rhcos_rpms(stream: str, version: str) -> List[RPMInfo]:
    """Get the list of RPMs included in the RHCOS build of a given OpenShift release payload.

    Args:
        stream: The release stream, e.g. '4.22.0-0.nightly', '4-stable', '4-dev-preview', '4.18.0-0.ci'
        version: The full release version tag, e.g. '4.22.0-0.nightly-2026-03-23-022245'
    """
    logger.info("get_rhcos_rpms called: stream=%s, version=%s", stream, version)
    return await _fetch_rhcos_rpms(stream, version)

@mcp.tool()
async def compare_rhcos_rpms(stream: str, version1: str, version2: str) -> RPMDiff:
    """Compare the RHCOS RPM lists between two OpenShift release payloads, showing added, removed, and updated packages.

    Args:
        stream: The release stream, e.g. '4.22.0-0.nightly', '4-stable', '4-dev-preview', '4.18.0-0.ci'
        version1: The newer release version tag
        version2: The older release version tag to compare against
    """
    logger.info("compare_rhcos_rpms called: stream=%s, version1=%s, version2=%s", stream, version1, version2)
    rpms_new = await _fetch_rhcos_rpms(stream, version1)
    rpms_old = await _fetch_rhcos_rpms(stream, version2)
    old_by_name = {rpm.name: rpm for rpm in rpms_old}
    new_by_name = {rpm.name: rpm for rpm in rpms_new}
    diff = RPMDiff()
    for name, rpm in new_by_name.items():
        if name not in old_by_name:
            diff.added.append(rpm)
        elif rpm.version != old_by_name[name].version or rpm.release != old_by_name[name].release or rpm.epoch != old_by_name[name].epoch:
            diff.updated.append({"name": name, "old": old_by_name[name], "new": rpm})
    for name, rpm in old_by_name.items():
        if name not in new_by_name:
            diff.removed.append(rpm)
    return diff

@mcp.tool()
async def get_pull_request_info(url: str) -> dict:
    """Get the details of a pull request from a pull request URL.

    Args:
        pull_request_url: The URL of the pull request
    """
    return await _get_text(url + ".patch")

@mcp.tool()
async def get_component_rpms(payload: str, component: str) -> List[RPMInfo]:
    """Get the list of RPMs included in a component of a release payload.

    Args:
        payload: The release version, e.g. '4.22.0-ec.4', '4.22.0-0.nightly-2026-03-23-022245'
        component: The component name, e.g. 'ovn-kubernetes', 'etcd'
    """
    if "nightly" in payload or ".ci-" in payload:
        registry = f"registry.ci.openshift.org/ocp/release"
        payload = f"{registry}:{payload}"
    elif "-ec." in payload:
        registry = f"quay.io/openshift-release-dev/ocp-release"
        payload = f"{registry}:{payload}-x86_64"
    else:
        registry = "quay.io/openshift-release-dev/ocp-release"
        payload = f"{registry}:{payload}-x86_64"
    cmd = f"oc adm release info {payload} --image-for={component}"
    component_image = await _run_shell(cmd)
    cmd = f"podman run --rm --entrypoint rpm {component_image} -qa --queryformat '%{{NAME}} %{{EPOCH}} %{{VERSION}} %{{RELEASE}} %{{ARCH}}\\n'"
    output = await _run_shell(cmd)
    rpm_list = []
    for line in output.splitlines():
        parts = line.split(None, 4)
        if len(parts) == 5:
            rpm_list.append(RPMInfo(name=parts[0], epoch=parts[1], version=parts[2], release=parts[3], architecture=parts[4]))
    return rpm_list

async def _run_shell(cmd: str) -> str:
    process = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    logger.info(f"Command: {cmd}")
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise Exception(f"Failed to run shell command: {stderr.decode()}")
    output = stdout.decode().strip()
    logger.info(f"Command output: {output}")
    return output