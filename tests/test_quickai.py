from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from quickai import query
from quickai.indexer import IndexOptions, index_codex_logs
from quickai.mcp import handle_message
from quickai.report import write_html_report


ROOT = Path(__file__).parent / "fixtures" / "codex"


class QuickAITest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = Path(self.tmp.name) / "quickai.db"

    def index_fixture(self):
        return index_codex_logs(IndexOptions(db_path=self.db_path, roots=[ROOT]))

    def test_indexer_deltas_and_incremental_skip(self) -> None:
        result = self.index_fixture()
        self.assertEqual(result.indexed, 1)
        self.assertEqual(result.failed, 0)

        with sqlite3.connect(self.db_path) as con:
            session = con.execute(
                """
                SELECT session_id, project, turn_count, input_tokens, cached_input_tokens,
                       output_tokens, reasoning_output_tokens, total_tokens, tool_call_count
                FROM sessions
                """
            ).fetchone()
            turns = con.execute("SELECT input_tokens, total_tokens FROM turns ORDER BY id").fetchall()

        self.assertEqual(session, ("fixture-session", "demo", 2, 150, 25, 15, 5, 165, 1))
        self.assertEqual(turns, [(100, 110), (50, 55)])

        second = self.index_fixture()
        self.assertEqual(second.indexed, 0)
        self.assertEqual(second.skipped, 1)

    def test_query_and_report(self) -> None:
        self.index_fixture()

        stats = query.stats(self.db_path)
        self.assertEqual(stats["sessions"], 1)
        self.assertEqual(stats["total_tokens"], 165)

        sessions = query.list_sessions(self.db_path)
        self.assertEqual(sessions[0]["title"], "Build a fixture demo")

        tools = query.tools(self.db_path)
        self.assertEqual(tools[0]["name"], "exec_command")

        report = write_html_report(self.db_path, output=Path(self.tmp.name) / "report.html")
        self.assertIn("quickai Codex report", report.read_text(encoding="utf-8"))

    def test_mcp_tools(self) -> None:
        self.index_fixture()

        listed = handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, self.db_path)
        self.assertEqual(listed["result"]["tools"][0]["name"], "quickai_stats")

        called = handle_message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "quickai_stats", "arguments": {}},
            },
            self.db_path,
        )
        text = called["result"]["content"][0]["text"]
        self.assertEqual(json.loads(text)["total_tokens"], 165)

        missing = handle_message({"jsonrpc": "2.0", "id": 3, "method": "missing"}, self.db_path)
        self.assertEqual(missing["error"]["code"], -32601)


if __name__ == "__main__":
    unittest.main()
