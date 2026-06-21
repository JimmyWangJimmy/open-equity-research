from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from open_equity_research.cli import main


class CLITests(unittest.TestCase):
    def test_init_writes_config(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "oer.toml"
            result = main(["init", "--output", str(output)])
            self.assertEqual(result, 0)
            self.assertTrue(output.exists())
            self.assertIn("sec_user_agent", output.read_text())


if __name__ == "__main__":
    unittest.main()
