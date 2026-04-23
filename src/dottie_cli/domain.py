from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .api import DottieClient
from .auth import current_employee_id


FOLLOW_UP_INDEX = 0
LEADER_FEEDBACK_INDEX = 16


def _parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.min
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _find_employee(employees: list[dict[str, Any]], needle: str) -> dict[str, Any]:
    lowered = needle.strip().lower()
    if not lowered:
        raise ValueError("Employee query cannot be empty.")

    exact = [employee for employee in employees if str(employee.get("name", "")).lower() == lowered]
    if len(exact) == 1:
        return exact[0]

    partial = [employee for employee in employees if lowered in str(employee.get("name", "")).lower()]
    if len(partial) == 1:
        return partial[0]
    if not partial:
        raise ValueError(f"No employee matched {needle!r}.")
    names = ", ".join(str(item.get("name", "?")) for item in partial[:8])
    raise ValueError(f"Employee query {needle!r} is ambiguous: {names}")


@dataclass
class SyncPreview:
    employee: dict[str, Any]
    current_meeting: dict[str, Any]
    previous_meeting: dict[str, Any]
    patches: list[dict[str, Any]]


class DottieService:
    def __init__(self, client: DottieClient):
        self.client = client

    def my_employee_id(self) -> int:
        return current_employee_id(self.client.token_bundle)

    def employees(self) -> list[dict[str, Any]]:
        return self.client.get("/Employee") or []

    def team(self, include_self: bool = False) -> list[dict[str, Any]]:
        my_id = self.my_employee_id()
        team = self.client.get("/Employee", query={"LeaderId": my_id}) or []
        if include_self:
            me = self.client.get(f"/Employee/{my_id}")
            if me:
                team = [me, *team]
        return sorted(team, key=lambda item: str(item.get("name", "")))

    def equipment_overview(self, include_self: bool = False) -> list[dict[str, Any]]:
        team = self.team(include_self=include_self)
        employees_by_id = {employee["id"]: employee for employee in team}
        leases = self.client.get("/EquipmentLease") or []
        relevant_leases = [lease for lease in leases if lease.get("employeeId") in employees_by_id]
        equipment_ids = sorted({lease.get("equipmentId") for lease in relevant_leases if lease.get("equipmentId")})
        equipment = self.client.get("/Equipment", query={"Id": equipment_ids}) if equipment_ids else []
        equipment_by_id = {item["id"]: item for item in equipment or []}

        rows: list[dict[str, Any]] = []
        for lease in relevant_leases:
            employee = employees_by_id.get(lease["employeeId"], {})
            item = equipment_by_id.get(lease["equipmentId"], {})
            rows.append(
                {
                    "employeeId": lease.get("employeeId"),
                    "employeeName": employee.get("name", f"#{lease.get('employeeId')}"),
                    "equipmentId": lease.get("equipmentId"),
                    "equipmentName": item.get("name", f"#{lease.get('equipmentId')}"),
                    "equipmentTypeName": item.get("equipmentTypeName", ""),
                    "identifier": item.get("identifier", ""),
                    "dateStart": lease.get("dateStart"),
                    "dateEnd": lease.get("dateEnd"),
                    "commentStart": lease.get("commentStart", ""),
                    "commentEnd": lease.get("commentEnd", ""),
                    "status": item.get("status"),
                }
            )
        return sorted(rows, key=lambda item: (item["employeeName"], item["equipmentName"]))

    def absence_overview(self, *, from_date: str | None, to_date: str | None, include_self: bool = True) -> list[dict[str, Any]]:
        team = self.team(include_self=include_self)
        employee_ids = [employee["id"] for employee in team]
        requests = self.client.get("/LeaveRequest", query={"EmployeeId": employee_ids}) or []
        request_ids = [item["id"] for item in requests]
        intervals = self.client.get(
            "/LeaveInterval",
            query={
                "EmployeeId": employee_ids,
                "RequestId": request_ids or None,
                "From": from_date,
                "To": to_date,
            },
        ) or []
        return sorted(intervals, key=lambda item: (item.get("dateStart", ""), item.get("employeeName", "")))

    def recurring_meetings_for(self, employee_id: int) -> list[dict[str, Any]]:
        meetings = self.client.get(
            "/RecurringMeeting",
            query={
                "ResponsibleEmployeeId": self.my_employee_id(),
                "EmployeeId": [employee_id],
            },
        ) or []
        return sorted(meetings, key=lambda item: _parse_dt(item.get("date")))

    def conversation_history(self, employee_query: str) -> tuple[dict[str, Any], list[dict[str, Any]], dict[int, list[dict[str, Any]]]]:
        employees = self.employees()
        employee = _find_employee(employees, employee_query)
        meetings = self.recurring_meetings_for(employee["id"])
        answers_by_meeting: dict[int, list[dict[str, Any]]] = {}
        for meeting in meetings:
            answers_by_meeting[meeting["id"]] = self.client.get("/RecurringMeetingAnswer", query={"RecurringMeetingId": meeting["id"]}) or []
        return employee, meetings, answers_by_meeting

    def prepare_note_sync(self, employee_query: str, leader_feedback: str | None = None) -> SyncPreview:
        employees = self.employees()
        employee = _find_employee(employees, employee_query)
        meetings = self.recurring_meetings_for(employee["id"])

        previous = [meeting for meeting in meetings if int(meeting.get("status", -1)) == 1]
        upcoming = [meeting for meeting in meetings if int(meeting.get("status", -1)) == 0]
        if not previous:
            raise ValueError(f"No completed recurring meeting found for {employee['name']}.")
        if not upcoming:
            raise ValueError(f"No upcoming recurring meeting found for {employee['name']}.")

        previous_meeting = previous[-1]
        current_meeting = upcoming[0]
        previous_answers = self.client.get("/RecurringMeetingAnswer", query={"RecurringMeetingId": previous_meeting["id"]}) or []
        current_answers = self.client.get("/RecurringMeetingAnswer", query={"RecurringMeetingId": current_meeting["id"]}) or []

        previous_by_index = {item["index"]: item for item in previous_answers}
        patches: list[dict[str, Any]] = []
        for current in current_answers:
            index = current.get("index")
            previous_item = previous_by_index.get(index)
            if previous_item is None:
                continue

            generated_text = build_generated_private_note(
                current_index=index,
                current_question=current.get("question"),
                previous_answer=previous_item.get("answer"),
                previous_answers=previous_answers,
                previous_meeting=previous_meeting,
            )
            if not generated_text:
                continue

            merged = merge_private_note(current.get("privateNote"), generated_text)
            if merged != (current.get("privateNote") or ""):
                patches.append(
                    {
                        "id": current["id"],
                        "property": "privateNote",
                        "value": merged,
                        "entityId": current["id"],
                        "replacesVersion": current.get("version"),
                        "question": current.get("question"),
                        "index": index,
                    }
                )

        if leader_feedback:
            feedback_candidates = [item for item in current_answers if item.get("index") == LEADER_FEEDBACK_INDEX]
            if feedback_candidates:
                feedback_target = feedback_candidates[0]
                patches.append(
                    {
                        "id": feedback_target["id"],
                        "property": "answer",
                        "value": leader_feedback.strip(),
                        "entityId": feedback_target["id"],
                        "replacesVersion": feedback_target.get("version"),
                        "question": feedback_target.get("question"),
                        "index": feedback_target.get("index"),
                    }
                )

        return SyncPreview(
            employee=employee,
            current_meeting=current_meeting,
            previous_meeting=previous_meeting,
            patches=patches,
        )

    def apply_sync(self, preview: SyncPreview) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for patch in preview.patches:
            payload = {
                "property": patch["property"],
                "value": patch["value"],
                "entityId": patch["entityId"],
                "replacesVersion": patch.get("replacesVersion"),
            }
            result = self.client.patch(f"/RecurringMeetingAnswer/{patch['id']}", body=payload)
            results.append(result or payload)
        return results


def build_generated_private_note(
    *,
    current_index: int,
    current_question: str | None,
    previous_answer: str | None,
    previous_answers: list[dict[str, Any]],
    previous_meeting: dict[str, Any],
) -> str:
    previous_date = str(previous_meeting.get("date", ""))[:10]
    if current_index == FOLLOW_UP_INDEX:
        bullets: list[str] = []
        for item in sorted(previous_answers, key=lambda answer: answer.get("index", 0)):
            answer_text = (item.get("answer") or "").strip()
            question_text = (item.get("question") or "").strip()
            if not answer_text:
                continue
            bullets.append(f"- {question_text}: {answer_text}")
        if not bullets:
            return ""
        return (
            f"Oppsummering fra forrige samtale ({previous_date})\n"
            f"[dottie-cli recurring-meeting:{previous_meeting.get('id')} index:{current_index}]\n\n"
            + "\n\n".join(bullets)
        )

    answer_text = (previous_answer or "").strip()
    if not answer_text:
        return ""
    question_label = (current_question or "Sporsmal").strip()
    return (
        f"Notat fra forrige samtale ({previous_date})\n"
        f"[dottie-cli recurring-meeting:{previous_meeting.get('id')} index:{current_index}]\n\n"
        f"{question_label}\n{answer_text}"
    )


def merge_private_note(existing: str | None, generated: str) -> str:
    existing_text = (existing or "").strip()
    generated_text = generated.strip()
    if not existing_text:
        return generated_text
    if generated_text in existing_text:
        return existing_text
    return f"{existing_text}\n\n{generated_text}"


def summarize_team_by_org(team: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for employee in team:
        buckets[str(employee.get("organizationUnitId") or "unassigned")].append(employee)
    summary = []
    for org_unit_id, members in sorted(buckets.items(), key=lambda item: item[0]):
        summary.append({"organizationUnitId": org_unit_id, "members": len(members)})
    return summary

