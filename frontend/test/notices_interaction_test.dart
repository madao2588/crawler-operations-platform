import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pharma_bid_monitor_frontend/app/navigation/app_navigation_intent.dart';
import 'package:pharma_bid_monitor_frontend/core/theme/app_theme.dart';
import 'package:pharma_bid_monitor_frontend/features/notices/data/models/notice_models.dart';
import 'package:pharma_bid_monitor_frontend/features/notices/data/repositories/notice_repository.dart';
import 'package:pharma_bid_monitor_frontend/features/notices/presentation/pages/notices_page.dart';
import 'package:pharma_bid_monitor_frontend/shared/models/page_data.dart';

void main() {
  testWidgets('initial query is loaded and rendered as removable drill-down',
      (tester) async {
    _useDesktopViewport(tester);
    final repository = _RecordingNoticeRepository();

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: NoticesPage(
          repository: repository,
          initialNoticeId: 2,
          initialQuery: const NoticeQuery(
            keyword: '创新药',
            category: '项目申报',
            capturedToday: true,
            sourceSite: 'nmpa.example',
            highPriority: true,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final firstQuery = repository.queries.first;
    expect(firstQuery.keyword, '创新药');
    expect(firstQuery.category, '项目申报');
    expect(firstQuery.capturedToday, isTrue);
    expect(firstQuery.sourceSite, 'nmpa.example');
    expect(firstQuery.highPriority, isTrue);
    expect(repository.detailIds.first, 2);
    expect(find.text('当前联动筛选'), findsOneWidget);
    expect(find.text('来源：国家药监局'), findsWidgets);
    expect(find.text('今日采集'), findsOneWidget);
    expect(find.byTooltip('清除全部联动筛选'), findsOneWidget);

    await tester.tap(find.byTooltip('清除全部联动筛选'));
    await tester.pumpAndSettle();
    expect(repository.queries.last.isEmpty, isTrue);
    expect(find.text('当前联动筛选'), findsNothing);
  });

  testWidgets('narrow active filters preserve the readable source name',
      (tester) async {
    _useViewport(tester, const Size(320, 1000));
    final repository = _RecordingNoticeRepository();

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: NoticesPage(
          repository: repository,
          initialQuery: const NoticeQuery(sourceSite: 'nmpa.example'),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.byKey(const Key('active-notice-filters-compact')),
      findsOneWidget,
    );
    expect(find.text('来源：国家药监局'), findsWidgets);
    expect(tester.takeException(), isNull);
  });

  testWidgets('unknown source filter falls back to the source site itself',
      (tester) async {
    _useViewport(tester, const Size(320, 1000));
    final repository = _PartialSourceNoticeRepository();

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: NoticesPage(
          repository: repository,
          initialQuery: const NoticeQuery(sourceSite: 'unknown.example'),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('来源：unknown.example'), findsWidgets);
    expect(find.text('来源：未命名来源'), findsNothing);
  });

  testWidgets(
      'summary cards and notice tags update the query without selecting',
      (tester) async {
    _useDesktopViewport(tester);
    final repository = _RecordingNoticeRepository();

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: Scaffold(
          body: NoticesPage(repository: repository),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('公告中心'), findsOneWidget);
    expect(
        find.byKey(const Key('notice-metric-high-priority')), findsOneWidget);
    expect(find.byKey(const Key('notice-metric-high-quality')), findsOneWidget);
    expect(find.byKey(const Key('notice-metric-keyword-hit')), findsOneWidget);

    await tester.tap(find.byKey(const Key('notice-metric-high-priority')));
    await tester.pumpAndSettle();
    expect(repository.queries.last.highPriority, isTrue);
    expect(find.text('业务优先'), findsWidgets);

    await tester.tap(find.byKey(const Key('notice-metric-high-quality')));
    await tester.pumpAndSettle();
    expect(repository.queries.last.highQuality, isTrue);
    expect(find.text('高质量内容'), findsWidgets);

    final detailCallsBeforeTagTap = repository.detailIds.length;
    await tester.tap(find.byKey(const Key('notice-source-1')));
    await tester.pumpAndSettle();
    expect(repository.queries.last.sourceSite, 'nmpa.example');
    expect(repository.detailIds.length, detailCallsBeforeTagTap);

    await tester.tap(find.byKey(const Key('notice-category-1')));
    await tester.pumpAndSettle();
    expect(repository.queries.last.category, '项目申报');

    await tester.tap(find.byKey(const Key('notice-keyword-1-创新药')));
    await tester.pumpAndSettle();
    expect(repository.queries.last.keyword, '创新药');
  });

  testWidgets('source website selector applies and clears the shared query',
      (tester) async {
    _useDesktopViewport(tester);
    final repository = _RecordingNoticeRepository();

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: Scaffold(
          body: NoticesPage(repository: repository),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final sourceFilter = find.byKey(const Key('notice-source-site-filter'));
    expect(sourceFilter, findsOneWidget);

    await tester.tap(sourceFilter);
    await tester.pumpAndSettle();
    await tester.tap(find.text('行业协会').last);
    await tester.pumpAndSettle();

    expect(repository.queries.last.sourceSite, 'association.example');
    expect(find.text('来源：行业协会'), findsWidgets);
    expect(find.textContaining('association.example'), findsNothing);

    await tester.tap(sourceFilter);
    await tester.pumpAndSettle();
    await tester.tap(find.text('全部来源').last);
    await tester.pumpAndSettle();

    expect(repository.queries.last.sourceSite, isNull);
  });

  testWidgets('a new navigation intent replaces the active notice query',
      (tester) async {
    _useDesktopViewport(tester);
    final repository = _RecordingNoticeRepository();

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: NoticesPage(
          repository: repository,
          initialQuery: const NoticeQuery(sourceSite: 'nmpa.example'),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: NoticesPage(
          repository: repository,
          initialNoticeId: 2,
          initialQuery: const NoticeQuery(
            keyword: '会议',
            category: '行业会议',
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(repository.queries.last.keyword, '会议');
    expect(repository.queries.last.category, '行业会议');
    expect(repository.queries.last.sourceSite, isNull);
    expect(repository.detailIds.last, 2);
  });

  testWidgets('an off-page initial notice remains selected in the detail pane',
      (tester) async {
    _useDesktopViewport(tester);
    final repository = _OffPageNoticeRepository();

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: NoticesPage(
          repository: repository,
          initialNoticeId: 2,
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(repository.detailIds, [2]);
    expect(find.byKey(const ValueKey(2)), findsOneWidget);
  });

  testWidgets('industry meeting detail renders structured meeting metadata',
      (tester) async {
    _useDesktopViewport(tester);
    final repository = _IndustryMeetingNoticeRepository();

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: NoticesPage(
          repository: repository,
          initialNoticeId: 2,
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('会议信息'), findsOneWidget);
    expect(find.text('会议时间'), findsOneWidget);
    expect(find.text('2026-08-15 09:00:00'), findsOneWidget);
    expect(find.text('会议地点'), findsOneWidget);
    expect(find.text('上海张江科学会堂'), findsOneWidget);
    expect(find.text('主办方'), findsOneWidget);
    expect(find.text('中国药学会'), findsOneWidget);
    expect(find.text('报名截止'), findsOneWidget);
    expect(find.text('2026-08-10 18:00:00'), findsOneWidget);
    expect(
      find.byKey(const Key('notice-meeting-registration-2')),
      findsOneWidget,
    );
  });

  testWidgets('a 1280x720 shell-sized notice page does not overflow',
      (tester) async {
    _useViewport(tester, const Size(1280, 720));
    final repository = _RecordingNoticeRepository();

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: Center(
          child: SizedBox(
            width: 918,
            height: 568,
            child: NoticesPage(repository: repository),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('notice-overview-toolbar')), findsOneWidget);
    expect(find.byKey(const Key('notice-refresh-action')), findsOneWidget);
    expect(find.byKey(const Key('notice-export-action')), findsOneWidget);
    expect(find.text('刷新'), findsOneWidget);
    expect(find.text('导出 Excel'), findsOneWidget);
    expect(find.byKey(const Key('notice-master-detail')), findsOneWidget);
    expect(find.byKey(const Key('notice-list-pane')), findsOneWidget);
    expect(find.byKey(const Key('notice-detail-pane')), findsOneWidget);
    expect(
      find.byKey(const Key('notice-compact-mode-switcher')),
      findsNothing,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets(
      'wide notice workspace exposes saved views facets results and detail',
      (tester) async {
    _useDesktopViewport(tester);
    final repository = _RecordingNoticeRepository();

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: Scaffold(
          body: NoticesPage(repository: repository),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('notice-saved-view-bar')), findsOneWidget);
    expect(find.byKey(const Key('notice-facet-pane')), findsOneWidget);
    expect(find.byKey(const Key('notice-results-pane')), findsOneWidget);
    expect(find.byKey(const Key('notice-detail-pane')), findsOneWidget);
    expect(find.text('公告详情'), findsOneWidget);
    expect(find.byKey(const Key('notice-match-reason')), findsOneWidget);

    await tester.tap(
      find.byKey(const Key('notice-saved-view-result-publication')),
    );
    await tester.pumpAndSettle();
    expect(repository.queries.last.projectSignal, '结果公示');

    await tester.tap(
      find.byKey(const Key('notice-facet-source-nmpa.example')),
    );
    await tester.pumpAndSettle();
    expect(repository.queries.last.sourceSite, 'nmpa.example');
    expect(repository.queries.last.projectSignal, '结果公示');
    expect(tester.takeException(), isNull);
  });

  testWidgets('active filter chips remove one condition without clearing all',
      (tester) async {
    _useDesktopViewport(tester);
    final repository = _RecordingNoticeRepository();

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: NoticesPage(
          repository: repository,
          initialQuery: const NoticeQuery(
            sourceSite: 'nmpa.example',
            projectSignal: '结果公示',
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final sourceChip = find.byKey(
      const Key('active-notice-filter-sourceSite'),
    );
    expect(sourceChip, findsOneWidget);

    tester.widget<InputChip>(sourceChip).onDeleted!();
    await tester.pumpAndSettle();

    expect(repository.queries.last.sourceSite, isNull);
    expect(repository.queries.last.projectSignal, '结果公示');
    expect(find.text('来源：国家药监局'), findsNothing);
  });

  testWidgets('375px keeps all four notice metric actions operable',
      (tester) async {
    _useViewport(tester, const Size(375, 812));
    final repository = _RecordingNoticeRepository();

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: NoticesPage(repository: repository),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.byKey(const Key('notice-compact-mode-switcher')),
      findsOneWidget,
    );
    expect(find.byKey(const Key('notice-master-detail')), findsNothing);
    expect(find.byKey(const Key('notice-metric-all')), findsOneWidget);
    expect(
      find.byKey(const Key('notice-metric-high-priority')),
      findsOneWidget,
    );
    expect(
      find.byKey(const Key('notice-metric-high-quality')),
      findsOneWidget,
    );
    expect(find.byKey(const Key('notice-metric-keyword-hit')), findsOneWidget);
    expect(
      find.byKey(const Key('notice-compact-metrics-grid')),
      findsOneWidget,
    );
    expect(find.text('本页优先 1'), findsOneWidget);
    expect(find.text('本页优质 2'), findsOneWidget);
    expect(find.text('本页命中 2'), findsOneWidget);
    expect(tester.takeException(), isNull);

    await tester.tap(find.byKey(const Key('notice-metric-high-priority')));
    await tester.pumpAndSettle();
    expect(repository.queries.last.highPriority, isTrue);

    await tester.tap(find.byKey(const Key('notice-metric-all')));
    await tester.pumpAndSettle();
    expect(repository.queries.last.isEmpty, isTrue);

    await tester.tap(find.byKey(const Key('notice-metric-high-quality')));
    await tester.pumpAndSettle();
    expect(repository.queries.last.highQuality, isTrue);

    await tester.tap(find.byKey(const Key('notice-metric-keyword-hit')));
    await tester.pumpAndSettle();
    expect(repository.queries.last.keywordHit, isTrue);
  });

  testWidgets(
      'review action disables per notice and ignores a rapid double tap',
      (tester) async {
    _useViewport(tester, const Size(375, 812));
    final repository = _DeferredReviewNoticeRepository();

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: Scaffold(
          body: NoticesPage(repository: repository),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final validAction = find.byKey(const Key('notice-review-1-有效'));
    final validButton = find.descendant(
      of: validAction,
      matching: find.byType(OutlinedButton),
    );
    expect(validAction, findsOneWidget);
    expect(validButton, findsOneWidget);

    await tester.ensureVisible(validAction);
    await tester.pumpAndSettle();
    await tester.tap(validAction);
    await tester.tap(validAction);
    await tester.pump();

    expect(repository.updateCalls, 1);
    expect(
      find.byKey(const Key('notice-review-progress-1-有效')),
      findsOneWidget,
    );
    expect(tester.widget<OutlinedButton>(validButton).onPressed, isNull);

    repository.completeReview();
    await tester.pumpAndSettle();

    expect(repository.updateCalls, 1);
    expect(
      find.byKey(const Key('notice-review-progress-1-有效')),
      findsNothing,
    );
  });
}

void _useDesktopViewport(WidgetTester tester) {
  _useViewport(tester, const Size(1440, 1000));
}

void _useViewport(WidgetTester tester, Size size) {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

class _RecordingNoticeRepository implements NoticeRepository {
  final List<NoticeQuery> queries = [];
  final List<int> detailIds = [];

  static const _items = [
    NoticeListItemModel(
      id: 1,
      title: '创新药项目申报通知',
      summary: '申报摘要',
      sourceSite: 'nmpa.example',
      sourceUrl: 'https://example.test/1',
      publishedAt: null,
      capturedAt: '2026-07-29T08:00:00',
      qualityScore: 90,
      matchedKeywords: ['创新药'],
      isHighPriority: true,
      category: '项目申报',
      aiSummary: null,
      reviewStatus: '待关注',
      isArchived: false,
      remark: null,
      taskId: 10,
    ),
    NoticeListItemModel(
      id: 2,
      title: '行业会议',
      summary: '会议信息',
      sourceSite: 'association.example',
      sourceUrl: 'https://example.test/2',
      publishedAt: null,
      capturedAt: '2026-07-29T09:00:00',
      qualityScore: 80,
      matchedKeywords: ['会议'],
      isHighPriority: false,
      category: '行业会议',
      aiSummary: null,
      reviewStatus: '待关注',
      isArchived: false,
      remark: null,
      taskId: 11,
    ),
  ];

  @override
  Future<List<NoticeSourceSiteOption>> fetchSourceSites() async {
    return const [
      NoticeSourceSiteOption(
        sourceSite: 'nmpa.example',
        displayName: '国家药监局',
      ),
      NoticeSourceSiteOption(
        sourceSite: 'association.example',
        displayName: '行业协会',
      ),
    ];
  }

  @override
  Future<PageData<NoticeListItemModel>> fetchNotices({
    int page = 1,
    int pageSize = 20,
    String? keyword,
    String? category,
    String? reviewStatus,
    bool? archived,
    bool? capturedToday,
    String? sourceSite,
    bool? keywordHit,
    bool? highPriority,
    bool? highQuality,
    String? projectSignal,
  }) async {
    queries.add(
      NoticeQuery(
        keyword: keyword,
        category: category,
        reviewStatus: reviewStatus,
        archived: archived,
        capturedToday: capturedToday,
        sourceSite: sourceSite,
        keywordHit: keywordHit,
        highPriority: highPriority,
        highQuality: highQuality,
        projectSignal: projectSignal,
      ),
    );
    return const PageData(
      items: _items,
      total: 2,
      page: 1,
      pageSize: 20,
    );
  }

  @override
  Future<NoticeDetailModel> fetchNoticeDetail(int id) async {
    detailIds.add(id);
    final item = _RecordingNoticeRepository._items
        .firstWhere((candidate) => candidate.id == id);
    return NoticeDetailModel(
      id: item.id,
      title: item.title,
      summary: item.summary,
      sourceSite: item.sourceSite,
      sourceUrl: item.sourceUrl,
      publishedAt: item.publishedAt,
      capturedAt: item.capturedAt,
      qualityScore: item.qualityScore,
      matchedKeywords: item.matchedKeywords,
      isHighPriority: item.isHighPriority,
      category: item.category,
      aiSummary: item.aiSummary,
      reviewStatus: item.reviewStatus,
      isArchived: item.isArchived,
      remark: item.remark,
      taskId: item.taskId,
      contentText: '正文',
      contentHtml: '<p>正文</p>',
      contentHash: null,
      snapshotPath: null,
      metadata: null,
    );
  }

  @override
  Future<NoticeSnapshotModel> fetchSnapshot(int id) {
    throw UnimplementedError();
  }

  @override
  Future<NoticeDetailModel> updateNoticeReview(
    int id,
    NoticeReviewPayload payload,
  ) {
    throw UnimplementedError();
  }

  @override
  Future<List<int>> downloadCollectedDataExport({
    int limit = 5000,
    int? taskId,
    String? category,
    String? reviewStatus,
    bool? archived,
  }) {
    throw UnimplementedError();
  }

  @override
  Future<List<int>> downloadInformationPoolExcel({
    int limit = 5000,
    int? taskId,
    String? category,
    String? reviewStatus,
    bool? archived,
  }) {
    throw UnimplementedError();
  }
}

class _OffPageNoticeRepository extends _RecordingNoticeRepository {
  @override
  Future<PageData<NoticeListItemModel>> fetchNotices({
    int page = 1,
    int pageSize = 20,
    String? keyword,
    String? category,
    String? reviewStatus,
    bool? archived,
    bool? capturedToday,
    String? sourceSite,
    bool? keywordHit,
    bool? highPriority,
    bool? highQuality,
    String? projectSignal,
  }) async {
    queries.add(
      NoticeQuery(
        keyword: keyword,
        category: category,
        reviewStatus: reviewStatus,
        archived: archived,
        capturedToday: capturedToday,
        sourceSite: sourceSite,
        keywordHit: keywordHit,
        highPriority: highPriority,
        highQuality: highQuality,
        projectSignal: projectSignal,
      ),
    );
    return PageData(
      items: [_RecordingNoticeRepository._items.first],
      total: 2,
      page: 1,
      pageSize: 20,
    );
  }
}

class _DeferredReviewNoticeRepository extends _RecordingNoticeRepository {
  final Completer<NoticeDetailModel> _reviewCompleter =
      Completer<NoticeDetailModel>();
  int updateCalls = 0;

  @override
  Future<NoticeDetailModel> updateNoticeReview(
    int id,
    NoticeReviewPayload payload,
  ) {
    updateCalls += 1;
    return _reviewCompleter.future;
  }

  void completeReview() {
    final item = _RecordingNoticeRepository._items.first;
    _reviewCompleter.complete(
      NoticeDetailModel(
        id: item.id,
        title: item.title,
        summary: item.summary,
        sourceSite: item.sourceSite,
        sourceUrl: item.sourceUrl,
        publishedAt: item.publishedAt,
        capturedAt: item.capturedAt,
        qualityScore: item.qualityScore,
        matchedKeywords: item.matchedKeywords,
        isHighPriority: item.isHighPriority,
        category: item.category,
        aiSummary: item.aiSummary,
        reviewStatus: '有效',
        isArchived: item.isArchived,
        remark: item.remark,
        taskId: item.taskId,
        contentText: '正文',
        contentHtml: '<p>正文</p>',
        contentHash: null,
        snapshotPath: null,
        metadata: null,
      ),
    );
  }
}

class _PartialSourceNoticeRepository extends _RecordingNoticeRepository {
  @override
  Future<List<NoticeSourceSiteOption>> fetchSourceSites() async {
    return const [
      NoticeSourceSiteOption(
        sourceSite: 'nmpa.example',
        displayName: '国家药监局',
      ),
    ];
  }
}

class _IndustryMeetingNoticeRepository extends _RecordingNoticeRepository {
  @override
  Future<NoticeDetailModel> fetchNoticeDetail(int id) async {
    detailIds.add(id);
    final item = _RecordingNoticeRepository._items.firstWhere(
      (candidate) => candidate.id == id,
    );
    return NoticeDetailModel(
      id: item.id,
      title: item.title,
      summary: item.summary,
      sourceSite: item.sourceSite,
      sourceUrl: item.sourceUrl,
      publishedAt: item.publishedAt,
      capturedAt: item.capturedAt,
      qualityScore: item.qualityScore,
      matchedKeywords: item.matchedKeywords,
      isHighPriority: item.isHighPriority,
      category: item.category,
      aiSummary: item.aiSummary,
      reviewStatus: item.reviewStatus,
      isArchived: item.isArchived,
      remark: item.remark,
      taskId: item.taskId,
      contentText: '会议详情正文',
      contentHtml: '<p>会议详情正文</p>',
      contentHash: null,
      snapshotPath: null,
      metadata: const {
        'kind': 'industry_meeting',
        'meeting_date': '2026-08-15T09:00:00+08:00',
        'location': '上海张江科学会堂',
        'organizer': '中国药学会',
        'registration_deadline': '2026-08-10T18:00:00+08:00',
        'registration_url': 'https://meeting.example.com/register',
      },
    );
  }
}
