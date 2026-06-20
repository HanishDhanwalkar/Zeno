from zeno_agent_core.tools import ToolExecutor


def test_write_then_read(tmp_path):
    ex = ToolExecutor(root=tmp_path)
    w = ex.execute("write", {"path": "a.txt", "content": "line1\nline2\nline3"})
    assert "error" not in w
    r = ex.execute("read", {"path": "a.txt"})
    assert "error" not in r
    assert "1|line1" in r["output"]
    assert "3|line3" in r["output"]


def test_read_missing_file(tmp_path):
    ex = ToolExecutor(root=tmp_path)
    r = ex.execute("read", {"path": "nope.txt"})
    assert "not found" in r["error"]


def test_read_limit_truncates(tmp_path):
    ex = ToolExecutor(root=tmp_path)
    content = "\n".join(str(i) for i in range(500))
    ex.execute("write", {"path": "big.txt", "content": content})
    r = ex.execute("read", {"path": "big.txt", "limit": 10})
    assert r["truncated"] is True
    assert len(r["output"].splitlines()) == 10


def test_edit_unique_match(tmp_path):
    ex = ToolExecutor(root=tmp_path)
    ex.execute("write", {"path": "b.txt", "content": "hello world"})
    e = ex.execute("edit", {"path": "b.txt", "old_string": "world", "new_string": "zeno"})
    assert "error" not in e
    r = ex.execute("read", {"path": "b.txt"})
    assert "hello zeno" in r["output"]


def test_edit_non_unique_match_fails(tmp_path):
    ex = ToolExecutor(root=tmp_path)
    ex.execute("write", {"path": "c.txt", "content": "x x x"})
    e = ex.execute("edit", {"path": "c.txt", "old_string": "x", "new_string": "y"})
    assert "not unique" in e["error"]


def test_edit_missing_match_fails(tmp_path):
    ex = ToolExecutor(root=tmp_path)
    ex.execute("write", {"path": "d.txt", "content": "abc"})
    e = ex.execute("edit", {"path": "d.txt", "old_string": "zzz", "new_string": "y"})
    assert "not found" in e["error"]


def test_bash_runs_and_captures_exit_code(tmp_path):
    ex = ToolExecutor(root=tmp_path)
    r = ex.execute("bash", {"command": "echo hello"})
    assert r["exitCode"] == 0
    assert "hello" in r["output"]


def test_unknown_tool(tmp_path):
    ex = ToolExecutor(root=tmp_path)
    r = ex.execute("frobnicate", {})
    assert "unknown tool" in r["error"]


def test_bad_arguments(tmp_path):
    ex = ToolExecutor(root=tmp_path)
    r = ex.execute("read", {"wrong": "arg"})
    assert "bad arguments" in r["error"]
