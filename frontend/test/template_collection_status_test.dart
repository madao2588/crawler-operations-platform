import 'package:flutter_test/flutter_test.dart';
import 'package:pharma_bid_monitor_frontend/features/source_sites/presentation/template_collection_status.dart';
import 'package:pharma_bid_monitor_frontend/features/system_management/data/models/task_models.dart';
import 'package:pharma_bid_monitor_frontend/features/system_management/data/models/task_template_models.dart';

void main() {
  const baseTemplate = TaskTemplateModel(
    id: 'base',
    label: '模板',
    name: '模板任务',
    startUrl: 'https://example.com',
    cronExpr: '0 9 * * *',
    parserRules: null,
    enabled: true,
    description: '模板说明',
    tags: <String>[],
    usageCount: 0,
    lastUsedAt: null,
  );

  test('resolveTemplateCollectionStatus distinguishes all current modes', () {
    final automated = resolveTemplateCollectionStatus(
      const TaskTemplateModel(
        id: 'pubmed_literature',
        label: 'PubMed 文献',
        name: 'PubMed 竞品文献入口',
        startUrl: 'https://pubmed.ncbi.nlm.nih.gov/',
        cronExpr: '0 10 * * *',
        parserRules:
            '{"query":"glioblastoma","metadata":{"kind":"competitor_intelligence"}}',
        enabled: true,
        description: '通过官方接口自动跟踪竞品文献。',
        tags: <String>['竞品信息'],
        usageCount: 0,
        lastUsedAt: null,
      ),
    );
    final manual = resolveTemplateCollectionStatus(
      const TaskTemplateModel(
        id: 'wechat_k_innovation',
        label: '公众号线索',
        name: '公众号线索登记',
        startUrl: 'https://mp.weixin.qq.com/',
        cronExpr: '0 9 * * *',
        parserRules: '{"collection_mode":"manual"}',
        enabled: false,
        description: '来源需要人工登记文章链接。',
        tags: <String>['线索'],
        usageCount: 0,
        lastUsedAt: null,
      ),
    );
    final authorization = resolveTemplateCollectionStatus(
      const TaskTemplateModel(
        id: 'pharnexcloud_drug_database',
        label: '摩熵医药数据库',
        name: '数据库入口',
        startUrl: 'https://vip.pharnexcloud.com/database/research',
        cronExpr: '0 10 * * *',
        parserRules: null,
        enabled: false,
        description: '数据库类来源涉及账号授权，默认仅登记入口。',
        tags: <String>['数据库'],
        usageCount: 0,
        lastUsedAt: null,
      ),
    );
    final unimplemented = resolveTemplateCollectionStatus(baseTemplate);
    final intermittent = resolveTemplateCollectionStatus(
      const TaskTemplateModel(
        id: 'bioon_meetings',
        label: '生物谷会议',
        name: '生物谷会议采集',
        startUrl: 'https://www.bioon.com/meeting/newest',
        cronExpr: '45 9,15 * * *',
        parserRules: '{"collection_mode":"intermittent"}',
        enabled: true,
        description: '列表页当前会触发验证码。',
        tags: <String>['行业会议'],
        usageCount: 0,
        lastUsedAt: null,
      ),
    );
    final stale = resolveTemplateCollectionStatus(
      const TaskTemplateModel(
        id: 'dxy_pharmacy_meetings',
        label: '丁香会议药学会议',
        name: '丁香会议药学会议采集',
        startUrl: 'https://meeting.dxy.cn/tag/list/category/pharmacy',
        cronExpr: '35 9,15 * * *',
        parserRules: '{"collection_mode":"stale"}',
        enabled: false,
        description: '官方列表长期未更新。',
        tags: <String>['行业会议'],
        usageCount: 0,
        lastUsedAt: null,
      ),
    );

    expect(automated.label, '自动采集');
    expect(automated.note, '已配置解析规则，可按定时任务自动采集。');
    expect(manual.label, '人工登记');
    expect(manual.note, '当前不做自动抓取，只支持人工登记文章链接。');
    expect(authorization.label, '需授权');
    expect(authorization.note, '该来源依赖账号或平台授权，当前仅保留入口信息。');
    expect(intermittent.label, '受限采集');
    expect(intermittent.note, '已配置自动采集，但来源可能间歇触发验证码并导致任务失败。');
    expect(stale.label, '已暂停');
    expect(stale.note, '解析规则已保留，但官方列表长期未更新，暂不自动运行。');
    expect(unimplemented.label, '未实现');
    expect(unimplemented.note, '当前仅登记来源信息，尚未配置解析规则或采集流程。');
  });

  test('resolveSourceSiteRuntimeStatus prefers real task health over template defaults', () {
    final success = resolveSourceSiteRuntimeStatus(
      template: const TaskTemplateModel(
        id: 'pubmed_literature',
        label: 'PubMed 文献',
        name: 'PubMed 竞品文献入口',
        startUrl: 'https://pubmed.ncbi.nlm.nih.gov/',
        cronExpr: '0 10 * * *',
        parserRules:
            '{"query":"glioblastoma","metadata":{"kind":"competitor_intelligence"}}',
        enabled: true,
        description: '通过官方接口自动跟踪竞品文献。',
        tags: <String>['竞品信息'],
        usageCount: 0,
        lastUsedAt: null,
      ),
      task: const TaskListItemModel(
        id: 7,
        name: 'PubMed 竞品文献入口',
        startUrl: 'https://pubmed.ncbi.nlm.nih.gov/',
        parserRules:
            '{"query":"glioblastoma","metadata":{"kind":"competitor_intelligence"}}',
        cronExpr: '0 10 * * *',
        status: 1,
        lastRunStatus: 'success',
        lastRunAt: '2026-07-30T12:00:00Z',
        lastSuccessAt: '2026-07-30T12:00:00Z',
        lastErrorMessage: null,
        createdAt: '2026-07-01T00:00:00Z',
      ),
    );

    final partial = resolveSourceSiteRuntimeStatus(
      template: const TaskTemplateModel(
        id: 'meeting_partial',
        label: '会议摘要',
        name: '会议摘要入口',
        startUrl: 'https://meeting.example.com',
        cronExpr: '0 */6 * * *',
        parserRules: '{"collection_mode":"automatic"}',
        enabled: true,
        description: '自动采集会议信息',
        tags: <String>['会议'],
        usageCount: 0,
        lastUsedAt: null,
      ),
      task: const TaskListItemModel(
        id: 8,
        name: '会议摘要入口',
        startUrl: 'https://meeting.example.com',
        parserRules: '{"collection_mode":"automatic"}',
        cronExpr: '0 */6 * * *',
        status: 1,
        lastRunStatus: 'partial',
        lastRunAt: '2026-07-30T10:00:00Z',
        lastSuccessAt: '2026-07-30T10:00:00Z',
        lastErrorMessage:
            'Run completed with partial failures; inspect the latest run summary.',
        createdAt: '2026-07-01T00:00:00Z',
      ),
      latestSummaryLog: const TaskLogItemModel(
        id: 1,
        taskId: 8,
        level: 'WARNING',
        message: 'partial summary',
        errorStack: null,
        runSummary: {
          'metrics': {
            'stored': 3,
            'failed': 1,
          },
        },
        createdAt: '2026-07-30T10:00:05Z',
      ),
    );

    final connectionFailure = resolveSourceSiteRuntimeStatus(
      template: baseTemplate,
      task: const TaskListItemModel(
        id: 9,
        name: '模板任务',
        startUrl: 'https://example.com',
        parserRules: '{"collection_mode":"automatic"}',
        cronExpr: '0 */6 * * *',
        status: 1,
        lastRunStatus: 'failed',
        lastRunAt: '2026-07-30T09:00:00Z',
        lastSuccessAt: '2026-07-29T09:00:00Z',
        lastErrorMessage: 'Connection reset by peer while fetching source page',
        createdAt: '2026-07-01T00:00:00Z',
      ),
      latestLog: const TaskLogItemModel(
        id: 2,
        taskId: 9,
        level: 'ERROR',
        message: 'Task 9 execution failed',
        errorStack: 'Connection reset by peer while fetching source page',
        runSummary: null,
        createdAt: '2026-07-30T09:00:02Z',
      ),
    );

    final parseFailure = resolveSourceSiteRuntimeStatus(
      template: baseTemplate,
      task: const TaskListItemModel(
        id: 10,
        name: '模板任务',
        startUrl: 'https://example.com',
        parserRules: '{"collection_mode":"automatic"}',
        cronExpr: '0 */6 * * *',
        status: 1,
        lastRunStatus: 'failed',
        lastRunAt: '2026-07-30T08:00:00Z',
        lastSuccessAt: '2026-07-29T08:00:00Z',
        lastErrorMessage: 'Parser failed to extract content from detail page',
        createdAt: '2026-07-01T00:00:00Z',
      ),
    );

    final stale = resolveSourceSiteRuntimeStatus(
      template: const TaskTemplateModel(
        id: 'dxy_pharmacy_meetings',
        label: '丁香会议药学会议',
        name: '丁香会议药学会议采集',
        startUrl: 'https://meeting.dxy.cn/tag/list/category/pharmacy',
        cronExpr: '35 9,15 * * *',
        parserRules: '{"collection_mode":"stale"}',
        enabled: false,
        description: '官方列表长期未更新。',
        tags: <String>['行业会议'],
        usageCount: 0,
        lastUsedAt: null,
      ),
    );

    final manual = resolveSourceSiteRuntimeStatus(
      template: const TaskTemplateModel(
        id: 'wechat_k_innovation',
        label: '公众号线索',
        name: '公众号线索登记',
        startUrl: 'https://mp.weixin.qq.com/',
        cronExpr: '0 9 * * *',
        parserRules: '{"collection_mode":"manual"}',
        enabled: false,
        description: '来源需要人工登记文章链接。',
        tags: <String>['线索'],
        usageCount: 0,
        lastUsedAt: null,
      ),
    );

    expect(success.label, '运行正常');
    expect(success.note, contains('最近一次运行成功'));
    expect(success.canRetry, isFalse);

    expect(partial.label, '部分失败');
    expect(partial.note, contains('入库 3 条'));
    expect(partial.note, contains('失败 1 条'));
    expect(partial.latestLog, contains('运行摘要'));
    expect(partial.canRetry, isTrue);

    expect(connectionFailure.label, '连接失败');
    expect(connectionFailure.note, contains('未连通源站'));
    expect(connectionFailure.latestLog, contains('Connection reset'));
    expect(connectionFailure.canRetry, isTrue);

    expect(parseFailure.label, '解析失败');
    expect(parseFailure.note, contains('解析规则'));
    expect(parseFailure.canRetry, isTrue);

    expect(stale.label, '已暂停');
    expect(stale.canRetry, isFalse);

    expect(manual.label, '人工登记');
    expect(manual.canRetry, isFalse);
  });
}
