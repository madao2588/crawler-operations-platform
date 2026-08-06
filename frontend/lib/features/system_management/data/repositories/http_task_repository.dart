import '../../../../core/constants/api_paths.dart';
import '../../../../core/network/api_client.dart';
import '../../../../shared/models/api_response.dart';
import '../../../../shared/models/page_data.dart';
import '../models/task_models.dart';
import 'task_repository.dart';

class HttpTaskRepository implements TaskRepository {
  final ApiClient apiClient;

  const HttpTaskRepository({
    required this.apiClient,
  });

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
    final queryParameters = <String, String>{
      'page': '$page',
      'page_size': '$pageSize',
      'enabled': enabled,
      'last_run': lastRun,
      'sort_by': sortBy,
      'sort_dir': sortDir,
    };
    if (search != null && search.trim().isNotEmpty) {
      queryParameters['search'] = search.trim();
    }
    final json = await apiClient.getJson(
      ApiPaths.tasks,
      queryParameters: queryParameters,
    );

    final response = ApiResponse<PageData<TaskListItemModel>>.fromJson(
      json,
      (rawData) => PageData<TaskListItemModel>.fromJson(
        rawData as Map<String, dynamic>? ?? {},
        TaskListItemModel.fromJson,
      ),
    );

    return response.data ??
        const PageData<TaskListItemModel>(
          items: [],
          total: 0,
          page: 1,
          pageSize: 20,
        );
  }

  @override
  Future<List<TaskListItemModel>> fetchTasksByNames(
    Iterable<String> names,
  ) async {
    final targetNames = names
        .map((name) => name.trim())
        .where((name) => name.isNotEmpty)
        .toSet();
    if (targetNames.isEmpty) {
      return const <TaskListItemModel>[];
    }

    const pageSize = 100;
    var pageNumber = 1;
    final matched = <String, TaskListItemModel>{};
    var total = 0;

    do {
      final page = await fetchTasks(
        page: pageNumber,
        pageSize: pageSize,
        sortBy: 'name',
        sortDir: 'asc',
      );
      total = page.total;
      for (final task in page.items) {
        final name = task.name.trim();
        if (targetNames.contains(name)) {
          matched[name] = task;
        }
      }
      if (matched.length == targetNames.length) {
        break;
      }
      pageNumber += 1;
    } while ((pageNumber - 1) * pageSize < total);

    return targetNames
        .where(matched.containsKey)
        .map((name) => matched[name]!)
        .toList();
  }

  @override
  Future<bool> hasActiveOrQueuedTasksGlobally() async {
    final page = await fetchTasks(
      page: 1,
      pageSize: 1,
      lastRun: 'active',
    );
    return page.total > 0;
  }

  @override
  Future<TaskListItemModel> createTask(TaskUpsertPayload payload) async {
    final json = await apiClient.postJson(
      ApiPaths.tasks,
      body: payload.toJson(),
    );
    final response = ApiResponse<TaskListItemModel>.fromJson(
      json,
      (rawData) => TaskListItemModel.fromJson(
        rawData as Map<String, dynamic>? ?? {},
      ),
    );
    return response.data ?? _emptyTask();
  }

  @override
  Future<TaskListItemModel> fetchTask(int id) async {
    final json = await apiClient.getJson(ApiPaths.taskDetail(id));
    final response = ApiResponse<TaskListItemModel>.fromJson(
      json,
      (rawData) => TaskListItemModel.fromJson(
        rawData as Map<String, dynamic>? ?? {},
      ),
    );
    return response.data ?? _emptyTask();
  }

  @override
  Future<TaskListItemModel> updateTask(
      int id, TaskUpsertPayload payload) async {
    final json = await apiClient.putJson(
      '${ApiPaths.tasks}/$id',
      body: payload.toJson(),
    );
    final response = ApiResponse<TaskListItemModel>.fromJson(
      json,
      (rawData) => TaskListItemModel.fromJson(
        rawData as Map<String, dynamic>? ?? {},
      ),
    );
    return response.data ?? _emptyTask();
  }

  @override
  Future<void> deleteTask(int id) async {
    await apiClient.deleteJson('${ApiPaths.tasks}/$id');
  }

  @override
  Future<TaskRunResultModel> runTask(int id) async {
    final json = await apiClient.postJson(ApiPaths.runTask(id));
    final response = ApiResponse<TaskRunResultModel>.fromJson(
      json,
      (rawData) => TaskRunResultModel.fromJson(
        rawData as Map<String, dynamic>? ?? {},
      ),
    );
    return response.data ??
        const TaskRunResultModel(
          taskId: 0,
          status: '',
          recoveredStaleRun: false,
        );
  }

  @override
  Future<RunAllEnabledResultModel> runAllEnabledTasks() async {
    final json = await apiClient.postJson(ApiPaths.tasksRunEnabled);
    final response = ApiResponse<RunAllEnabledResultModel>.fromJson(
      json,
      (rawData) => RunAllEnabledResultModel.fromJson(
        rawData as Map<String, dynamic>? ?? {},
      ),
    );
    return response.data ??
        const RunAllEnabledResultModel(
          queuedTaskIds: [],
          skippedTaskIds: [],
          recoveredTaskIds: [],
          quarantinedTaskIds: [],
          errors: [],
        );
  }

  @override
  Future<PageData<TaskLogItemModel>> fetchTaskLogs(
    int taskId, {
    int page = 1,
    int pageSize = 10,
    bool onlySummary = false,
  }) async {
    final queryParameters = <String, String>{
      'task_id': '$taskId',
      'page': '$page',
      'page_size': '$pageSize',
    };
    if (onlySummary) {
      queryParameters['only_summary'] = 'true';
    }
    final json = await apiClient.getJson(
      ApiPaths.logs,
      queryParameters: queryParameters,
    );
    final response = ApiResponse<PageData<TaskLogItemModel>>.fromJson(
      json,
      (rawData) => PageData<TaskLogItemModel>.fromJson(
        rawData as Map<String, dynamic>? ?? {},
        TaskLogItemModel.fromJson,
      ),
    );

    return response.data ??
        const PageData<TaskLogItemModel>(
          items: [],
          total: 0,
          page: 1,
          pageSize: 10,
        );
  }

  @override
  Future<PageData<TaskLogItemModel>> fetchLogs({
    int page = 1,
    int pageSize = 20,
    int? taskId,
    String? level,
    String? messageContains,
  }) async {
    final queryParameters = <String, String>{
      'page': '$page',
      'page_size': '$pageSize',
    };
    if (taskId != null) {
      queryParameters['task_id'] = '$taskId';
    }
    if (level != null && level.isNotEmpty) {
      queryParameters['level'] = level;
    }
    if (messageContains != null && messageContains.isNotEmpty) {
      queryParameters['message_contains'] = messageContains;
    }

    final json = await apiClient.getJson(
      ApiPaths.logs,
      queryParameters: queryParameters,
    );
    final response = ApiResponse<PageData<TaskLogItemModel>>.fromJson(
      json,
      (rawData) => PageData<TaskLogItemModel>.fromJson(
        rawData as Map<String, dynamic>? ?? {},
        TaskLogItemModel.fromJson,
      ),
    );

    return response.data ??
        const PageData<TaskLogItemModel>(
          items: [],
          total: 0,
          page: 1,
          pageSize: 20,
        );
  }

  @override
  Future<LogSummaryModel> fetchLogSummary() async {
    final json = await apiClient.getJson(ApiPaths.logSummary);
    final response = ApiResponse<LogSummaryModel>.fromJson(
      json,
      (rawData) => LogSummaryModel.fromJson(
        rawData as Map<String, dynamic>? ?? {},
      ),
    );
    return response.data ??
        const LogSummaryModel(
          totalLogs: 0,
          infoLogs: 0,
          warningLogs: 0,
          errorLogs: 0,
          failedTaskCount: 0,
        );
  }

  TaskListItemModel _emptyTask() {
    return const TaskListItemModel(
      id: 0,
      name: '',
      startUrl: '',
      parserRules: null,
      cronExpr: '',
      status: 0,
      lastRunStatus: null,
      lastRunAt: null,
      lastSuccessAt: null,
      lastErrorMessage: null,
      createdAt: '',
    );
  }
}
