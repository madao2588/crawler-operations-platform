from datetime import datetime, timezone
from urllib.parse import parse_qs

import httpx
import pytest

from app.engine.pubmed import (
    PubMedClient,
    _extract_targets,
    infer_development_stage,
    infer_development_stage_details,
    infer_evidence_level,
    parse_pubmed_xml,
)


PUBMED_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID Version="1">12345678</PMID>
      <Article>
        <Journal>
          <JournalIssue>
            <PubDate>
              <Year>2026</Year>
              <Month>Jul</Month>
              <Day>20</Day>
            </PubDate>
          </JournalIssue>
          <Title>Journal of Translational Medicine</Title>
        </Journal>
        <ArticleTitle>Targeted <i>therapy</i> for recurrent glioblastoma</ArticleTitle>
        <Abstract>
          <AbstractText Label="BACKGROUND">Existing treatment options are limited.</AbstractText>
          <AbstractText Label="RESULTS">A phase 2 clinical trial showed a response.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author>
            <LastName>Zhang</LastName>
            <ForeName>Wei</ForeName>
            <AffiliationInfo>
              <Affiliation>Department of Oncology, Example University.</Affiliation>
            </AffiliationInfo>
          </Author>
        </AuthorList>
        <PublicationTypeList>
          <PublicationType UI="D017427">Clinical Trial, Phase II</PublicationType>
          <PublicationType UI="D016428">Journal Article</PublicationType>
        </PublicationTypeList>
      </Article>
      <ChemicalList>
        <Chemical>
          <NameOfSubstance UI="D000001">Examplemab</NameOfSubstance>
        </Chemical>
      </ChemicalList>
      <KeywordList>
        <Keyword MajorTopicYN="Y">glioblastoma</Keyword>
        <Keyword MajorTopicYN="N">targeted therapy</Keyword>
      </KeywordList>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="pubmed">12345678</ArticleId>
        <ArticleId IdType="doi">10.1000/example.2026.1</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>
"""


ENRICHED_PUBMED_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID Version="1">87654321</PMID>
      <Article>
        <Journal>
          <JournalIssue>
            <PubDate>
              <Year>2026</Year>
              <Month>Jun</Month>
              <Day>10</Day>
            </PubDate>
          </JournalIssue>
          <Title>Clinical Cancer Research</Title>
        </Journal>
        <ArticleTitle>Phase III evaluation of EX-101 in recurrent glioblastoma with EGFR alterations</ArticleTitle>
        <Abstract>
          <AbstractText>Example Therapeutics reported that the NCT01234567 study is recruiting participants in the United States and Canada.</AbstractText>
          <AbstractText Label="RESULTS">The EGFR inhibitor EX-101 demonstrated promising activity.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author>
            <LastName>Doe</LastName>
            <ForeName>Jane</ForeName>
            <AffiliationInfo>
              <Affiliation>Translational Medicine, Example Therapeutics, Boston, MA, United States.</Affiliation>
            </AffiliationInfo>
          </Author>
        </AuthorList>
        <PublicationTypeList>
          <PublicationType UI="D016428">Journal Article</PublicationType>
        </PublicationTypeList>
      </Article>
      <ChemicalList>
        <Chemical>
          <NameOfSubstance UI="D000001">Examplemab</NameOfSubstance>
        </Chemical>
      </ChemicalList>
      <MeshHeadingList>
        <MeshHeading>
          <DescriptorName UI="D005909">Glioblastoma</DescriptorName>
        </MeshHeading>
        <MeshHeading>
          <DescriptorName UI="D000080884">Clinical Trials, Phase III as Topic</DescriptorName>
        </MeshHeading>
      </MeshHeadingList>
      <KeywordList>
        <Keyword MajorTopicYN="Y">glioblastoma</Keyword>
        <Keyword MajorTopicYN="N">EGFR inhibitor</Keyword>
      </KeywordList>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="pubmed">87654321</ArticleId>
        <ArticleId IdType="doi">10.1000/example.2026.2</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>
"""


def test_parse_pubmed_xml_extracts_competitor_intelligence_fields() -> None:
    articles = parse_pubmed_xml(PUBMED_XML, topic="脑胶质瘤")

    assert len(articles) == 1
    article = articles[0]
    assert article.pmid == "12345678"
    assert article.topic == "脑胶质瘤"
    assert article.title == "Targeted therapy for recurrent glioblastoma"
    assert article.doi == "10.1000/example.2026.1"
    assert article.journal == "Journal of Translational Medicine"
    assert article.published_at == datetime(2026, 7, 20, tzinfo=timezone.utc)
    assert article.authors == ["Wei Zhang"]
    assert article.organizations == ["Department of Oncology, Example University."]
    assert article.drugs == ["Examplemab"]
    assert article.keywords == ["glioblastoma", "targeted therapy"]
    assert article.publication_types == ["Clinical Trial, Phase II", "Journal Article"]
    assert article.development_stage == "临床Ⅱ期"
    assert article.evidence_level == "临床试验证据"
    assert "BACKGROUND: Existing treatment options are limited." in article.abstract
    assert "RESULTS: A phase 2 clinical trial showed a response." in article.abstract


def test_parse_pubmed_xml_extracts_enriched_requirement3_fields() -> None:
    articles = parse_pubmed_xml(ENRICHED_PUBMED_XML, topic="脑胶质瘤")

    assert len(articles) == 1
    article = articles[0]
    assert article.mesh_terms == [
        "Glioblastoma",
        "Clinical Trials, Phase III as Topic",
    ]
    assert article.drugs == ["Examplemab", "EX-101"]
    assert article.targets == ["EGFR"]
    assert article.sponsor_hints == ["Example Therapeutics"]
    assert article.trial_ids == ["NCT01234567"]
    assert article.trial_status == "recruiting"
    assert article.countries == ["United States", "Canada"]
    assert article.development_stage == "临床Ⅲ期"
    assert article.development_stage_confidence == "high"
    assert "Phase III evaluation of EX-101" in article.development_stage_evidence


def test_target_extraction_does_not_treat_kidney_egfr_as_egfr_target() -> None:
    assert _extract_targets(
        "Treat-to-target urate management in CKD",
        "The estimated glomerular filtration rate (eGFR) was monitored.",
        ["kidney outcomes"],
        [],
    ) == []
    assert _extract_targets(
        "EGFR inhibitor in glioblastoma",
        "Epidermal growth factor receptor was altered.",
        [],
        [],
    ) == ["EGFR"]


@pytest.mark.parametrize(
    ("publication_types", "abstract", "expected_stage", "expected_evidence"),
    [
        (
            ["Clinical Trial, Phase I"],
            "Dose escalation study in recurrent glioma.",
            "临床Ⅰ期",
            "临床试验证据",
        ),
        (
            ["Clinical Trial, Phase I/II"],
            "Open-label phase Ib/II study in advanced solid tumors.",
            "临床Ⅱ期",
            "临床试验证据",
        ),
        (
            ["Clinical Trial, Phase III"],
            "Randomized phase III study met the primary endpoint.",
            "临床Ⅲ期",
            "临床试验证据",
        ),
        (
            ["Journal Article"],
            "Antitumor activity was validated in patient-derived xenograft and mouse models.",
            "临床前研究",
            "临床前证据",
        ),
        (
            ["Journal Article"],
            "Mechanistic observations were reported without a stated development phase.",
            "研究阶段未明确",
            "探索性研究证据",
        ),
    ],
)
def test_infer_development_stage_covers_requirement3_regression_cases(
    publication_types: list[str],
    abstract: str,
    expected_stage: str,
    expected_evidence: str,
) -> None:
    stage = infer_development_stage(
        publication_types=publication_types,
        abstract=abstract,
    )

    assert stage == expected_stage
    assert (
        infer_evidence_level(
            publication_types=publication_types,
            development_stage=stage,
        )
        == expected_evidence
    )


def test_infer_development_stage_uses_title_keywords_and_mesh_terms() -> None:
    assessment = infer_development_stage_details(
        title="Phase III evaluation of EX-101 in recurrent glioblastoma",
        abstract="Mechanistic biomarkers were also assessed.",
        publication_types=["Journal Article"],
        keywords=["glioblastoma", "EGFR inhibitor"],
        mesh_terms=["Clinical Trials, Phase III as Topic"],
    )

    assert assessment.stage == "临床Ⅲ期"
    assert assessment.confidence == "high"
    assert "Phase III evaluation of EX-101" in assessment.evidence_snippet
    assert (
        infer_development_stage(
            title="Exploratory biomarker analysis",
            abstract="Open-label expansion cohort.",
            publication_types=["Journal Article"],
            keywords=["phase II study"],
            mesh_terms=[],
        )
        == "临床Ⅱ期"
    )


@pytest.mark.asyncio
async def test_pubmed_client_uses_official_esearch_and_efetch_endpoints() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/esearch.fcgi"):
            query = parse_qs(request.url.query.decode())
            assert query["db"] == ["pubmed"]
            assert query["term"] == ["glioma AND clinical trial"]
            assert query["retmax"] == ["25"]
            assert query["sort"] == ["pub date"]
            assert query["datetype"] == ["pdat"]
            assert query["reldate"] == ["730"]
            return httpx.Response(
                200,
                json={"esearchresult": {"count": "1", "idlist": ["12345678"]}},
            )
        if request.url.path.endswith("/efetch.fcgi"):
            query = parse_qs(request.url.query.decode())
            assert query["db"] == ["pubmed"]
            assert query["id"] == ["12345678"]
            assert query["retmode"] == ["xml"]
            return httpx.Response(200, text=PUBMED_XML)
        raise AssertionError(f"Unexpected request: {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = PubMedClient(http_client=http_client)
        articles = await client.fetch_topic(
            topic="脑胶质瘤",
            query="glioma AND clinical trial",
            max_results=25,
            lookback_days=730,
        )

    assert [article.pmid for article in articles] == ["12345678"]
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_pubmed_client_skips_efetch_when_search_has_no_ids() -> None:
    paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(
            200,
            json={"esearchresult": {"count": "0", "idlist": []}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = PubMedClient(http_client=http_client)
        articles = await client.fetch_topic(
            topic="降尿酸药物",
            query="urate lowering",
            max_results=10,
            lookback_days=365,
        )

    assert articles == []
    assert paths == ["/entrez/eutils/esearch.fcgi"]
