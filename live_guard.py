"""Live-credential guard for test runs (pace-core#31).

Incident 2026-09-14: a test ran a CRM backfill with --execute and a stray .env
next to it; 251 live rows were written. Tests must never run where live
credentials are reachable. check() is pure: env dict + root path in, problems out.
Only variable NAMES and file paths are ever reported, never values.
"""
import fnmatch
import os
import re

ENV_PREFIXES = (
    "ZOHO_", "CRM_", "CAMPAIGNS_", "DESK_", "JIRA_", "ATLASSIAN_", "PODIO_",
    "GOOGLE_", "GCP_", "DRIVE_", "DESTINY_", "QUALTRICS_", "ANTHROPIC_",
    "OPENAI_", "CLOUDFLARE_", "CF_API", "MONGO", "SLACK_",
)
ENV_SUFFIXES = ("_TOKEN", "_SECRET", "_REFRESH_TOKEN", "_API_KEY", "_PASSWORD", "_CLIENT_SECRET")
ENV_EXEMPT_PREFIXES = ("GITHUB_", "ACTIONS_", "RUNNER_", "CLAUDE_CODE_")  # Claude Code harness vars, not service creds
ENV_EXEMPT_NAMES = ("GH_TOKEN", "GITHUB_TOKEN")

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__"}
ENV_TEMPLATE_SUFFIXES = (".example", ".sample", ".template")
FILE_PATTERNS = ("*token*.json", "token_cache*", "*.token", "credentials*.json",
                 "service_account*.json", "client_secret*.json")
# Fake fixtures committed under tests/ may be allowlisted here by repo-relative path.
ALLOWLIST = frozenset()


def bad_env_names(env):
    out = []
    for name, value in env.items():
        u = name.upper()
        if not value:
            continue
        if u in ENV_EXEMPT_NAMES or u.startswith(ENV_EXEMPT_PREFIXES):
            continue
        if u.startswith(ENV_PREFIXES) or u.endswith(ENV_SUFFIXES):
            out.append(name)
    return sorted(out)


def _is_cred_file(fname):
    low = fname.lower()
    if low == ".env" or (low.startswith(".env.") and not low.endswith(ENV_TEMPLATE_SUFFIXES)):
        return True
    return any(fnmatch.fnmatch(low, p) for p in FILE_PATTERNS)


def bad_files(root, allowlist=ALLOWLIST):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        keep = []
        for d in dirnames:
            if d in SKIP_DIRS:
                continue
            if d == ".playwright_profile":
                out.append(os.path.relpath(os.path.join(dirpath, d), root) + "/")
                continue
            keep.append(d)
        dirnames[:] = keep
        for f in filenames:
            rel = os.path.relpath(os.path.join(dirpath, f), root)
            if rel in allowlist:
                continue
            if _is_cred_file(f):
                out.append(rel)
    return sorted(out)


def check(env, root, allowlist=ALLOWLIST):
    return bad_env_names(env) + bad_files(root, allowlist)


def refusal_message(problems):
    return ("Refusing to run tests: live credentials present (%s). "
            "Run tests in a clean git worktree." % ", ".join(problems))


def enforce(env, root):
    """pytest: call from a root conftest. Returns the problems list (empty = ok)."""
    return check(env, root)
