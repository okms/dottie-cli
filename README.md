# dottie-cli

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
- recurring meeting history
- append-only manager note preparation for upcoming recurring meetings

## Authentication

The CLI uses a short-lived JWT from the live Dottie web application. It does not mint credentials, store refresh tokens, or expect secrets in the repository.

Default lookup order:

1. `DOTTIE_TOKEN` environment variable
2. `~/.dottie-token`

The token must be the Dottie application token used against `https://api.dottie.no`, not a generic identity token.

## Token Capture

Print a bookmarklet:

```bash
python -m dottie_cli token bookmarklet
```

Print a console snippet:

```bash
python -m dottie_cli token console-snippet
```

Validate the local token file without printing the token:

```bash
python -m dottie_cli token status
```

Typical capture flow:

1. Open `https://app.dottie.no`
2. Use the bookmarklet or console snippet
3. Copy the token
4. Write it locally:

```bash
pbpaste > ~/.dottie-token
```

## Install

Editable install:

```bash
python3 -m pip install -e .
```

Run without installing:

```bash
python3 -m dottie_cli --help
```

Once published, the package can be invoked through `uvx` with either command name:

```bash
uvx --from dottie-cli dottie --help
uvx dottie-cli --help
```

## Commands

Read team members:

```bash
dottie team list
dottie team list --include-self --json
```

Summarize headcount and organization distribution:

```bash
dottie team overview
```

Read equipment assigned to your team:

```bash
dottie equipment overview
```

Read absence for you and your team:

```bash
dottie absence overview --from 2026-01-01 --to 2026-12-31
```

Read conversation history for one employee:

```bash
dottie conversations history "Employee Name"
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
- use `token status` as a preflight
- treat `conversations sync-notes` without `--apply` as the planning step
- only escalate to `--apply` once the preview matches the intended note append

No user or tenant identifiers are hard-coded in the source tree. The current employee is resolved from `app_uid` in the live token.
