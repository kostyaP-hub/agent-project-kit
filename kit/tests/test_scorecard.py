"""Legacy coverage plus fleet scorecard probes against real temporary git repos."""
import os
import shutil
import subprocess
import importlib.util
from pathlib import Path
from lib.config import load_config
from lib.lint import scorecard_row, render_scorecard, read_vault_entity, UNIVERSAL_RULES
from lib.archmap import write_map
from lib.scorecard import build_scorecard, scorecard_row as fleet_scorecard_row
import lib.scorecard as fleet_scorecard

HERE = os.path.dirname(__file__)
FIX = os.path.join(HERE, "fixtures", "sample_app")
SRC = os.path.join(os.path.dirname(HERE), "rules")


def _full_repo(tmp_path):
    d = tmp_path / "repo"
    shutil.copytree(FIX, d)
    (d / "AGENTS.md").write_text('---\nproject: "x"\n---\n@./rules/git.md\n')
    (d / "GEMINI.md").write_text("@AGENTS.md\n")
    (d / "rules").mkdir()
    for fn in UNIVERSAL_RULES:
        shutil.copy(os.path.join(SRC, fn), d / "rules" / fn)
    write_map(str(d))                    # produces ARCHITECTURE.md + hookup
    return d


def test_scorecard_all_but_vault(tmp_path):
    d = _full_repo(tmp_path)
    row = scorecard_row(str(d))
    assert row["agents"] and row["rules"] and row["gemini"] and row["legibility"]
    assert not row["vault"]              # no vault_entity yet


def test_vault_bridge_recognized(tmp_path):
    d = _full_repo(tmp_path)
    a = d / "AGENTS.md"
    a.write_text(a.read_text().replace('project: "x"', 'project: "x"\nvault_entity: example-cut'))
    assert read_vault_entity(str(d)) == "example-cut"
    assert scorecard_row(str(d))["vault"]


def test_render_scorecard_markdown(tmp_path):
    d = _full_repo(tmp_path)
    md = render_scorecard([str(d)])
    assert "| repo |" in md and "legibility" in md
    assert "✓" in md


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, text=True, capture_output=True)


def _init_repo(path):
    path.mkdir()
    _git(path, "init")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")
    (path / "AGENTS.md").write_text("rules\n")
    (path / "tracked.txt").write_text("one\n")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "initial")
    return path


def _ctx_lint_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "ctx-lint.py"
    spec = importlib.util.spec_from_file_location("ctx_lint_scorecard_test", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fleet_dedupes_worktree_and_reports_dirty_ahead(tmp_path):
    main = _init_repo(tmp_path / "main")
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, text=True, capture_output=True)
    _git(main, "remote", "add", "origin", str(remote))
    _git(main, "push", "-u", "origin", "HEAD")
    _git(main, "worktree", "add", "-b", "linked", "../linked")
    (main / "tracked.txt").write_text("dirty\n")
    (main / "ahead.txt").write_text("ahead\n")
    _git(main, "add", "ahead.txt")
    _git(main, "commit", "-m", "ahead")
    rows = build_scorecard([str(main), str(tmp_path / "linked")], owned=[])
    assert len(rows) == 1 and rows[0]["worktrees"] == 1
    assert rows[0]["dirty"] == 1 and rows[0]["ahead"] == 1


def test_claude_state_kind_and_vault(tmp_path, monkeypatch):
    knowledge = tmp_path / "knowledge"
    card = knowledge / "wiki" / "projects" / "demo.md"
    card.parent.mkdir(parents=True)
    card.write_text("---\nstatus: maintained\n---\n")
    repo = _init_repo(tmp_path / "repo")
    _git(repo, "remote", "add", "origin", "git@github.com:acme/demo.git")
    (repo / "AGENTS.md").write_text("see wiki/projects/demo.md\n")
    (repo / "CLAUDE.md").write_text("@./AGENTS.md\n")
    valid = (Path(__file__).resolve().parents[1] / "examples" / "project.state.recipe-calculator.yaml").read_text()
    (repo / "project.state.yaml").write_text(valid)
    row = fleet_scorecard_row(str(repo), ["acme"], knowledge_root=str(knowledge), knowledge_entity_glob="wiki/projects/*.md")
    assert row["kind"] == "owned" and row["entity"] == "demo" and row["vault_status"] == "maintained"
    assert row["claude"] == "wrapper" and row["project_state"] == "✓"
    (repo / "CLAUDE.md").write_text("# detailed instructions\n")
    (repo / "project.state.yaml").write_text("bad: state\n")
    row = fleet_scorecard_row(str(repo), ["acme"], knowledge_root=str(knowledge), knowledge_entity_glob="wiki/projects/*.md")
    assert row["claude"] == "full" and row["project_state"] == "invalid"
    (repo / "project.state.yaml").unlink()
    assert fleet_scorecard_row(str(repo), ["acme"], knowledge_root=str(knowledge), knowledge_entity_glob="wiki/projects/*.md")["project_state"] == "✗"


def test_scorecard_without_knowledge_root_has_no_entity_data(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path / "repo")
    (repo / "AGENTS.md").write_text("see wiki/projects/demo.md\n")
    monkeypatch.setattr(fleet_scorecard, "load_config", lambda: {
        "knowledge_root": None, "knowledge_entity_glob": "wiki/projects/*.md"})
    row = fleet_scorecard_row(str(repo), [])
    assert row["entity"] == row["vault_status"] == "—"


def test_discovery_includes_git_repo_without_instructions(tmp_path, monkeypatch):
    scan_root = tmp_path / "scan"
    scan_root.mkdir()
    repo = _init_repo(scan_root / "plain-git")
    (repo / "AGENTS.md").unlink()
    _git(repo, "add", "-u")
    _git(repo, "commit", "-m", "remove instructions")
    ctx_lint = _ctx_lint_module()
    monkeypatch.setattr(ctx_lint, "SCAN_ROOTS", [str(scan_root)])
    monkeypatch.setattr(ctx_lint, "EXTRA_ROOTS", [])
    discovered = ctx_lint.discover()
    rows = build_scorecard(discovered, owned=[])
    assert discovered == [str(repo)]
    assert rows[0]["agents"] == "✗"


def test_agents_symlink_is_thin_wrapper_for_claude_and_gemini(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    (repo / "CLAUDE.md").symlink_to("AGENTS.md")
    (repo / "GEMINI.md").symlink_to("AGENTS.md")
    assert fleet_scorecard_row(str(repo), [])["claude"] == "wrapper"
    report = _ctx_lint_module().check(str(repo))
    messages = [message for _, message in report["issues"]]
    assert not any(message.startswith("CLAUDE.md не") for message in messages)
    assert not any(message.startswith("GEMINI.md не") for message in messages)


def test_extra_roots_are_loaded_and_nested_parent_does_not_recurse(tmp_path, monkeypatch):
    config = tmp_path / "config.json"
    config.write_text('{"scan_roots": [], "extra_roots": ["~/one", "~/two"]}')
    assert load_config(str(config))["scan_roots"][-2:] == [os.path.expanduser("~/one"), os.path.expanduser("~/two")]

    claude = _init_repo(tmp_path / "claude")
    skills = claude / "skills"
    skills.mkdir()
    skill_repo = _init_repo(skills / "skill-repo")
    ignored = _init_repo(claude / "unrelated")
    ctx_lint = _ctx_lint_module()
    monkeypatch.setattr(ctx_lint, "SCAN_ROOTS", [str(skills), str(claude)])
    monkeypatch.setattr(ctx_lint, "EXTRA_ROOTS", [str(skills), str(claude)])
    assert ctx_lint.discover() == sorted([str(claude), str(skill_repo)])
    assert str(ignored) not in ctx_lint.discover()
