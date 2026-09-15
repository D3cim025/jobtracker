"""Standard-library smoke test for a running packaged JobTracker instance."""

from __future__ import annotations

import argparse
import http.cookiejar
import re
import urllib.parse
import urllib.request
from uuid import uuid4


EXPECTED_PAGES = ("/", "/applications", "/analytics", "/resumes", "/reminders")


def multipart(fields: dict[str, str], name: str, filename: str, content_type: str, data: bytes):
    boundary = f"JobTrackerSmoke{uuid4().hex}"
    chunks: list[bytes] = []
    for key, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode(),
                value.encode(),
                b"\r\n",
            ]
        )
    chunks.extend(
        [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            data,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


class SmokeClient:
    def __init__(self, base_url: str):
        cookies = http.cookiejar.CookieJar()
        self.base_url = base_url.rstrip("/")
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))

    def get(self, path: str) -> tuple[str, str]:
        with self.opener.open(f"{self.base_url}{path}", timeout=10) as response:
            assert response.status == 200, (path, response.status)
            return response.read().decode("utf-8"), response.geturl()

    def csrf(self, path: str) -> str:
        body, _ = self.get(path)
        match = re.search(r'name="csrf_token" value="([^"]+)"', body)
        assert match, f"No CSRF token on {path}"
        return match.group(1)

    def post(self, path: str, fields: dict[str, str]) -> tuple[str, str]:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=urllib.parse.urlencode(fields).encode(),
            method="POST",
        )
        with self.opener.open(request, timeout=10) as response:
            return response.read().decode("utf-8"), response.geturl()

    def upload(
        self,
        path: str,
        fields: dict[str, str],
        filename: str,
        content_type: str,
        data: bytes,
    ) -> tuple[str, str]:
        body, header = multipart(fields, "file", filename, content_type, data)
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": header},
            method="POST",
        )
        with self.opener.open(request, timeout=10) as response:
            return response.read().decode("utf-8"), response.geturl()


def check_pages(client: SmokeClient) -> None:
    for path in EXPECTED_PAGES:
        client.get(path)
    css, _ = client.get("/static/css/app.css")
    javascript, _ = client.get("/static/js/app.js")
    assert "--bg" in css
    assert "localStorage" in javascript and "theme" in javascript


def create_records(client: SmokeClient) -> None:
    create_path = "/applications/new"
    fields = {
        "csrf_token": client.csrf(create_path),
        "company_name": "Packaged Smoke Co",
        "position_title": "Offline Engineer",
        "job_type": "Full-time",
        "work_setup": "Remote",
        "status": "Saved",
        "priority": "Medium",
        "currency": "PHP",
    }
    body, location = client.post(create_path, fields)
    assert "Packaged Smoke Co" in body
    match = re.search(r"/applications/(\d+)$", urllib.parse.urlparse(location).path)
    assert match, location
    application_id = match.group(1)

    edit_path = f"/applications/{application_id}/edit"
    fields.update(
        csrf_token=client.csrf(edit_path),
        company_name="Packaged Smoke Co Edited",
    )
    body, _ = client.post(edit_path, fields)
    assert "Packaged Smoke Co Edited" in body

    resume_path = "/resumes/new"
    body, _ = client.upload(
        resume_path,
        {
            "csrf_token": client.csrf(resume_path),
            "display_name": "Packaged Resume",
            "target_role": "Offline Engineer",
            "description": "Persistence smoke test",
        },
        "packaged-resume.pdf",
        "application/pdf",
        b"%PDF-1.4\n% packaged smoke\n",
    )
    assert "Packaged Resume" in body

    document_path = f"/applications/{application_id}/documents/new"
    body, _ = client.upload(
        document_path,
        {
            "csrf_token": client.csrf(document_path),
            "document_type": "Other",
            "notes": "Persistence smoke test",
        },
        "packaged-note.txt",
        "text/plain",
        b"Packaged JobTracker persistence test.",
    )
    assert "packaged-note.txt" in body


def verify_records(client: SmokeClient) -> None:
    applications, _ = client.get("/applications")
    resumes, _ = client.get("/resumes")
    assert "Packaged Smoke Co Edited" in applications
    assert "Packaged Resume" in resumes
    application = re.search(r'href="(/applications/\d+)">Packaged Smoke Co Edited', applications)
    assert application
    detail, _ = client.get(application.group(1))
    assert "packaged-note.txt" in detail


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("create", "verify"))
    parser.add_argument("--url", default="http://127.0.0.1:5000")
    args = parser.parse_args()

    client = SmokeClient(args.url)
    check_pages(client)
    if args.mode == "create":
        create_records(client)
    verify_records(client)
    print(f"Packaged smoke test ({args.mode}) passed.")


if __name__ == "__main__":
    main()
