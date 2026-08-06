import '../../../../shared/models/page_data.dart';
import '../models/task_models.dart';

abstract class TaskRepository {
  Future<PageData<TaskListItemModel>> fetchTasks({
    int page = 1,
    int pageSize = 20,
    String? search,
    String enabled = 'all',
    String lastRun = 'all',
    String sortBy = 'id',
    String sortDir = 'desc',
  });

  /// Fetches the latest task records matching the provided task names.
  Future<List<TaskListItemModel>> fetchTasksByNames(Iterable<String> names);

  /// Whether any task is queued or running (global, ignores list filters).
  Future<bool> hasActiveOrQueuedTasksGlobally();

  Future<TaskListItemModel> createTask(TaskUpsertPayload payload);

  Future<TaskListItemModel> fetchTask(int id);

  Future<TaskListItemModel> updateTask(int id, TaskUpsertPayload payload);

  Future<void> deleteTask(int id);

  Future<TaskRunResultModel> runTask(int id);

  /// Enqueue a run for every enabled task (busy tasks are skipped).
  Future<RunAllEnabledResultModel> runAllEnabledTasks();

  Future<PageData<TaskLogItemModel>> fetchTaskLogs(
    int taskId, {
    int page = 1,
    int pageSize = 10,
    bool onlySummary = false,
  });

  Future<PageData<TaskLogItemModel>> fetchLogs({
    int page = 1,
    int pageSize = 20,
    int? taskId,
    String? level,
    String? messageContains,
  });

  Future<LogSummaryModel> fetchLogSummary();
}
