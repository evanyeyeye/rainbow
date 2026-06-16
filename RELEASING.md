# Releasing rainbow-api to PyPI

Releases are automated. **Pushing a version tag publishes to PyPI** — nothing
else does. A normal commit or merge to `main` never triggers a release.

## How to cut a release

1. Edit `version` in `pyproject.toml` (e.g. `1.0.11` -> `1.0.12`) and merge it to `main`.
2. Tag that commit and push the tag:

   ```bash
   git checkout main && git pull
   git tag -a v1.0.12 -m "Release 1.0.12"
   git push origin v1.0.12
   ```

That's it. Pushing the `v1.0.12` tag triggers
`.github/workflows/publish.yml`, which builds the package and uploads it to
PyPI. Watch it run under the repo's **Actions** tab; when it's green, verify
with `pip install --upgrade rainbow-api`.

Keep the tag version and the `pyproject.toml` version the same (both `1.0.12`).

## What the workflow builds

Because the package includes an optional compiled extension (the `.uv`
accelerator), the workflow builds **binary wheels** with
[`cibuildwheel`](https://cibuildwheel.pypa.io/) across Linux, macOS, and Windows
(the `wheels` job) plus a source distribution (the `sdist` job), then publishes
all of them together. Users on common platforms install a prebuilt wheel with
the accelerator included; everyone else gets the sdist, which falls back to
pure Python if it cannot compile. A release therefore takes a few minutes
longer than a pure-Python one while the wheels build in parallel.

## Rules of thumb

- `git push origin main` -> nothing publishes.
- `git push origin v1.0.12` -> a release happens.
- A version can only be published to PyPI **once**. If a release is broken,
  bump to the next number (`1.0.13`) and tag again — you can't reuse `1.0.12`.

## How the credentials work (the "sausage")

The workflow publishes using PyPI **Trusted Publishing (OIDC)**: GitHub proves
the workflow's identity to PyPI at run time, so there is **no API token** stored
in the repo or on anyone's laptop.

This relies on a one-time setting on PyPI. Because `rainbow-api` already
exists, add it from the project's own settings page (not the account-level
"pending publisher", which is only for projects that don't exist yet):
https://pypi.org/manage/project/rainbow-api/settings/publishing/ -> Add a new
publisher -> GitHub. The values must match the workflow:

| Field            | Value          |
| ---------------- | -------------- |
| PyPI Project     | `rainbow-api`  |
| Owner            | `evanyeyeye`   |
| Repository       | `rainbow`      |
| Workflow         | `publish.yml`  |
| Environment      | `pypi`         |

If a release tag builds successfully but fails at the publish step with an auth
error, that trusted-publisher entry is missing or doesn't match.

## Manual fallback (only if the workflow is broken)

```bash
pip install --upgrade build twine
rm -rf dist build *.egg-info
python -m build
twine check dist/*
twine upload dist/*        # needs a PyPI API token in ~/.pypirc
```
