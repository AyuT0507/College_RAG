"""Read-only connector for the signed-in user's own Fusion data.

Routes are derived from the public Fusion frontend (https://github.com/FusionIIIT/Fusion-client).
Credentials and the short-lived API token stay in memory for one user-triggered sync
and are never written to the database.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import requests

FUSION_ORIGIN = "https://fusion.iiitdmj.ac.in"
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
TIMEOUT_SECONDS = (5, 20)


class FusionError(Exception):
    """A safe-to-display Fusion connection error without credential details."""


class FusionAuthenticationError(FusionError):
    """Fusion rejected credentials or the account token."""


@dataclass
class FusionRecord:
    category: str
    title: str
    external_id: str
    text: str
    source_url: str


def _clean(value: Any) -> Any:
    """Remove session fields and image payloads before indexing API data."""
    excluded = {
        "password", "token", "access_token", "refresh_token", "photo", "profile_photo",
        "profile_image", "avatar", "image", "image_url"
    }
    if isinstance(value, dict):
        return {
            str(key): _clean(item)
            for key, item in value.items()
            if str(key).lower() not in excluded
        }
    if isinstance(value, list):
        return [_clean(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class FusionClient:
    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self._token: str | None = None

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        params: dict | None = None,
        authenticated: bool = True,
    ) -> Any:
        if not path.startswith("/") or path.startswith("//"):
            raise FusionError("Invalid Fusion API path")
        headers = {"Accept": "application/json"}
        if authenticated:
            if not self._token:
                raise FusionError("Fusion login is required")
            headers["Authorization"] = f"Token {self._token}"
        try:
            response = self.session.request(
                method,
                FUSION_ORIGIN + path,
                json=json_body,
                params=params,
                headers=headers,
                timeout=TIMEOUT_SECONDS,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise FusionError("Could not connect to Fusion; check your connection and retry") from exc
        if response.status_code in {301, 302, 303, 307, 308}:
            raise FusionError("Fusion redirected the request; login or API behavior may have changed")
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise FusionError("Fusion response exceeded the 5 MB safety limit")
        if response.status_code in {401, 403}:
            raise FusionAuthenticationError("Fusion rejected the login or access to this data")
        if not response.ok:
            raise FusionError(f"Fusion returned HTTP {response.status_code}")
        try:
            return response.json()
        except (ValueError, requests.JSONDecodeError) as exc:
            raise FusionError("Fusion returned an unexpected non-JSON response") from exc

    def login(self, username: str, password: str) -> None:
        if not username.strip() or not password:
            raise FusionError("Enter your Fusion username and password")
        payload = self._request(
            "POST",
            "/api/auth/login/",
            json_body={"username": username.strip(), "password": password},
            authenticated=False,
        )
        token = payload.get("token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token:
            raise FusionAuthenticationError("Fusion login failed; check your credentials or login requirements")
        self._token = token

    @staticmethod
    def _as_record(category: str, title: str, external_id: str, data: Any, source_path: str) -> FusionRecord | None:
        cleaned = _clean(data)
        if cleaned in (None, {}, [], ""):
            return None
        body = json.dumps(cleaned, ensure_ascii=False, indent=2, default=str)
        if len(body.encode("utf-8")) > MAX_RESPONSE_BYTES:
            raise FusionError(f"Fusion {category} data exceeded the 5 MB safety limit")
        return FusionRecord(
            category=category,
            title=title,
            external_id=external_id,
            text=body,
            source_url=FUSION_ORIGIN + source_path,
        )

    def fetch_records(self) -> tuple[list[FusionRecord], dict[str, str]]:
        if not self._token:
            raise FusionError("Fusion login is required")
        records: list[FusionRecord] = []
        errors: dict[str, str] = {}

        def add(
            category: str,
            title: str,
            external_id: str,
            path: str,
            *,
            method: str = "GET",
            json_body: dict | None = None,
            params: dict | None = None,
        ) -> Any:
            try:
                data = self._request(method, path, json_body=json_body, params=params)
                errors.pop(category, None)
                record = self._as_record(category, title, external_id, data, path)
                if record:
                    records.append(record)
                return data
            except FusionError as exc:
                errors[category] = str(exc)
                return None

        add("profile", "Fusion profile", "profile", "/api/profile/")
        add("notices", "Fusion notifications", "notifications", "/api/notification/")
        add(
            "courses",
            "Current Fusion course registration",
            "courses:current",
            "/academic-procedures/api/stu/current_courseregistration",
        )

        semesters = add(
            "grades",
            "Fusion result semesters",
            "result-semesters",
            "/examination/api/student/result_semesters/",
        )
        semester_rows = semesters.get("semesters", []) if isinstance(semesters, dict) else []
        if not isinstance(semester_rows, list):
            errors["grades"] = "Fusion returned an unexpected semester list"
            semester_rows = []

        for semester in semester_rows[:30]:
            if not isinstance(semester, dict):
                continue
            number = semester.get("semester_no")
            kind = semester.get("semester_type")
            if number is None or kind is None:
                continue
            key = f"{number}:{kind}"
            params = {"semester": str(number), "semester_type": str(kind)}
            add(
                "courses",
                f"Course registration · semester {number} {kind}",
                f"courses:{key}",
                "/academic-procedures/api/stu/current_courseregistration",
                params=params,
            )
            add(
                "grades",
                f"Results · semester {number} {kind}",
                f"grades:{key}",
                "/examination/api/check_result/",
                method="POST",
                json_body={"semester_no": number, "semester_type": kind},
            )

        if "attendance" not in errors:
            errors["attendance"] = (
                "The published Fusion frontend source does not expose a student attendance API route; "
                "attendance sync needs an official route or an authorized export."
            )
        return records, errors

    def close(self) -> None:
        self._token = None
        self.session.close()
