from pathlib import Path


def test_primary_navigation_marks_the_current_section(client):
    cases = {
        "/": "Dashboard",
        "/applications": "Applications",
        "/resumes": "Resume Library",
        "/reminders": "Reminders",
        "/analytics": "Analytics",
    }
    for path, label in cases.items():
        body = client.get(path).get_data(as_text=True)
        assert f'aria-current="page">{label}</a>' in body
        assert body.count('aria-current="page"') == 1


def test_reminder_empty_states_explain_meaning_and_next_step(client):
    body = client.get("/reminders").get_data(as_text=True)
    assert "You are all caught up" in body
    assert "Open an application to schedule one" in body
    assert "Completed reminders will stay visible here" in body


def test_readme_describes_only_implemented_local_product():
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "local-first job application management system" in readme
    assert "Immutable Resume Library versions" in readme
    assert "python.exe -m flask --app run.py init-db" in readme
    assert "instance/.secret_key" in readme
    assert "No backup, restore, export, LAN, PWA" in readme
    assert "iPhone access on trusted Wi-Fi" not in readme
    assert "remaining workflows will be added" not in readme
