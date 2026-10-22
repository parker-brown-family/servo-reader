# Releasing

Releases are automated by `.github/workflows/release.yml`, triggered by a version
tag. PyPI publishing uses [Trusted Publishing][tp] (OIDC) — no API tokens.

servo-reader depends on `servo-agent>=0.3.0` from PyPI. A servo-reader release
that needs a newer servo-agent has to wait until that servo-agent is published.

## PyPI setup (in place)

PyPI trusts this repository's release workflow through a Trusted Publisher,
registered on 2026-10-21. The first upload through it, 0.4.0, created
[the project](https://pypi.org/project/servo-reader/). It trusts exactly:

- Owner `parker-brown-family`, repository `servo-reader`
- Workflow `release.yml`, environment `pypi`

Renaming the workflow file or the environment breaks publishing until the
publisher is edited to match, in the project's
[publishing settings](https://pypi.org/manage/project/servo-reader/settings/publishing/)
on PyPI.

The GitHub environment `pypi` requires approval from @parker-brown-family, and
only `v*` tags may deploy to it, so a pushed tag builds and creates the GitHub
Release at once, but publishes to PyPI only after someone approves the waiting
deployment.

## Cutting a release

1. Update the version in `pyproject.toml` and `src/servo_reader/__init__.py`.
2. Commit, then tag and push:

   ```bash
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

The workflow builds the wheel + sdist, runs `twine check`, creates a GitHub
Release with auto-generated notes and the artifacts attached, and waits for the
`pypi` deployment to be approved before publishing to PyPI.

## Local dry run

```bash
uv build
uv run --with twine twine check dist/*
```

[tp]: https://docs.pypi.org/trusted-publishers/
