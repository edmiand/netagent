import asyncio
import functools
import os
import re

from langchain_core.tools import tool

_INCLUDE_DOMAINS = ["github.com/open5gs/open5gs"]

# Open5GS daemons report `git describe --abbrev=7 --dirty=+` output, e.g.
# "Open5GS v2.8.0-68-gb811f1d" (68 commits past the v2.8.0 tag, at b811f1d).
# GitHub only has release notes/advisories for the tag itself, so searching
# on the full describe string returns nothing — pull out the base tag.
_VERSION_RE = re.compile(r"v?(\d+\.\d+\.\d+)(?:-(\d+)-g([0-9a-f]+))?")


@functools.lru_cache(maxsize=1)
def _get_client():
    from tavily import TavilyClient

    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return None
    return TavilyClient(api_key=api_key)


@tool
async def check_open5gs_release_info(version: str) -> str:
    """Check what has changed upstream in Open5GS since a given version —
    fixes, releases, and security advisories landed after it.

    Pass the exact version string as reported by the running network (e.g.
    from a config file, an NF's log startup banner, or a version-query tool),
    and nothing else. This includes raw `git describe` build strings like
    "v2.8.0-68-gb811f1d" — this tool normalizes those itself. Do not use
    this for general questions the knowledge base can already answer — it
    is only for "what's new since version X" lookups.
    """
    client = _get_client()
    if client is None:
        return (
            "The release-check tool is not configured — TAVILY_API_KEY is "
            "missing from .env. Add a Tavily API key to enable this tool."
        )

    match = _VERSION_RE.search(version)
    if not match:
        return (
            f"Could not parse an Open5GS version out of {version!r} — "
            "expected something like '2.8.0' or 'v2.8.0-68-gb811f1d'."
        )
    tag, commits_ahead, commit = match.groups()
    base_version = f"v{tag}"

    query = f"Open5GS {base_version} release notes OR fixes OR security advisory"
    try:
        response = await asyncio.to_thread(
            client.search,
            query,
            include_domains=_INCLUDE_DOMAINS,
            max_results=5,
        )
    except Exception as exc:
        return f"Release check failed: {exc}"

    results = response.get("results", [])
    if not results:
        return f"No release or advisory information found for Open5GS {base_version}."

    sections = [
        f"[{r.get('title', 'untitled')}]({r.get('url', '')})\n{r.get('content', '').strip()}"
        for r in results
    ]
    body = "\n\n---\n\n".join(sections)

    if commits_ahead:
        body = (
            f"Note: the running build ({version}) is {commits_ahead} commits "
            f"past the {base_version} tag (at {commit}) — results below are "
            f"relative to the last tagged release, not that exact commit.\n\n"
            + body
        )
    return body
