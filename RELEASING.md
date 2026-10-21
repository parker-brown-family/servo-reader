# Releasing

Releases are automated by `.github/workflows/release.yml`, triggered by a version
tag. PyPI publishing uses [Trusted Publishing][tp] (OIDC) — no API tokens.

servo-reader depends on `servo-agent>=0.2.0`, so `servo-agent` has to be on PyPI
before a servo-reader release can be installed from there.

## One-time setup (PyPI)

1. On PyPI, add a **Trusted Publisher** for this repository. Before the project
   exists this is a *pending* publisher (Account → Publishing), and the first
   upload through it creates the project:
   - PyPI project name: `servo-reader`
   - Owner: `parker-brown-family`, Repository: `servo-reader`
   - Workflow: `release.yml`, Environment: `pypi`
2. The GitHub environment `pypi` already exists. It requires approval from
   @parker-brown-family, and only `v*` tags may deploy to it, so a pushed tag
   builds and creates the GitHub Release at once, but publishes to PyPI only
   after someone approves the waiting deployment.

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
