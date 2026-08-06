import 'dart:async';

import 'package:flutter/material.dart';

import '../../../../app/navigation/app_navigation_intent.dart';
import '../../../../core/network/api_client.dart';
import '../../../../core/utils/date_formatter.dart';
import '../../../../core/utils/user_facing_error.dart';
import '../../../../core/widgets/async_error_panel.dart';
import '../../../../core/widgets/page_chrome.dart';
import '../../../../shared/models/page_data.dart';
import '../../data/models/task_models.dart';
import '../../data/models/task_template_models.dart';
import '../../data/repositories/http_task_repository.dart';
import '../../data/repositories/task_repository.dart';
import '../../data/repositories/http_template_repository.dart';

class SystemManagementPage extends StatefulWidget {
  final SystemManagementTab initialTab;
  final String? initialTaskFilter;
  final String? initialLogLevel;
  final int? initialTaskId;
  final TaskTemplateModel? pendingTemplate;
  final VoidCallback? onPendingTemplateHandled;
  final Future<void> Function() onTemplatesChanged;
  final HttpTemplateRepository templateRepository;
  final List<TaskTemplateModel> templates;
  final TaskRepository? taskRepository;

  const SystemManagementPage({
    super.key,
    this.initialTab = SystemManagementTab.tasks,
    this.initialTaskFilter,
    this.initialLogLevel,
    this.initialTaskId,
    this.pendingTemplate,
    this.onPendingTemplateHandled,
    required this.onTemplatesChanged,
    required this.templateRepository,
    required this.templates,
    this.taskRepository,
  });

  @override
  State<SystemManagementPage> createState() => _SystemManagementPageState();
}

class _SystemManagementPageState extends State<SystemManagementPage> {
  late final TaskRepository _repository;
  late Future<PageData<TaskListItemModel>> _tasksFuture;
  late Future<PageData<TaskLogItemModel>> _logsFuture;
  late Future<LogSummaryModel> _logSummaryFuture;
  late final TextEditingController _searchController;
  late final TextEditingController _logTaskIdController;
  late final TextEditingController _logSearchController;
  late final ScrollController _taskPageScrollController;
  late final ScrollController _logPageScrollController;
  late final ScrollController _taskTableHorizontalScrollController;
  late final ScrollController _taskTableVerticalScrollController;
  Timer? _taskAutoRefreshTimer;
  Timer? _logAutoRefreshTimer;
  Timer? _listPollingTimer;
  bool _isAutoRefreshing = false;
  bool _isBulkRefreshInFlight = false;
  bool _isLogRefreshInFlight = false;
  bool _listPollInFlight = false;
  final Set<int> _runningTaskIds = <int>{};
  int _remainingPollTicks = 0;
  int _selectedTabIndex = 0;
  int _taskPage = 1;
  final int _taskPageSize = 20;
  int _logPage = 1;
  final int _logPageSize = 20;
  String _searchQuery = '';
  String _enabledFilter = 'all';
  String _resultFilter = 'all';
  String _taskSortBy = 'id';
  String _taskSortDir = 'desc';
  String _logLevelFilter = 'all';

  static const Duration _bulkPollInterval = Duration(seconds: 2);
  static const int _bulkPollAttempts = 30;

  @override
  void initState() {
    super.initState();
    _repository =
        widget.taskRepository ?? HttpTaskRepository(apiClient: ApiClient());
    _searchController = TextEditingController();
    _logTaskIdController = TextEditingController(
      text: widget.initialTab == SystemManagementTab.logs &&
              widget.initialTaskId != null
          ? '${widget.initialTaskId}'
          : '',
    );
    _logSearchController = TextEditingController();
    _taskPageScrollController = ScrollController();
    _logPageScrollController = ScrollController();
    _taskTableHorizontalScrollController = ScrollController();
    _taskTableVerticalScrollController = ScrollController();
    _selectedTabIndex = widget.initialTab.index;
    _applyTaskFilterValue(widget.initialTaskFilter);
    _logLevelFilter = _normalizeLogLevel(widget.initialLogLevel);
    _tasksFuture = _fetchTasks();
    _logsFuture = _fetchLogs();
    _logSummaryFuture = _repository.fetchLogSummary();
    _startAutoRefresh();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _consumePendingTemplateIfNeeded();
      _openInitialTaskIfNeeded();
    });
  }

  @override
  void didUpdateWidget(covariant SystemManagementPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.pendingTemplate?.id != oldWidget.pendingTemplate?.id &&
        widget.pendingTemplate != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _consumePendingTemplateIfNeeded();
      });
    }
    if (widget.initialTab != oldWidget.initialTab ||
        widget.initialTaskFilter != oldWidget.initialTaskFilter ||
        widget.initialLogLevel != oldWidget.initialLogLevel ||
        widget.initialTaskId != oldWidget.initialTaskId) {
      _applyIncomingNavigation();
    }
  }

  @override
  void dispose() {
    _searchController.dispose();
    _logTaskIdController.dispose();
    _logSearchController.dispose();
    _taskPageScrollController.dispose();
    _logPageScrollController.dispose();
    _taskTableHorizontalScrollController.dispose();
    _taskTableVerticalScrollController.dispose();
    _taskAutoRefreshTimer?.cancel();
    _logAutoRefreshTimer?.cancel();
    _listPollingTimer?.cancel();
    super.dispose();
  }

  Future<void> _refresh() async {
    setState(() {
      _tasksFuture = _fetchTasks();
    });
    await _tasksFuture;
  }

  Future<void> _refreshLogs() async {
    if (!mounted || _isLogRefreshInFlight) {
      return;
    }
    setState(() {
      _isLogRefreshInFlight = true;
      _logsFuture = _fetchLogs();
      _logSummaryFuture = _repository.fetchLogSummary();
    });
    try {
      await Future.wait([_logsFuture, _logSummaryFuture]);
    } finally {
      if (mounted) {
        setState(() {
          _isLogRefreshInFlight = false;
        });
      } else {
        _isLogRefreshInFlight = false;
      }
    }
  }

  Future<void> _waitForGlobalTasksToSettle() async {
    for (var attempt = 0; attempt < _bulkPollAttempts; attempt += 1) {
      if (!mounted) {
        return;
      }
      await _refresh();
      if (_selectedTabIndex == 1) {
        await _refreshLogs();
      }
      final stillActive = await _repository.hasActiveOrQueuedTasksGlobally();
      if (!stillActive) {
        return;
      }
      await Future<void>.delayed(_bulkPollInterval);
    }
    await _refresh();
    if (_selectedTabIndex == 1) {
      await _refreshLogs();
    }
  }

  Future<void> _triggerEnabledTasksRefresh({
    required bool showFeedback,
  }) async {
    if (_isBulkRefreshInFlight) {
      return;
    }
    if (mounted) {
      setState(() {
        _isBulkRefreshInFlight = true;
      });
    } else {
      _isBulkRefreshInFlight = true;
    }
    try {
      final result = await _repository.runAllEnabledTasks();
      if (!mounted) {
        return;
      }
      await _refresh();
      if (_selectedTabIndex == 1) {
        await _refreshLogs();
      }
      final shouldPoll =
          result.queuedTaskIds.isNotEmpty || result.skippedTaskIds.isNotEmpty;
      if (showFeedback) {
        if (result.queuedTaskIds.isNotEmpty) {
          var message = '已触发 ${result.queuedTaskIds.length} 个启用任务重新采集';
          if (result.quarantinedTaskIds.isNotEmpty) {
            message += '；已隔离 ${result.quarantinedTaskIds.length} 个失败源';
          }
          if (result.recoveredTaskIds.isNotEmpty) {
            message += '，其中 ${result.recoveredTaskIds.length} 个任务已从卡死状态恢复';
          }
          if (result.skippedTaskIds.isNotEmpty) {
            message += '；${result.skippedTaskIds.length} 个任务仍在运行中';
          }
          _showMessage('$message。');
        } else if (result.skippedTaskIds.isNotEmpty) {
          var message = '没有新任务入队，当前有 ${result.skippedTaskIds.length} 个任务仍在运行中';
          if (result.quarantinedTaskIds.isNotEmpty) {
            message += '；已隔离 ${result.quarantinedTaskIds.length} 个失败源';
          }
          _showMessage('$message，将继续等待列表刷新。');
        } else if (result.quarantinedTaskIds.isNotEmpty) {
          _showMessage(
              '已隔离 ${result.quarantinedTaskIds.length} 个失败源，本次没有其余启用任务可触发采集。');
        } else {
          _showMessage('当前没有已启用任务可触发采集。');
        }
        if (result.errors.isNotEmpty) {
          _showMessage(result.errors.join('\n'), isError: true);
        }
      }
      if (shouldPoll) {
        await _waitForGlobalTasksToSettle();
      }
    } catch (error) {
      if (showFeedback) {
        _showMessage('触发采集失败：${userFacingError(error)}', isError: true);
      }
      await _refresh();
    } finally {
      if (mounted) {
        setState(() {
          _isBulkRefreshInFlight = false;
        });
      } else {
        _isBulkRefreshInFlight = false;
      }
    }
  }

  void _startAutoRefresh() {
    _taskAutoRefreshTimer?.cancel();
    _taskAutoRefreshTimer =
        Timer.periodic(const Duration(minutes: 5), (_) async {
      if (!mounted || _isAutoRefreshing || _isBulkRefreshInFlight) {
        return;
      }
      _isAutoRefreshing = true;
      try {
        await _refresh();
      } finally {
        _isAutoRefreshing = false;
      }
    });

    _logAutoRefreshTimer?.cancel();
    _logAutoRefreshTimer =
        Timer.periodic(const Duration(seconds: 5), (_) async {
      if (!mounted || _isAutoRefreshing || _selectedTabIndex != 1) {
        return;
      }
      _isAutoRefreshing = true;
      try {
        await _refreshLogs();
      } finally {
        _isAutoRefreshing = false;
      }
    });
  }

  static const Set<String> _supportedTaskFilters = {
    'all',
    'enabled',
    'disabled',
    'active',
    'success',
    'failed',
    'never',
  };

  String _normalizeTaskFilter(String? value) {
    final normalized = value?.trim().toLowerCase() ?? 'all';
    return _supportedTaskFilters.contains(normalized) ? normalized : 'all';
  }

  String _normalizeLogLevel(String? value) {
    final normalized = value?.trim().toUpperCase() ?? 'ALL';
    return switch (normalized) {
      'INFO' || 'WARNING' || 'ERROR' => normalized,
      _ => 'all',
    };
  }

  void _applyTaskFilterValue(String? value) {
    final normalized = _normalizeTaskFilter(value);
    _enabledFilter = 'all';
    _resultFilter = 'all';
    if (normalized == 'enabled' || normalized == 'disabled') {
      _enabledFilter = normalized;
    } else if (normalized != 'all') {
      _resultFilter = normalized;
    }
  }

  void _applyIncomingNavigation() {
    final isLogsTab = widget.initialTab == SystemManagementTab.logs;
    _logTaskIdController.text = isLogsTab && widget.initialTaskId != null
        ? '${widget.initialTaskId}'
        : '';
    setState(() {
      _selectedTabIndex = widget.initialTab.index;
      _taskPage = 1;
      _logPage = 1;
      _applyTaskFilterValue(widget.initialTaskFilter);
      _logLevelFilter = _normalizeLogLevel(widget.initialLogLevel);
      _tasksFuture = _fetchTasks();
      _logsFuture = _fetchLogs();
      _logSummaryFuture = _repository.fetchLogSummary();
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _openInitialTaskIfNeeded();
    });
  }

  void _openInitialTaskIfNeeded() {
    final taskId = widget.initialTaskId;
    if (!mounted ||
        taskId == null ||
        widget.initialTab != SystemManagementTab.tasks) {
      return;
    }
    unawaited(_openTaskDetailsById(taskId));
  }

  void _selectTaskSummaryFilter(String value) {
    setState(() {
      _taskPage = 1;
      _applyTaskFilterValue(value);
      _tasksFuture = _fetchTasks();
    });
  }

  void _selectLogLevel(String value) {
    setState(() {
      _logPage = 1;
      _logLevelFilter = _normalizeLogLevel(value);
      _logsFuture = _fetchLogs();
      _logSummaryFuture = _repository.fetchLogSummary();
    });
  }

  Future<PageData<TaskListItemModel>> _fetchTasks() {
    return _repository.fetchTasks(
      page: _taskPage,
      pageSize: _taskPageSize,
      search: _searchQuery.isEmpty ? null : _searchQuery,
      enabled: _enabledFilter,
      lastRun: _resultFilter,
      sortBy: _taskSortBy,
      sortDir: _taskSortDir,
    );
  }

  bool _hasTaskFilters() {
    return _searchQuery.isNotEmpty ||
        _enabledFilter != 'all' ||
        _resultFilter != 'all' ||
        _taskSortBy != 'id' ||
        _taskSortDir != 'desc';
  }

  Future<PageData<TaskLogItemModel>> _fetchLogs() {
    final keyword = _logSearchController.text.trim();
    return _repository.fetchLogs(
      page: _logPage,
      pageSize: _logPageSize,
      taskId: _parseTaskIdFilter(),
      level: _logLevelFilter == 'all' ? null : _logLevelFilter,
      messageContains: keyword.isEmpty ? null : keyword,
    );
  }

  Future<void> _openTaskEditor([TaskListItemModel? task]) async {
    final saved = await showDialog<bool>(
      context: context,
      builder: (context) => _TaskEditorDialog(
        task: task,
        repository: _repository,
        templates: widget.templates,
      ),
    );

    if (saved == true && mounted) {
      await _refresh();
      _showMessage(task == null ? '任务已创建。' : '任务已更新。');
    }
  }

  Future<void> _openTaskEditorWithTemplate(TaskTemplateModel template) async {
    final saved = await showDialog<bool>(
      context: context,
      builder: (context) => _TaskEditorDialog(
        repository: _repository,
        initialTemplate: template,
        templates: widget.templates,
      ),
    );

    widget.onPendingTemplateHandled?.call();

    if (saved == true && mounted) {
      await _refresh();
      _showMessage('已通过模板“${template.label}”创建任务。');
    }
  }

  Future<void> _consumePendingTemplateIfNeeded() async {
    final template = widget.pendingTemplate;
    if (template == null || !mounted) {
      return;
    }
    await _openTaskEditorWithTemplate(template);
  }

  Future<void> _toggleTask(TaskListItemModel task) async {
    try {
      await _repository.updateTask(
        task.id,
        TaskUpsertPayload(
          name: task.name,
          startUrl: task.startUrl,
          parserRules: _normalizeParserRules(task.parserRules),
          cronExpr: task.cronExpr,
          status: task.isEnabled ? 0 : 1,
        ),
      );
      if (!mounted) {
        return;
      }
      await _refresh();
      _showMessage(task.isEnabled ? '任务已停用。' : '任务已启用。');
    } catch (error) {
      _showMessage('更新任务失败：${userFacingError(error)}', isError: true);
    }
  }

  Future<void> _runTask(TaskListItemModel task) {
    return _runTaskId(task.id);
  }

  Future<void> _runTaskId(
    int taskId, {
    bool refreshLogsAfterRun = false,
  }) async {
    if (_runningTaskIds.contains(taskId)) {
      return;
    }
    setState(() {
      _runningTaskIds.add(taskId);
    });
    try {
      final result = await _repository.runTask(taskId);
      if (!mounted) {
        return;
      }
      await _refresh();
      _startListPolling(taskId);
      if (refreshLogsAfterRun) {
        await _refreshLogs();
      }
      _showMessage(
        '任务 ${result.taskId} 已进入队列；将自动刷新当前任务状态直到结束。',
      );
    } catch (error) {
      _showMessage('运行任务失败：${userFacingError(error)}', isError: true);
    } finally {
      if (mounted) {
        setState(() {
          _runningTaskIds.remove(taskId);
        });
      } else {
        _runningTaskIds.remove(taskId);
      }
    }
  }

  void _startListPolling(int taskId) {
    _remainingPollTicks = 40;
    _listPollingTimer?.cancel();

    Future<void> tick() async {
      if (!mounted || _listPollInFlight) {
        return;
      }
      _listPollInFlight = true;
      try {
        await _refresh();
        _remainingPollTicks -= 1;
        final freshTask = await _repository.fetchTask(taskId);
        final status = (freshTask.lastRunStatus ?? '').toLowerCase();
        final stillActive = status == 'queued' || status == 'running';
        if (_remainingPollTicks <= 0 || !stillActive) {
          _listPollingTimer?.cancel();
          _listPollingTimer = null;
        }
      } catch (_) {
        _listPollingTimer?.cancel();
        _listPollingTimer = null;
      } finally {
        _listPollInFlight = false;
      }
    }

    unawaited(tick());
    _listPollingTimer = Timer.periodic(const Duration(seconds: 2), (_) {
      unawaited(tick());
    });
  }

  Future<void> _openTaskDetails(TaskListItemModel task) async {
    await showDialog<void>(
      context: context,
      builder: (context) => _TaskDetailsDialog(
        task: task,
        repository: _repository,
      ),
    );
  }

  Future<void> _deleteTask(TaskListItemModel task) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('删除任务？'),
        content: Text('这会永久删除“${task.name}”。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('删除'),
          ),
        ],
      ),
    );

    if (confirmed != true) {
      return;
    }

    try {
      await _repository.deleteTask(task.id);
      if (!mounted) {
        return;
      }
      await _refresh();
      _showMessage('任务已删除。');
    } catch (error) {
      _showMessage('删除任务失败：${userFacingError(error)}', isError: true);
    }
  }

  Future<void> _openTaskDetailsById(int taskId) async {
    try {
      final task = await _repository.fetchTask(taskId);
      if (!mounted) {
        return;
      }
      await _openTaskDetails(task);
    } catch (error) {
      _showMessage('打开任务详情失败：${userFacingError(error)}', isError: true);
    }
  }

  Future<void> _openTaskEditorById(int taskId) async {
    try {
      final task = await _repository.fetchTask(taskId);
      if (!mounted) {
        return;
      }
      await _openTaskEditor(task);
    } catch (error) {
      _showMessage('打开任务编辑器失败：${userFacingError(error)}', isError: true);
    }
  }

  Future<void> _runTaskById(int taskId) async {
    await _runTaskId(taskId, refreshLogsAfterRun: true);
  }

  Future<void> _saveTaskAsTemplate(TaskListItemModel task) async {
    final saved = await showDialog<bool>(
      context: context,
      builder: (context) => _SaveTaskAsTemplateDialog(
        task: task,
        repository: widget.templateRepository,
      ),
    );

    if (saved == true && mounted) {
      await widget.onTemplatesChanged();
      if (!mounted) {
        return;
      }
      _showMessage('已根据“${task.name}”生成模板。');
    }
  }

  void _showMessage(String message, {bool isError = false}) {
    if (!mounted) {
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: isError ? const Color(0xFFB3261E) : null,
      ),
    );
  }

  String? _normalizeParserRules(String? value) {
    final trimmed = value?.trim();
    if (trimmed == null || trimmed.isEmpty) {
      return null;
    }
    return trimmed;
  }

  int? _parseTaskIdFilter() {
    final value = _logTaskIdController.text.trim();
    if (value.isEmpty) {
      return null;
    }
    return int.tryParse(value);
  }

  @override
  Widget build(BuildContext context) {
    return AppPageFrame(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _SystemManagementPageHero(
            templateCount: widget.templates.length,
            onRefreshTasks: () =>
                _triggerEnabledTasksRefresh(showFeedback: true),
            onRefreshLogs: _refreshLogs,
            isRefreshingTasks: _isBulkRefreshInFlight,
            isRefreshingLogs: _isLogRefreshInFlight,
          ),
          const SizedBox(height: 16),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: SegmentedButton<int>(
                segments: const [
                  ButtonSegment<int>(value: 0, label: Text('任务')),
                  ButtonSegment<int>(value: 1, label: Text('日志')),
                ],
                selected: {_selectedTabIndex},
                onSelectionChanged: (value) {
                  setState(() {
                    _selectedTabIndex = value.first;
                  });
                },
              ),
            ),
          ),
          const SizedBox(height: 16),
          Expanded(
            child: _selectedTabIndex == 0 ? _buildTasksTab() : _buildLogsTab(),
          ),
        ],
      ),
    );
  }

  Widget _buildTasksTab() {
    return FutureBuilder<PageData<TaskListItemModel>>(
      future: _tasksFuture,
      builder: (context, snapshot) {
        return LayoutBuilder(
          builder: (context, constraints) {
            final isCompact = constraints.maxWidth < 760;
            final viewportHeight = MediaQuery.sizeOf(context).height;
            final bodyHeight = (viewportHeight * 0.56).clamp(360.0, 620.0);
            final header = isCompact
                ? Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '任务管理',
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                      const SizedBox(height: 12),
                      Wrap(
                        spacing: 12,
                        runSpacing: 12,
                        children: [
                          FilledButton.icon(
                            onPressed: () => _openTaskEditor(),
                            icon: const Icon(Icons.add),
                            label: const Text('新建任务'),
                          ),
                          FilledButton.tonalIcon(
                            key: const ValueKey('bulk-run-toolbar'),
                            onPressed: _isBulkRefreshInFlight
                                ? null
                                : () => _triggerEnabledTasksRefresh(
                                      showFeedback: true,
                                    ),
                            icon: _AsyncButtonIcon(
                              isLoading: _isBulkRefreshInFlight,
                              idleIcon: Icons.refresh,
                              progressLabel: '正在触发采集',
                            ),
                            label: Text(
                              _isBulkRefreshInFlight ? '采集中' : '触发采集',
                            ),
                          ),
                        ],
                      ),
                    ],
                  )
                : Row(
                    children: [
                      Text(
                        '任务管理',
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                      const Spacer(),
                      FilledButton.icon(
                        onPressed: () => _openTaskEditor(),
                        icon: const Icon(Icons.add),
                        label: const Text('新建任务'),
                      ),
                      const SizedBox(width: 12),
                      FilledButton.tonalIcon(
                        key: const ValueKey('bulk-run-toolbar'),
                        onPressed: _isBulkRefreshInFlight
                            ? null
                            : () => _triggerEnabledTasksRefresh(
                                  showFeedback: true,
                                ),
                        icon: _AsyncButtonIcon(
                          isLoading: _isBulkRefreshInFlight,
                          idleIcon: Icons.refresh,
                          progressLabel: '正在触发采集',
                        ),
                        label: Text(
                          _isBulkRefreshInFlight ? '采集中' : '触发采集',
                        ),
                      ),
                    ],
                  );

            final content = [
              header,
              const SizedBox(height: 12),
              Text(
                '创建采集任务、调整调度周期，并在需要时手动触发执行。',
                style: Theme.of(context).textTheme.bodyMedium,
              ),
              if (_listPollingTimer != null) ...[
                const SizedBox(height: 8),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  decoration: BoxDecoration(
                    color: const Color(0xFFE8F0FE),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Text(
                    '最近有任务正在执行，列表会自动刷新。',
                  ),
                ),
              ],
              const SizedBox(height: 16),
              _TaskSummaryBar(
                pageTasks: snapshot.data?.items ?? const <TaskListItemModel>[],
                filteredTotal: snapshot.data?.total ?? 0,
                enabledFilter: _enabledFilter,
                resultFilter: _resultFilter,
                onFilterSelected: _selectTaskSummaryFilter,
              ),
              const SizedBox(height: 16),
              _TaskFilterBar(
                searchController: _searchController,
                enabledFilter: _enabledFilter,
                resultFilter: _resultFilter,
                sortBy: _taskSortBy,
                sortDir: _taskSortDir,
                onSearchChanged: (value) {
                  setState(() {
                    _taskPage = 1;
                    _searchQuery = value.trim().toLowerCase();
                    _tasksFuture = _fetchTasks();
                  });
                },
                onEnabledFilterChanged: (value) {
                  setState(() {
                    _taskPage = 1;
                    _enabledFilter = value;
                    _tasksFuture = _fetchTasks();
                  });
                },
                onResultFilterChanged: (value) {
                  setState(() {
                    _taskPage = 1;
                    _resultFilter = value;
                    _tasksFuture = _fetchTasks();
                  });
                },
                onSortByChanged: (value) {
                  setState(() {
                    _taskPage = 1;
                    _taskSortBy = value;
                    _tasksFuture = _fetchTasks();
                  });
                },
                onSortDirChanged: (value) {
                  setState(() {
                    _taskPage = 1;
                    _taskSortDir = value;
                    _tasksFuture = _fetchTasks();
                  });
                },
                onClear: () {
                  _searchController.clear();
                  setState(() {
                    _taskPage = 1;
                    _searchQuery = '';
                    _enabledFilter = 'all';
                    _resultFilter = 'all';
                    _taskSortBy = 'id';
                    _taskSortDir = 'desc';
                    _tasksFuture = _fetchTasks();
                  });
                },
              ),
              const SizedBox(height: 16),
              SizedBox(
                height: bodyHeight,
                child: _buildBody(snapshot),
              ),
              const SizedBox(height: 12),
              _PaginationBar(
                page: snapshot.data?.page ?? _taskPage,
                pageSize: snapshot.data?.pageSize ?? _taskPageSize,
                total: snapshot.data?.total ?? 0,
                onPrevious: _taskPage > 1
                    ? () {
                        setState(() {
                          _taskPage -= 1;
                          _tasksFuture = _fetchTasks();
                        });
                      }
                    : null,
                onNext: ((snapshot.data?.page ?? _taskPage) *
                            (snapshot.data?.pageSize ?? _taskPageSize) <
                        (snapshot.data?.total ?? 0))
                    ? () {
                        setState(() {
                          _taskPage += 1;
                          _tasksFuture = _fetchTasks();
                        });
                      }
                    : null,
              ),
            ];

            return Scrollbar(
              controller: _taskPageScrollController,
              thumbVisibility: true,
              child: ListView(
                controller: _taskPageScrollController,
                padding: EdgeInsets.zero,
                children: content,
              ),
            );
          },
        );
      },
    );
  }

  Widget _buildLogsTab() {
    return FutureBuilder<PageData<TaskLogItemModel>>(
      future: _logsFuture,
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          return AsyncErrorPanel(
            error: snapshot.error!,
            title: '加载日志列表失败',
            onRetry: () {
              setState(() {
                _logsFuture = _fetchLogs();
                _logSummaryFuture = _repository.fetchLogSummary();
              });
            },
          );
        }
        final filteredLogs = snapshot.data?.items ?? const <TaskLogItemModel>[];
        return FutureBuilder<LogSummaryModel>(
          future: _logSummaryFuture,
          builder: (context, summarySnapshot) {
            final summary = summarySnapshot.data;
            return LayoutBuilder(
              builder: (context, constraints) {
                final isCompact = constraints.maxWidth < 760;
                final viewportHeight = MediaQuery.sizeOf(context).height;
                final bodyHeight = (viewportHeight * 0.56).clamp(360.0, 620.0);

                final header = isCompact
                    ? Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '全局日志',
                            style: Theme.of(context).textTheme.titleLarge,
                          ),
                          const SizedBox(height: 12),
                          FilledButton.tonalIcon(
                            key: const ValueKey('log-refresh-toolbar'),
                            onPressed:
                                _isLogRefreshInFlight ? null : _refreshLogs,
                            icon: _AsyncButtonIcon(
                              isLoading: _isLogRefreshInFlight,
                              idleIcon: Icons.refresh,
                              progressLabel: '正在刷新日志',
                            ),
                            label: Text(
                              _isLogRefreshInFlight ? '刷新中' : '刷新',
                            ),
                          ),
                        ],
                      )
                    : Row(
                        children: [
                          Text(
                            '全局日志',
                            style: Theme.of(context).textTheme.titleLarge,
                          ),
                          const Spacer(),
                          FilledButton.tonalIcon(
                            key: const ValueKey('log-refresh-toolbar'),
                            onPressed:
                                _isLogRefreshInFlight ? null : _refreshLogs,
                            icon: _AsyncButtonIcon(
                              isLoading: _isLogRefreshInFlight,
                              idleIcon: Icons.refresh,
                              progressLabel: '正在刷新日志',
                            ),
                            label: Text(
                              _isLogRefreshInFlight ? '刷新中' : '刷新',
                            ),
                          ),
                        ],
                      );

                final content = [
                  header,
                  const SizedBox(height: 12),
                  Text(
                    '查看全部任务的警告、错误与执行历史，快速定位异常。',
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                  const SizedBox(height: 16),
                  _LogSummaryBar(
                    summary: summary,
                    selectedLevel: _logLevelFilter,
                    onLevelSelected: _selectLogLevel,
                  ),
                  const SizedBox(height: 16),
                  _FailedTaskActionBar(
                    logs: filteredLogs,
                    onOpenTask: _openTaskDetailsById,
                    onEditTask: _openTaskEditorById,
                    onRunTask: _runTaskById,
                    runningTaskIds: _runningTaskIds,
                  ),
                  const SizedBox(height: 16),
                  _LogFilterBar(
                    taskIdController: _logTaskIdController,
                    searchController: _logSearchController,
                    levelFilter: _logLevelFilter,
                    onLevelChanged: (value) {
                      setState(() {
                        _logPage = 1;
                        _logLevelFilter = value;
                      });
                      _refreshLogs();
                    },
                    onApplyFilters: () {
                      setState(() {
                        _logPage = 1;
                      });
                      return _refreshLogs();
                    },
                    isApplying: _isLogRefreshInFlight,
                    onClear: () {
                      _logTaskIdController.clear();
                      _logSearchController.clear();
                      setState(() {
                        _logPage = 1;
                        _logLevelFilter = 'all';
                        _logsFuture = _fetchLogs();
                        _logSummaryFuture = _repository.fetchLogSummary();
                      });
                    },
                  ),
                  const SizedBox(height: 16),
                  SizedBox(
                    height: bodyHeight,
                    child: _buildLogsBody(snapshot, filteredLogs),
                  ),
                  const SizedBox(height: 12),
                  _PaginationBar(
                    page: snapshot.data?.page ?? _logPage,
                    pageSize: snapshot.data?.pageSize ?? _logPageSize,
                    total: snapshot.data?.total ?? 0,
                    onPrevious: _logPage > 1
                        ? () {
                            setState(() {
                              _logPage -= 1;
                              _logsFuture = _fetchLogs();
                            });
                          }
                        : null,
                    onNext: ((snapshot.data?.page ?? _logPage) *
                                (snapshot.data?.pageSize ?? _logPageSize) <
                            (snapshot.data?.total ?? 0))
                        ? () {
                            setState(() {
                              _logPage += 1;
                              _logsFuture = _fetchLogs();
                            });
                          }
                        : null,
                  ),
                ];

                return Scrollbar(
                  controller: _logPageScrollController,
                  thumbVisibility: true,
                  child: ListView(
                    controller: _logPageScrollController,
                    padding: EdgeInsets.zero,
                    children: content,
                  ),
                );
              },
            );
          },
        );
      },
    );
  }

  Widget _buildBody(AsyncSnapshot<PageData<TaskListItemModel>> snapshot) {
    if (snapshot.connectionState == ConnectionState.waiting) {
      return const Card(
        child: Padding(
          padding: EdgeInsets.all(28),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              CircularProgressIndicator(),
              SizedBox(height: 16),
              Text('正在刷新任务列表...'),
            ],
          ),
        ),
      );
    }

    if (snapshot.hasError) {
      return AsyncErrorPanel(
        error: snapshot.error!,
        title: '加载任务列表失败',
        onRetry: () {
          setState(() {
            _tasksFuture = _fetchTasks();
          });
        },
      );
    }

    final data = snapshot.data;
    final pageTasks = data?.items ?? const <TaskListItemModel>[];
    final total = data?.total ?? 0;
    if (total == 0) {
      final filtered = _hasTaskFilters();
      return Card(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                filtered ? '无符合条件的任务' : '暂无任务',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 8),
              Text(
                filtered
                    ? '调整搜索关键词或筛选条件，或清空筛选后查看全部任务。'
                    : '先创建一个包含起始地址和定时表达式的采集任务。',
              ),
              const SizedBox(height: 16),
              if (filtered)
                OutlinedButton.icon(
                  onPressed: () {
                    _searchController.clear();
                    setState(() {
                      _taskPage = 1;
                      _searchQuery = '';
                      _enabledFilter = 'all';
                      _resultFilter = 'all';
                      _taskSortBy = 'id';
                      _taskSortDir = 'desc';
                      _tasksFuture = _fetchTasks();
                    });
                  },
                  icon: const Icon(Icons.filter_alt_off),
                  label: const Text('清空筛选'),
                )
              else
                FilledButton.icon(
                  onPressed: () => _openTaskEditor(),
                  icon: const Icon(Icons.add),
                  label: const Text('创建第一个任务'),
                ),
            ],
          ),
        ),
      );
    }

    return Card(
      child: Scrollbar(
        controller: _taskTableVerticalScrollController,
        thumbVisibility: true,
        child: SingleChildScrollView(
          controller: _taskTableVerticalScrollController,
          child: Scrollbar(
            controller: _taskTableHorizontalScrollController,
            thumbVisibility: true,
            trackVisibility: true,
            notificationPredicate: (notification) =>
                notification.metrics.axis == Axis.horizontal,
            scrollbarOrientation: ScrollbarOrientation.bottom,
            child: SingleChildScrollView(
              controller: _taskTableHorizontalScrollController,
              scrollDirection: Axis.horizontal,
              child: Padding(
                padding: const EdgeInsets.all(8),
                child: ConstrainedBox(
                  constraints: const BoxConstraints(minWidth: 1180),
                  child: DataTable(
                    columnSpacing: 20,
                    columns: const [
                      DataColumn(label: Text('名称')),
                      DataColumn(label: Text('地址')),
                      DataColumn(label: Text('定时')),
                      DataColumn(label: Text('状态')),
                      DataColumn(label: Text('最近运行')),
                      DataColumn(label: Text('最近结果')),
                      DataColumn(label: Text('创建时间')),
                      DataColumn(label: Text('操作')),
                    ],
                    rows: pageTasks.map(_buildTaskRow).toList(),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  DataRow _buildTaskRow(TaskListItemModel task) {
    final isRunning = _runningTaskIds.contains(task.id);
    return DataRow(
      key: ValueKey('task-row-${task.id}'),
      onSelectChanged: (_) => _openTaskDetails(task),
      cells: [
        DataCell(
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 180),
            child: Text(
              task.name,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ),
        DataCell(
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 320),
            child: Text(
              task.startUrl,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ),
        DataCell(Text(task.cronExpr)),
        DataCell(
          Chip(
            label: Text(task.isEnabled ? '已启用' : '已停用'),
            backgroundColor: task.isEnabled
                ? const Color(0xFFE3F6E8)
                : const Color(0xFFF3F4F6),
          ),
        ),
        DataCell(Text(_displayValue(task.lastRunAt))),
        DataCell(_TaskResultCell(task: task)),
        DataCell(Text(_displayValue(task.createdAt))),
        DataCell(
          SizedBox(
            width: 280,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                FilledButton.tonalIcon(
                  key: ValueKey('task-run-${task.id}'),
                  style: FilledButton.styleFrom(
                    visualDensity: VisualDensity.compact,
                    padding: const EdgeInsets.symmetric(
                      horizontal: 12,
                      vertical: 10,
                    ),
                    minimumSize: const Size(0, 44),
                    tapTargetSize: MaterialTapTargetSize.padded,
                  ),
                  onPressed: isRunning ? null : () => _runTask(task),
                  icon: _AsyncButtonIcon(
                    isLoading: isRunning,
                    idleIcon: Icons.play_arrow,
                    progressLabel: '任务 ${task.id} 正在提交运行',
                  ),
                  label: Text(isRunning ? '运行中' : '运行'),
                ),
                const SizedBox(width: 8),
                OutlinedButton.icon(
                  style: OutlinedButton.styleFrom(
                    visualDensity: VisualDensity.compact,
                    padding: const EdgeInsets.symmetric(
                      horizontal: 12,
                      vertical: 10,
                    ),
                    minimumSize: const Size(0, 44),
                    tapTargetSize: MaterialTapTargetSize.padded,
                  ),
                  onPressed: () => _openTaskDetails(task),
                  icon: const Icon(Icons.info_outline, size: 18),
                  label: const Text('详情'),
                ),
                const SizedBox(width: 8),
                MenuAnchor(
                  menuChildren: [
                    MenuItemButton(
                      onPressed: () => _openTaskEditor(task),
                      child: const Text('编辑'),
                    ),
                    MenuItemButton(
                      onPressed: () => _saveTaskAsTemplate(task),
                      child: const Text('存为模板'),
                    ),
                    MenuItemButton(
                      onPressed: () => _toggleTask(task),
                      child: Text(task.isEnabled ? '停用' : '启用'),
                    ),
                    MenuItemButton(
                      onPressed: () => _deleteTask(task),
                      child: const Text('删除'),
                    ),
                  ],
                  builder: (context, controller, child) {
                    return OutlinedButton.icon(
                      style: OutlinedButton.styleFrom(
                        visualDensity: VisualDensity.compact,
                        padding: const EdgeInsets.symmetric(
                          horizontal: 12,
                          vertical: 10,
                        ),
                        minimumSize: const Size(0, 44),
                        tapTargetSize: MaterialTapTargetSize.padded,
                      ),
                      onPressed: () {
                        if (controller.isOpen) {
                          controller.close();
                        } else {
                          controller.open();
                        }
                      },
                      icon: const Icon(Icons.more_horiz, size: 18),
                      label: const Text('更多'),
                    );
                  },
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildLogsBody(
    AsyncSnapshot<PageData<TaskLogItemModel>> snapshot,
    List<TaskLogItemModel> logs,
  ) {
    if (snapshot.connectionState == ConnectionState.waiting) {
      return const Card(
        child: Padding(
          padding: EdgeInsets.all(28),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              CircularProgressIndicator(),
              SizedBox(height: 16),
              Text('正在刷新日志列表...'),
            ],
          ),
        ),
      );
    }

    if (snapshot.hasError) {
      return AsyncErrorPanel(
        error: snapshot.error!,
        title: '加载日志失败',
        onRetry: () {
          setState(() {
            _logsFuture = _fetchLogs();
            _logSummaryFuture = _repository.fetchLogSummary();
          });
        },
      );
    }

    if (logs.isEmpty) {
      return Card(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text(
            _logSearchController.text.trim().isEmpty
                ? '当前筛选条件下没有日志。'
                : '当前搜索条件下没有日志。',
          ),
        ),
      );
    }

    return Card(
      child: ListView.separated(
        padding: const EdgeInsets.all(16),
        itemCount: logs.length,
        separatorBuilder: (_, __) => const Divider(height: 24),
        itemBuilder: (context, index) {
          final log = logs[index];
          return _InteractiveLogRow(
            key: ValueKey('log-row-${log.id}'),
            semanticLabel: log.taskId == null
                ? '${log.level} 系统日志'
                : '${log.level} 日志，任务 ${log.taskId}，点击打开任务',
            onTap: log.taskId == null
                ? null
                : () => _openTaskDetailsById(log.taskId!),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _LogLevelBadge(level: log.level),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          _LogMessageWithRunHighlight(
                            message: log.message,
                            baseStyle: Theme.of(context).textTheme.titleSmall,
                          ),
                          const SizedBox(height: 6),
                          Wrap(
                            spacing: 8,
                            runSpacing: 8,
                            children: [
                              _InlineMetaChip(
                                label: '时间',
                                value: _displayValue(log.createdAt),
                              ),
                              _InlineMetaChip(
                                label: '任务 ID',
                                value: log.taskId?.toString() ?? '系统',
                              ),
                            ],
                          ),
                          if (log.taskId != null) ...[
                            const SizedBox(height: 10),
                            Wrap(
                              spacing: 8,
                              runSpacing: 8,
                              children: [
                                OutlinedButton(
                                  onPressed: () =>
                                      _openTaskDetailsById(log.taskId!),
                                  child: const Text('打开任务'),
                                ),
                                OutlinedButton(
                                  onPressed: () =>
                                      _openTaskEditorById(log.taskId!),
                                  child: const Text('编辑任务'),
                                ),
                                FilledButton.tonal(
                                  key: ValueKey('log-run-${log.id}'),
                                  onPressed:
                                      _runningTaskIds.contains(log.taskId)
                                          ? null
                                          : () => _runTaskById(log.taskId!),
                                  child: _InlineLoadingLabel(
                                    isLoading:
                                        _runningTaskIds.contains(log.taskId),
                                    idleLabel: '重新运行',
                                    loadingLabel: '运行中',
                                    progressLabel:
                                        '任务 ${log.taskId} 正在提交运行',
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ],
                      ),
                    ),
                  ],
                ),
                if (log.errorStack != null && log.errorStack!.isNotEmpty) ...[
                  const SizedBox(height: 10),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: const Color(0xFFF8FAFC),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: const Color(0xFFE3E8EF)),
                    ),
                    child: SelectableText(
                      log.errorStack!,
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ),
                ],
              ],
            ),
          );
        },
      ),
    );
  }
}

class _AsyncButtonIcon extends StatelessWidget {
  final bool isLoading;
  final IconData idleIcon;
  final String progressLabel;

  const _AsyncButtonIcon({
    required this.isLoading,
    required this.idleIcon,
    required this.progressLabel,
  });

  @override
  Widget build(BuildContext context) {
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 180),
      switchInCurve: Curves.easeOut,
      switchOutCurve: Curves.easeIn,
      child: isLoading
          ? SizedBox(
              key: const ValueKey('loading'),
              width: 18,
              height: 18,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                semanticsLabel: progressLabel,
              ),
            )
          : Icon(
              idleIcon,
              key: const ValueKey('idle'),
              size: 18,
            ),
    );
  }
}

class _InlineLoadingLabel extends StatelessWidget {
  final bool isLoading;
  final String idleLabel;
  final String loadingLabel;
  final String progressLabel;

  const _InlineLoadingLabel({
    required this.isLoading,
    required this.idleLabel,
    required this.loadingLabel,
    required this.progressLabel,
  });

  @override
  Widget build(BuildContext context) {
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 180),
      switchInCurve: Curves.easeOut,
      switchOutCurve: Curves.easeIn,
      child: isLoading
          ? Row(
              key: const ValueKey('loading'),
              mainAxisSize: MainAxisSize.min,
              children: [
                SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    semanticsLabel: progressLabel,
                  ),
                ),
                const SizedBox(width: 8),
                Text(loadingLabel),
              ],
            )
          : Text(
              idleLabel,
              key: const ValueKey('idle'),
            ),
    );
  }
}

class _SystemManagementPageHero extends StatelessWidget {
  final int templateCount;
  final Future<void> Function() onRefreshTasks;
  final Future<void> Function() onRefreshLogs;
  final bool isRefreshingTasks;
  final bool isRefreshingLogs;

  const _SystemManagementPageHero({
    required this.templateCount,
    required this.onRefreshTasks,
    required this.onRefreshLogs,
    required this.isRefreshingTasks,
    required this.isRefreshingLogs,
  });

  @override
  Widget build(BuildContext context) {
    return AppPageHero(
      title: '系统管理',
      subtitle: '统一管理采集任务、运行状态和平台日志，适合日常调度、批量触发与故障排查。',
      primaryChips: const [
        AppPageHeroChipData.overlay('任务调度'),
        AppPageHeroChipData.overlay('日志排障'),
        AppPageHeroChipData.overlay('模板协作'),
      ],
      secondaryChips: [
        const AppPageHeroChipData.overlay('手动刷新触发采集'),
        const AppPageHeroChipData.overlay('任务每 5 分钟自动触发'),
        AppPageHeroChipData.overlay('模板库 · $templateCount'),
      ],
      actions: [
        FilledButton.tonalIcon(
          key: const ValueKey('bulk-run-hero'),
          onPressed: isRefreshingTasks ? null : onRefreshTasks,
          icon: _AsyncButtonIcon(
            isLoading: isRefreshingTasks,
            idleIcon: Icons.refresh,
            progressLabel: '正在触发采集',
          ),
          label: Text(isRefreshingTasks ? '采集中' : '触发采集'),
        ),
        FilledButton.tonalIcon(
          key: const ValueKey('log-refresh-hero'),
          onPressed: isRefreshingLogs ? null : onRefreshLogs,
          icon: _AsyncButtonIcon(
            isLoading: isRefreshingLogs,
            idleIcon: Icons.library_books_outlined,
            progressLabel: '正在刷新日志',
          ),
          label: Text(isRefreshingLogs ? '刷新中' : '刷新日志'),
        ),
      ],
    );
  }
}

// ignore: unused_element
class _SystemManagementHero extends StatelessWidget {
  final Future<void> Function() onRefreshTasks;
  final Future<void> Function() onRefreshLogs;

  const _SystemManagementHero({
    required this.onRefreshTasks,
    required this.onRefreshLogs,
  });

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final isCompact = constraints.maxWidth < 960;

        final infoColumn = Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '系统管理',
              style: Theme.of(context).textTheme.headlineMedium,
            ),
            const SizedBox(height: 8),
            Text(
              '统一管理采集任务、运行状态和平台日志，适合日常调度和故障排查。',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 16),
            const Wrap(
              spacing: 10,
              runSpacing: 10,
              children: [
                _SystemHeroChip(label: '任务调度'),
                _SystemHeroChip(label: '日志排障'),
                _SystemHeroChip(label: '模板协作'),
              ],
            ),
          ],
        );

        final actionColumn = Column(
          crossAxisAlignment:
              isCompact ? CrossAxisAlignment.start : CrossAxisAlignment.end,
          mainAxisSize: MainAxisSize.min,
          children: [
            FilledButton.tonalIcon(
              onPressed: onRefreshTasks,
              icon: const Icon(Icons.refresh),
              label: const Text('触发采集'),
            ),
            const SizedBox(height: 10),
            FilledButton.tonalIcon(
              onPressed: onRefreshLogs,
              icon: const Icon(Icons.library_books_outlined),
              label: const Text('刷新日志'),
            ),
            const SizedBox(height: 12),
            const _SystemHeroChip(label: '下方切换任务 / 日志'),
          ],
        );

        return Container(
          width: double.infinity,
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [
                Color(0xFF1D4E89),
                Color(0xFF235F9B),
                Color(0xFF13786A),
              ],
            ),
            borderRadius: BorderRadius.circular(28),
            boxShadow: const [
              BoxShadow(
                color: Color(0x281D4E89),
                blurRadius: 30,
                offset: Offset(0, 16),
              ),
            ],
          ),
          child: isCompact
              ? Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    infoColumn,
                    const SizedBox(height: 16),
                    actionColumn,
                  ],
                )
              : Row(
                  children: [
                    Expanded(child: infoColumn),
                    const SizedBox(width: 16),
                    actionColumn,
                  ],
                ),
        );
      },
    );
  }
}

class _SystemHeroChip extends StatelessWidget {
  final String label;

  const _SystemHeroChip({required this.label});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.16),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: const Color(0x33FFFFFF)),
      ),
      child: Text(
        label,
        style: Theme.of(context).textTheme.labelMedium?.copyWith(
              color: Colors.white,
              fontWeight: FontWeight.w700,
            ),
      ),
    );
  }
}

class _LogMessageWithRunHighlight extends StatelessWidget {
  final String message;
  final TextStyle? baseStyle;

  const _LogMessageWithRunHighlight({
    required this.message,
    this.baseStyle,
  });

  static final _runPattern = RegExp(r'(\[run=[a-fA-F0-9]+\])');

  @override
  Widget build(BuildContext context) {
    final style = baseStyle ?? Theme.of(context).textTheme.titleSmall;
    if (!_runPattern.hasMatch(message)) {
      return Text(message, style: style);
    }
    final spans = <InlineSpan>[];
    var start = 0;
    for (final m in _runPattern.allMatches(message)) {
      if (m.start > start) {
        spans.add(TextSpan(text: message.substring(start, m.start)));
      }
      spans.add(TextSpan(
        text: m.group(0),
        style: style?.copyWith(
          fontWeight: FontWeight.w600,
          color: const Color(0xFF5B2C83),
          backgroundColor: const Color(0xFFF3E5F5),
        ),
      ));
      start = m.end;
    }
    if (start < message.length) {
      spans.add(TextSpan(text: message.substring(start)));
    }
    return Text.rich(TextSpan(style: style, children: spans));
  }
}

class _LogFilterBar extends StatelessWidget {
  final TextEditingController taskIdController;
  final TextEditingController searchController;
  final String levelFilter;
  final ValueChanged<String> onLevelChanged;
  final Future<void> Function() onApplyFilters;
  final bool isApplying;
  final VoidCallback onClear;

  const _LogFilterBar({
    required this.taskIdController,
    required this.searchController,
    required this.levelFilter,
    required this.onLevelChanged,
    required this.onApplyFilters,
    required this.isApplying,
    required this.onClear,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Wrap(
          spacing: 12,
          runSpacing: 12,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            SizedBox(
              width: 180,
              child: TextField(
                controller: taskIdController,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  labelText: '任务 ID',
                  hintText: '可选',
                ),
                onSubmitted: (_) => onApplyFilters(),
              ),
            ),
            SizedBox(
              width: 180,
              child: DropdownButtonFormField<String>(
                initialValue: levelFilter,
                decoration: const InputDecoration(
                  labelText: '级别',
                ),
                items: const [
                  DropdownMenuItem(value: 'all', child: Text('全部')),
                  DropdownMenuItem(value: 'INFO', child: Text('INFO')),
                  DropdownMenuItem(value: 'WARNING', child: Text('WARNING')),
                  DropdownMenuItem(value: 'ERROR', child: Text('ERROR')),
                ],
                onChanged: (value) => onLevelChanged(value ?? 'all'),
              ),
            ),
            SizedBox(
              width: 320,
              child: TextField(
                controller: searchController,
                onSubmitted: (_) => onApplyFilters(),
                decoration: const InputDecoration(
                  labelText: '搜索日志',
                  hintText: '消息 / 错误堆栈 / run_id，回车或点应用查后端',
                  prefixIcon: Icon(Icons.search),
                ),
              ),
            ),
            FilledButton.tonal(
              onPressed: isApplying ? null : onApplyFilters,
              child: _InlineLoadingLabel(
                isLoading: isApplying,
                idleLabel: '应用',
                loadingLabel: '应用中',
                progressLabel: '正在应用日志筛选',
              ),
            ),
            OutlinedButton.icon(
              onPressed: onClear,
              icon: const Icon(Icons.clear),
              label: const Text('清空'),
            ),
          ],
        ),
      ),
    );
  }
}

class _InlineMetaChip extends StatelessWidget {
  final String label;
  final String value;

  const _InlineMetaChip({
    required this.label,
    required this.value,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: const Color(0xFFF3F6FA),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text('$label：$value'),
    );
  }
}

class _InteractiveLogRow extends StatefulWidget {
  final String semanticLabel;
  final VoidCallback? onTap;
  final Widget child;

  const _InteractiveLogRow({
    super.key,
    required this.semanticLabel,
    required this.onTap,
    required this.child,
  });

  @override
  State<_InteractiveLogRow> createState() => _InteractiveLogRowState();
}

class _InteractiveLogRowState extends State<_InteractiveLogRow> {
  bool _highlighted = false;

  void _setHighlighted(bool value) {
    if (_highlighted == value) {
      return;
    }
    setState(() {
      _highlighted = value;
    });
  }

  @override
  Widget build(BuildContext context) {
    final enabled = widget.onTap != null;
    final primary = Theme.of(context).colorScheme.primary;
    return Semantics(
      button: enabled,
      label: widget.semanticLabel,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOut,
        constraints: const BoxConstraints(minHeight: 44),
        decoration: BoxDecoration(
          color: enabled && _highlighted
              ? primary.withValues(alpha: 0.06)
              : Colors.transparent,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            borderRadius: BorderRadius.circular(12),
            onTap: widget.onTap,
            onHover: enabled ? _setHighlighted : null,
            onFocusChange: enabled ? _setHighlighted : null,
            mouseCursor:
                enabled ? SystemMouseCursors.click : SystemMouseCursors.basic,
            canRequestFocus: enabled,
            child: Padding(
              padding: const EdgeInsets.symmetric(
                horizontal: 8,
                vertical: 8,
              ),
              child: widget.child,
            ),
          ),
        ),
      ),
    );
  }
}

class _TaskFilterBar extends StatelessWidget {
  final TextEditingController searchController;
  final String enabledFilter;
  final String resultFilter;
  final String sortBy;
  final String sortDir;
  final ValueChanged<String> onSearchChanged;
  final ValueChanged<String> onEnabledFilterChanged;
  final ValueChanged<String> onResultFilterChanged;
  final ValueChanged<String> onSortByChanged;
  final ValueChanged<String> onSortDirChanged;
  final VoidCallback onClear;

  const _TaskFilterBar({
    required this.searchController,
    required this.enabledFilter,
    required this.resultFilter,
    required this.sortBy,
    required this.sortDir,
    required this.onSearchChanged,
    required this.onEnabledFilterChanged,
    required this.onResultFilterChanged,
    required this.onSortByChanged,
    required this.onSortDirChanged,
    required this.onClear,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Wrap(
          spacing: 12,
          runSpacing: 12,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            SizedBox(
              width: 280,
              child: TextField(
                controller: searchController,
                onChanged: onSearchChanged,
                decoration: const InputDecoration(
                  labelText: '搜索任务',
                  hintText: '名称、地址或定时表达式',
                  prefixIcon: Icon(Icons.search),
                ),
              ),
            ),
            SizedBox(
              width: 180,
              child: DropdownButtonFormField<String>(
                initialValue: enabledFilter,
                decoration: const InputDecoration(
                  labelText: '启用状态',
                ),
                items: const [
                  DropdownMenuItem(value: 'all', child: Text('全部')),
                  DropdownMenuItem(value: 'enabled', child: Text('已启用')),
                  DropdownMenuItem(value: 'disabled', child: Text('已停用')),
                ],
                onChanged: (value) => onEnabledFilterChanged(value ?? 'all'),
              ),
            ),
            SizedBox(
              width: 180,
              child: DropdownButtonFormField<String>(
                initialValue: resultFilter,
                decoration: const InputDecoration(
                  labelText: '最近结果',
                ),
                items: const [
                  DropdownMenuItem(value: 'all', child: Text('全部')),
                  DropdownMenuItem(value: 'active', child: Text('排队中 / 运行中')),
                  DropdownMenuItem(value: 'success', child: Text('成功')),
                  DropdownMenuItem(value: 'failed', child: Text('失败')),
                  DropdownMenuItem(value: 'never', child: Text('未运行')),
                ],
                onChanged: (value) => onResultFilterChanged(value ?? 'all'),
              ),
            ),
            SizedBox(
              width: 160,
              child: DropdownButtonFormField<String>(
                initialValue: sortBy,
                decoration: const InputDecoration(
                  labelText: '排序',
                ),
                items: const [
                  DropdownMenuItem(value: 'id', child: Text('按 ID')),
                  DropdownMenuItem(value: 'name', child: Text('按名称')),
                  DropdownMenuItem(
                    value: 'last_run_at',
                    child: Text('按最近运行'),
                  ),
                  DropdownMenuItem(
                    value: 'created_at',
                    child: Text('按创建时间'),
                  ),
                ],
                onChanged: (value) => onSortByChanged(value ?? 'id'),
              ),
            ),
            SizedBox(
              width: 120,
              child: DropdownButtonFormField<String>(
                initialValue: sortDir,
                decoration: const InputDecoration(
                  labelText: '顺序',
                ),
                items: const [
                  DropdownMenuItem(value: 'asc', child: Text('升序')),
                  DropdownMenuItem(value: 'desc', child: Text('降序')),
                ],
                onChanged: (value) => onSortDirChanged(value ?? 'desc'),
              ),
            ),
            OutlinedButton.icon(
              onPressed: onClear,
              icon: const Icon(Icons.clear),
              label: const Text('清空'),
            ),
          ],
        ),
      ),
    );
  }
}

class _TaskSummaryBar extends StatelessWidget {
  final List<TaskListItemModel> pageTasks;
  final int filteredTotal;
  final String enabledFilter;
  final String resultFilter;
  final ValueChanged<String> onFilterSelected;

  const _TaskSummaryBar({
    required this.pageTasks,
    required this.filteredTotal,
    required this.enabledFilter,
    required this.resultFilter,
    required this.onFilterSelected,
  });

  @override
  Widget build(BuildContext context) {
    final enabledCount = pageTasks.where((task) => task.isEnabled).length;
    final activeCount = pageTasks
        .where(
          (task) =>
              task.lastRunStatus == 'queued' || task.lastRunStatus == 'running',
        )
        .length;
    final failedCount =
        pageTasks.where((task) => task.lastRunStatus == 'failed').length;

    return Wrap(
      spacing: 16,
      runSpacing: 16,
      children: [
        _TaskMetricCard(
          key: const ValueKey('task-metric-all'),
          title: '符合条件的任务',
          value: '$filteredTotal',
          icon: Icons.assignment_outlined,
          accentColor: const Color(0xFF1E4F8A),
          selected: enabledFilter == 'all' && resultFilter == 'all',
          onTap: () => onFilterSelected('all'),
        ),
        _TaskMetricCard(
          key: const ValueKey('task-metric-enabled'),
          title: '本页已启用',
          value: '$enabledCount',
          icon: Icons.toggle_on_outlined,
          accentColor: const Color(0xFF117A65),
          selected: enabledFilter == 'enabled',
          onTap: () => onFilterSelected('enabled'),
        ),
        _TaskMetricCard(
          key: const ValueKey('task-metric-active'),
          title: '本页排队 / 运行',
          value: '$activeCount',
          icon: Icons.timelapse_outlined,
          accentColor: const Color(0xFF2D6CDF),
          selected: resultFilter == 'active',
          onTap: () => onFilterSelected('active'),
        ),
        _TaskMetricCard(
          key: const ValueKey('task-metric-failed'),
          title: '本页最近失败',
          value: '$failedCount',
          icon: Icons.error_outline,
          accentColor: const Color(0xFFC45A1A),
          selected: resultFilter == 'failed',
          onTap: () => onFilterSelected('failed'),
        ),
      ],
    );
  }
}

class _TaskMetricCard extends StatelessWidget {
  final String title;
  final String value;
  final IconData icon;
  final Color accentColor;
  final bool selected;
  final VoidCallback onTap;

  const _TaskMetricCard({
    super.key,
    required this.title,
    required this.value,
    required this.icon,
    required this.accentColor,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      selected: selected,
      label: '$title，$value，点击筛选',
      child: SizedBox(
        width: 190,
        child: Card(
          clipBehavior: Clip.antiAlias,
          elevation: selected ? 2 : 0,
          child: InkWell(
            onTap: onTap,
            mouseCursor: SystemMouseCursors.click,
            canRequestFocus: true,
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 180),
              curve: Curves.easeOut,
              constraints: const BoxConstraints(minHeight: 156),
              decoration: BoxDecoration(
                border: Border.all(
                  color: selected ? accentColor : Colors.transparent,
                  width: selected ? 2 : 1,
                ),
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [
                    accentColor.withValues(alpha: selected ? 0.14 : 0.08),
                    Colors.white,
                  ],
                ),
              ),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Container(
                          width: 40,
                          height: 40,
                          decoration: BoxDecoration(
                            color: accentColor.withValues(alpha: 0.12),
                            borderRadius: BorderRadius.circular(14),
                          ),
                          child: Icon(icon, color: accentColor),
                        ),
                        const Spacer(),
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 10,
                            vertical: 6,
                          ),
                          decoration: BoxDecoration(
                            color: const Color(0xFFF2F6FC),
                            borderRadius: BorderRadius.circular(999),
                          ),
                          child: Text(
                            selected ? '已筛选' : '点击筛选',
                            style: Theme.of(context)
                                .textTheme
                                .labelMedium
                                ?.copyWith(
                                  color: accentColor,
                                  fontWeight: FontWeight.w700,
                                ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 14),
                    Text(
                      title,
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 8),
                    Text(
                      value,
                      style: Theme.of(context).textTheme.displaySmall?.copyWith(
                            color: const Color(0xFF0F223D),
                          ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _TaskResultCell extends StatelessWidget {
  final TaskListItemModel task;

  const _TaskResultCell({
    required this.task,
  });

  @override
  Widget build(BuildContext context) {
    final status = task.lastRunStatus ?? 'never';
    final detail = task.lastErrorMessage;
    final slowRunning = _isLongRunningRunningTask(task);
    final color = switch (status) {
      'success' => const Color(0xFFE3F6E8),
      'failed' => const Color(0xFFFCE8E6),
      'queued' || 'running' => const Color(0xFFE8F0FE),
      _ => const Color(0xFFF3F4F6),
    };

    return Tooltip(
      message: detail == null || detail.isEmpty
          ? _statusLabel(status)
          : '${_statusLabel(status)}\n$detail',
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Chip(
            label: Text(_statusLabel(status)),
            backgroundColor: color,
          ),
          if (slowRunning) ...[
            const SizedBox(width: 6),
            const Tooltip(
              message: '任务已运行超过 5 分钟，详情页将使用降频轮询。',
              child: Icon(
                Icons.hourglass_bottom,
                size: 16,
                color: Color(0xFF8A4B00),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

bool _isLongRunningRunningTask(TaskListItemModel task) {
  if ((task.lastRunStatus ?? '') != 'running') {
    return false;
  }
  final raw = task.lastRunAt;
  if (raw == null || raw.trim().isEmpty) {
    return false;
  }
  try {
    final started = DateTime.parse(raw).toUtc();
    return DateTime.now().toUtc().difference(started) >=
        const Duration(minutes: 5);
  } catch (_) {
    return false;
  }
}

String _statusLabel(String status) {
  return switch (status) {
    'success' => '成功',
    'failed' => '失败',
    'queued' => '排队中',
    'running' => '运行中',
    'never' => '未运行',
    _ => status,
  };
}

String _displayValue(String? value) {
  return DateFormatter.formatDateTime(value);
}

class _TaskEditorDialog extends StatefulWidget {
  final TaskListItemModel? task;
  final TaskRepository repository;
  final TaskTemplateModel? initialTemplate;
  final List<TaskTemplateModel> templates;

  const _TaskEditorDialog({
    this.task,
    required this.repository,
    this.initialTemplate,
    required this.templates,
  });

  @override
  State<_TaskEditorDialog> createState() => _TaskEditorDialogState();
}

class _TaskEditorDialogState extends State<_TaskEditorDialog> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _nameController;
  late final TextEditingController _urlController;
  late final TextEditingController _cronController;
  late final TextEditingController _rulesController;
  late bool _enabled;
  bool _submitting = false;
  String? _submitError;

  @override
  void initState() {
    super.initState();
    final task = widget.task;
    _nameController = TextEditingController(text: task?.name ?? '');
    _urlController = TextEditingController(text: task?.startUrl ?? '');
    _cronController =
        TextEditingController(text: task?.cronExpr ?? '0 */6 * * *');
    _rulesController = TextEditingController(text: task?.parserRules ?? '');
    _enabled = task?.isEnabled ?? true;
    if (task == null && widget.initialTemplate != null) {
      _applyTemplate(widget.initialTemplate!);
    }
  }

  @override
  void dispose() {
    _nameController.dispose();
    _urlController.dispose();
    _cronController.dispose();
    _rulesController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) {
      return;
    }

    setState(() {
      _submitting = true;
      _submitError = null;
    });

    final payload = TaskUpsertPayload(
      name: _nameController.text.trim(),
      startUrl: _urlController.text.trim(),
      parserRules: _nullableText(_rulesController.text),
      cronExpr: _cronController.text.trim(),
      status: _enabled ? 1 : 0,
    );

    try {
      if (widget.task == null) {
        await widget.repository.createTask(payload);
      } else {
        await widget.repository.updateTask(widget.task!.id, payload);
      }
      if (!mounted) {
        return;
      }
      Navigator.of(context).pop(true);
    } catch (error) {
      setState(() {
        _submitError = userFacingError(error);
      });
    } finally {
      if (mounted) {
        setState(() {
          _submitting = false;
        });
      }
    }
  }

  String? _nullableText(String value) {
    final trimmed = value.trim();
    if (trimmed.isEmpty) {
      return null;
    }
    return trimmed;
  }

  void _applyTemplate(TaskTemplateModel template) {
    setState(() {
      _nameController.text = template.name;
      _urlController.text = template.startUrl;
      _cronController.text = template.cronExpr;
      _rulesController.text = template.parserRules ?? '';
      _enabled = template.enabled;
      _submitError = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.task == null ? '新建任务' : '编辑任务'),
      content: SizedBox(
        width: 520,
        child: Form(
          key: _formKey,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (widget.task == null) ...[
                  Text(
                    '快捷模板',
                    style: Theme.of(context).textTheme.titleSmall,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '先选择一个模板预填常用采集配置，再按实际需求调整。',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  const SizedBox(height: 12),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: widget.templates.map((template) {
                      return ActionChip(
                        label: Text(template.label),
                        onPressed: () => _applyTemplate(template),
                      );
                    }).toList(),
                  ),
                  const SizedBox(height: 12),
                  ...widget.templates.map((template) {
                    return Padding(
                      padding: const EdgeInsets.only(bottom: 8),
                      child: Text(
                        '${template.label}: ${template.description}',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    );
                  }),
                  const SizedBox(height: 8),
                ],
                TextFormField(
                  controller: _nameController,
                  decoration: const InputDecoration(
                    labelText: '任务名称',
                  ),
                  validator: (value) {
                    if (value == null || value.trim().isEmpty) {
                      return '请输入任务名称。';
                    }
                    return null;
                  },
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: _urlController,
                  decoration: const InputDecoration(
                    labelText: '起始地址',
                  ),
                  validator: (value) {
                    final text = value?.trim() ?? '';
                    if (text.isEmpty) {
                      return '请输入起始地址。';
                    }
                    if (!text.startsWith('http://') &&
                        !text.startsWith('https://')) {
                      return '地址必须以 http:// 或 https:// 开头';
                    }
                    return null;
                  },
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: _cronController,
                  decoration: const InputDecoration(
                    labelText: '定时表达式',
                    helperText: '示例：0 */6 * * *',
                  ),
                  validator: (value) {
                    if (value == null || value.trim().isEmpty) {
                      return '请输入定时表达式。';
                    }
                    return null;
                  },
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: _rulesController,
                  maxLines: 5,
                  decoration: const InputDecoration(
                    labelText: '解析规则 JSON（可选）',
                    helperText:
                        'list_follow：list_item、detail_link、max_items；分页：'
                        'list_url_template、list_page_urls、list_next_page、'
                        'max_list_pages、list_delay_ms；详情：detail_delay_ms、'
                        'detail_retries、detail_retry_backoff_ms、'
                        'detail_retry_policy（all 或 transient）；请求：'
                        'request_timeout_sec、user_agent、http_headers；'
                        '登录态：http_cookies、cookie_domain（敏感，勿泄露）。',
                  ),
                ),
                const SizedBox(height: 12),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('立即启用任务'),
                  value: _enabled,
                  onChanged: (value) {
                    setState(() {
                      _enabled = value;
                    });
                  },
                ),
                if (_submitError != null) ...[
                  const SizedBox(height: 12),
                  Text(
                    _submitError!,
                    style: const TextStyle(color: Color(0xFFB3261E)),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed:
              _submitting ? null : () => Navigator.of(context).pop(false),
          child: const Text('取消'),
        ),
        FilledButton(
          onPressed: _submitting ? null : _submit,
          child: Text(_submitting ? '保存中...' : '保存'),
        ),
      ],
    );
  }
}

class _TaskDetailsDialog extends StatefulWidget {
  final TaskListItemModel task;
  final TaskRepository repository;

  const _TaskDetailsDialog({
    required this.task,
    required this.repository,
  });

  @override
  State<_TaskDetailsDialog> createState() => _TaskDetailsDialogState();
}

class _TaskDetailsDialogState extends State<_TaskDetailsDialog> {
  static const _pollingStatuses = {'queued', 'running'};
  static const _fastPollingInterval = Duration(seconds: 3);
  static const _slowPollingInterval = Duration(seconds: 10);
  static const _slowPollingThreshold = Duration(minutes: 5);

  late Future<TaskListItemModel> _taskFuture;
  late Future<TaskLogItemModel?> _summaryLogFuture;
  late Future<PageData<TaskLogItemModel>> _logsFuture;
  Timer? _pollingTimer;
  Timer? _highlightClearTimer;
  int? _highlightLogId;
  String? _lastObservedRunStatus;
  DateTime? _pollingStartedAt;
  Duration _currentPollingInterval = _fastPollingInterval;

  @override
  void initState() {
    super.initState();
    _taskFuture = widget.repository.fetchTask(widget.task.id);
    _summaryLogFuture = _fetchLatestSummaryLog();
    _logsFuture = widget.repository.fetchTaskLogs(widget.task.id);
    _lastObservedRunStatus = widget.task.lastRunStatus;
    _maybeStartPolling(widget.task.lastRunStatus);
  }

  @override
  void dispose() {
    _pollingTimer?.cancel();
    _highlightClearTimer?.cancel();
    super.dispose();
  }

  Future<void> _refreshDetails({bool refreshLogs = true}) async {
    if (!mounted) {
      return;
    }

    final taskFuture = widget.repository.fetchTask(widget.task.id);
    final summaryFuture = _fetchLatestSummaryLog();
    final logsFuture =
        refreshLogs ? widget.repository.fetchTaskLogs(widget.task.id) : null;

    setState(() {
      _taskFuture = taskFuture;
      _summaryLogFuture = summaryFuture;
      if (logsFuture != null) {
        _logsFuture = logsFuture;
      }
    });

    try {
      final task = await taskFuture;
      final statusChanged = task.lastRunStatus != _lastObservedRunStatus;
      _lastObservedRunStatus = task.lastRunStatus;
      _maybeStartPolling(task.lastRunStatus);
      if (!refreshLogs && statusChanged && mounted) {
        final forcedLogsFuture =
            widget.repository.fetchTaskLogs(widget.task.id);
        setState(() {
          _logsFuture = forcedLogsFuture;
        });
      }
      if (!_shouldPoll(task.lastRunStatus)) {
        _pollingTimer?.cancel();
        _pollingTimer = null;
        if (!refreshLogs && mounted) {
          final finalLogsFuture =
              widget.repository.fetchTaskLogs(widget.task.id);
          setState(() {
            _logsFuture = finalLogsFuture;
          });
        }
      }
    } catch (_) {
      _pollingTimer?.cancel();
      _pollingTimer = null;
    }
  }

  void _maybeStartPolling(String? status) {
    if (!_shouldPoll(status)) {
      _pollingTimer?.cancel();
      _pollingTimer = null;
      _pollingStartedAt = null;
      _currentPollingInterval = _fastPollingInterval;
      return;
    }

    _pollingStartedAt ??= DateTime.now();
    _currentPollingInterval = _resolvePollingInterval();
    if (_pollingTimer == null || !_pollingTimer!.isActive) {
      _scheduleNextPollingTick();
    }
  }

  bool _shouldPoll(String? status) => _pollingStatuses.contains(status);

  Duration _resolvePollingInterval() {
    final startedAt = _pollingStartedAt;
    if (startedAt == null) {
      return _fastPollingInterval;
    }
    final runningFor = DateTime.now().difference(startedAt);
    if (runningFor >= _slowPollingThreshold) {
      return _slowPollingInterval;
    }
    return _fastPollingInterval;
  }

  void _scheduleNextPollingTick() {
    _pollingTimer?.cancel();
    _pollingTimer = Timer(_currentPollingInterval, () async {
      _pollingTimer = null;
      await _refreshDetails(refreshLogs: true);
    });
  }

  bool get _isSlowPolling => _currentPollingInterval == _slowPollingInterval;

  Future<TaskLogItemModel?> _fetchLatestSummaryLog() async {
    final page = await widget.repository.fetchTaskLogs(
      widget.task.id,
      page: 1,
      pageSize: 1,
      onlySummary: true,
    );
    if (page.items.isEmpty) {
      return null;
    }
    return page.items.first;
  }

  List<MapEntry<String, String>> _extractSummaryMetrics(TaskLogItemModel log) {
    final structured = log.runSummary;
    if (structured == null) {
      return const <MapEntry<String, String>>[];
    }
    final metricsRaw = structured['metrics'];
    if (metricsRaw is! Map<String, dynamic>) {
      return const <MapEntry<String, String>>[];
    }
    return metricsRaw.entries
        .map((entry) => MapEntry(entry.key, entry.value.toString()))
        .toList();
  }

  String _summaryLabel(String key) {
    return switch (key) {
      'list_pages' => '列表页',
      'detail_discovered' => '发现详情',
      'detail_processed' => '处理详情',
      'stored' => '入库',
      'skipped_hash' => '重复跳过',
      'failed' => '失败',
      'detail_limit' => '详情上限',
      'detail_limit_hit' => '命中上限',
      'remaining_list_queue' => '待扫列表',
      'processed' => '处理数',
      _ => key,
    };
  }

  _SummaryMetricTone _summaryTone(MapEntry<String, String> metric) {
    final key = metric.key;
    final value = metric.value.trim().toLowerCase();

    if (key == 'failed') {
      final n = int.tryParse(value) ?? 0;
      if (n > 0) {
        return _SummaryMetricTone.danger;
      }
    }

    if (key == 'detail_limit_hit' &&
        (value == 'true' || value == '1' || value == 'yes')) {
      return _SummaryMetricTone.danger;
    }

    if (key == 'skipped_hash') {
      final n = int.tryParse(value) ?? 0;
      if (n > 0) {
        return _SummaryMetricTone.warning;
      }
    }

    return _SummaryMetricTone.neutral;
  }

  Future<void> _refreshManually() async {
    await _refreshDetails(refreshLogs: true);
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Row(
        children: [
          Expanded(
            child: FutureBuilder<TaskListItemModel>(
              future: _taskFuture,
              builder: (context, snapshot) {
                final name =
                    snapshot.hasData ? snapshot.data!.name : widget.task.name;
                return Text(
                  name,
                  overflow: TextOverflow.ellipsis,
                );
              },
            ),
          ),
          const SizedBox(width: 12),
          IconButton(
            tooltip: '刷新详情',
            onPressed: _refreshManually,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      content: SizedBox(
        width: 900,
        child: FutureBuilder<TaskListItemModel>(
          future: _taskFuture,
          builder: (context, taskSnapshot) {
            if (taskSnapshot.connectionState == ConnectionState.waiting &&
                !taskSnapshot.hasData) {
              return const Center(child: CircularProgressIndicator());
            }

            if (taskSnapshot.hasError && !taskSnapshot.hasData) {
              return _DetailBlock(
                title: '任务加载失败',
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SelectableText(userFacingError(taskSnapshot.error)),
                    const SizedBox(height: 12),
                    FilledButton.tonalIcon(
                      onPressed: _refreshManually,
                      icon: const Icon(Icons.refresh),
                      label: const Text('重试'),
                    ),
                  ],
                ),
              );
            }

            final task = taskSnapshot.data!;
            final isPolling = _shouldPoll(task.lastRunStatus);

            return Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (isPolling)
                  Container(
                    width: double.infinity,
                    margin: const EdgeInsets.only(bottom: 12),
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: const Color(0xFFE8F0FE),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: const Text(
                      '该任务正在执行中，详情与日志会每隔几秒自动刷新。',
                    ),
                  ),
                if (isPolling)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: [
                        Text(
                          '当前轮询间隔：${_currentPollingInterval.inSeconds} 秒',
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                        if (_isSlowPolling)
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 8,
                              vertical: 4,
                            ),
                            decoration: BoxDecoration(
                              color: const Color(0xFFFFF4E5),
                              borderRadius: BorderRadius.circular(999),
                            ),
                            child: const Text(
                              '长时运行，已降频轮询',
                              style: TextStyle(
                                color: Color(0xFF8A4B00),
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ),
                      ],
                    ),
                  ),
                Wrap(
                  spacing: 12,
                  runSpacing: 12,
                  children: [
                    _DetailChip(label: '任务 ID', value: '${task.id}'),
                    _DetailChip(
                      label: '状态',
                      value: task.isEnabled ? '已启用' : '已停用',
                    ),
                    _DetailChip(
                      label: '最近运行',
                      value: _displayValue(task.lastRunAt),
                    ),
                    _DetailChip(
                      label: '最近成功',
                      value: _displayValue(task.lastSuccessAt),
                    ),
                    _DetailChip(
                      label: '最近结果',
                      value: _statusLabel(task.lastRunStatus ?? 'never'),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                _DetailBlock(
                  title: '起始地址',
                  child: SelectableText(task.startUrl),
                ),
                const SizedBox(height: 12),
                _DetailBlock(
                  title: '定时表达式',
                  child: Text(task.cronExpr),
                ),
                const SizedBox(height: 12),
                _DetailBlock(
                  title: '解析规则',
                  child: SelectableText(task.parserRules?.isNotEmpty == true
                      ? task.parserRules!
                      : '当前未配置解析规则。'),
                ),
                const SizedBox(height: 12),
                _DetailBlock(
                  title: '最近错误',
                  child: SelectableText(
                    task.lastErrorMessage?.isNotEmpty == true
                        ? task.lastErrorMessage!
                        : '最近没有错误信息。',
                  ),
                ),
                const SizedBox(height: 16),
                Text(
                  '最近日志',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 8),
                Flexible(
                  child: FutureBuilder<PageData<TaskLogItemModel>>(
                    future: _logsFuture,
                    builder: (context, snapshot) {
                      if (snapshot.connectionState == ConnectionState.waiting &&
                          !snapshot.hasData) {
                        return const Center(child: CircularProgressIndicator());
                      }

                      if (snapshot.hasError) {
                        return _DetailBlock(
                          title: '日志加载失败',
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              SelectableText(userFacingError(snapshot.error)),
                              const SizedBox(height: 12),
                              FilledButton.tonalIcon(
                                onPressed: _refreshDetails,
                                icon: const Icon(Icons.refresh),
                                label: const Text('重试'),
                              ),
                            ],
                          ),
                        );
                      }

                      final logs =
                          snapshot.data?.items ?? const <TaskLogItemModel>[];
                      if (logs.isEmpty) {
                        return const _DetailBlock(
                          title: '日志',
                          child: Text('当前任务还没有可用日志。'),
                        );
                      }

                      final firstErrorIndex = logs.indexWhere(
                        (log) => log.level.toUpperCase() == 'ERROR',
                      );
                      final firstErrorKey = GlobalKey();
                      return FutureBuilder<TaskLogItemModel?>(
                        future: _summaryLogFuture,
                        builder: (context, summarySnapshot) {
                          final latestSummary = summarySnapshot.data;
                          final summaryMetrics = latestSummary == null
                              ? const <MapEntry<String, String>>[]
                              : _extractSummaryMetrics(latestSummary);
                          final hasDangerSummaryMetric = summaryMetrics.any(
                            (metric) =>
                                _summaryTone(metric) ==
                                _SummaryMetricTone.danger,
                          );
                          return Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              if (latestSummary != null) ...[
                                _DetailBlock(
                                  title: '运行摘要',
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      if (hasDangerSummaryMetric) ...[
                                        Container(
                                          margin:
                                              const EdgeInsets.only(bottom: 8),
                                          decoration: BoxDecoration(
                                            color: const Color(0xFFFCE8E6),
                                            borderRadius:
                                                BorderRadius.circular(999),
                                          ),
                                          child: InkWell(
                                            borderRadius:
                                                BorderRadius.circular(999),
                                            onTap: firstErrorIndex < 0
                                                ? null
                                                : () {
                                                    final errorLog =
                                                        logs[firstErrorIndex];
                                                    WidgetsBinding.instance
                                                        .addPostFrameCallback(
                                                            (_) {
                                                      final ctx = firstErrorKey
                                                          .currentContext;
                                                      if (ctx != null) {
                                                        Scrollable
                                                            .ensureVisible(
                                                          ctx,
                                                          duration:
                                                              const Duration(
                                                            milliseconds: 260,
                                                          ),
                                                          curve: Curves.easeOut,
                                                          alignment: 0.2,
                                                        );
                                                      }
                                                    });
                                                    if (!mounted) {
                                                      return;
                                                    }
                                                    setState(() {
                                                      _highlightLogId =
                                                          errorLog.id;
                                                    });
                                                    _highlightClearTimer
                                                        ?.cancel();
                                                    _highlightClearTimer =
                                                        Timer(
                                                      const Duration(
                                                          seconds: 2),
                                                      () {
                                                        if (!mounted) {
                                                          return;
                                                        }
                                                        setState(() {
                                                          _highlightLogId =
                                                              null;
                                                        });
                                                      },
                                                    );
                                                  },
                                            child: Padding(
                                              padding:
                                                  const EdgeInsets.symmetric(
                                                horizontal: 10,
                                                vertical: 6,
                                              ),
                                              child: Text(
                                                firstErrorIndex < 0
                                                    ? '本次有异常'
                                                    : '本次有异常（点击定位错误日志）',
                                                style: const TextStyle(
                                                  color: Color(0xFFB3261E),
                                                  fontWeight: FontWeight.w600,
                                                ),
                                              ),
                                            ),
                                          ),
                                        ),
                                      ],
                                      if (summaryMetrics.isNotEmpty) ...[
                                        Wrap(
                                          spacing: 8,
                                          runSpacing: 8,
                                          children: summaryMetrics.map((entry) {
                                            return _SummaryMetricChip(
                                              label: _summaryLabel(entry.key),
                                              value: entry.value,
                                              tone: _summaryTone(entry),
                                            );
                                          }).toList(),
                                        ),
                                        const SizedBox(height: 8),
                                      ],
                                      SelectableText(latestSummary.message),
                                      const SizedBox(height: 6),
                                      Text(
                                        '时间：${_displayValue(latestSummary.createdAt)}',
                                        style: Theme.of(context)
                                            .textTheme
                                            .bodySmall,
                                      ),
                                    ],
                                  ),
                                ),
                                const SizedBox(height: 8),
                              ],
                              Expanded(
                                child: ListView.separated(
                                  shrinkWrap: true,
                                  itemCount: logs.length,
                                  separatorBuilder: (_, __) =>
                                      const Divider(height: 1),
                                  itemBuilder: (context, index) {
                                    final log = logs[index];
                                    final highlighted =
                                        _highlightLogId == log.id;
                                    return ListTile(
                                      key: index == firstErrorIndex
                                          ? firstErrorKey
                                          : null,
                                      contentPadding: EdgeInsets.zero,
                                      tileColor: highlighted
                                          ? const Color(0xFFFCE8E6)
                                          : null,
                                      leading: _LogLevelBadge(level: log.level),
                                      title: Text(log.message),
                                      subtitle: Column(
                                        crossAxisAlignment:
                                            CrossAxisAlignment.start,
                                        children: [
                                          const SizedBox(height: 4),
                                          Text(_displayValue(log.createdAt)),
                                          if (log.errorStack != null &&
                                              log.errorStack!.isNotEmpty) ...[
                                            const SizedBox(height: 8),
                                            SelectableText(
                                              log.errorStack!,
                                              style: Theme.of(context)
                                                  .textTheme
                                                  .bodySmall,
                                            ),
                                          ],
                                        ],
                                      ),
                                    );
                                  },
                                ),
                              ),
                            ],
                          );
                        },
                      );
                    },
                  ),
                ),
              ],
            );
          },
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('关闭'),
        ),
      ],
    );
  }
}

class _SaveTaskAsTemplateDialog extends StatefulWidget {
  final TaskListItemModel task;
  final HttpTemplateRepository repository;

  const _SaveTaskAsTemplateDialog({
    required this.task,
    required this.repository,
  });

  @override
  State<_SaveTaskAsTemplateDialog> createState() =>
      _SaveTaskAsTemplateDialogState();
}

class _SaveTaskAsTemplateDialogState extends State<_SaveTaskAsTemplateDialog> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _labelController;
  late final TextEditingController _descriptionController;
  late final TextEditingController _tagsController;
  bool _submitting = false;
  String? _submitError;

  @override
  void initState() {
    super.initState();
    _labelController = TextEditingController(
      text: '${widget.task.name} 模板',
    );
    _descriptionController = TextEditingController(
      text: '基于任务“${widget.task.name}”创建的模板。',
    );
    _tagsController = TextEditingController(text: '导入,任务');
  }

  @override
  void dispose() {
    _labelController.dispose();
    _descriptionController.dispose();
    _tagsController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) {
      return;
    }

    setState(() {
      _submitting = true;
      _submitError = null;
    });

    final template = TaskTemplateModel(
      id: _labelController.text.trim().toLowerCase().replaceAll(' ', '_'),
      label: _labelController.text.trim(),
      name: widget.task.name,
      startUrl: widget.task.startUrl,
      cronExpr: widget.task.cronExpr,
      parserRules: widget.task.parserRules,
      enabled: widget.task.isEnabled,
      description: _descriptionController.text.trim(),
      tags: _tagsController.text
          .split(',')
          .map((tag) => tag.trim())
          .where((tag) => tag.isNotEmpty)
          .toList(),
      usageCount: 0,
      lastUsedAt: null,
    );

    try {
      await widget.repository.createTaskTemplate(template);
      if (!mounted) {
        return;
      }
      Navigator.of(context).pop(true);
    } catch (error) {
      setState(() {
        _submitError = userFacingError(error);
      });
    } finally {
      if (mounted) {
        setState(() {
          _submitting = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('另存为模板'),
      content: SizedBox(
        width: 520,
        child: Form(
          key: _formKey,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '将当前任务配置保存为可复用模板，便于后续快速建任务。',
                style: Theme.of(context).textTheme.bodyMedium,
              ),
              const SizedBox(height: 16),
              TextFormField(
                controller: _labelController,
                decoration: const InputDecoration(
                  labelText: '模板名称',
                ),
                validator: (value) =>
                    value == null || value.trim().isEmpty ? '必填项' : null,
              ),
              const SizedBox(height: 16),
              TextFormField(
                controller: _descriptionController,
                maxLines: 3,
                decoration: const InputDecoration(
                  labelText: '模板说明',
                ),
                validator: (value) =>
                    value == null || value.trim().isEmpty ? '必填项' : null,
              ),
              const SizedBox(height: 16),
              TextFormField(
                controller: _tagsController,
                decoration: const InputDecoration(
                  labelText: '标签',
                  hintText: '用英文逗号分隔多个标签',
                ),
              ),
              if (_submitError != null) ...[
                const SizedBox(height: 12),
                Text(
                  _submitError!,
                  style: const TextStyle(color: Color(0xFFB3261E)),
                ),
              ],
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed:
              _submitting ? null : () => Navigator.of(context).pop(false),
          child: const Text('取消'),
        ),
        FilledButton(
          onPressed: _submitting ? null : _submit,
          child: Text(_submitting ? '保存中...' : '保存模板'),
        ),
      ],
    );
  }
}

class _DetailChip extends StatelessWidget {
  final String label;
  final String value;

  const _DetailChip({
    required this.label,
    required this.value,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(0xFFF3F6FA),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            label,
            style: Theme.of(context).textTheme.labelMedium,
          ),
          const SizedBox(height: 4),
          SelectableText(value),
        ],
      ),
    );
  }
}

enum _SummaryMetricTone { neutral, warning, danger }

class _SummaryMetricChip extends StatelessWidget {
  final String label;
  final String value;
  final _SummaryMetricTone tone;

  const _SummaryMetricChip({
    required this.label,
    required this.value,
    required this.tone,
  });

  @override
  Widget build(BuildContext context) {
    final background = switch (tone) {
      _SummaryMetricTone.danger => const Color(0xFFFCE8E6),
      _SummaryMetricTone.warning => const Color(0xFFFFF4E5),
      _SummaryMetricTone.neutral => const Color(0xFFF3F6FA),
    };
    final valueColor = switch (tone) {
      _SummaryMetricTone.danger => const Color(0xFFB3261E),
      _SummaryMetricTone.warning => const Color(0xFF8A4B00),
      _SummaryMetricTone.neutral => null,
    };

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            label,
            style: Theme.of(context).textTheme.labelMedium,
          ),
          const SizedBox(height: 4),
          SelectableText(
            value,
            style: valueColor == null ? null : TextStyle(color: valueColor),
          ),
        ],
      ),
    );
  }
}

class _DetailBlock extends StatelessWidget {
  final String title;
  final Widget child;

  const _DetailBlock({
    required this.title,
    required this.child,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border.all(color: const Color(0xFFE3E8EF)),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: Theme.of(context).textTheme.labelLarge,
          ),
          const SizedBox(height: 8),
          child,
        ],
      ),
    );
  }
}

class _LogLevelBadge extends StatelessWidget {
  final String level;

  const _LogLevelBadge({
    required this.level,
  });

  @override
  Widget build(BuildContext context) {
    final normalized = level.toUpperCase();
    final background = switch (normalized) {
      'ERROR' => const Color(0xFFFCE8E6),
      'WARNING' => const Color(0xFFFFF4E5),
      'INFO' => const Color(0xFFE8F0FE),
      _ => const Color(0xFFF3F4F6),
    };

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        normalized,
        style: Theme.of(context).textTheme.labelMedium,
      ),
    );
  }
}

class _PaginationBar extends StatelessWidget {
  final int page;
  final int pageSize;
  final int total;
  final VoidCallback? onPrevious;
  final VoidCallback? onNext;

  const _PaginationBar({
    required this.page,
    required this.pageSize,
    required this.total,
    required this.onPrevious,
    required this.onNext,
  });

  @override
  Widget build(BuildContext context) {
    final hasPrevious = onPrevious != null;
    final hasNext = onNext != null;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: LayoutBuilder(
          builder: (context, constraints) {
            final isCompact = constraints.maxWidth < 720;

            final info = Text(
              '第 $page 页 · 共 $total 条 · 每页 $pageSize 条',
              style: Theme.of(context).textTheme.bodyMedium,
            );

            final actions = Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                OutlinedButton.icon(
                  onPressed: hasPrevious ? onPrevious : null,
                  icon: const Icon(Icons.chevron_left),
                  label: const Text('上一页'),
                ),
                OutlinedButton.icon(
                  onPressed: hasNext ? onNext : null,
                  icon: const Icon(Icons.chevron_right),
                  label: const Text('下一页'),
                ),
              ],
            );

            if (isCompact) {
              return Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  info,
                  const SizedBox(height: 12),
                  actions,
                ],
              );
            }

            return Row(
              children: [
                Expanded(child: info),
                const SizedBox(width: 16),
                actions,
              ],
            );
          },
        ),
      ),
    );
  }
}

class _LogSummaryBar extends StatelessWidget {
  final LogSummaryModel? summary;
  final String selectedLevel;
  final ValueChanged<String> onLevelSelected;

  const _LogSummaryBar({
    required this.summary,
    required this.selectedLevel,
    required this.onLevelSelected,
  });

  @override
  Widget build(BuildContext context) {
    if (summary == null) {
      return const SizedBox.shrink();
    }

    return Wrap(
      spacing: 16,
      runSpacing: 16,
      children: [
        _TaskMetricCard(
          key: const ValueKey('log-metric-all'),
          title: '日志总数',
          value: '${summary!.totalLogs}',
          icon: Icons.receipt_long_outlined,
          accentColor: const Color(0xFF1E4F8A),
          selected: selectedLevel == 'all',
          onTap: () => onLevelSelected('all'),
        ),
        _TaskMetricCard(
          key: const ValueKey('log-metric-info'),
          title: 'INFO',
          value: '${summary!.infoLogs}',
          icon: Icons.info_outline,
          accentColor: const Color(0xFF117A65),
          selected: selectedLevel == 'INFO',
          onTap: () => onLevelSelected('INFO'),
        ),
        _TaskMetricCard(
          key: const ValueKey('log-metric-warning'),
          title: 'WARNING',
          value: '${summary!.warningLogs}',
          icon: Icons.warning_amber_outlined,
          accentColor: const Color(0xFFC45A1A),
          selected: selectedLevel == 'WARNING',
          onTap: () => onLevelSelected('WARNING'),
        ),
        _TaskMetricCard(
          key: const ValueKey('log-metric-error'),
          title: 'ERROR',
          value: '${summary!.errorLogs}',
          icon: Icons.error_outline,
          accentColor: const Color(0xFFB3261E),
          selected: selectedLevel == 'ERROR',
          onTap: () => onLevelSelected('ERROR'),
        ),
      ],
    );
  }
}

class _FailedTaskActionBar extends StatelessWidget {
  final List<TaskLogItemModel> logs;
  final ValueChanged<int> onOpenTask;
  final ValueChanged<int> onEditTask;
  final ValueChanged<int> onRunTask;
  final Set<int> runningTaskIds;

  const _FailedTaskActionBar({
    required this.logs,
    required this.onOpenTask,
    required this.onEditTask,
    required this.onRunTask,
    required this.runningTaskIds,
  });

  @override
  Widget build(BuildContext context) {
    final failedTaskIds = logs
        .where(
            (log) => log.taskId != null && log.level.toLowerCase() == 'error')
        .map((log) => log.taskId!)
        .toSet()
        .toList()
      ..sort();

    if (failedTaskIds.isEmpty) {
      return const SizedBox.shrink();
    }

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '失败任务快捷操作',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 12,
              runSpacing: 12,
              children: failedTaskIds.take(3).map((taskId) {
                final isRunning = runningTaskIds.contains(taskId);
                return Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: const Color(0xFFF8FAFC),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: const Color(0xFFE3E8EF)),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        '任务 #$taskId',
                        style: Theme.of(context).textTheme.titleSmall,
                      ),
                      const SizedBox(height: 10),
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: [
                          OutlinedButton(
                            onPressed: () => onOpenTask(taskId),
                            child: const Text('打开'),
                          ),
                          OutlinedButton(
                            onPressed: () => onEditTask(taskId),
                            child: const Text('编辑'),
                          ),
                          FilledButton.tonal(
                            key: ValueKey('failed-run-$taskId'),
                            onPressed:
                                isRunning ? null : () => onRunTask(taskId),
                            child: _InlineLoadingLabel(
                              isLoading: isRunning,
                              idleLabel: '重新运行',
                              loadingLabel: '运行中',
                              progressLabel: '任务 $taskId 正在提交运行',
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                );
              }).toList(),
            ),
          ],
        ),
      ),
    );
  }
}
