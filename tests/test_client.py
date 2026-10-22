import unittest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from gitlab_pat_manager.client import GitLabProjectTokenClient
from gitlab_pat_manager.exceptions import GitLabAPIError, TokenNotFoundError


def _mock_response(status_code=200, json_data=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = b"x" if json_data is not None else b""
    resp.json.return_value = json_data
    resp.text = text
    return resp


class GitLabProjectTokenClientTest(unittest.TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.client = GitLabProjectTokenClient(
            gitlab_url="https://gitlab.example.com",
            root_token="root-secret",
            session=self.session,
        )

    def test_root_token_set_as_header_not_logged(self):
        self.session.headers.update.assert_called_once_with({"PRIVATE-TOKEN": "root-secret"})

    def test_list_tokens(self):
        self.session.request.return_value = _mock_response(
            json_data=[
                {
                    "id": 1,
                    "name": "domino-clone-ro",
                    "scopes": ["read_repository"],
                    "access_level": 20,
                    "expires_at": "2026-01-01",
                    "active": True,
                    "revoked": False,
                    "created_at": "2025-12-01T00:00:00.000Z",
                }
            ]
        )
        tokens = self.client.list_tokens("group/repo")
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0].name, "domino-clone-ro")
        self.assertIsNone(tokens[0].token)

        args, kwargs = self.session.request.call_args
        self.assertEqual(args[0], "GET")
        self.assertIn("/projects/group%2Frepo/access_tokens", args[1])

    def test_find_active_token_by_name_skips_inactive(self):
        self.session.request.return_value = _mock_response(
            json_data=[
                {
                    "id": 1,
                    "name": "domino-clone-ro",
                    "scopes": ["read_repository"],
                    "access_level": 20,
                    "expires_at": "2026-01-01",
                    "active": False,
                    "revoked": True,
                    "created_at": None,
                },
                {
                    "id": 2,
                    "name": "domino-clone-ro",
                    "scopes": ["read_repository"],
                    "access_level": 20,
                    "expires_at": "2026-02-01",
                    "active": True,
                    "revoked": False,
                    "created_at": None,
                },
            ]
        )
        token = self.client.find_active_token_by_name("group/repo", "domino-clone-ro")
        self.assertEqual(token.id, 2)

    def test_create_token_returns_secret_once(self):
        self.session.request.return_value = _mock_response(
            json_data={
                "id": 5,
                "name": "domino-clone-ro",
                "scopes": ["read_repository"],
                "access_level": 20,
                "expires_at": "2026-01-01",
                "active": True,
                "revoked": False,
                "created_at": "2025-12-01T00:00:00.000Z",
                "token": "glpat-xyz",
            }
        )
        token = self.client.create_token(
            "group/repo", "domino-clone-ro", expires_at=date(2026, 1, 1)
        )
        self.assertEqual(token.token, "glpat-xyz")

        args, kwargs = self.session.request.call_args
        self.assertEqual(args[0], "POST")
        self.assertEqual(
            kwargs["json"],
            {
                "name": "domino-clone-ro",
                "scopes": ["read_repository"],
                "access_level": 20,
                "expires_at": "2026-01-01",
            },
        )

    def test_rotate_token(self):
        self.session.request.return_value = _mock_response(
            json_data={
                "id": 5,
                "name": "domino-clone-ro",
                "scopes": ["read_repository"],
                "access_level": 20,
                "expires_at": "2026-02-01",
                "active": True,
                "revoked": False,
                "created_at": "2025-12-01T00:00:00.000Z",
                "token": "glpat-new",
            }
        )
        token = self.client.rotate_token("group/repo", 5, expires_at=date(2026, 2, 1))
        self.assertEqual(token.token, "glpat-new")
        args, kwargs = self.session.request.call_args
        self.assertTrue(args[1].endswith("/access_tokens/5/rotate"))

    def test_revoke_token(self):
        self.session.request.return_value = _mock_response(status_code=204)
        self.client.revoke_token("group/repo", 5)
        args, kwargs = self.session.request.call_args
        self.assertEqual(args[0], "DELETE")

    def test_revoke_token_by_name_not_found_raises(self):
        self.session.request.return_value = _mock_response(json_data=[])
        with self.assertRaises(TokenNotFoundError):
            self.client.revoke_token_by_name("group/repo", "nope")

    def test_api_error_raised_on_4xx(self):
        self.session.request.return_value = _mock_response(
            status_code=404, json_data=None, text="Not Found"
        )
        with self.assertRaises(GitLabAPIError) as ctx:
            self.client.list_tokens("group/repo")
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
