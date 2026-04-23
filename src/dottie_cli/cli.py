from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .api import DottieAPIError, DottieClient
from .auth import DEFAULT_TOKEN_PATH, TokenError, load_token
from .domain import ALLOWED_ANSWER_PROPERTIES, DottieService, summarize_team_by_org
from .formatting import iso_to_date, print_json, print_table


BOOKMARKLET = """javascript:void((function(){function parseJwt(t){try{return JSON.parse(atob(t.split('.')[1].replace(/-/g,'+').replace(/_/g,'/')))}catch(e){return null}}function isJwt(v){return typeof v==='string'&&/^eyJ[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+$/.test(v)}function isDottieToken(t){var p=parseJwt(t);return !!(p&&(p.app_uid||p.app_tid||p.app_auth_role||p.app_uname))}function outputToken(t,msg){if(navigator.clipboard&&document.hasFocus()){navigator.clipboard.writeText(t).then(function(){alert(msg+'\\n\\nKjør i terminalen:\\npbpaste > ~/.dottie-token')},function(){prompt(msg+' - kopier manuelt:',t)})}else{prompt(msg+' - kopier manuelt:',t)}}function extractFromHeaders(h){if(!h)return null;if(h instanceof Headers)return h.get('Authorization')||h.get('authorization');return h.Authorization||h.authorization||null}function captureToken(t,msg){if(t&&isJwt(t)){outputToken(t,msg);return true}return false}var candidates=[];[localStorage,sessionStorage].forEach(function(s){for(var i=0;i<s.length;i++){var k=s.key(i),v=s.getItem(k);if(isJwt(v))candidates.push(v);try{var o=JSON.parse(v);['token','access_token','accessToken','id_token','idToken'].forEach(function(f){if(isJwt(o&&o[f]))candidates.push(o[f])})}catch(e){}}});var picked=candidates.find(isDottieToken)||null;if(picked){captureToken(picked,'Dottie-token funnet');return}var of=window.fetch;window.fetch=function(){var a=arguments,url=String(a[0]&&a[0].url||a[0]||''),auth=extractFromHeaders(a[1]&&a[1].headers);if(auth&&auth.startsWith('Bearer ')){var tk=auth.slice(7);if(url.indexOf('api.dottie.no')!==-1||isDottieToken(tk)){captureToken(tk,'Dottie-token fanget');window.fetch=of}}return of.apply(this,a)};var ox=window.XMLHttpRequest;if(ox){var open=ox.prototype.open,send=ox.prototype.send,setHeader=ox.prototype.setRequestHeader;ox.prototype.open=function(m,u){this.__url=u;return open.apply(this,arguments)};ox.prototype.setRequestHeader=function(k,v){this.__headers=this.__headers||{};this.__headers[k]=v;return setHeader.apply(this,arguments)};ox.prototype.send=function(){var auth=extractFromHeaders(this.__headers);if(auth&&auth.startsWith('Bearer ')){var tk=auth.slice(7),url=String(this.__url||'');if(url.indexOf('api.dottie.no')!==-1||isDottieToken(tk)){captureToken(tk,'Dottie-token fanget');ox.prototype.open=open;ox.prototype.send=send;ox.prototype.setRequestHeader=setHeader}}return send.apply(this,arguments)}}alert('Fant ikke et Dottie-token i storage. Klikk rundt i Dottie, så fanges tokenet fra neste API-kall.');})())"""

CONSOLE_SNIPPET = """const parseJwt = t => { try { return JSON.parse(atob(t.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))); } catch { return null; } };
const isJwt = v => /^eyJ[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+$/.test(v || '');
const isDottieToken = t => { const p = parseJwt(t); return !!(p && (p.app_uid || p.app_tid || p.app_auth_role || p.app_uname)); };
let token;
[localStorage, sessionStorage].forEach(s => {
  for (let i = 0; i < s.length; i++) {
    const v = s.getItem(s.key(i));
    if (isJwt(v) && isDottieToken(v)) { token = v; break; }
    try {
      const o = JSON.parse(v);
      for (const k of ['token', 'access_token', 'accessToken', 'id_token', 'idToken']) {
        if (isJwt(o?.[k]) && isDottieToken(o[k])) { token = o[k]; break; }
      }
    } catch {}
    if (token) break;
  }
});
if (token) prompt('Kopier Dottie-tokenet:', token);
else console.log('Fant ikke Dottie-token i storage. Hent Authorization-headeren fra et kall mot api.dottie.no i Network-fanen.');"""


class RichHelpFormatter(argparse.RawDescriptionHelpFormatter, argparse.ArgumentDefaultsHelpFormatter):
    pass


def normalize_global_flags(argv: list[str] | None) -> list[str] | None:
    if argv is None:
        return None

    remaining = list(argv)
    prefix: list[str] = []

    idx = 0
    while idx < len(remaining):
        token = remaining[idx]
        if token == "--json":
            prefix.append(token)
            del remaining[idx]
            continue
        if token == "--token-file":
            if idx + 1 >= len(remaining):
                return list(argv)
            prefix.extend([token, remaining[idx + 1]])
            del remaining[idx : idx + 2]
            continue
        idx += 1

    return [*prefix, *remaining]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dottie",
        description=(
            "Dottie CLI uses a live app token from app.dottie.no to read your team, summarize "
            "conversations, inspect equipment, and review absence.\n\n"
            "The CLI is designed for human and agent use: commands are stable, read-heavy by default, "
            "and write paths expose a preview before you apply them."
        ),
        epilog=(
            "Concepts:\n"
            "  token            A short-lived JWT copied from a live Dottie browser session.\n"
            "  team             Employees where your employee id is the current leader.\n"
            "  conversation     Recurring meeting data and answer rows in Dottie.\n"
            "  sync-notes       Append manager-private notes from the previous completed meeting into the next one.\n\n"
            "Typical agent flow:\n"
            "  1. dottie token status\n"
            "  2. dottie team overview --json\n"
            "  3. dottie absence overview --from 2026-01-01 --to 2026-12-31\n"
            "  4. dottie conversations sync-notes \"Employee Name\" --dry-run\n"
            "  5. dottie conversations sync-notes \"Employee Name\" --apply\n"
        ),
        formatter_class=RichHelpFormatter,
    )
    parser.add_argument(
        "--token-file",
        type=Path,
        default=DEFAULT_TOKEN_PATH,
        help="Read the Dottie app token from this file unless DOTTIE_TOKEN is set.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a table or prose view.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    token_parser = subparsers.add_parser(
        "token",
        help="Inspect token state and print safe capture helpers.",
        formatter_class=RichHelpFormatter,
        description="Token helpers. These commands never print the actual token value.",
    )
    token_sub = token_parser.add_subparsers(dest="token_command", required=True)
    token_sub.add_parser("status", help="Validate the token file and show non-secret claims.")
    token_sub.add_parser("bookmarklet", help="Print the bookmarklet used to capture a live Dottie token.")
    token_sub.add_parser("console-snippet", help="Print a browser console snippet that locates a Dottie token.")

    team_parser = subparsers.add_parser(
        "team",
        help="Read team membership and produce manager-facing summaries.",
        formatter_class=RichHelpFormatter,
    )
    team_sub = team_parser.add_subparsers(dest="team_command", required=True)
    team_list = team_sub.add_parser("list", help="List team members.")
    team_list.add_argument("--include-self", action="store_true", help="Include your own employee record.")
    team_sub.add_parser("overview", help="Summarize headcount and organization-unit distribution.")

    equipment_parser = subparsers.add_parser(
        "equipment",
        help="Show equipment leased to your team based on EquipmentLease and Equipment.",
        formatter_class=RichHelpFormatter,
    )
    equipment_sub = equipment_parser.add_subparsers(dest="equipment_command", required=True)
    equipment_overview = equipment_sub.add_parser("overview", help="List equipment assigned to your team.")
    equipment_overview.add_argument("--include-self", action="store_true", help="Include your own equipment leases.")

    absence_parser = subparsers.add_parser(
        "absence",
        help="Show leave requests and intervals for you and your team.",
        formatter_class=RichHelpFormatter,
    )
    absence_sub = absence_parser.add_subparsers(dest="absence_command", required=True)
    absence_overview = absence_sub.add_parser("overview", help="List scheduled leave intervals.")
    absence_overview.add_argument("--from", dest="from_date", help="ISO date or datetime lower bound.")
    absence_overview.add_argument("--to", dest="to_date", help="ISO date or datetime upper bound.")
    absence_overview.add_argument("--exclude-self", action="store_true", help="Only include direct reports.")

    conv_parser = subparsers.add_parser(
        "conversations",
        help="Read recurring meeting history and append internal notes into the next meeting.",
        formatter_class=RichHelpFormatter,
        description=(
            "Conversation commands never overwrite manager private notes. Sync operations append a new section "
            "for the previous meeting and carry a small provenance marker to avoid accidental duplicate writes."
        ),
    )
    conv_sub = conv_parser.add_subparsers(dest="conversation_command", required=True)
    history = conv_sub.add_parser("history", help="Show meetings and answers for one employee.")
    history_target = history.add_mutually_exclusive_group(required=True)
    history_target.add_argument("employee", nargs="?", help="Employee name or unique partial match.")
    history_target.add_argument("--self", dest="self_only", action="store_true", help="Show your own recurring meetings.")
    upcoming = conv_sub.add_parser("upcoming", help="Show the next upcoming recurring meeting and any visible prefilled answers.")
    upcoming_target = upcoming.add_mutually_exclusive_group(required=True)
    upcoming_target.add_argument("employee", nargs="?", help="Employee name or unique partial match.")
    upcoming_target.add_argument("--self", dest="self_only", action="store_true", help="Show your own upcoming recurring meeting.")
    answer = conv_sub.add_parser(
        "answer",
        help="Write one or more answer (or privateNote) values on the upcoming meeting.",
        formatter_class=RichHelpFormatter,
        description=(
            "Set the 'answer' field (default) or 'privateNote' on one or more questions of the next "
            "upcoming recurring meeting. Use --self to target your own meeting, or pass the employee name "
            "when you are the responsible leader. Shows a diff preview; --apply persists."
        ),
    )
    answer_target = answer.add_mutually_exclusive_group(required=True)
    answer_target.add_argument("employee", nargs="?", help="Employee name or unique partial match.")
    answer_target.add_argument("--self", dest="self_only", action="store_true", help="Target your own upcoming meeting.")
    answer.add_argument("--index", type=int, help="Question index to write.")
    answer.add_argument("--text", help="Value to write on the given --index.")
    answer.add_argument(
        "--property",
        dest="answer_property",
        choices=("answer", "privateNote"),
        default="answer",
        help="Field to patch (default: answer).",
    )
    answer.add_argument(
        "--from-file",
        dest="from_file",
        type=Path,
        help="JSON file with {\"answers\": [{\"index\":N,\"text\":\"...\",\"property\":\"answer|privateNote\"}]}.",
    )
    answer.add_argument(
        "--footer",
        help="Footer appended (with blank-line separator) unless already present in the final text.",
    )
    answer_mode = answer.add_mutually_exclusive_group()
    answer_mode.add_argument("--apply", action="store_true", help="Persist the patches after the preview.")
    answer_mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicitly request preview mode. This is the default unless --apply is given.",
    )

    sync = conv_sub.add_parser("sync-notes", help="Preview or apply append-only note updates for one employee.")
    sync.add_argument("employee", help="Employee name or unique partial match.")
    sync.add_argument("--leader-feedback", help="Optional leader feedback to write to the feedback question.")
    mode = sync.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Apply PATCH requests after showing the preview.")
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicitly request preview mode. This is the default unless --apply is given.",
    )

    return parser


def build_service(args: argparse.Namespace) -> DottieService:
    token_bundle = load_token(args.token_file)
    return DottieService(DottieClient(token_bundle=token_bundle))


def handle_token(args: argparse.Namespace) -> int:
    if args.token_command == "bookmarklet":
        print(BOOKMARKLET)
        return 0
    if args.token_command == "console-snippet":
        print(CONSOLE_SNIPPET)
        return 0

    token_bundle = load_token(args.token_file)
    payload = {
        "tokenFile": str(token_bundle.path) if token_bundle.path else "(from DOTTIE_TOKEN)",
        "claims": {
            key: token_bundle.claims.get(key)
            for key in ("app_uid", "app_uname", "app_tid", "app_auth_role", "iss", "exp")
            if key in token_bundle.claims
        },
    }
    print_json(payload)
    return 0


def handle_team(args: argparse.Namespace) -> int:
    service = build_service(args)
    if args.team_command == "list":
        team = service.team(include_self=args.include_self)
        if args.json:
            print_json(team)
            return 0
        rows = [
            {
                "id": item.get("id"),
                "name": item.get("name", ""),
                "email": item.get("preferredEmailAddress", ""),
                "leaderId": item.get("leaderId", ""),
                "org": item.get("organizationUnitId", ""),
                "jobTitleId": item.get("jobTitleId", ""),
                "firstDay": iso_to_date(item.get("firstDayOfWork")),
                "lastDay": iso_to_date(item.get("lastDayOfWork")),
            }
            for item in team
        ]
        print_table(rows, [("id", "ID"), ("name", "Name"), ("email", "Email"), ("org", "Org"), ("jobTitleId", "JobTitle"), ("firstDay", "Start"), ("lastDay", "End")])
        return 0

    team = service.team(include_self=False)
    summary = {
        "headcount": len(team),
        "organizationUnits": summarize_team_by_org(team),
    }
    if args.json:
        print_json(summary)
        return 0
    print(f"Headcount: {summary['headcount']}")
    print()
    print_table(summary["organizationUnits"], [("organizationUnitId", "OrgUnitId"), ("members", "Members")])
    return 0


def handle_equipment(args: argparse.Namespace) -> int:
    service = build_service(args)
    rows = service.equipment_overview(include_self=args.include_self)
    if args.json:
        print_json(rows)
        return 0
    display = [
        {
            "employeeName": row["employeeName"],
            "equipmentName": row["equipmentName"],
            "equipmentTypeName": row["equipmentTypeName"],
            "identifier": row["identifier"],
            "dateStart": iso_to_date(row["dateStart"]),
            "dateEnd": iso_to_date(row["dateEnd"]),
        }
        for row in rows
    ]
    print_table(
        display,
        [
            ("employeeName", "Employee"),
            ("equipmentName", "Equipment"),
            ("equipmentTypeName", "Type"),
            ("identifier", "Identifier"),
            ("dateStart", "From"),
            ("dateEnd", "To"),
        ],
    )
    return 0


def handle_absence(args: argparse.Namespace) -> int:
    service = build_service(args)
    rows = service.absence_overview(
        from_date=args.from_date,
        to_date=args.to_date,
        include_self=not args.exclude_self,
    )
    if args.json:
        print_json(rows)
        return 0
    display = [
        {
            "employeeName": row.get("employeeName", ""),
            "dateStart": iso_to_date(row.get("dateStart")),
            "dateEnd": iso_to_date(row.get("dateEnd")),
            "dayCount": row.get("dayCount", ""),
            "status": row.get("status", ""),
            "requestId": row.get("leaveRequestId", ""),
        }
        for row in rows
    ]
    print_table(display, [("employeeName", "Employee"), ("dateStart", "From"), ("dateEnd", "To"), ("dayCount", "Days"), ("status", "Status"), ("requestId", "RequestId")])
    return 0


def _load_answer_updates(args: argparse.Namespace) -> list[dict[str, object]]:
    has_inline = args.index is not None or args.text is not None
    if has_inline and args.from_file:
        raise ValueError("Use either --index/--text or --from-file, not both.")
    if has_inline:
        if args.index is None or args.text is None:
            raise ValueError("--index and --text must be given together.")
        return [{"index": args.index, "text": args.text, "property": args.answer_property}]
    if args.from_file:
        try:
            raw = args.from_file.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"Could not read {args.from_file}: {exc}") from exc
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {args.from_file}: {exc}") from exc
        items = payload.get("answers") if isinstance(payload, dict) else None
        if not isinstance(items, list) or not items:
            raise ValueError("JSON must contain a non-empty 'answers' array.")
        normalized: list[dict[str, object]] = []
        for position, raw_item in enumerate(items, start=1):
            if not isinstance(raw_item, dict):
                raise ValueError("Each answers entry must be an object.")
            index = raw_item.get("index")
            if type(index) is not int:
                raise ValueError(f"answers[{position}] must contain an integer 'index'.")
            text = raw_item.get("text", "")
            if not isinstance(text, str):
                raise ValueError(f"answers[{position}] 'text' must be a string.")
            prop = raw_item.get("property") or args.answer_property
            if not isinstance(prop, str):
                raise ValueError(f"answers[{position}] 'property' must be a string.")
            if prop not in ALLOWED_ANSWER_PROPERTIES:
                raise ValueError(
                    f"answers[{position}] unsupported property {prop!r}; "
                    f"must be one of {ALLOWED_ANSWER_PROPERTIES}."
                )
            normalized.append(
                {
                    "index": index,
                    "text": text,
                    "property": prop,
                }
            )
        return normalized
    raise ValueError("Provide --index/--text or --from-file.")


def handle_answer(service: DottieService, args: argparse.Namespace) -> int:
    updates = _load_answer_updates(args)
    preview = service.prepare_answer_updates(
        args.employee,
        self_only=getattr(args, "self_only", False),
        updates=updates,
        footer=args.footer,
    )
    results: list[dict[str, object]] = []
    if args.json and args.apply and preview.patches:
        results = service.apply_answer_updates(preview)
    payload = {
        "employee": {"id": preview.employee.get("id"), "name": preview.employee.get("name")},
        "currentMeeting": {"id": preview.current_meeting.get("id"), "date": preview.current_meeting.get("date")},
        "patches": preview.patches,
        "skipped": preview.skipped,
        "applyRequested": bool(args.apply),
        "applied": bool(args.apply),
        "appliedCount": len(preview.patches) if args.apply else 0,
        "results": results,
    }
    if args.json:
        print_json(payload)
    else:
        print(f"Employee: {preview.employee.get('name')} ({preview.employee.get('id')})")
        print(f"Upcoming meeting: {preview.current_meeting.get('id')} on {iso_to_date(preview.current_meeting.get('date'))}")
        print()
        if not preview.patches and not preview.skipped:
            print("No updates to apply.")
        for patch in preview.patches:
            print(f"[{patch['index']}] {patch.get('question')}  ({patch['property']})")
            print(patch["value"])
            print()
        for skipped in preview.skipped:
            print(f"[{skipped['index']}] {skipped.get('question')}  ({skipped['property']}) — skipped ({skipped.get('reason')})")
        if preview.patches and not args.apply:
            print("Preview only. Re-run with --apply to persist these changes.")

    if not args.json and args.apply and preview.patches:
        service.apply_answer_updates(preview)
        print(f"Applied {len(preview.patches)} patch(es).")
    return 0


def handle_conversations(args: argparse.Namespace) -> int:
    service = build_service(args)
    if args.conversation_command == "history":
        employee, meetings, answers_by_meeting = service.conversation_history(args.employee, self_only=getattr(args, "self_only", False))
        payload = {
            "employee": employee,
            "meetings": meetings,
            "answersByMeeting": answers_by_meeting,
        }
        if args.json:
            print_json(payload)
            return 0
        print(f"Employee: {employee.get('name')} ({employee.get('id')})")
        print()
        for meeting in meetings:
            print(f"{iso_to_date(meeting.get('date'))}  status={meeting.get('status')}  id={meeting.get('id')}  {meeting.get('name', '')}")
            for answer in sorted(answers_by_meeting.get(meeting["id"], []), key=lambda item: item.get("index", 0)):
                answer_text = (answer.get("answer") or "").strip()
                if answer_text:
                    print(f"  [{answer.get('index')}] {answer.get('question')}: {answer_text}")
            print()
        return 0

    if args.conversation_command == "upcoming":
        employee, meeting, answers = service.upcoming_conversation(args.employee, self_only=getattr(args, "self_only", False))
        visible_answers = [answer for answer in sorted(answers, key=lambda item: item.get("index", 0)) if (answer.get("answer") or "").strip()]
        payload = {
            "employee": employee,
            "meeting": meeting,
            "answers": answers,
            "visibleAnswers": visible_answers,
        }
        if args.json:
            print_json(payload)
            return 0
        print(f"Employee: {employee.get('name')} ({employee.get('id')})")
        print(f"Upcoming meeting: {meeting.get('id')} on {iso_to_date(meeting.get('date'))}")
        print()
        if not visible_answers:
            print("No visible answers have been entered yet.")
        for answer in visible_answers:
            print(f"[{answer.get('index')}] {answer.get('question')}: {(answer.get('answer') or '').strip()}")
        return 0

    if args.conversation_command == "answer":
        return handle_answer(service, args)

    preview = service.prepare_note_sync(args.employee, leader_feedback=args.leader_feedback)
    results: list[dict[str, object]] = []
    if args.json and args.apply and preview.patches:
        results = service.apply_sync(preview)
    preview_payload = {
        "employee": {"id": preview.employee.get("id"), "name": preview.employee.get("name")},
        "previousMeeting": {"id": preview.previous_meeting.get("id"), "date": preview.previous_meeting.get("date")},
        "currentMeeting": {"id": preview.current_meeting.get("id"), "date": preview.current_meeting.get("date")},
        "patches": preview.patches,
        "applyRequested": bool(args.apply),
        "applied": bool(args.apply),
        "appliedCount": len(preview.patches) if args.apply else 0,
        "results": results,
    }
    if args.json:
        print_json(preview_payload)
    else:
        print(f"Employee: {preview.employee.get('name')} ({preview.employee.get('id')})")
        print(f"Previous meeting: {preview.previous_meeting.get('id')} on {iso_to_date(preview.previous_meeting.get('date'))}")
        print(f"Current meeting: {preview.current_meeting.get('id')} on {iso_to_date(preview.current_meeting.get('date'))}")
        print()
        if not preview.patches:
            print("No note updates are needed.")
        for patch in preview.patches:
            print(f"[{patch['index']}] {patch.get('question')}")
            print(f"property: {patch['property']}")
            print(patch["value"])
            print()
        if not args.apply:
            print("Preview only. Re-run with --apply to persist these changes.")

    if not args.json and args.apply:
        service.apply_sync(preview)
        print(f"Applied {len(preview.patches)} patch(es).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    effective_argv = list(sys.argv[1:]) if argv is None else argv
    args = parser.parse_args(normalize_global_flags(effective_argv))
    try:
        if args.command == "token":
            return handle_token(args)
        if args.command == "team":
            return handle_team(args)
        if args.command == "equipment":
            return handle_equipment(args)
        if args.command == "absence":
            return handle_absence(args)
        if args.command == "conversations":
            return handle_conversations(args)
        parser.error(f"Unknown command: {args.command}")
    except (TokenError, DottieAPIError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
