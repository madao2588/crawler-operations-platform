import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pharma_bid_monitor_frontend/app/navigation/app_navigation_intent.dart';
import 'package:pharma_bid_monitor_frontend/app/navigation/app_shell.dart';
import 'package:pharma_bid_monitor_frontend/features/dashboard/data/models/dashboard_models.dart';
import 'package:pharma_bid_monitor_frontend/features/dashboard/data/repositories/dashboard_repository.dart';
import 'package:pharma_bid_monitor_frontend/features/notices/presentation/pages/notices_page.dart';
import 'package:pharma_bid_monitor_frontend/features/system_management/data/models/task_template_models.dart';

void main() {
  testWidgets('dashboard intent opens notices with its initial query',
      (tester) async {
    tester.view.physicalSize = const Size(1500, 1000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      MaterialApp(
        home: AppShell(
          userName: '测试用户',
          avatarBytes: null,
          onLogout: () async {},
          templatesFuture: Future.value(const <TaskTemplateModel>[]),
          dashboardRepository: const _FakeDashboardRepository(_emptyOverview),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('dashboard-metric-today')));
    await tester.pump();

    final noticesPage = tester.widget<NoticesPage>(find.byType(NoticesPage));
    expect(
      noticesPage.initialQuery,
      const NoticeQuery(capturedToday: true),
    );
    expect(noticesPage.initialNoticeId, isNull);
  });
}

class _FakeDashboardRepository implements DashboardRepository {
  final DashboardOverviewModel overview;

  const _FakeDashboardRepository(this.overview);

  @override
  Future<DashboardOverviewModel> fetchOverview() async => overview;
}

const _emptyOverview = DashboardOverviewModel(
  metrics: DashboardMetricsModel(
    todayNewNotices: 1,
    keywordHitNotices: 0,
    monitoringSiteCount: 0,
    highPriorityNotices: 0,
    projectDeclarationNotices: 0,
    resultPublicationNotices: 0,
  ),
  runtime: DashboardRuntimeModel(
    status: 'ok',
    database: 'connected',
    scheduler: 'running',
    scheduledJobs: 0,
  ),
  highValueNotices: [],
  recentNotices: [],
  keywordHeat: [],
  sourceDistribution: [],
  projectSignalDistribution: [],
  lastUpdatedAt: null,
);
