import 'package:flutter_test/flutter_test.dart';
import 'package:pharma_bid_monitor_frontend/app/navigation/app_navigation_intent.dart';

void main() {
  group('AppNavigationIntent', () {
    test('carries all notice filters and an optional notice id', () {
      const query = NoticeQuery(
        keyword: '创新药',
        category: '项目申报',
        reviewStatus: '重点关注',
        archived: false,
        capturedToday: true,
        sourceSite: '国家药监局',
        keywordHit: true,
        highPriority: true,
        highQuality: false,
        projectSignal: '结果公示',
      );

      const intent = AppNavigationIntent.notices(
        query: query,
        noticeId: 42,
      );

      expect(intent.destination, AppDestination.notices);
      expect(intent.noticeQuery, same(query));
      expect(intent.noticeId, 42);
      expect(intent.systemTab, isNull);
      expect(intent.taskFilter, isNull);
      expect(intent.logLevel, isNull);
      expect(intent.taskId, isNull);
    });

    test('carries system management navigation state', () {
      const intent = AppNavigationIntent.systemManagement(
        tab: SystemManagementTab.logs,
        taskFilter: 'failed',
        logLevel: 'ERROR',
        taskId: 7,
      );

      expect(intent.destination, AppDestination.systemManagement);
      expect(intent.systemTab, SystemManagementTab.logs);
      expect(intent.taskFilter, 'failed');
      expect(intent.logLevel, 'ERROR');
      expect(intent.taskId, 7);
      expect(intent.noticeQuery, isNull);
      expect(intent.noticeId, isNull);
    });

    test('provides useful empty defaults', () {
      const noticeIntent = AppNavigationIntent.notices();
      const sourceIntent = AppNavigationIntent.sourceSites();

      expect(noticeIntent.noticeQuery, const NoticeQuery());
      expect(sourceIntent.destination, AppDestination.sourceSites);
    });
  });
}
