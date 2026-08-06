import 'package:flutter_test/flutter_test.dart';
import 'package:pharma_bid_monitor_frontend/core/constants/api_paths.dart';

void main() {
  test('ApiPaths static routes use v1 prefix', () {
    expect(ApiPaths.dashboardOverview, startsWith('/v1/'));
    expect(ApiPaths.notices, '/v1/notices');
    expect(ApiPaths.noticeSourceSites, '/v1/notices/source-sites');
    expect(ApiPaths.logSummary, '/v1/logs/summary');
    expect(ApiPaths.dataExportCsv, '/v1/data/export/csv');
    expect(ApiPaths.dataExportExcel, '/v1/data/export/excel');
    expect(ApiPaths.statsOverview, '/v1/stats/overview');
    expect(ApiPaths.tasksRunEnabled, '/v1/tasks/run-enabled');
  });

  test('ApiPaths builders interpolate ids', () {
    expect(ApiPaths.noticeDetail(42), '/v1/notices/42');
    expect(ApiPaths.noticeReview(42), '/v1/notices/42/review');
    expect(ApiPaths.taskDetail(7), '/v1/tasks/7');
    expect(ApiPaths.runTask(3), '/v1/tasks/3/run');
    expect(ApiPaths.useTaskTemplate('abc'), '/v1/templates/tasks/abc/use');
  });
}
