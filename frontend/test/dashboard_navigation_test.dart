import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pharma_bid_monitor_frontend/app/navigation/app_navigation_intent.dart';
import 'package:pharma_bid_monitor_frontend/features/dashboard/data/models/dashboard_models.dart';
import 'package:pharma_bid_monitor_frontend/features/dashboard/data/repositories/dashboard_repository.dart';
import 'package:pharma_bid_monitor_frontend/features/dashboard/presentation/pages/dashboard_page.dart';
import 'package:pharma_bid_monitor_frontend/features/notices/data/models/notice_models.dart';

void main() {
  late _FakeDashboardRepository repository;
  late List<AppNavigationIntent> intents;

  setUp(() {
    repository = _FakeDashboardRepository(_overview);
    intents = [];
  });

  Future<void> pumpDashboard(WidgetTester tester) async {
    tester.view.physicalSize = const Size(1500, 1000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: DashboardPage(
            repository: repository,
            onNavigate: intents.add,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('seven metric cards emit precise navigation intents',
      (tester) async {
    await pumpDashboard(tester);

    await tester.tap(find.byKey(const Key('dashboard-metric-today')));
    await tester.tap(find.byKey(const Key('dashboard-metric-declaration')));
    await tester.tap(find.byKey(const Key('dashboard-metric-result')));
    await tester.tap(find.byKey(const Key('dashboard-metric-sites')));
    await tester.tap(find.byKey(const Key('dashboard-metric-keywords')));
    await tester
        .tap(find.byKey(const Key('dashboard-metric-business-priority')));
    await tester.tap(find.byKey(const Key('dashboard-metric-high-quality')));

    expect(intents, hasLength(7));
    expect(intents[0].destination, AppDestination.notices);
    expect(
      intents[0].noticeQuery,
      const NoticeQuery(capturedToday: true),
    );
    expect(
      intents[1].noticeQuery,
      const NoticeQuery(projectSignal: '申报通知'),
    );
    expect(
      intents[2].noticeQuery,
      const NoticeQuery(projectSignal: '结果公示'),
    );
    expect(intents[3].destination, AppDestination.sourceSites);
    expect(
      intents[4].noticeQuery,
      const NoticeQuery(keywordHit: true),
    );
    expect(
      intents[5].noticeQuery,
      const NoticeQuery(highPriority: true),
    );
    expect(
      intents[6].noticeQuery,
      const NoticeQuery(highQuality: true),
    );
  });

  testWidgets('notice and distribution surfaces drill into exact data',
      (tester) async {
    await pumpDashboard(tester);
    final sourceSurface =
        find.byKey(const Key('dashboard-source-nmpa.example'));
    await tester.scrollUntilVisible(
      sourceSurface,
      500,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    expect(
      find.descendant(
        of: sourceSurface,
        matching: find.text('国家药监局项目申报通知'),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: sourceSurface,
        matching: find.text('nmpa.example'),
      ),
      findsNothing,
    );

    Future<void> tapSurface(String key) async {
      final finder = find.byKey(Key(key));
      await tester.ensureVisible(finder);
      await tester.pumpAndSettle();
      await tester.tap(finder);
      await tester.pump();
    }

    await tapSurface('dashboard-notice-high-11');
    await tapSurface('dashboard-notice-recent-12');
    await tapSurface('dashboard-keyword-创新药');
    await tapSurface('dashboard-project-结果公示');
    await tapSurface('dashboard-source-nmpa.example');

    expect(intents, hasLength(5));
    expect(intents[0].noticeId, 11);
    expect(intents[1].noticeId, 12);
    expect(
      intents[2].noticeQuery,
      const NoticeQuery(keyword: '创新药'),
    );
    expect(
      intents[3].noticeQuery,
      const NoticeQuery(projectSignal: '结果公示'),
    );
    expect(
      intents[4].noticeQuery,
      const NoticeQuery(sourceSite: 'nmpa.example'),
    );
  });

  testWidgets('notice cards reuse readable source labels when available',
      (tester) async {
    await pumpDashboard(tester);

    expect(find.text('国家药监局项目申报通知'), findsOneWidget);
    expect(find.text('科技部项目申报通知 · 07-29'), findsOneWidget);
    expect(find.text('nmpa.example'), findsNothing);
    expect(find.text('service.most.gov.cn · 07-29'), findsNothing);
  });

  testWidgets('interactive surfaces expose button semantics and affordances',
      (tester) async {
    final semantics = tester.ensureSemantics();
    await pumpDashboard(tester);

    final metric = find.byKey(const Key('dashboard-metric-today'));
    final node = tester.getSemantics(metric);

    expect(node.label, contains('今日新增公告'));
    expect(node.getSemanticsData().flagsCollection.isButton, isTrue);
    expect(find.descendant(of: metric, matching: find.byType(InkWell)),
        findsOneWidget);
    expect(find.descendant(of: metric, matching: find.byType(MouseRegion)),
        findsWidgets);
    expect(tester.getSize(metric).height, greaterThanOrEqualTo(44));
    semantics.dispose();
  });

  testWidgets('visible page scrollbar shares its controller with the list',
      (tester) async {
    await pumpDashboard(tester);

    final scrollbar = tester.widget<Scrollbar>(find.byType(Scrollbar).first);
    final listView = tester.widget<ListView>(find.byType(ListView).first);

    expect(scrollbar.thumbVisibility, isTrue);
    expect(scrollbar.controller, isNotNull);
    expect(identical(scrollbar.controller, listView.controller), isTrue);
    expect(tester.takeException(), isNull);
  });
}

class _FakeDashboardRepository implements DashboardRepository {
  final DashboardOverviewModel overview;

  const _FakeDashboardRepository(this.overview);

  @override
  Future<DashboardOverviewModel> fetchOverview() async => overview;
}

NoticeListItemModel _notice({
  required int id,
  required String title,
  required String sourceSite,
}) {
  return NoticeListItemModel(
    id: id,
    title: title,
    summary: '$title 摘要',
    sourceSite: sourceSite,
    sourceUrl: 'https://example.com/$id',
    publishedAt: '2026-07-29T08:00:00',
    capturedAt: '2026-07-29T09:00:00',
    qualityScore: 90,
    matchedKeywords: const ['创新药'],
    isHighPriority: true,
    category: '项目申报',
    aiSummary: null,
    reviewStatus: '待关注',
    isArchived: false,
    remark: null,
    taskId: 3,
  );
}

final _overview = DashboardOverviewModel(
  metrics: const DashboardMetricsModel(
    todayNewNotices: 8,
    keywordHitNotices: 6,
    monitoringSiteCount: 5,
    highPriorityNotices: 4,
    highQualityNotices: 5,
    projectDeclarationNotices: 3,
    resultPublicationNotices: 2,
  ),
  runtime: const DashboardRuntimeModel(
    status: 'ok',
    database: 'connected',
    scheduler: 'running',
    scheduledJobs: 3,
  ),
  highValueNotices: [
    _notice(id: 11, title: '高价值公告', sourceSite: 'nmpa.example'),
  ],
  recentNotices: [
    _notice(id: 12, title: '最近公告', sourceSite: 'service.most.gov.cn'),
  ],
  keywordHeat: const [
    KeywordHeatItemModel(keyword: '创新药', count: 6),
  ],
  sourceDistribution: const [
    SourceDistributionItemModel(
      sourceSite: 'nmpa.example',
      displayName: '国家药监局项目申报通知',
      noticeCount: 5,
      percentage: 62.5,
    ),
    SourceDistributionItemModel(
      sourceSite: 'service.most.gov.cn',
      displayName: '科技部项目申报通知',
      noticeCount: 3,
      percentage: 37.5,
    ),
  ],
  projectSignalDistribution: const [
    ProjectSignalItemModel(
      label: '结果公示',
      noticeCount: 2,
      percentage: 25,
    ),
  ],
  lastUpdatedAt: '2026-07-29T09:30:00',
);
