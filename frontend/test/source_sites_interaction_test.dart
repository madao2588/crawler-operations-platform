import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:pharma_bid_monitor_frontend/core/network/api_client.dart';
import 'package:pharma_bid_monitor_frontend/core/theme/app_theme.dart';
import 'package:pharma_bid_monitor_frontend/features/source_sites/presentation/pages/source_sites_page.dart';
import 'package:pharma_bid_monitor_frontend/features/system_management/data/models/task_models.dart';
import 'package:pharma_bid_monitor_frontend/features/system_management/data/models/task_template_models.dart';
import 'package:pharma_bid_monitor_frontend/features/system_management/data/repositories/http_template_repository.dart';
import 'package:pharma_bid_monitor_frontend/features/system_management/data/repositories/task_repository.dart';
import 'package:pharma_bid_monitor_frontend/shared/models/page_data.dart';

void main() {
  const government = TaskTemplateModel(
    id: 'wechat_k_innovation',
    label: '政府通知模板',
    name: '公众号线索登记',
    startUrl: 'https://gov.example.com',
    cronExpr: '0 */6 * * *',
    parserRules: '{"collection_mode":"manual"}',
    enabled: true,
    description: '采集政府申报通知',
    tags: ['政府', '申报'],
    usageCount: 2,
    lastUsedAt: null,
  );
  const meeting = TaskTemplateModel(
    id: 'meeting',
    label: '行业会议模板',
    name: '会议任务',
    startUrl: 'https://meeting.example.com',
    cronExpr: '0 */12 * * *',
    parserRules: null,
    enabled: true,
    description: '采集行业会议',
    tags: ['会议'],
    usageCount: 1,
    lastUsedAt: null,
  );
  const authorized = TaskTemplateModel(
    id: 'pharnexcloud_drug_database',
    label: '摩熵医药数据库',
    name: '竞品研发数据库入口',
    startUrl: 'https://vip.pharnexcloud.com/database/research',
    cronExpr: '0 10 * * *',
    parserRules: null,
    enabled: false,
    description: '数据库类来源涉及账号授权，默认仅登记入口。',
    tags: ['竞品信息', '数据库'],
    usageCount: 0,
    lastUsedAt: null,
  );
  const automated = TaskTemplateModel(
    id: 'pubmed_literature',
    label: 'PubMed 文献',
    name: 'PubMed 竞品文献入口',
    startUrl: 'https://pubmed.ncbi.nlm.nih.gov/',
    cronExpr: '0 10 * * *',
    parserRules:
        '{"query":"glioblastoma","metadata":{"kind":"competitor_intelligence"}}',
    enabled: true,
    description: '通过官方接口自动跟踪竞品文献。',
    tags: ['竞品信息', 'PubMed'],
    usageCount: 0,
    lastUsedAt: null,
  );
  const partialTemplate = TaskTemplateModel(
    id: 'meeting_partial',
    label: '会议摘要',
    name: '会议摘要入口',
    startUrl: 'https://partial.example.com',
    cronExpr: '0 */6 * * *',
    parserRules: '{"collection_mode":"automatic"}',
    enabled: true,
    description: '自动采集会议摘要',
    tags: ['会议'],
    usageCount: 0,
    lastUsedAt: null,
  );
  const parseTemplate = TaskTemplateModel(
    id: 'parse_source',
    label: '规则解析源',
    name: '规则解析源任务',
    startUrl: 'https://parse.example.com',
    cronExpr: '0 */6 * * *',
    parserRules: '{"collection_mode":"automatic"}',
    enabled: true,
    description: '验证解析规则是否稳定。',
    tags: ['解析'],
    usageCount: 0,
    lastUsedAt: null,
  );
  const connectionTemplate = TaskTemplateModel(
    id: 'connection_source',
    label: '网络依赖源',
    name: '网络依赖源任务',
    startUrl: 'https://network.example.com',
    cronExpr: '0 */6 * * *',
    parserRules: '{"collection_mode":"automatic"}',
    enabled: true,
    description: '验证连接失败提示。',
    tags: ['网络'],
    usageCount: 0,
    lastUsedAt: null,
  );
  late ApiClient apiClient;
  late HttpTemplateRepository repository;
  late FakeTaskRepository taskRepository;
  var usedTemplates = <TaskTemplateModel>[];
  Completer<http.Response>? pendingUseResponse;
  Completer<http.Response>? pendingCollectionResponse;
  Completer<http.Response>? pendingDeleteResponse;
  var useRequestCount = 0;
  var collectionRequestCount = 0;
  var deleteRequestCount = 0;

  setUp(() {
    usedTemplates = [];
    pendingUseResponse = null;
    pendingCollectionResponse = null;
    pendingDeleteResponse = null;
    useRequestCount = 0;
    collectionRequestCount = 0;
    deleteRequestCount = 0;
    taskRepository = FakeTaskRepository(
      tasks: const <TaskListItemModel>[],
      logsByTaskId: const <int, List<TaskLogItemModel>>{},
      summaryLogsByTaskId: const <int, List<TaskLogItemModel>>{},
    );
    final mock = MockClient((request) async {
      if (request.method == 'POST' &&
          request.url.path == '/v1/templates/tasks/wechat_k_innovation/use') {
        useRequestCount += 1;
        if (pendingUseResponse != null) {
          return pendingUseResponse!.future;
        }
        return http.Response(
          jsonEncode({
            'code': 0,
            'message': 'success',
            'data': government.toJson(),
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (request.method == 'POST' &&
          request.url.path ==
              '/v1/templates/tasks/wechat_k_innovation/collect') {
        collectionRequestCount += 1;
        if (pendingCollectionResponse != null) {
          return pendingCollectionResponse!.future;
        }
        return http.Response(
          jsonEncode({
            'code': 0,
            'message': 'success',
            'data': {
              'source_id': 'wechat_k_innovation',
              'source_url': 'https://mp.weixin.qq.com/s/article',
              'status': 'stored',
              'notice_id': 88,
            },
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (request.method == 'DELETE' &&
          request.url.path == '/v1/templates/tasks/wechat_k_innovation') {
        deleteRequestCount += 1;
        if (pendingDeleteResponse != null) {
          return pendingDeleteResponse!.future;
        }
      }
      return http.Response(
        jsonEncode({'code': 0, 'message': 'success', 'data': {}}),
        200,
        headers: {'content-type': 'application/json'},
      );
    });
    apiClient = ApiClient(baseUrl: 'http://localhost', httpClient: mock);
    repository = HttpTemplateRepository(apiClient: apiClient);
  });

  tearDown(() {
    apiClient.dispose();
  });

  Future<void> pumpPage(
    WidgetTester tester, {
    List<TaskTemplateModel> templates = const [
      government,
      meeting,
      authorized,
      automated,
    ],
    FakeTaskRepository? injectedTaskRepository,
  }) async {
    tester.view.physicalSize = const Size(1440, 2600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: Scaffold(
          body: SourceSitesPage(
            templates: templates,
            templateRepository: repository,
            taskRepository: injectedTaskRepository ?? taskRepository,
            onTemplatesChanged: () async {},
            onUseTemplate: usedTemplates.add,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('tag click filters templates without opening the card editor',
      (tester) async {
    await pumpPage(tester);

    await tester.tap(
      find.byKey(
        const Key('source-template-tag-wechat_k_innovation-政府'),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('筛选标签：政府'), findsOneWidget);
    expect(find.text('政府通知模板'), findsOneWidget);
    expect(find.text('行业会议模板'), findsNothing);
    expect(find.text('编辑模板'), findsNothing);
    expect(
      tester
          .getSize(
            find.byKey(
              const Key('source-template-tag-wechat_k_innovation-政府'),
            ),
          )
          .height,
      greaterThanOrEqualTo(44),
    );
  });

  testWidgets(
      'card opens editor but nested use and delete controls stay independent',
      (tester) async {
    await pumpPage(tester);

    await tester.tap(
      find.byKey(const Key('source-template-card-wechat_k_innovation')),
    );
    await tester.pumpAndSettle();
    expect(find.text('编辑模板'), findsOneWidget);
    await tester.tap(find.text('取消'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('使用此模板').first);
    await tester.pumpAndSettle();
    expect(usedTemplates, [government]);
    expect(find.text('编辑模板'), findsNothing);

    await tester.tap(find.text('删除').first);
    await tester.pumpAndSettle();
    expect(find.text('删除模板？'), findsOneWidget);
    expect(find.text('编辑模板'), findsNothing);
  });

  testWidgets(
      'use, collect, and delete expose disabled progress states while pending',
      (tester) async {
    await pumpPage(tester);

    pendingUseResponse = Completer<http.Response>();
    final useButton = find.byKey(
      const Key('source-template-use-wechat_k_innovation'),
    );
    await tester.tap(useButton);
    await tester.pump();

    expect(useRequestCount, 1);
    expect(tester.widget<FilledButton>(useButton).onPressed, isNull);
    expect(
      find.descendant(
        of: useButton,
        matching: find.byType(CircularProgressIndicator),
      ),
      findsOneWidget,
    );
    await tester.tap(useButton);
    await tester.pump();
    expect(useRequestCount, 1);

    pendingUseResponse!.complete(
      http.Response(
        jsonEncode({
          'code': 0,
          'message': 'success',
          'data': government.toJson(),
        }),
        200,
        headers: {'content-type': 'application/json'},
      ),
    );
    await tester.pumpAndSettle();

    pendingCollectionResponse = Completer<http.Response>();
    final collectButton = find.byKey(
      const Key('source-template-collect-wechat_k_innovation'),
    );
    await tester.tap(collectButton);
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byType(TextFormField).last,
      'https://mp.weixin.qq.com/s/article',
    );
    await tester.tap(find.text('采集文章'));
    await tester.pump();

    expect(collectionRequestCount, 1);
    expect(tester.widget<FilledButton>(collectButton).onPressed, isNull);
    expect(
      find.descendant(
        of: collectButton,
        matching: find.byType(CircularProgressIndicator),
      ),
      findsOneWidget,
    );
    await tester.tap(collectButton);
    await tester.pump();
    expect(collectionRequestCount, 1);

    pendingCollectionResponse!.complete(
      http.Response(
        jsonEncode({
          'code': 0,
          'message': 'success',
          'data': {
            'source_id': 'wechat_k_innovation',
            'source_url': 'https://mp.weixin.qq.com/s/article',
            'status': 'stored',
            'notice_id': 88,
          },
        }),
        200,
        headers: {'content-type': 'application/json'},
      ),
    );
    await tester.pumpAndSettle();

    await pumpPage(tester);
    pendingDeleteResponse = Completer<http.Response>();
    final deleteButton = find.byKey(
      const Key('source-template-delete-wechat_k_innovation'),
    );
    expect(tester.widget<OutlinedButton>(deleteButton).onPressed, isNotNull);
    await tester.tap(deleteButton);
    await tester.pumpAndSettle();
    expect(find.text('删除模板？'), findsOneWidget);
    await tester.tap(find.widgetWithText(FilledButton, '删除'));
    await tester.pump();

    expect(deleteRequestCount, 1);
    expect(tester.widget<OutlinedButton>(deleteButton).onPressed, isNull);
    expect(
      find.descendant(
        of: deleteButton,
        matching: find.byType(CircularProgressIndicator),
      ),
      findsOneWidget,
    );
    await tester.tap(deleteButton);
    await tester.pump();
    expect(deleteRequestCount, 1);

    pendingDeleteResponse!.complete(
      http.Response(
        jsonEncode({'code': 0, 'message': 'success', 'data': null}),
        200,
        headers: {'content-type': 'application/json'},
      ),
    );
    await tester.pumpAndSettle();
  });

  testWidgets('cards render real task health with latest success, logs, and retry',
      (tester) async {
    taskRepository = FakeTaskRepository(
      tasks: const <TaskListItemModel>[
        TaskListItemModel(
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
        TaskListItemModel(
          id: 8,
          name: '会议摘要入口',
          startUrl: 'https://partial.example.com',
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
        TaskListItemModel(
          id: 9,
          name: '规则解析源任务',
          startUrl: 'https://parse.example.com',
          parserRules: '{"collection_mode":"automatic"}',
          cronExpr: '0 */6 * * *',
          status: 1,
          lastRunStatus: 'failed',
          lastRunAt: '2026-07-30T09:00:00Z',
          lastSuccessAt: '2026-07-29T09:00:00Z',
          lastErrorMessage: 'Parser failed to extract content from detail page',
          createdAt: '2026-07-01T00:00:00Z',
        ),
        TaskListItemModel(
          id: 10,
          name: '网络依赖源任务',
          startUrl: 'https://network.example.com',
          parserRules: '{"collection_mode":"automatic"}',
          cronExpr: '0 */6 * * *',
          status: 1,
          lastRunStatus: 'failed',
          lastRunAt: '2026-07-30T08:00:00Z',
          lastSuccessAt: '2026-07-29T08:00:00Z',
          lastErrorMessage: 'Connection reset by peer while fetching source page',
          createdAt: '2026-07-01T00:00:00Z',
        ),
      ],
      logsByTaskId: const <int, List<TaskLogItemModel>>{
        9: <TaskLogItemModel>[
          TaskLogItemModel(
            id: 91,
            taskId: 9,
            level: 'ERROR',
            message: 'Task 9 execution failed',
            errorStack: 'Parser failed to extract content from detail page',
            runSummary: null,
            createdAt: '2026-07-30T09:00:02Z',
          ),
        ],
        10: <TaskLogItemModel>[
          TaskLogItemModel(
            id: 101,
            taskId: 10,
            level: 'ERROR',
            message: 'Task 10 execution failed',
            errorStack: 'Connection reset by peer while fetching source page',
            runSummary: null,
            createdAt: '2026-07-30T08:00:02Z',
          ),
        ],
      },
      summaryLogsByTaskId: const <int, List<TaskLogItemModel>>{
        8: <TaskLogItemModel>[
          TaskLogItemModel(
            id: 81,
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
        ],
      },
      runTaskResponses: <int, Future<TaskRunResultModel>>{
        9: Completer<TaskRunResultModel>().future,
      },
    );

    await pumpPage(
      tester,
      templates: const <TaskTemplateModel>[
        automated,
        partialTemplate,
        parseTemplate,
        connectionTemplate,
      ],
      injectedTaskRepository: taskRepository,
    );

    expect(
      _textData(tester, const Key('source-template-status-label-pubmed_literature')),
      '运行正常',
    );
    expect(
      _textData(tester, const Key('source-template-status-label-meeting_partial')),
      '部分失败',
    );
    expect(
      _textData(tester, const Key('source-template-status-label-parse_source')),
      '解析失败',
    );
    await tester.scrollUntilVisible(
      find.byKey(const Key('source-template-card-connection_source')),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    expect(
      _textData(tester, const Key('source-template-status-label-connection_source')),
      '连接失败',
    );
    expect(
      _textData(tester, const Key('source-template-status-note-meeting_partial')),
      contains('入库 3 条'),
    );
    expect(
      find.descendant(
        of: find.byKey(const Key('source-template-last-success-pubmed_literature')),
        matching: find.textContaining('2026-07-30'),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: find.byKey(const Key('source-template-latest-log-connection_source')),
        matching: find.textContaining('Connection reset'),
      ),
      findsOneWidget,
    );

    final retryButton = find.byKey(const Key('source-template-retry-parse_source'));
    expect(retryButton, findsOneWidget);
    await tester.tap(retryButton);
    await tester.pump();

    expect(taskRepository.runTaskIds, [9]);
    expect(tester.widget<FilledButton>(retryButton).onPressed, isNull);
    expect(
      find.descendant(
        of: retryButton,
        matching: find.byType(CircularProgressIndicator),
      ),
      findsOneWidget,
    );
  });
}

String? _textData(WidgetTester tester, Key key) {
  return tester.widget<Text>(find.byKey(key)).data;
}

class FakeTaskRepository implements TaskRepository {
  final List<TaskListItemModel> tasks;
  final Map<int, List<TaskLogItemModel>> logsByTaskId;
  final Map<int, List<TaskLogItemModel>> summaryLogsByTaskId;
  final Map<int, Future<TaskRunResultModel>> runTaskResponses;
  final List<int> runTaskIds = <int>[];

  FakeTaskRepository({
    required this.tasks,
    required this.logsByTaskId,
    required this.summaryLogsByTaskId,
    Map<int, Future<TaskRunResultModel>>? runTaskResponses,
  }) : runTaskResponses = runTaskResponses ?? <int, Future<TaskRunResultModel>>{};

  @override
  Future<List<TaskListItemModel>> fetchTasksByNames(Iterable<String> names) async {
    final targetNames = names.map((name) => name.trim()).toSet();
    return tasks.where((task) => targetNames.contains(task.name.trim())).toList();
  }

  @override
  Future<PageData<TaskListItemModel>> fetchTasks({
    int page = 1,
    int pageSize = 20,
    String? search,
    String enabled = 'all',
    String lastRun = 'all',
    String sortBy = 'id',
    String sortDir = 'desc',
  }) async {
    return PageData<TaskListItemModel>(
      items: tasks,
      total: tasks.length,
      page: page,
      pageSize: pageSize,
    );
  }

  @override
  Future<bool> hasActiveOrQueuedTasksGlobally() async => false;

  @override
  Future<TaskListItemModel> createTask(TaskUpsertPayload payload) {
    throw UnimplementedError();
  }

  @override
  Future<TaskListItemModel> fetchTask(int id) {
    throw UnimplementedError();
  }

  @override
  Future<TaskListItemModel> updateTask(int id, TaskUpsertPayload payload) {
    throw UnimplementedError();
  }

  @override
  Future<void> deleteTask(int id) {
    throw UnimplementedError();
  }

  @override
  Future<TaskRunResultModel> runTask(int id) async {
    runTaskIds.add(id);
    final response = runTaskResponses[id];
    if (response != null) {
      return await response;
    }
    return const TaskRunResultModel(
      taskId: 0,
      status: 'queued',
      recoveredStaleRun: false,
    );
  }

  @override
  Future<RunAllEnabledResultModel> runAllEnabledTasks() {
    throw UnimplementedError();
  }

  @override
  Future<PageData<TaskLogItemModel>> fetchTaskLogs(
    int taskId, {
    int page = 1,
    int pageSize = 10,
    bool onlySummary = false,
  }) async {
    final source = onlySummary ? summaryLogsByTaskId : logsByTaskId;
    final items = source[taskId] ?? const <TaskLogItemModel>[];
    return PageData<TaskLogItemModel>(
      items: items.take(pageSize).toList(),
      total: items.length,
      page: page,
      pageSize: pageSize,
    );
  }

  @override
  Future<PageData<TaskLogItemModel>> fetchLogs({
    int page = 1,
    int pageSize = 20,
    int? taskId,
    String? level,
    String? messageContains,
  }) {
    throw UnimplementedError();
  }

  @override
  Future<LogSummaryModel> fetchLogSummary() {
    throw UnimplementedError();
  }
}
