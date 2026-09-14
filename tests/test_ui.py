def test_theme_bootstrap_validates_saved_preference_before_render(client):
    body = client.get("/").get_data(as_text=True)
    assert 'saved === "light" || saved === "dark"' in body
    assert "prefers-color-scheme: dark" in body
    assert body.index("jobtracker-theme") < body.index('rel="stylesheet"')


def test_theme_control_exposes_accessible_state_on_every_page(client):
    for path in ("/", "/applications", "/resumes", "/reminders", "/analytics"):
        body = client.get(path).get_data(as_text=True)
        assert "data-theme-toggle" in body
        assert 'aria-pressed="false"' in body
        assert 'aria-label="Switch to dark mode"' in body


def test_theme_script_persists_updates_and_syncs_navigation(client):
    script = client.get("/static/js/app.js").get_data(as_text=True)
    assert 'localStorage.setItem("jobtracker-theme", next)' in script
    assert 'window.addEventListener("storage"' in script
    assert 'toggle.setAttribute("aria-pressed", String(dark))' in script
    assert 'document.documentElement.dataset.theme = next' in script


def test_responsive_styles_cover_global_high_risk_components(client):
    css = client.get("/static/css/app.css").get_data(as_text=True)
    assert "@media (max-width: 720px)" in css
    assert "@media (max-width: 420px)" in css
    assert ".table-wrap { max-width: 100%" in css
    assert ".actions > .button" in css
    assert ".search-bar { align-items: stretch; flex-direction: column; }" in css
    assert ".analytics-columns" in css and ".dashboard-columns" in css
    assert "prefers-reduced-motion: reduce" in css


def test_dark_theme_defines_component_contrast_states(client):
    css = client.get("/static/css/app.css").get_data(as_text=True)
    for selector in (
        ':root[data-theme="dark"] .button-primary',
        ':root[data-theme="dark"] .button-danger',
        ':root[data-theme="dark"] .field-error',
        ':root[data-theme="dark"] .flash-success',
        ':root[data-theme="dark"] .reminder-overdue',
    ):
        assert selector in css
