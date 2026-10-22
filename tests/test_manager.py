import unittest
from datetime import date, timedelta
from unittest.mock import MagicMock

from gitlab_pat_manager.config import RepoTokenSpec
from gitlab_pat_manager.manager import ensure_repo_token
from gitlab_pat_manager.models import ProjectAccessToken


def _token(expires_in_days, token_value=None):
    return ProjectAccessToken(
        id=1,
        name="domino-clone-ro",
        scopes=["read_repository"],
        access_level=20,
        expires_at=date.today() + timedelta(days=expires_in_days),
        active=True,
        revoked=False,
        created_at=None,
        token=token_value,
    )


class EnsureRepoTokenTest(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.spec = RepoTokenSpec(
            project="group/repo",
            name="domino-clone-ro",
            expires_in_days=30,
            rotate_within_days=7,
        )

    def test_creates_when_missing(self):
        self.client.find_active_token_by_name.return_value = None
        self.client.create_token.return_value = _token(30, token_value="glpat-new")

        token, changed = ensure_repo_token(self.client, self.spec)

        self.assertTrue(changed)
        self.assertEqual(token.token, "glpat-new")
        self.client.create_token.assert_called_once()
        self.client.rotate_token.assert_not_called()

    def test_no_op_when_far_from_expiry(self):
        self.client.find_active_token_by_name.return_value = _token(20)

        token, changed = ensure_repo_token(self.client, self.spec)

        self.assertFalse(changed)
        self.assertIsNone(token.token)
        self.client.create_token.assert_not_called()
        self.client.rotate_token.assert_not_called()

    def test_rotates_when_near_expiry(self):
        self.client.find_active_token_by_name.return_value = _token(3)
        self.client.rotate_token.return_value = _token(30, token_value="glpat-rotated")

        token, changed = ensure_repo_token(self.client, self.spec)

        self.assertTrue(changed)
        self.assertEqual(token.token, "glpat-rotated")
        self.client.rotate_token.assert_called_once()
        self.client.create_token.assert_not_called()


if __name__ == "__main__":
    unittest.main()
