from app.engine.meeting import (
    extract_meeting_metadata,
    extract_meeting_table_records,
    is_valid_meeting_record,
)


def test_extract_meeting_metadata_from_detail_page() -> None:
    html = """
    <html>
      <body>
        <h1>第36届中国药学会医院药学学术年会</h1>
        <main>
          <p>会议时间：2026年10月23-25日。</p>
          <p>会议地点：广东省深圳市。</p>
          <p>主办方：中国药学会医院药学专业委员会</p>
          <p>报名截止：2026年10月10日18:00</p>
          <p>网站注册：
            <a href="https://meeting.example.com/register">大会官网</a>
          </p>
        </main>
      </body>
    </html>
    """

    metadata = extract_meeting_metadata(
        html,
        source_url="https://www.cpa.org.cn/?do=info&cid=1",
    )

    assert metadata == {
        "kind": "industry_meeting",
        "meeting_date": "2026年10月23-25日",
        "location": "广东省深圳市",
        "organizer": "中国药学会医院药学专业委员会",
        "registration_deadline": "2026年10月10日18:00",
        "registration_url": "https://meeting.example.com/register",
    }
    assert is_valid_meeting_record(
        "第36届中国药学会医院药学学术年会",
        metadata,
    )


def test_homepage_without_meeting_fields_is_not_a_meeting_record() -> None:
    metadata = extract_meeting_metadata(
        "<html><body><h1>中国药学会</h1><p>欢迎访问学会首页</p></body></html>",
        source_url="https://www.cpa.org.cn/",
    )

    assert metadata == {"kind": "industry_meeting"}
    assert not is_valid_meeting_record("中国药学会", metadata)


def test_hosting_notice_with_date_and_location_is_a_meeting_record() -> None:
    metadata = {
        "kind": "industry_meeting",
        "meeting_date": "2025年12月26日—28日",
        "location": "北京市",
    }

    assert is_valid_meeting_record(
        "关于举办第二十五届中国药师周的通知（第三轮）",
        metadata,
    )


def test_extract_meeting_metadata_rejects_login_and_detail_pages_as_registration_url() -> None:
    html = """
    <html>
      <body>
        <h1>2026 Clinical Innovation Meeting</h1>
        <p>会议时间：2026年11月5日</p>
        <p>会议地点：上海</p>
        <p>
          <a href="https://example.com/auth/login?redirect=%2Fregister">报名入口</a>
        </p>
        <p>
          <a href="https://example.com/news/detail?id=42">大会官网</a>
        </p>
      </body>
    </html>
    """

    metadata = extract_meeting_metadata(
        html,
        source_url="https://example.com/events/meeting-2026",
    )

    assert metadata == {
        "kind": "industry_meeting",
        "meeting_date": "2026年11月5日",
        "location": "上海",
    }


def test_extract_meeting_metadata_prefers_explicit_registration_link() -> None:
    html = """
    <html>
      <body>
        <h1>2026 Clinical Innovation Meeting</h1>
        <p>会议时间：2026年11月5日</p>
        <p>会议地点：上海</p>
        <p>
          <a href="https://example.com/news/detail?id=42">大会官网</a>
        </p>
        <p>
          <a href="https://event.example.com/register">立即报名</a>
        </p>
      </body>
    </html>
    """

    metadata = extract_meeting_metadata(
        html,
        source_url="https://example.com/events/meeting-2026",
    )

    assert metadata["registration_url"] == "https://event.example.com/register"


def test_extract_cphi_meeting_table_rows_as_individual_records() -> None:
    html = """
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
          <td rowspan="2">Biotech 生物科技</td>
          <td width="514">生物医药创新开发论坛</td>
          <td width="99"></td><td width="97">✓</td>
          <td width="99">✓</td><td width="99"></td>
          <td width="167">W4馆M6会议室</td><td width="131">中文</td>
        </tr>
        <tr>
          <td width="514">创新药出海研讨会</td>
          <td width="99"></td><td width="97"></td>
          <td width="99">✓</td><td width="99"></td>
          <td width="167">W3馆M10会议室</td><td width="131">中英文</td>
        </tr>
      </tbody>
    </table>
    """

    records = extract_meeting_table_records(
        html,
        source_url="https://www.cphi-china.cn/newconferences/list/",
        rules={
            "meeting_year": 2026,
            "organizer": "CPHI & PMEC China",
            "registration_url": "https://reg.cphi-china.cn/",
        },
    )

    assert len(records) == 2
    assert records[0].title == "生物医药创新开发论坛"
    assert records[0].meeting_date == "2026-06-16、2026-06-17"
    assert records[0].location == "W4馆M6会议室"
    assert records[0].organizer == "CPHI & PMEC China"
    assert records[0].registration_url == "https://reg.cphi-china.cn/"
    assert records[0].metadata["industry"] == "Biotech 生物科技"
    assert records[0].source_url.startswith(
        "https://www.cphi-china.cn/newconferences/list/#meeting-"
    )
    assert records[1].title == "创新药出海研讨会"
    assert records[1].meeting_date == "2026-06-17"
