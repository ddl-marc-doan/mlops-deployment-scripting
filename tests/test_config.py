import tempfile
import unittest
from pathlib import Path

from gitlab_pat_manager.config import load_repo_specs


class LoadRepoSpecsTest(unittest.TestCase):
    def test_loads_yaml(self):
        content = """
repos:
  - project: group/repo-a
    name: domino-clone-ro
    expires_in_days: 45
  - project: 123
"""
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write(content)
            path = f.name

        specs = load_repo_specs(path)
        Path(path).unlink()

        self.assertEqual(len(specs), 2)
        self.assertEqual(specs[0].project, "group/repo-a")
        self.assertEqual(specs[0].expires_in_days, 45)
        self.assertEqual(specs[1].project, "123")
        self.assertEqual(specs[1].name, "domino-clone-ro")  # default

    def test_loads_json(self):
        content = '{"repos": [{"project": "group/repo-a"}]}'
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write(content)
            path = f.name

        specs = load_repo_specs(path)
        Path(path).unlink()

        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0].project, "group/repo-a")

    def test_empty_repos_list(self):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write("repos: []\n")
            path = f.name

        specs = load_repo_specs(path)
        Path(path).unlink()

        self.assertEqual(specs, [])


if __name__ == "__main__":
    unittest.main()
