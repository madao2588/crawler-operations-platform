import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pharma_bid_monitor_frontend/app/navigation/app_navigation_intent.dart';
import 'package:pharma_bid_monitor_frontend/core/network/api_client.dart';
import 'package:pharma_bid_monitor_frontend/features/system_management/data/models/task_models.dart';
import 'package:pharma_bid_monitor_frontend/features/system_management/data/repositories/http_template_repository.dart';
import 'package:pharma_bid_monitor_frontend/features/system_management/data/repositories/task_repository.dart';
import 'package:pharma_bid_monitor_frontend/features/system_management/presentation/pages/system_management_page.dart';
import 'package:pharma_bid_monitor_frontend/shared/models/page_data.dart';

void main() {
  const task = TaskListItemModel(
    id: 7,
    name: '国家药监局采集',
    startUrl: 'https://example.com/notices',
    parserRules: null,
    cronExpr: '0 */2 * * *',
    status: 1,
    lastRunStatus: 'failed',
    lastRunAt: '2026-07-29T08:00:00',
    lastSuccessAt: null,
    lastErrorMessage: 'timeout',
    createdAt: '2026-07-20T08:00:00',
  );
  const log = TaskLogItemModel(
    id: 31,
    taskId: 7,
    level: 'ERROR',
    message: '抓取请求超时',
    errorStack: null,
    runSummary: null,
    createdAt: '2026-07-29T08:01:00',
  );

  Future<void> pumpPage(
    WidgetTester tester,
    FakeTaskRepository repository, {
    SystemManagementTab initialTab = SystemManagementTab.tasks,
    String? initialTaskFilter,
    String? initialLogLevel,
    int? initialTaskId,
  }) async {
    tester.view.physicalSize = const Size(1800, 1400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData(useMaterial3: true),
        home: Scaffold(
          body: SystemManagementPage(
            initialTab: initialTab,
            initialTaskFilter: initialTaskFilter,
            initialLogLevel: initialLogLevel,
            initialTaskId: initialTaskId,
            taskRepository: repository,
            onTemplatesChanged: () async {},
            templateRepository: HttpTemplateRepository(
              apiClient: ApiClient(),
            ),
            templates: const [],
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('initial log intent applies normalized level and task filter',
      (tester) async {
    final repository =
        FakeTaskRepository(tasks: const [task], logs: const [log]);

    await pumpPage(
      tester,
      repository,
      initialTab: SystemManagementTab.logs,
      initialLogLevel: 'error',
      initialTaskId: 7,
    );

    expect(find.text('全局日志'), findsOneWidget);
    expect(repository.lastLogLevel, 'ERROR');
    expect(repository.lastLogTaskId, 7);
    expect(find.text('7'), findsWidgets);
  });

  testWidgets('task metric cards apply filters and keep a 44px hit target',
      (tester) async {
    final repository =
        FakeTaskRepository(tasks: const [task], logs: const [log]);
    await pumpPage(
      tester,
      repository,
      initialTaskFilter: 'success',
    );
    expect(repository.lastEnabled, 'all');
    expect(repository.lastRun, 'success');

    final enabledMetric = find.byKey(const ValueKey('task-metric-enabled'));
    expect(enabledMetric, findsOneWidget);
    expect(tester.getSize(enabledMetric).height, greaterThanOrEqualTo(44));

    await tester.tap(enabledMetric);
    await tester.pumpAndSettle();
    expect(repository.lastEnabled, 'enabled');
    expect(repository.lastRun, 'all');

    await tester.tap(find.byKey(const ValueKey('task-metric-failed')));
    await tester.pumpAndSettle();
    expect(repository.lastEnabled, 'all');
    expect(repository.lastRun, 'failed');
  });

  testWidgets('task row opens details while its run button stays independent',
      (tester) async {
    final repository =
        FakeTaskRepository(tasks: const [task], logs: const [log]);
    await pumpPage(tester, repository);

    await tester.tap(find.text('国家药监局采集'));
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsOneWidget);

    await tester.tap(find.text('关闭'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, '运行'));
    await tester.pump();

    expect(repository.runTaskCalls, 1);
    expect(find.byType(AlertDialog), findsNothing);
  });

  testWidgets('log metric filters by level and a task log row opens the task',
      (tester) async {
    final repository =
        FakeTaskRepository(tasks: const [task], logs: const [log]);
    await pumpPage(
      tester,
      repository,
      initialTab: SystemManagementTab.logs,
    );

    final errorMetric = find.byKey(const ValueKey('log-metric-error'));
    expect(errorMetric, findsOneWidget);
    expect(tester.getSize(errorMetric).height, greaterThanOrEqualTo(44));
    await tester.tap(errorMetric);
    await tester.pumpAndSettle();
    expect(repository.lastLogLevel, 'ERROR');

    await tester.tap(find.byKey(const ValueKey('log-row-31')));
    await tester.pumpAndSettle();
    expect(repository.fetchTaskIds, contains(7));
    expect(find.byType(AlertDialog), findsOneWidget);
  });

  testWidgets(
      'rapid task run clicks enqueue once and show a disabled progress state',
      (tester) async {
    final repository =
        FakeTaskRepository(tasks: const [task], logs: const [log]);
    await pumpPage(tester, repository);
    repository.runTaskCompleter = Completer<TaskRunResultModel>();

    final runButton = find.byKey(const ValueKey('task-run-7'));
    await tester.tap(runButton);
    await tester.tap(runButton);
    await tester.pump();

    expect(repository.runTaskCalls, 1);
    expect(tester.widget<FilledButton>(runButton).onPressed, isNull);
    expect(
      find.descendant(
        of: runButton,
        matching: find.byType(CircularProgressIndicator),
      ),
      findsOneWidget,
    );
    expect(find.text('运行中'), findsOneWidget);

    repository.runTaskCompleter!.complete(
      const TaskRunResultModel(
        taskId: 7,
        status: 'queued',
        recoveredStaleRun: false,
      ),
    );
    await tester.pumpAndSettle();

    expect(tester.widget<FilledButton>(runButton).onPressed, isNotNull);
  });

  testWidgets(
      'bulk collection disables every trigger while one request is pending',
      (tester) async {
    final repository =
        FakeTaskRepository(tasks: const [task], logs: const [log]);
    await pumpPage(tester, repository);
    repository.runAllEnabledCompleter =
        Completer<RunAllEnabledResultModel>();

    final heroTrigger = find.byKey(const ValueKey('bulk-run-hero'));
    final toolbarTrigger = find.byKey(const ValueKey('bulk-run-toolbar'));
    await tester.tap(heroTrigger);
    await tester.tap(toolbarTrigger);
    await tester.pump();

    expect(repository.runAllEnabledCalls, 1);
    expect(tester.widget<FilledButton>(heroTrigger).onPressed, isNull);
    expect(tester.widget<FilledButton>(toolbarTrigger).onPressed, isNull);
    expect(
      find.descendant(
        of: heroTrigger,
        matching: find.byType(CircularProgressIndicator),
      ),
      findsOneWidget,
    );
    expect(find.text('采集中'), findsWidgets);

    repository.runAllEnabledCompleter!.complete(
      const RunAllEnabledResultModel(
        queuedTaskIds: [],
        skippedTaskIds: [],
        recoveredTaskIds: [],
        quarantinedTaskIds: [],
        errors: [],
      ),
    );
    await tester.pumpAndSettle();

    expect(tester.widget<FilledButton>(heroTrigger).onPressed, isNotNull);
    expect(tester.widget<FilledButton>(toolbarTrigger).onPressed, isNotNull);
  });

  testWidgets('five minute task refresh never starts a collection run',
      (tester) async {
    final repository =
        FakeTaskRepository(tasks: const [task], logs: const [log]);
    await pumpPage(tester, repository);
    final fetchCallsBeforeTimer = repository.fetchTasksCalls;

    await tester.pump(const Duration(minutes: 5));
    await tester.pump();

    expect(repository.fetchTasksCalls, greaterThan(fetchCallsBeforeTimer));
    expect(repository.runAllEnabledCalls, 0);
  });

  testWidgets('rapid log refresh clicks share one request and show progress',
      (tester) async {
    final repository =
        FakeTaskRepository(tasks: const [task], logs: const [log]);
    await pumpPage(
      tester,
      repository,
      initialTab: SystemManagementTab.logs,
    );
    repository.fetchLogsCompleter =
        Completer<PageData<TaskLogItemModel>>();
    final callsBeforeRefresh = repository.fetchLogsCalls;

    final heroRefresh = find.byKey(const ValueKey('log-refresh-hero'));
    final toolbarRefresh = find.byKey(const ValueKey('log-refresh-toolbar'));
    await tester.tap(heroRefresh);
    await tester.tap(toolbarRefresh);
    await tester.pump();

    expect(repository.fetchLogsCalls, callsBeforeRefresh + 1);
    expect(tester.widget<FilledButton>(heroRefresh).onPressed, isNull);
    expect(tester.widget<FilledButton>(toolbarRefresh).onPressed, isNull);
    expect(find.text('刷新中'), findsWidgets);

    repository.fetchLogsCompleter!.complete(
      const PageData(
        items: [log],
        total: 1,
        page: 1,
        pageSize: 20,
      ),
    );
    await tester.pumpAndSettle();

    expect(tester.widget<FilledButton>(heroRefresh).onPressed, isNotNull);
    expect(tester.widget<FilledButton>(toolbarRefresh).onPressed, isNotNull);
  });
}

class FakeTaskRepository implements TaskRepository {
  final List<TaskListItemModel> tasks;
  final List<TaskLogItemModel> logs;

  String? lastEnabled;
  String? lastRun;
  String? lastLogLevel;
  int? lastLogTaskId;
  int runTaskCalls = 0;
  int runAllEnabledCalls = 0;
  int fetchTasksCalls = 0;
  int fetchLogsCalls = 0;
  Completer<TaskRunResultModel>? runTaskCompleter;
  Completer<RunAllEnabledResultModel>? runAllEnabledCompleter;
  Completer<PageData<TaskLogItemModel>>? fetchLogsCompleter;
  final List<int> fetchTaskIds = [];

  FakeTaskRepository({
    required this.tasks,
    required this.logs,
  });

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
    fetchTasksCalls += 1;
    lastEnabled = enabled;
    this.lastRun = lastRun;
    return PageData(
      items: tasks,
      total: tasks.length,
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
    fetchLogsCalls += 1;
    lastLogTaskId = taskId;
    lastLogLevel = level;
    return fetchLogsCompleter?.future ??
        Future.value(
          PageData(
            items: logs,
            total: logs.length,
            page: page,
            pageSize: pageSize,
          ),
        );
  }

  @override
  Future<LogSummaryModel> fetchLogSummary() async {
    return const LogSummaryModel(
      totalLogs: 3,
      infoLogs: 1,
      warningLogs: 1,
      errorLogs: 1,
      failedTaskCount: 1,
    );
  }

  @override
  Future<TaskListItemModel> fetchTask(int id) async {
    fetchTaskIds.add(id);
    return tasks.firstWhere((task) => task.id == id);
  }

  @override
  Future<PageData<TaskLogItemModel>> fetchTaskLogs(
    int taskId, {
    int page = 1,
    int pageSize = 10,
    bool onlySummary = false,
  }) async {
    return PageData(
      items: logs,
      total: logs.length,
      page: page,
      pageSize: pageSize,
    );
  }

  @override
  Future<TaskRunResultModel> runTask(int id) {
    runTaskCalls += 1;
    return runTaskCompleter?.future ??
        Future.value(
          TaskRunResultModel(
            taskId: id,
            status: 'queued',
            recoveredStaleRun: false,
          ),
        );
  }

  @override
  Future<bool> hasActiveOrQueuedTasksGlobally() async => false;

  @override
  Future<RunAllEnabledResultModel> runAllEnabledTasks() {
    runAllEnabledCalls += 1;
    return runAllEnabledCompleter?.future ??
        Future.value(
          const RunAllEnabledResultModel(
            queuedTaskIds: [],
            skippedTaskIds: [],
            recoveredTaskIds: [],
            quarantinedTaskIds: [],
            errors: [],
          ),
        );
  }

  @override
  Future<TaskListItemModel> createTask(TaskUpsertPayload payload) async =>
      tasks.first;

  @override
  Future<TaskListItemModel> updateTask(
    int id,
    TaskUpsertPayload payload,
  ) async =>
      tasks.firstWhere((task) => task.id == id);

  @override
  Future<void> deleteTask(int id) async {}
}
