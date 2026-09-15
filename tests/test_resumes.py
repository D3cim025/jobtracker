from hashlib import sha256
from io import BytesIO
from pathlib import Path

from app import create_app, db
from app.models import Application, Resume


PDF_BYTES = b"%PDF-1.4\n% local test resume\n"


def resume_form(**overrides):
    data = {
        "display_name": "Software Engineer Resume",
        "version_name": "v1",
        "target_role": "Software Engineering",
        "description": "Backend-focused resume",
        "file": (BytesIO(PDF_BYTES), "Rafael Resume.pdf", "application/pdf"),
    }
    data.update(overrides)
    return data


def add_resume(upload_root: Path, **overrides):
    values = {
        "display_name": "Software Engineer Resume",
        "version_name": "v1",
        "target_role": "Software Engineering",
        "description": "Backend-focused resume",
        "original_file_name": "Rafael Resume.pdf",
        "stored_file_name": "a" * 32 + ".pdf",
        "file_hash": sha256(PDF_BYTES).hexdigest(),
    }
    values.update(overrides)
    resume = Resume(**values)
    db.session.add(resume)
    db.session.commit()
    resume_dir = upload_root / "resumes"
    resume_dir.mkdir(parents=True, exist_ok=True)
    (resume_dir / resume.stored_file_name).write_bytes(PDF_BYTES)
    return resume


def test_resume_library_has_useful_empty_state(client):
    response = client.get("/resumes")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "No resumes found" in body
    assert "/resumes/new" in body


def test_upload_creates_hashed_version_with_generated_storage_name(app, client, tmp_path):
    response = client.post("/resumes/new", data=resume_form(), follow_redirects=False)
    assert response.status_code == 302
    with app.app_context():
        resume = db.session.scalar(db.select(Resume))
        assert resume.display_name == "Software Engineer Resume"
        assert resume.version_name == "v1"
        assert resume.original_file_name == "Rafael Resume.pdf"
        assert resume.stored_file_name != resume.original_file_name
        assert resume.stored_file_name.endswith(".pdf")
        assert len(Path(resume.stored_file_name).stem) == 32
        assert resume.file_hash == sha256(PDF_BYTES).hexdigest()
        assert (tmp_path / "uploads" / "resumes" / resume.stored_file_name).read_bytes() == PDF_BYTES


def test_resume_version_is_hidden_and_generated_internally(app, client):
    upload_page = client.get("/resumes/new").get_data(as_text=True)
    assert 'name="version_name"' not in upload_page
    assert ">Version<" not in upload_page

    response = client.post(
        "/resumes/new",
        data={
            "display_name": "General Resume",
            "target_role": "Engineering",
            "description": "Primary resume",
            "file": (BytesIO(PDF_BYTES), "resume.pdf", "application/pdf"),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        resume = db.session.scalar(db.select(Resume))
        assert resume.version_name.startswith("resume-")
        internal_identifier = resume.version_name
        resume_id = resume.id

    detail = response.get_data(as_text=True)
    library = client.get("/resumes").get_data(as_text=True)
    edit_page = client.get(f"/resumes/{resume_id}/edit").get_data(as_text=True)
    assert internal_identifier not in detail
    assert internal_identifier not in library
    assert 'name="version_name"' not in edit_page

    edit_response = client.post(
        f"/resumes/{resume_id}/edit",
        data={
            "display_name": "Updated Resume",
            "target_role": "Platform Engineering",
            "description": "Updated details",
        },
    )
    assert edit_response.status_code == 302
    with app.app_context():
        assert db.session.get(Resume, resume_id).version_name == internal_identifier


def test_upload_requires_metadata_and_file(app, client):
    response = client.post(
        "/resumes/new",
        data={"display_name": "", "version_name": "", "target_role": "Data"},
    )
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Display Name is required" in body
    assert 'name="version_name"' not in body
    assert "Choose a resume file" in body
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Resume.id))) == 0


def test_upload_rejects_unsupported_extension(app, client):
    response = client.post(
        "/resumes/new",
        data=resume_form(file=(BytesIO(b"malware"), "resume.exe", "application/octet-stream")),
    )
    assert "PDF, DOC, DOCX, ODT, or TXT" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Resume.id))) == 0


def test_upload_rejects_extension_content_mismatch(app, client):
    response = client.post(
        "/resumes/new",
        data=resume_form(file=(BytesIO(b"not a PDF"), "resume.pdf", "application/pdf")),
    )
    assert "contents do not match" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Resume.id))) == 0


def test_upload_rejects_unsafe_original_filename(app, client):
    response = client.post(
        "/resumes/new",
        data=resume_form(file=(BytesIO(PDF_BYTES), "../resume.pdf", "application/pdf")),
    )
    assert "file name is unsafe" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Resume.id))) == 0


def test_upload_rejects_unexpected_mime_type(app, client):
    response = client.post(
        "/resumes/new",
        data=resume_form(file=(BytesIO(PDF_BYTES), "resume.pdf", "text/html")),
    )
    assert "does not match an allowed" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Resume.id))) == 0


def test_resume_versions_coexist_and_first_file_is_unchanged(app, client, tmp_path):
    first_response = client.post("/resumes/new", data=resume_form())
    second_bytes = b"%PDF-1.4\n% version two\n"
    second_response = client.post(
        "/resumes/new",
        data=resume_form(
            version_name="v2",
            file=(BytesIO(second_bytes), "Rafael Resume v2.pdf", "application/pdf"),
        ),
    )
    assert first_response.status_code == 302
    assert second_response.status_code == 302
    with app.app_context():
        resumes = list(db.session.scalars(db.select(Resume).order_by(Resume.id)))
        assert len(resumes) == 2
        assert resumes[0].stored_file_name != resumes[1].stored_file_name
        root = tmp_path / "uploads" / "resumes"
        assert (root / resumes[0].stored_file_name).read_bytes() == PDF_BYTES
        assert (root / resumes[1].stored_file_name).read_bytes() == second_bytes


def test_uploading_new_version_does_not_replace_application_resume(app, client, tmp_path):
    with app.app_context():
        first = add_resume(tmp_path / "uploads")
        first_id = first.id
        application = Application(
            company_name="Historical Co",
            position_title="Software Engineer",
            resume=first,
        )
        db.session.add(application)
        db.session.commit()
        application_id = application.id

    response = client.post(
        "/resumes/new",
        data=resume_form(
            version_name="v2",
            file=(BytesIO(b"%PDF-1.4\n% newer version\n"), "Resume v2.pdf", "application/pdf"),
        ),
    )
    assert response.status_code == 302
    with app.app_context():
        application = db.session.get(Application, application_id)
        assert application.resume_id == first_id
        assert application.resume.version_name == "v1"
        assert db.session.scalar(db.select(db.func.count(Resume.id))) == 2


def test_resume_detail_and_search_show_metadata(app, client, tmp_path):
    with app.app_context():
        resume_id = add_resume(tmp_path / "uploads").id
    detail = client.get(f"/resumes/{resume_id}").get_data(as_text=True)
    assert "Software Engineer Resume" in detail
    assert "Software Engineering" in detail
    assert sha256(PDF_BYTES).hexdigest() in detail
    results = client.get("/resumes", query_string={"q": "backend-focused"}).get_data(as_text=True)
    assert "Software Engineer Resume" in results
    empty = client.get("/resumes", query_string={"q": "accounting"}).get_data(as_text=True)
    assert "Software Engineer Resume" not in empty


def test_open_and_download_serve_only_database_backed_file(app, client, tmp_path):
    with app.app_context():
        resume_id = add_resume(tmp_path / "uploads").id
    opened = client.get(f"/resumes/{resume_id}/open")
    downloaded = client.get(f"/resumes/{resume_id}/download")
    assert opened.status_code == 200
    assert opened.data == PDF_BYTES
    assert "attachment" not in opened.headers["Content-Disposition"]
    assert downloaded.status_code == 200
    assert downloaded.data == PDF_BYTES
    assert "attachment" in downloaded.headers["Content-Disposition"]
    assert "Rafael Resume.pdf" in downloaded.headers["Content-Disposition"]
    assert client.get("/resumes/9999/download").status_code == 404


def test_missing_local_file_returns_to_detail_with_error(app, client, tmp_path):
    with app.app_context():
        resume = add_resume(tmp_path / "uploads")
        resume_id = resume.id
        (tmp_path / "uploads" / "resumes" / resume.stored_file_name).unlink()
    response = client.get(f"/resumes/{resume_id}/open", follow_redirects=True)
    assert response.status_code == 200
    assert "file is missing from local storage" in response.get_data(as_text=True)


def test_edit_changes_metadata_but_not_file_identity(app, client, tmp_path):
    with app.app_context():
        resume = add_resume(tmp_path / "uploads")
        resume_id = resume.id
        stored_name = resume.stored_file_name
        digest = resume.file_hash
    response = client.post(
        f"/resumes/{resume_id}/edit",
        data={
            "display_name": "Platform Resume",
            "version_name": "v1.1",
            "target_role": "Platform Engineering",
            "description": "Updated metadata",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        resume = db.session.get(Resume, resume_id)
        assert resume.display_name == "Platform Resume"
        assert resume.stored_file_name == stored_name
        assert resume.file_hash == digest
        assert (tmp_path / "uploads" / "resumes" / stored_name).read_bytes() == PDF_BYTES


def test_application_can_select_resume_and_usage_history_is_bidirectional(app, client, tmp_path):
    with app.app_context():
        resume_id = add_resume(tmp_path / "uploads").id
    from tests.test_applications import valid_form

    response = client.post("/applications/new", data=valid_form(resume_id=str(resume_id)))
    assert response.status_code == 302
    with app.app_context():
        application = db.session.scalar(db.select(Application))
        application_id = application.id
        assert application.resume_id == resume_id
    resume_page = client.get(f"/resumes/{resume_id}").get_data(as_text=True)
    application_page = client.get(f"/applications/{application_id}").get_data(as_text=True)
    assert "Acme Labs" in resume_page
    assert "Backend Developer" in resume_page
    assert "Software Engineer Resume" in application_page
    assert f"/resumes/{resume_id}/download" in application_page


def test_application_rejects_nonexistent_resume(app, client):
    from tests.test_applications import valid_form

    response = client.post("/applications/new", data=valid_form(resume_id="9999"))
    assert "selected resume no longer exists" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Application.id))) == 0


def test_delete_unreferenced_resume_removes_record_and_file(app, client, tmp_path):
    with app.app_context():
        resume = add_resume(tmp_path / "uploads")
        resume_id = resume.id
        path = tmp_path / "uploads" / "resumes" / resume.stored_file_name
    assert client.get(f"/resumes/{resume_id}/delete").status_code == 405
    response = client.post(f"/resumes/{resume_id}/delete", follow_redirects=True)
    assert "Resume deleted" in response.get_data(as_text=True)
    assert not path.exists()
    with app.app_context():
        assert db.session.get(Resume, resume_id) is None


def test_delete_referenced_resume_is_blocked_and_preserves_history(app, client, tmp_path):
    with app.app_context():
        resume = add_resume(tmp_path / "uploads")
        resume_id = resume.id
        stored_name = resume.stored_file_name
        db.session.add(Application(company_name="History Co", position_title="Engineer", resume=resume))
        db.session.commit()
    response = client.post(f"/resumes/{resume_id}/delete", follow_redirects=True)
    body = response.get_data(as_text=True)
    assert "used by an application and cannot be deleted" in body
    with app.app_context():
        assert db.session.get(Resume, resume_id) is not None
        assert (tmp_path / "uploads" / "resumes" / stored_name).exists()


def test_stored_path_traversal_is_rejected(app, client, tmp_path):
    outside = tmp_path / "private.pdf"
    outside.write_bytes(PDF_BYTES)
    with app.app_context():
        resume = Resume(
            display_name="Tampered",
            version_name="v1",
            original_file_name="private.pdf",
            stored_file_name="..\\..\\private.pdf",
        )
        db.session.add(resume)
        db.session.commit()
        resume_id = resume.id
    response = client.get(f"/resumes/{resume_id}/open", follow_redirects=True)
    assert response.status_code == 200
    assert "stored resume path is invalid" in response.get_data(as_text=True)
    assert outside.read_bytes() == PDF_BYTES


def test_resume_upload_requires_csrf_when_enabled(tmp_path):
    protected_app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "csrf-test-secret",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'csrf.db').as_posix()}",
            "UPLOAD_ROOT": str(tmp_path / "uploads"),
        }
    )
    response = protected_app.test_client().post("/resumes/new", data=resume_form())
    assert response.status_code == 400
