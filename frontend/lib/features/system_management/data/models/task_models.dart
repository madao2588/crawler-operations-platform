class TaskListItemModel {
  final int id;
  final String name;
  final String startUrl;
  final String? parserRules;
  final String cronExpr;
  final int status;
  final String? lastRunStatus;
  final String? lastRunAt;
  final String? lastSuccessAt;
  final String? lastErrorMessage;
  final String createdAt;

  const TaskListItemModel({
    required this.id,
    required this.name,
    required this.startUrl,
    required this.parserRules,
    required this.cronExpr,
    required this.status,
    required this.lastRunStatus,
    required this.lastRunAt,
    required this.lastSuccessAt,
    required this.lastErrorMessage,
    required this.createdAt,
  });

  bool get isEnabled => status == 1;

  factory TaskListItemModel.fromJson(Map<String, dynamic> json) {
    return TaskListItemModel(
      id: json['id'] as int? ?? 0,
      name: json['name']?.toString() ?? '',
      startUrl: json['start_url']?.toString() ?? '',
      parserRules: json['parser_rules']?.toString(),
      cronExpr: json['cron_expr']?.toString() ?? '',
      status: json['status'] as int? ?? 0,
      lastRunStatus: json['last_run_status']?.toString(),
      lastRunAt: json['last_run_at']?.toString(),
      lastSuccessAt: json['last_success_at']?.toString(),
      lastErrorMessage: json['last_error_message']?.toString(),
      createdAt: json['created_at']?.toString() ?? '',
    );
  }
}

class TaskRunResultModel {
  final int taskId;
  final String status;
  final bool recoveredStaleRun;

  const TaskRunResultModel({
    required this.taskId,
    required this.status,
    required this.recoveredStaleRun,
  });

  factory TaskRunResultModel.fromJson(Map<String, dynamic> json) {
    return TaskRunResultModel(
      taskId: json['task_id'] as int? ?? 0,
      status: json['status']?.toString() ?? '',
      recoveredStaleRun: json['recovered_stale_run'] as bool? ?? false,
    );
  }
}

class RunAllEnabledResultModel {
  final List<int> queuedTaskIds;
  final List<int> skippedTaskIds;
  final List<int> recoveredTaskIds;
  final List<int> quarantinedTaskIds;
  final List<String> errors;

  const RunAllEnabledResultModel({
    required this.queuedTaskIds,
    required this.skippedTaskIds,
    required this.recoveredTaskIds,
    required this.quarantinedTaskIds,
    required this.errors,
  });

  factory RunAllEnabledResultModel.fromJson(Map<String, dynamic> json) {
    return RunAllEnabledResultModel(
      queuedTaskIds: (json['queued_task_ids'] as List<dynamic>? ?? [])
          .map((e) => e as int)
          .toList(),
      skippedTaskIds: (json['skipped_task_ids'] as List<dynamic>? ?? [])
          .map((e) => e as int)
          .toList(),
      recoveredTaskIds: (json['recovered_task_ids'] as List<dynamic>? ?? [])
          .map((e) => e as int)
          .toList(),
      quarantinedTaskIds:
          (json['quarantined_task_ids'] as List<dynamic>? ?? [])
              .map((e) => e as int)
              .toList(),
      errors: (json['errors'] as List<dynamic>? ?? [])
          .map((e) => e.toString())
          .toList(),
    );
  }
}

class TaskUpsertPayload {
  final String name;
  final String startUrl;
  final String? parserRules;
  final String cronExpr;
  final int status;

  const TaskUpsertPayload({
    required this.name,
    required this.startUrl,
    required this.parserRules,
    required this.cronExpr,
    required this.status,
  });

  Map<String, dynamic> toJson() {
    return {
      'name': name,
      'start_url': startUrl,
      'parser_rules': parserRules,
      'cron_expr': cronExpr,
      'status': status,
    };
  }
}

class TaskLogItemModel {
  final int id;
  final int? taskId;
  final String level;
  final String message;
  final String? errorStack;
  final Map<String, dynamic>? runSummary;
  final String createdAt;

  const TaskLogItemModel({
    required this.id,
    required this.taskId,
    required this.level,
    required this.message,
    required this.errorStack,
    required this.runSummary,
    required this.createdAt,
  });

  factory TaskLogItemModel.fromJson(Map<String, dynamic> json) {
    return TaskLogItemModel(
      id: json['id'] as int? ?? 0,
      taskId: json['task_id'] as int?,
      level: json['level']?.toString() ?? '',
      message: json['message']?.toString() ?? '',
      errorStack: json['error_stack']?.toString(),
      runSummary: json['run_summary'] is Map<String, dynamic>
          ? json['run_summary'] as Map<String, dynamic>
          : null,
      createdAt: json['created_at']?.toString() ?? '',
    );
  }
}

class LogSummaryModel {
  final int totalLogs;
  final int infoLogs;
  final int warningLogs;
  final int errorLogs;
  final int failedTaskCount;

  const LogSummaryModel({
    required this.totalLogs,
    required this.infoLogs,
    required this.warningLogs,
    required this.errorLogs,
    required this.failedTaskCount,
  });

  factory LogSummaryModel.fromJson(Map<String, dynamic> json) {
    return LogSummaryModel(
      totalLogs: json['total_logs'] as int? ?? 0,
      infoLogs: json['info_logs'] as int? ?? 0,
      warningLogs: json['warning_logs'] as int? ?? 0,
      errorLogs: json['error_logs'] as int? ?? 0,
      failedTaskCount: json['failed_task_count'] as int? ?? 0,
    );
  }
}
