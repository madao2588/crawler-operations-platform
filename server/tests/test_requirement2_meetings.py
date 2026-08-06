import json
import sys
from importlib import util
from pathlib import Path

import pytest
from sqlalchemy import select

from app.engine import pipeline as pipeline_mod
from app.engine.parser import looks_like_anti_bot_challenge
from app.models.data import CollectedData
from app.models.task import Task
from app.repositories.data_repo import DataRepository
from app.repositories.log_repo import LogRepository
from app.schemas.task import TaskStatus
from app.services.template_service import NEW_DRUG_SOURCE_TEMPLATES


CPA_DETAIL_HTML = """
<html>
  <head>
    <meta name="ArticleTitle" content="关于召开2026年中国药学会中药资源专业委员会学术年会的通知（第二轮）" />
    <meta name="PubDate" content="2026-07-16 17:49:16" />
  </head>
  <body>
    <div id="clist">
      <div id="ctis">来源：原创 发布时间：2026-07-16</div>
      <div id="cpabody">
        <p>各有关单位、各位专家：</p>
        <p>由中国药学会中药资源专业委员会主办的“2026年中国药学会中药资源专业委员会学术年会”定于2026年7月18日-21日在甘肃兰州召开。</p>
        <p><strong>三、时间、地点</strong></p>
        <p>1、时间：2026年7月18日-21日，7月18日全天报到，7月19日-20日大会报告及分论坛报告，7月21日离会。</p>
        <p>2、地点：甘肃省兰州市，兰州奥体如意华玺酒店（兰州市七里河区大滩中路13号）。</p>
        <p><strong>四、会议收费</strong></p>
        <p>1、报名会议注册费缴费标准：1500元/人。</p>
      </div>
    </div>
  </body>
</html>
"""


BIOON_DETAIL_HTML = """
<html>
  <body>
    <div class="address-time fr">
      <span>2026-07-24至2026-07-25</span>
      上海南翔温德姆酒店
    </div>
    <div class="banner-text efft-text banner_font_white">
      <h1>2026（第十届）细胞外囊泡（EVs）合规与 临床应用大会</h1>
      <p>本次论坛聚焦“合规转型+临床转化”，汇聚上海及江浙沪顶尖资源，推动行业从“概念炒作”走向“规范发展”，助力合规企业抢占临床应用先机。将于7月24-25日在上海召开！</p>
      <p><a href="https://meeting.bioon.com/2026evs/reg-without-login" class="enroll-btn signup_btn">报名参会</a></p>
    </div>
    <div class="message-warp">
      <div class="message-top">
        <p><span class="icon2"></span>E-mail: wenyi.jiang@medsci.cn</p>
        <p><span class="icon4"></span>MP: 17321098232</p>
      </div>
    </div>
  </body>
</html>
"""

CPHI_TABLE_HTML = """
<table>
  <thead>
    <tr>
      <th>行业</th><th>会议活动名称</th>
      <th>6/15</th><th>6/16</th><th>6/17</th><th>6/18</th>
      <th>地点</th><th>语言</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>Biotech 生物科技</td>
      <td width="514">生物医药创新开发论坛</td>
      <td width="99"></td><td width="97">✓</td>
      <td width="99">✓</td><td width="99"></td>
      <td width="167">W4馆M6会议室</td><td width="131">中文</td>
    </tr>
  </tbody>
</table>
"""


def _template_rules(template_id: str) -> dict[str, object]:
    template = next(item for item in NEW_DRUG_SOURCE_TEMPLATES if item["id"] == template_id)
    rules = json.loads(template["parser_rules"])
    assert isinstance(rules, dict)
    return rules


def _load_requirement2_script():
    script_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "check_requirement2_meetings.py"
    )
    module_name = "tests_check_requirement2_meetings_script"
    sys.modules.pop(module_name, None)
    spec = util.spec_from_file_location(module_name, script_path)
    assert spec is not None and spec.loader is not None
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_extract_meeting_metadata_from_cpa_contract() -> None:
    metadata = pipeline_mod.extract_meeting_metadata(
        CPA_DETAIL_HTML,
        source_url="https://www.cpa.org.cn/?do=info&cid=78903",
        rules=_template_rules("cpa_association"),
        fallback_title=None,
    )

    assert metadata is not None
    assert metadata["kind"] == "industry_meeting"
    assert metadata["meeting_name"] == "关于召开2026年中国药学会中药资源专业委员会学术年会的通知（第二轮）"
    assert metadata["start_date"] == "2026-07-18"
    assert metadata["end_date"] == "2026-07-21"
    assert metadata["location"] == "甘肃省兰州市，兰州奥体如意华玺酒店（兰州市七里河区大滩中路13号）"
    assert metadata["organizer"] == "中国药学会中药资源专业委员会"
    assert metadata["registration_url"] is None
    assert metadata["deadline"] is None


def test_extract_meeting_metadata_from_bioon_contract() -> None:
    rules = _template_rules("bioon_meetings")
    assert not looks_like_anti_bot_challenge(BIOON_DETAIL_HTML, rules)

    metadata = pipeline_mod.extract_meeting_metadata(
        BIOON_DETAIL_HTML,
        source_url="https://meeting.bioon.com/2026evs",
        rules=rules,
        fallback_title=None,
    )

    assert metadata is not None
    assert metadata["kind"] == "industry_meeting"
    assert metadata["meeting_name"] == "2026（第十届）细胞外囊泡（EVs）合规与 临床应用大会"
    assert metadata["start_date"] == "2026-07-24"
    assert metadata["end_date"] == "2026-07-25"
    assert metadata["location"] == "上海南翔温德姆酒店"
    assert metadata["registration_url"] == "https://meeting.bioon.com/2026evs/reg-without-login"
    assert metadata["organizer"] is None
    assert metadata["deadline"] is None


@pytest.mark.asyncio
async def test_collect_and_store_one_persists_meeting_metadata(async_session, monkeypatch) -> None:
    async_session.add(
        Task(
            name="CPA Meeting",
            start_url="https://www.cpa.org.cn/?classid=270&do=infolist",
            cron_expr="0 9,15 * * *",
            status=int(TaskStatus.ENABLED),
        )
    )
    await async_session.flush()
    task_id = (await async_session.execute(select(Task.id))).scalar_one()
    page_url = "https://www.cpa.org.cn/?do=info&cid=78903"

    async def fake_download(**_kwargs) -> str:
        return CPA_DETAIL_HTML

    async def fake_parse(_html: str, **_kwargs) -> dict[str, str | None]:
        return {
            "title": "关于召开2026年中国药学会中药资源专业委员会学术年会的通知（第二轮）",
            "published_at": "2026-07-16 17:49:16",
            "content_html": (
                "<div id='cpabody'>"
                "<p>由中国药学会中药资源专业委员会主办的“2026年中国药学会中药资源专业委员会学术年会”"
                "定于2026年7月18日-21日在甘肃兰州召开。</p>"
                "<p>1、报名会议注册费缴费标准：1500元/人。</p>"
                "</div>"
            ),
        }

    monkeypatch.setattr(pipeline_mod, "_download_page", fake_download)
    monkeypatch.setattr(pipeline_mod, "_parse_page", fake_parse)
    monkeypatch.setattr(pipeline_mod, "save_snapshot", lambda **kwargs: "snap/meeting.html")

    result = await pipeline_mod._collect_and_store_one(
        task_id=task_id,
        run_id="meeting-run",
        page_url=page_url,
        parser_rules=json.dumps(_template_rules("cpa_association"), ensure_ascii=False),
        log_repo=LogRepository(async_session),
        data_repo=DataRepository(async_session),
        crawl_rules=_template_rules("cpa_association"),
    )

    assert result == "stored"
    row = (await async_session.execute(select(CollectedData))).scalar_one()
    assert row.category == "行业会议"
    metadata = json.loads(row.metadata_json or "{}")
    assert metadata["kind"] == "industry_meeting"
    assert metadata["meeting_name"] == "关于召开2026年中国药学会中药资源专业委员会学术年会的通知（第二轮）"
    assert metadata["start_date"] == "2026-07-18"
    assert metadata["end_date"] == "2026-07-21"
    assert metadata["location"] == "甘肃省兰州市，兰州奥体如意华玺酒店（兰州市七里河区大滩中路13号）"
    assert "2026-07-18 至 2026-07-21" in (row.content_text or "")
    assert "甘肃省兰州市，兰州奥体如意华玺酒店" in (row.content_text or "")


@pytest.mark.asyncio
async def test_collect_meeting_table_stores_each_schedule_row(async_session, monkeypatch) -> None:
    async_session.add(
        Task(
            name="CPHI Meeting",
            start_url="https://www.cphi-china.cn/newconferences/list/",
            cron_expr="50 9,15 * * *",
            status=int(TaskStatus.ENABLED),
        )
    )
    await async_session.flush()
    task_id = (await async_session.execute(select(Task.id))).scalar_one()

    async def fake_download(**_kwargs) -> str:
        return CPHI_TABLE_HTML

    monkeypatch.setattr(pipeline_mod, "_download_page", fake_download)
    monkeypatch.setattr(pipeline_mod, "save_snapshot", lambda **kwargs: "snap/cphi.html")
    metrics = await pipeline_mod._collect_meeting_table(
        task_id=task_id,
        run_id="meeting-table-run",
        start_url="https://www.cphi-china.cn/newconferences/list/",
        rules=_template_rules("cphi_china_events"),
        log_repo=LogRepository(async_session),
        data_repo=DataRepository(async_session),
    )

    assert metrics == {
        "discovered": 1,
        "stored": 1,
        "skipped_hash": 0,
        "failed": 0,
    }
    row = (await async_session.execute(select(CollectedData))).scalar_one()
    assert row.title == "生物医药创新开发论坛"
    assert row.category == "行业会议"
    assert row.source_url.startswith(
        "https://www.cphi-china.cn/newconferences/list/#meeting-"
    )
    metadata = json.loads(row.metadata_json or "{}")
    assert metadata["meeting_date"] == "2026-06-16、2026-06-17"
    assert metadata["location"] == "W4馆M6会议室"
    assert metadata["industry"] == "Biotech 生物科技"


@pytest.mark.asyncio
async def test_requirement2_probe_marks_detail_page_registration_url_as_partial(
    monkeypatch,
) -> None:
    script = _load_requirement2_script()

    async def fake_fetch(url: str, rules: dict[str, object]) -> str:
        _ = rules
        if "detail" in url:
            return "<html><body>detail</body></html>"
        return "<html><body>list</body></html>"

    monkeypatch.setattr(script, "_fetch", fake_fetch)
    monkeypatch.setattr(
        script,
        "extract_list_follow_items",
        lambda *args, **kwargs: [
            {
                "title": "关于召开2026年中国药学会中药资源专业委员会学术年会的通知（第二轮）",
                "url": "https://www.cpa.org.cn/news/detail?id=42",
            }
        ],
    )
    monkeypatch.setattr(
        script,
        "extract_meeting_metadata",
        lambda *args, **kwargs: {
            "kind": "industry_meeting",
            "meeting_name": "关于召开2026年中国药学会中药资源专业委员会学术年会的通知（第二轮）",
            "start_date": "2026-07-18",
            "end_date": "2026-07-21",
            "location": "甘肃兰州",
            "registration_url": "https://www.cpa.org.cn/news/detail?id=42",
        },
    )

    result = await script._probe_list_follow(
        {
            "id": "cpa_association",
            "label": "CPA",
            "enabled": True,
            "start_url": "https://www.cpa.org.cn/?classid=270&do=infolist",
            "parser_rules": json.dumps(_template_rules("cpa_association"), ensure_ascii=False),
        },
        expected_status="ok",
    )

    assert result["status"] == "partial"
    assert result["error"] == "invalid registration_url: https://www.cpa.org.cn/news/detail?id=42"


def test_requirement2_main_reports_status_counts(capsys, monkeypatch) -> None:
    script = _load_requirement2_script()

    async def fake_run() -> list[dict[str, object]]:
        return [
            {"source_id": "cpa_association", "status": "partial"},
            {"source_id": "cphi_china_events", "status": "ok"},
            {"source_id": "dxy_pharmacy_meetings", "status": "stale"},
            {"source_id": "bioon_meetings", "status": "intermittent"},
        ]

    monkeypatch.setattr(script, "_run", fake_run)

    exit_code = script.main()

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["overall"] == "partial"
    assert payload["counts"] == {
        "ok": 1,
        "intermittent": 1,
        "stale": 1,
        "partial": 1,
    }


def test_requirement2_expected_source_constraints_are_not_reported_as_failure(
    capsys,
    monkeypatch,
) -> None:
    script = _load_requirement2_script()

    async def fake_run() -> list[dict[str, object]]:
        return [
            {"source_id": "cpa_association", "status": "ok"},
            {"source_id": "cphi_china_events", "status": "ok"},
            {"source_id": "dxy_pharmacy_meetings", "status": "stale"},
            {"source_id": "bioon_meetings", "status": "intermittent"},
        ]

    monkeypatch.setattr(script, "_run", fake_run)

    exit_code = script.main()

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["overall"] == "operational_with_constraints"
