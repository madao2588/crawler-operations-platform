import app.engine.pipeline as pipeline_mod


def test_meeting_without_explicit_registration_url_keeps_field_empty(monkeypatch) -> None:
    monkeypatch.setattr(
        pipeline_mod,
        "_extract_meeting_metadata",
        lambda _html, *, source_url: {
            "meeting_date": "2026-08-20",
            "location": "广州",
        },
    )

    metadata = pipeline_mod.extract_meeting_metadata(
        "<h1>2026生物医药创新大会</h1>",
        source_url="https://meeting.example/detail/1",
        rules={
            "metadata": {
                "kind": "industry_meeting",
                "source": "测试来源",
            }
        },
    )

    assert metadata is not None
    assert metadata["registration_url"] is None


def test_best_title_can_prefer_trusted_list_title() -> None:
    assert pipeline_mod._best_title(
        "李志坚",
        "关于开展2026年度科技项目申报工作的通知",
        prefer_fallback=True,
    ) == "关于开展2026年度科技项目申报工作的通知"


def test_unchanged_record_can_replace_bad_title_from_trusted_list() -> None:
    update = pipeline_mod._unchanged_metadata_update(
        "李志坚",
        "关于开展2026年度科技项目申报工作的通知",
        "旧摘要",
        "旧摘要",
        prefer_incoming_title=True,
    )

    assert update["title"] == "关于开展2026年度科技项目申报工作的通知"
