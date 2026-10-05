import pytest

import live_guard


def test_clean_env_and_tree(tmp_path):
    assert live_guard.check({"PATH": "/bin", "HOME": "/h"}, str(tmp_path)) == []


@pytest.mark.parametrize("name", [
    "ZOHO_CLIENT_ID", "crm_x", "ANTHROPIC_API_KEY", "MONGODB_URI", "FOO_TOKEN",
    "X_SECRET", "SLACK_WEBHOOK", "CF_API_X", "DB_PASSWORD", "GOOGLE_APPLICATION_CREDENTIALS",
])
def test_credential_env_names_refused(name, tmp_path):
    assert live_guard.check({name: "x"}, str(tmp_path)) == [name]


def test_empty_value_and_github_exempt(tmp_path):
    env = {"ZOHO_X": "", "GITHUB_TOKEN": "t", "GH_TOKEN": "t", "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "t",
           "RUNNER_TOKEN": "t", "GITHUB_API_KEY": "t"}
    assert live_guard.check(env, str(tmp_path)) == []


def test_values_never_reported(tmp_path):
    msg = live_guard.refusal_message(live_guard.check({"ZOHO_A": "supersecret"}, str(tmp_path)))
    assert "supersecret" not in msg and "ZOHO_A" in msg and "clean git worktree" in msg


@pytest.mark.parametrize("rel", [
    ".env", ".env.local", "sub/token.json", "a/b/google_token.json", "token_cache.pkl", "x.token",
    "credentials.json", "service_account_key.json", "client_secret_123.json",
    ".playwright_profile/Default/x",
])
def test_credential_files_refused(rel, tmp_path):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x")
    assert live_guard.check({}, str(tmp_path))


@pytest.mark.parametrize("rel", [".env.example", ".env.sample", ".env.template", "node_modules/a/.env",
                                 ".git/x/token.json", ".venv/y/credentials.json", "readme.md"])
def test_templates_and_skipped_dirs_ok(rel, tmp_path):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x")
    assert live_guard.check({}, str(tmp_path)) == []


def test_allowlist(tmp_path):
    p = tmp_path / "tests" / "fake_token.json"
    p.parent.mkdir()
    p.write_text("{}")
    assert live_guard.check({}, str(tmp_path), allowlist={"tests/fake_token.json"}) == []
