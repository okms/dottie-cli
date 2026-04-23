# dottie-cli

[![PyPI](https://img.shields.io/pypi/v/dottie-cli.svg)](https://pypi.org/project/dottie-cli/)
[![Python](https://img.shields.io/pypi/pyversions/dottie-cli.svg)](https://pypi.org/project/dottie-cli/)

`dottie-cli` is a Python command line interface for the Dottie HR web application at `https://app.dottie.no` and the corresponding API at `https://api.dottie.no`.

The tool is designed for both direct shell use and agent-driven workflows:

- read commands are stable and scriptable
- write commands default to preview mode
- token handling is explicit and never committed
- output can be table-shaped for people or JSON for automation

## Features

Current command coverage includes:

- team membership and team overview
- equipment assigned to team members
- scheduled vacation and other absence for the current employee and team scope
- recurring meeting history, including self-history for employees
- the next upcoming recurring meeting and any visible prefilled answers
- append-only manager note preparation for upcoming recurring meetings

## Install

From PyPI:

```bash
pip install dottie-cli
```

Run without installing (via `uv`):

```bash
uvx dottie-cli --help
uvx --from dottie-cli dottie --help
```

From source (editable):

```bash
git clone https://github.com/okms/dottie-cli
cd dottie-cli
python3 -m pip install -e .
```

After install, both script names are available:

```bash
dottie --help
dottie-cli --help
```

You can also run the module directly without installing:

```bash
python3 -m dottie_cli --help
```

## Authentication

The CLI uses a short-lived JWT from the live Dottie web application. It does not mint credentials, store refresh tokens, or expect secrets in the repository.

Default lookup order:

1. `DOTTIE_TOKEN` environment variable
2. `~/.dottie-token`
3. `--token-file <path>` to override explicitly

The token must be the Dottie application token used against `https://api.dottie.no`, not a generic identity token.

## Token Capture

Print a bookmarklet:

```bash
dottie token bookmarklet
```

Print a console snippet:

```bash
dottie token console-snippet
```

Validate the local token file without printing the token:

```bash
dottie token status
```

Typical capture flow:

1. Open `https://app.dottie.no`
2. Use the bookmarklet or console snippet
3. Copy the token
4. Write it locally:

```bash
pbpaste > ~/.dottie-token
```

## Global Flags

These flags can appear anywhere on the command line:

- `--json` — emit JSON instead of a table or prose view
- `--token-file <path>` — override the token file location

## Commands

### Team

List team members:

```bash
dottie team list
dottie team list --include-self
dottie team list --json
```

Summarize headcount and organization distribution:

```bash
dottie team overview
```

### Equipment

Read equipment assigned to your team:

```bash
dottie equipment overview
dottie equipment overview --include-self
```

### Absence

Read absence for you and your team:

```bash
dottie absence overview --from 2026-01-01 --to 2026-12-31
dottie absence overview --from 2026-01-01 --to 2026-12-31 --exclude-self
```

Both bounds are optional and accept ISO dates or datetimes.

### Conversations

Read conversation history for one employee:

```bash
dottie conversations history "Employee Name"
```

Read your own conversation history (works for non-managers):

```bash
dottie conversations history --self
```

Read the next upcoming recurring meeting and any visible prefilled answers:

```bash
dottie conversations upcoming "Employee Name"
dottie conversations upcoming --self
```

Preview append-only conversation note updates:

```bash
dottie conversations sync-notes "Employee Name" --dry-run
```

Apply the updates after preview:

```bash
dottie conversations sync-notes "Employee Name" --apply
```

Optionally include leader feedback in the same run:

```bash
dottie conversations sync-notes "Employee Name" \
  --leader-feedback "Takk for at du tok ansvar for overleveringen i april." \
  --apply
```

## Write Safety

`sync-notes` is intentionally append-only for private notes:

- existing `privateNote` content is preserved
- generated content is appended as a new section
- a small provenance marker is included so repeated runs do not duplicate the same note block
- feedback writes are explicit through `--leader-feedback`
- without `--apply`, no PATCH requests are sent

## API Basis

The command layout is based on Dottie's public OpenAPI document:

- `https://api.dottie.no/swagger/index.html`
- `https://api.dottie.no/swagger/v1/swagger.json`

Relevant resources used by this CLI:

- `Employee`
- `Equipment`
- `EquipmentLease`
- `LeaveRequest`
- `LeaveInterval`
- `RecurringMeeting`
- `RecurringMeetingAnswer`

## Notes for Agents

This CLI is intended to be straightforward to drive from another agent or automation layer:

- prefer `--json` when another tool will consume the result
- use `dottie token status` as a preflight
- treat `dottie conversations sync-notes` without `--apply` as the planning step
- only escalate to `--apply` once the preview matches the intended note append

No user or tenant identifiers are hard-coded in the source tree. The current employee is resolved from `app_uid` in the live token.

## Releases

New versions are published to PyPI from GitHub Actions when a `v*` tag is pushed. The workflow uses PyPI trusted publishing against the `pypi` environment in this repository, so no long-lived API tokens are stored.

Release flow:

```bash
# bump version in pyproject.toml, commit
git tag v0.2.2
git push origin main --tags
```

The `.github/workflows/publish.yml` workflow builds the distribution and publishes it on tag push. Tag-less runs can also be triggered via `workflow_dispatch` from the Actions tab.
