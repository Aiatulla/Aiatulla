import pytest

from app.cloner import CloneError, directory_size_bytes, validate_repo_url


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("file:///etc/passwd", "scheme"),
        ("http://github.com/a/b", "scheme"),
        ("git://github.com/a/b", "scheme"),
        ("ssh://git@github.com/a/b", "scheme"),
        ("https://user:token@github.com/a/b", "credentials"),
        ("https://internal.corp.example.com/a/b", "not allowed"),
        ("https://169.254.169.254/latest/meta-data", "not allowed"),
    ],
    ids=[
        "local_file_read",
        "plain_http",
        "git_protocol",
        "ssh_uses_server_keys",
        "embedded_credentials",
        "arbitrary_internal_host",
        "cloud_metadata_endpoint",
    ],
)
def test_dangerous_urls_are_rejected(url, reason):
    """A repository URL is untrusted input. Each of these reaches somewhere it should not."""
    with pytest.raises(CloneError, match=reason):
        validate_repo_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/psf/requests",
        "https://gitlab.com/group/project",
        "https://bitbucket.org/team/repo",
    ],
)
def test_allowed_hosts_pass(url):
    assert validate_repo_url(url) == url


def test_directory_size_counts_nested_files(tmp_path):
    (tmp_path / "a.txt").write_text("x" * 10)
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "b.txt").write_text("y" * 15)

    assert directory_size_bytes(tmp_path) == 25


def test_directory_size_skips_symlinks(tmp_path):
    """Following a symlink would both mis-count the size and read a file outside
    the workspace, so they are skipped rather than measured."""
    real = tmp_path / "real.txt"
    real.write_text("z" * 100)
    link_dir = tmp_path / "repo"
    link_dir.mkdir()
    (link_dir / "link.txt").symlink_to(real)

    assert directory_size_bytes(link_dir) == 0
