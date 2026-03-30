# openshift-release-mcp

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that exposes tools for querying the OpenShift release API. It is built with [FastMCP](https://github.com/jlowin/fastmcp) and [httpx](https://www.python-httpx.org/), and speaks **streamable HTTP** so clients can connect to a URL (for example from Cursor).

The default API base is `https://amd64.ocp.releases.ci.openshift.org/api/v1`.

## Requirements

- Python **3.13+**

## Install (uv)

```bash
git clone https://github.com/openshift/ocp-release-mcp.git
cd ocp-release-mcp
uv venv
source .venv/bin/activate
uv pip install .
```

## Configuration

Optional environment variables (or a `.env` file in the working directory):

| Variable    | Default | Purpose |
|------------|---------|---------|
| `BASE_URL` | `https://amd64.ocp.releases.ci.openshift.org/api/v1` | OpenShift release API root |
| `HOST`     | `0.0.0.0` | Bind address for the HTTP server |
| `PORT`     | `8000`    | Listen port |
| `LOG_LEVEL`| `INFO`    | Logging level |

## Run

```bash
openshift-release-mcp
```

The server starts with **streamable HTTP** transport. By default it listens on `http://0.0.0.0:8000`; the MCP endpoint path is `/mcp` (for example `http://localhost:8000/mcp`).

## Use with Cursor

Example `.mcp.json` in your project:

```json
{
  "mcpServers": {
    "openshift-release": {
      "type": "http",
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

Start `openshift-release-mcp` before connecting from the IDE.

## MCP tools

| Tool | Description |
|------|-------------|
| `get_release` | Fetches a release by **stream** and **version** tag. Returns structured data: version, phase, and updated images with commit subjects and PR URLs when the payload includes `changeLogJson`. |
| `list_tags` | Lists tags for a **stream**, optionally filtered by **phase** (passed as a query parameter to the API). |
| `compare_releases` | Compares two releases in the same **stream**: **payload1** vs **payload2** (base), using the API’s `from=` comparison. |
| `get_rhcos_rpms` | Lists all RPMs in the RHCOS build of a release payload. |
| `compare_rhcos_rpms` | Compares RHCOS RPM lists between two release payloads, showing added, removed, and updated packages. |
| `get_component_rpms` | Lists all RPMs installed in a specific component image of a release payload. Requires `oc` and `podman` on the server. |
| `get_pull_request_info` | Fetches the raw **`.patch`** text for a given pull request URL (appends `.patch` to the URL). |

### Concepts

- **Release stream**: A channel such as `4.22.0-0.nightly`, `4-stable`, `4-dev-preview`, or `4.18.0-0.ci`.
- **Version / tag**: A specific build identifier, for example `4.22.0-0.nightly-2026-03-23-022245`.
- **Component**: A container image within a release payload, for example `ovn-kubernetes`, `etcd`, or `kube-apiserver`.

### Stream naming conventions

| Stream type | Example |
|-------------|---------|
| Nightly | `4.22.0-0.nightly` |
| CI | `4.18.0-0.ci` |
| Dev Preview | `4-dev-preview` |
| Stable | `4-stable` |

EC (engineering candidate) releases such as `4.22.0-ec.4` use the `4-dev-preview` stream.

## Examples

Below are examples of questions you can ask an LLM connected to this MCP server:

- **"What is the OVN version in the ovn-kubernetes component in 4.22.0-ec.4?"**
  Uses `get_component_rpms` to inspect the `ovn-kubernetes` image and filter for `ovn` RPMs.

- **"What is the OVS version in the ovn-kubernetes component in 4.22.0-ec.4?"**
  Uses `get_component_rpms` to inspect the `ovn-kubernetes` image and filter for `openvswitch` RPMs.

- **"What is the etcd version in 4.22.0-ec.4?"**
  Uses `get_component_rpms` to inspect the `etcd` image. Since etcd is a Go binary (not an RPM), the LLM can also run the `etcd --version` entrypoint on the image directly.

- **"List the latest accepted nightly releases for 4.22"**
  Uses `list_tags` with `stream=4.22.0-0.nightly` and `phase=Accepted`.

- **"What changed between two nightly releases?"**
  Uses `compare_releases` with the stream and two version tags to show updated images, commits, and component changes.

- **"What RHCOS RPMs changed between two releases?"**
  Uses `compare_rhcos_rpms` to diff the full RPM lists between two payloads, showing added, removed, and updated packages.

- **"What RPMs are included in the RHCOS build for 4.22.0-0.nightly-2026-03-23-022245?"**
  Uses `get_rhcos_rpms` with the stream and version tag.

## License

See [LICENSE](LICENSE) in this repository.
