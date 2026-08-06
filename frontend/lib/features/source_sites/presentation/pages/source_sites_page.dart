import 'package:flutter/material.dart';

import '../../../../core/network/api_client.dart';
import '../../../../core/utils/date_formatter.dart';
import '../../../../core/utils/user_facing_error.dart';
import '../../../../core/widgets/page_chrome.dart';
import '../../../system_management/data/models/task_models.dart';
import '../../../system_management/data/models/task_template_models.dart';
import '../../../system_management/data/repositories/http_template_repository.dart';
import '../../../system_management/data/repositories/http_task_repository.dart';
import '../../../system_management/data/repositories/task_repository.dart';
import '../template_collection_status.dart';

class SourceSitesPage extends StatefulWidget {
  final ValueChanged<TaskTemplateModel>? onUseTemplate;
  final List<TaskTemplateModel> templates;
  final HttpTemplateRepository templateRepository;
  final TaskRepository? taskRepository;
  final Future<void> Function() onTemplatesChanged;

  const SourceSitesPage({
    super.key,
    this.onUseTemplate,
    required this.templates,
    required this.templateRepository,
    this.taskRepository,
    required this.onTemplatesChanged,
  });

  @override
  State<SourceSitesPage> createState() => _SourceSitesPageState();
}

class _SourceSitesPageState extends State<SourceSitesPage> {
  late final TextEditingController _templateSearchController;
  final ScrollController _templateListScrollController = ScrollController();
  ApiClient? _ownedTaskApiClient;
  late final TaskRepository _taskRepository;
  String _sortKey = 'usage';
  bool _sortAscending = false;
  String? _selectedTag;
  final Set<String> _usingTemplateIds = {};
  final Set<String> _deletingTemplateIds = {};
  final Set<String> _collectingTemplateIds = {};
  final Set<int> _retryingTaskIds = {};
  Map<String, _TaskHealthSnapshot> _taskHealthByTemplateId =
      const <String, _TaskHealthSnapshot>{};
  String? _taskHealthError;
  bool _refreshing = false;
  bool _taskHealthLoading = false;
  int _taskHealthRequestId = 0;

  @override
  void initState() {
    super.initState();
    if (widget.taskRepository != null) {
      _taskRepository = widget.taskRepository!;
    } else {
      _ownedTaskApiClient = ApiClient();
      _taskRepository = HttpTaskRepository(apiClient: _ownedTaskApiClient!);
    }
    _templateSearchController = TextEditingController()
      ..addListener(() {
        if (mounted) {
          setState(() {});
        }
      });
    _loadTaskHealth();
  }

  @override
  void didUpdateWidget(covariant SourceSitesPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.templates != widget.templates) {
      _loadTaskHealth();
    }
  }

  @override
  void dispose() {
    _templateSearchController.dispose();
    _templateListScrollController.dispose();
    _ownedTaskApiClient?.dispose();
    super.dispose();
  }

  List<TaskTemplateModel> _visibleTemplates() {
    final q = _templateSearchController.text.trim().toLowerCase();
    final list = List<TaskTemplateModel>.from(widget.templates);
    final selectedTag = _selectedTag?.toLowerCase();
    if (selectedTag != null) {
      list.retainWhere(
        (template) =>
            template.tags.any((tag) => tag.toLowerCase() == selectedTag),
      );
    }
    if (q.isNotEmpty) {
      list.retainWhere((t) {
        if (t.label.toLowerCase().contains(q)) {
          return true;
        }
        if (t.name.toLowerCase().contains(q)) {
          return true;
        }
        if (t.description.toLowerCase().contains(q)) {
          return true;
        }
        if (t.startUrl.toLowerCase().contains(q)) {
          return true;
        }
        if (t.id.toLowerCase().contains(q)) {
          return true;
        }
        return t.tags.any((tag) => tag.toLowerCase().contains(q));
      });
    }

    int cmp(TaskTemplateModel a, TaskTemplateModel b) {
      switch (_sortKey) {
        case 'usage':
          return a.usageCount.compareTo(b.usageCount);
        case 'last_used':
          if (a.lastUsedAt == null && b.lastUsedAt == null) {
            return 0;
          }
          if (a.lastUsedAt == null) {
            return 1;
          }
          if (b.lastUsedAt == null) {
            return -1;
          }
          return a.lastUsedAt!.compareTo(b.lastUsedAt!);
        default:
          return a.label.toLowerCase().compareTo(b.label.toLowerCase());
      }
    }

    list.sort((a, b) {
      final c = cmp(a, b);
      return _sortAscending ? c : -c;
    });
    return list;
  }

  Future<void> _refreshTemplates() async {
    if (_refreshing) return;
    setState(() {
      _refreshing = true;
    });
    try {
      await widget.onTemplatesChanged();
      await _loadTaskHealth();
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('刷新模板列表失败：${userFacingError(error)}'),
          backgroundColor: const Color(0xFFB3261E),
        ),
      );
    } finally {
      if (mounted) {
        setState(() {
          _refreshing = false;
        });
      }
    }
  }

  Future<void> _loadTaskHealth() async {
    final requestId = ++_taskHealthRequestId;
    final templateNames = widget.templates
        .map((template) => template.name.trim())
        .where((name) => name.isNotEmpty)
        .toSet();
    if (templateNames.isEmpty) {
      if (!mounted || requestId != _taskHealthRequestId) {
        return;
      }
      setState(() {
        _taskHealthByTemplateId = const <String, _TaskHealthSnapshot>{};
        _taskHealthError = null;
        _taskHealthLoading = false;
      });
      return;
    }

    setState(() {
      _taskHealthLoading = true;
      _taskHealthError = null;
    });

    try {
      final tasks = await _taskRepository.fetchTasksByNames(templateNames);
      final tasksByName = <String, TaskListItemModel>{
        for (final task in tasks) task.name.trim(): task,
      };
      final healthByTemplateId = <String, _TaskHealthSnapshot>{};

      for (final template in widget.templates) {
        final task = tasksByName[template.name.trim()];
        TaskLogItemModel? latestLog;
        TaskLogItemModel? latestSummaryLog;
        final lastRunStatus = task?.lastRunStatus?.trim().toLowerCase();
        if (task != null && lastRunStatus == 'failed') {
          final page = await _taskRepository.fetchTaskLogs(task.id, pageSize: 1);
          if (page.items.isNotEmpty) {
            latestLog = page.items.first;
          }
        }
        if (task != null && lastRunStatus == 'partial') {
          final page = await _taskRepository.fetchTaskLogs(
            task.id,
            pageSize: 1,
            onlySummary: true,
          );
          if (page.items.isNotEmpty) {
            latestSummaryLog = page.items.first;
          }
        }
        healthByTemplateId[template.id] = _TaskHealthSnapshot(
          task: task,
          latestLog: latestLog,
          latestSummaryLog: latestSummaryLog,
        );
      }

      if (!mounted || requestId != _taskHealthRequestId) {
        return;
      }
      setState(() {
        _taskHealthByTemplateId = healthByTemplateId;
        _taskHealthError = null;
        _taskHealthLoading = false;
      });
    } catch (error) {
      if (!mounted || requestId != _taskHealthRequestId) {
        return;
      }
      setState(() {
        _taskHealthError = userFacingError(error);
        _taskHealthLoading = false;
      });
    }
  }

  Future<void> _useTemplate(TaskTemplateModel template) async {
    if (_usingTemplateIds.contains(template.id)) return;
    setState(() {
      _usingTemplateIds.add(template.id);
    });
    try {
      await widget.templateRepository.trackTaskTemplateUse(template.id);
      await widget.onTemplatesChanged();
      widget.onUseTemplate?.call(template);
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('套用模板失败：${userFacingError(error)}'),
          backgroundColor: const Color(0xFFB3261E),
        ),
      );
    } finally {
      if (mounted) {
        setState(() {
          _usingTemplateIds.remove(template.id);
        });
      }
    }
  }

  Future<void> _collectManualSource(TaskTemplateModel template) async {
    if (_collectingTemplateIds.contains(template.id) ||
        _usingTemplateIds.contains(template.id) ||
        _deletingTemplateIds.contains(template.id)) {
      return;
    }
    final formKey = GlobalKey<FormState>();
    var pendingArticleUrl = '';
    final articleUrl = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('登记${template.label}文章'),
        content: Form(
          key: formKey,
          child: SizedBox(
            width: 520,
            child: TextFormField(
              autofocus: true,
              onChanged: (value) {
                pendingArticleUrl = value;
              },
              decoration: const InputDecoration(
                labelText: '公众号文章链接',
                hintText: 'https://mp.weixin.qq.com/s/...',
              ),
              validator: (value) {
                final text = value?.trim() ?? '';
                final uri = Uri.tryParse(text);
                if (uri == null ||
                    !{'http', 'https'}.contains(uri.scheme) ||
                    uri.host.toLowerCase() != 'mp.weixin.qq.com') {
                  return '请输入 mp.weixin.qq.com 的完整文章链接';
                }
                return null;
              },
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () {
              if (formKey.currentState?.validate() == true) {
                Navigator.of(context).pop(pendingArticleUrl.trim());
              }
            },
            child: const Text('采集文章'),
          ),
        ],
      ),
    );
    if (articleUrl == null || !mounted) {
      return;
    }

    setState(() {
      _collectingTemplateIds.add(template.id);
    });
    try {
      final result = await widget.templateRepository.collectManualSource(
        template.id,
        articleUrl,
      );
      await _loadTaskHealth();
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            result.status == 'stored'
                ? '文章已采集到通知池（编号 ${result.noticeId}）。'
                : '文章已存在，通知池编号 ${result.noticeId}。',
          ),
        ),
      );
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('公众号文章采集失败：${userFacingError(error)}'),
          backgroundColor: const Color(0xFFB3261E),
        ),
      );
    } finally {
      if (mounted) {
        setState(() {
          _collectingTemplateIds.remove(template.id);
        });
      }
    }
  }

  Future<void> _retryTask(
    TaskTemplateModel template,
    TaskListItemModel task,
  ) async {
    if (_retryingTaskIds.contains(task.id)) {
      return;
    }
    setState(() {
      _retryingTaskIds.add(task.id);
    });
    try {
      final result = await _taskRepository.runTask(task.id);
      await _loadTaskHealth();
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            result.status == 'queued'
                ? '已重新排队执行 ${template.label}。'
                : '已触发 ${template.label}，当前状态：${result.status}。',
          ),
        ),
      );
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('重试 ${template.label} 失败：${userFacingError(error)}'),
          backgroundColor: const Color(0xFFB3261E),
        ),
      );
    } finally {
      if (mounted) {
        setState(() {
          _retryingTaskIds.remove(task.id);
        });
      }
    }
  }

  Future<void> _openTemplateEditor([TaskTemplateModel? template]) async {
    bool? saved;
    try {
      saved = await showDialog<bool>(
        context: context,
        builder: (context) => _TemplateEditorDialog(
          template: template,
          repository: widget.templateRepository,
        ),
      );
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('打开模板编辑器失败：${userFacingError(error)}'),
          backgroundColor: const Color(0xFFB3261E),
        ),
      );
      return;
    }

    if (saved == true && mounted) {
      try {
        await widget.onTemplatesChanged();
      } catch (error) {
        if (!mounted) {
          return;
        }
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('刷新模板列表失败：${userFacingError(error)}'),
            backgroundColor: const Color(0xFFB3261E),
          ),
        );
        return;
      }
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(template == null ? '模板已创建。' : '模板已更新。'),
        ),
      );
    }
  }

  Future<void> _deleteTemplate(TaskTemplateModel template) async {
    if (_deletingTemplateIds.contains(template.id) ||
        _usingTemplateIds.contains(template.id) ||
        _collectingTemplateIds.contains(template.id)) {
      return;
    }
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('删除模板？'),
        content: Text('这会永久删除“${template.label}”。'),
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

    setState(() {
      _deletingTemplateIds.add(template.id);
    });
    try {
      await widget.templateRepository.deleteTaskTemplate(template.id);
      await widget.onTemplatesChanged();
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('模板“${template.label}”已删除。')),
      );
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('删除模板失败：${userFacingError(error)}'),
          backgroundColor: const Color(0xFFB3261E),
        ),
      );
    } finally {
      if (mounted) {
        setState(() {
          _deletingTemplateIds.remove(template.id);
        });
      }
    }
  }

  void _selectTag(String tag) {
    setState(() {
      _selectedTag = tag;
    });
  }

  void _clearFilters() {
    _templateSearchController.clear();
    if (_selectedTag != null) {
      setState(() {
        _selectedTag = null;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final visible = _visibleTemplates();
    return AppPageFrame(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _SourceSitesPageHero(
            templates: widget.templates,
            onCreate: () => _openTemplateEditor(),
            onRefresh: _refreshTemplates,
            refreshing: _refreshing,
          ),
          const SizedBox(height: 16),
          Expanded(
            child: widget.templates.isEmpty
                ? _SourceSitesEmptyState(
                    onCreate: () => _openTemplateEditor(),
                  )
                : Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      _TemplateFilterBar(
                        searchController: _templateSearchController,
                        sortKey: _sortKey,
                        sortAscending: _sortAscending,
                        onSortKeyChanged: (v) {
                          setState(() {
                            _sortKey = v;
                          });
                        },
                        onToggleAscending: () {
                          setState(() {
                            _sortAscending = !_sortAscending;
                          });
                        },
                        onClearSearch: () {
                          _clearFilters();
                        },
                        selectedTag: _selectedTag,
                        onClearTag: () {
                          setState(() {
                            _selectedTag = null;
                          });
                        },
                        matchCount: visible.length,
                        totalCount: widget.templates.length,
                      ),
                      const SizedBox(height: 12),
                      if (_taskHealthLoading || _taskHealthError != null) ...[
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 14,
                            vertical: 12,
                          ),
                          decoration: BoxDecoration(
                            color: _taskHealthError == null
                                ? const Color(0xFFEAF3FF)
                                : const Color(0xFFFFF4E5),
                            borderRadius: BorderRadius.circular(12),
                            border: Border.all(
                              color: _taskHealthError == null
                                  ? const Color(0xFFB8D2F2)
                                  : const Color(0xFFE8BF87),
                            ),
                          ),
                          child: Row(
                            children: [
                              Icon(
                                _taskHealthError == null
                                    ? Icons.sync
                                    : Icons.warning_amber_rounded,
                                color: _taskHealthError == null
                                    ? const Color(0xFF1E4F8A)
                                    : const Color(0xFF8A4B00),
                                size: 18,
                              ),
                              const SizedBox(width: 10),
                              Expanded(
                                child: Text(
                                  _taskHealthError == null
                                      ? '正在同步任务状态和最近日志...'
                                      : '任务状态加载失败，当前先显示模板配置状态：$_taskHealthError',
                                  style: Theme.of(context).textTheme.bodyMedium,
                                ),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 12),
                      ],
                      Expanded(
                        child: visible.isEmpty
                            ? Card(
                                child: Padding(
                                  padding: const EdgeInsets.all(28),
                                  child: Column(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    children: [
                                      Text(
                                        '没有匹配的模板',
                                        style: Theme.of(context)
                                            .textTheme
                                            .titleMedium,
                                      ),
                                      const SizedBox(height: 8),
                                      Text(
                                        '试试缩短关键词，或清空搜索。',
                                        style: Theme.of(context)
                                            .textTheme
                                            .bodyMedium,
                                      ),
                                      const SizedBox(height: 16),
                                      OutlinedButton(
                                        onPressed: () {
                                          _templateSearchController.clear();
                                        },
                                        child: const Text('清空搜索'),
                                      ),
                                    ],
                                  ),
                                ),
                              )
                            : Scrollbar(
                                controller: _templateListScrollController,
                                thumbVisibility: true,
                                child: ListView.separated(
                                  controller: _templateListScrollController,
                                  itemCount: visible.length,
                                  separatorBuilder: (_, __) =>
                                      const SizedBox(height: 16),
                                  itemBuilder: (context, index) {
                                    final template = visible[index];
                                    final health =
                                        _taskHealthByTemplateId[template.id];
                                    final runtimeStatus =
                                        resolveSourceSiteRuntimeStatus(
                                      template: template,
                                      task: health?.task,
                                      latestLog: health?.latestLog,
                                      latestSummaryLog: health?.latestSummaryLog,
                                    );
                                    final latestSuccessText =
                                        _formatLastSuccess(health?.task);
                                    final usingTemplate =
                                        _usingTemplateIds.contains(template.id);
                                    final deletingTemplate =
                                        _deletingTemplateIds
                                            .contains(template.id);
                                    final collectingTemplate =
                                        _collectingTemplateIds
                                            .contains(template.id);
                                    final retryingTask =
                                        _retryingTaskIds.contains(health?.task?.id);
                                    final busy = usingTemplate ||
                                        deletingTemplate ||
                                        collectingTemplate ||
                                        retryingTask;
                                    const cardRadius = BorderRadius.all(
                                      Radius.circular(12),
                                    );
                                    return Semantics(
                                      button: true,
                                      label:
                                          '编辑模板 ${template.label}，${template.description}',
                                      child: MouseRegion(
                                        cursor: busy
                                            ? SystemMouseCursors.basic
                                            : SystemMouseCursors.click,
                                        child: Card(
                                          clipBehavior: Clip.antiAlias,
                                          child: InkWell(
                                            key: Key(
                                              'source-template-card-${template.id}',
                                            ),
                                            borderRadius: cardRadius,
                                            onTap: busy
                                                ? null
                                                : () => _openTemplateEditor(
                                                      template,
                                                    ),
                                            focusColor: const Color(0xFF1E4F8A)
                                                .withValues(alpha: 0.12),
                                            hoverColor: const Color(0xFF1E4F8A)
                                                .withValues(alpha: 0.06),
                                            child: AnimatedContainer(
                                              duration: const Duration(
                                                milliseconds: 180,
                                              ),
                                              curve: Curves.easeOut,
                                              decoration: BoxDecoration(
                                                gradient: LinearGradient(
                                                  begin: Alignment.topLeft,
                                                  end: Alignment.bottomRight,
                                                  colors: [
                                                    const Color(0xFF1E4F8A)
                                                        .withValues(
                                                            alpha: 0.05),
                                                    Colors.white,
                                                  ],
                                                ),
                                              ),
                                              child: Padding(
                                                padding:
                                                    const EdgeInsets.all(20),
                                                child: Column(
                                                  crossAxisAlignment:
                                                      CrossAxisAlignment.start,
                                                  children: [
                                                    Row(
                                                      crossAxisAlignment:
                                                          CrossAxisAlignment
                                                              .start,
                                                      children: [
                                                        Expanded(
                                                          child: Text(
                                                            template.label,
                                                            style: Theme.of(
                                                                    context)
                                                                .textTheme
                                                                .titleLarge,
                                                          ),
                                                        ),
                                                        Wrap(
                                                          spacing: 8,
                                                          runSpacing: 8,
                                                          children:
                                                              template.tags
                                                                  .map(
                                                                    (tag) =>
                                                                        ActionChip(
                                                                      key: Key(
                                                                        'source-template-tag-${template.id}-$tag',
                                                                      ),
                                                                      label: Text(
                                                                          tag),
                                                                      tooltip:
                                                                          '按“$tag”筛选模板',
                                                                      onPressed:
                                                                          () =>
                                                                              _selectTag(tag),
                                                                    ),
                                                                  )
                                                                  .toList(),
                                                        ),
                                                      ],
                                                    ),
                                                    const SizedBox(height: 12),
                                                    Text(
                                                      template.description,
                                                      style: Theme.of(context)
                                                          .textTheme
                                                          .bodyMedium,
                                                    ),
                                                    const SizedBox(height: 12),
                                                    Container(
                                                      key: Key(
                                                        'source-template-status-${template.id}',
                                                      ),
                                                      padding: const EdgeInsets
                                                          .symmetric(
                                                        horizontal: 12,
                                                        vertical: 8,
                                                      ),
                                                      decoration: BoxDecoration(
                                                        color: runtimeStatus
                                                            .backgroundColor,
                                                        borderRadius:
                                                            BorderRadius
                                                                .circular(
                                                          999,
                                                        ),
                                                        border: Border.all(
                                                          color:
                                                              runtimeStatus
                                                                  .borderColor,
                                                        ),
                                                      ),
                                                      child: Row(
                                                        mainAxisSize:
                                                            MainAxisSize.min,
                                                        children: [
                                                          Icon(
                                                            runtimeStatus.icon,
                                                            size: 16,
                                                            color: runtimeStatus
                                                                .foregroundColor,
                                                          ),
                                                          const SizedBox(
                                                            width: 6,
                                                          ),
                                                          Text(
                                                            runtimeStatus.label,
                                                            key: Key(
                                                              'source-template-status-label-${template.id}',
                                                            ),
                                                            style: Theme.of(
                                                                    context)
                                                                .textTheme
                                                                .labelLarge
                                                                ?.copyWith(
                                                                  color: runtimeStatus
                                                                      .foregroundColor,
                                                                  fontWeight:
                                                                      FontWeight
                                                                          .w700,
                                                                ),
                                                          ),
                                                        ],
                                                      ),
                                                    ),
                                                    const SizedBox(height: 8),
                                                    Text(
                                                      runtimeStatus.note,
                                                      key: Key(
                                                        'source-template-status-note-${template.id}',
                                                      ),
                                                      style: Theme.of(context)
                                                          .textTheme
                                                          .bodySmall
                                                          ?.copyWith(
                                                            color: const Color(
                                                              0xFF556A86,
                                                            ),
                                                            height: 1.45,
                                                          ),
                                                    ),
                                                    const SizedBox(height: 12),
                                                    _TemplateMetaRow(
                                                      key: Key(
                                                        'source-template-last-success-${template.id}',
                                                      ),
                                                      label: '最近成功',
                                                      value: latestSuccessText,
                                                    ),
                                                    if (runtimeStatus.latestLog !=
                                                            null &&
                                                        runtimeStatus.latestLog!
                                                            .trim()
                                                            .isNotEmpty)
                                                      _TemplateMetaRow(
                                                        key: Key(
                                                          'source-template-latest-log-${template.id}',
                                                        ),
                                                        label: '最新日志',
                                                        value:
                                                            runtimeStatus.latestLog!,
                                                      ),
                                                    const SizedBox(height: 16),
                                                    _TemplateMetaRow(
                                                      label: '建议任务名',
                                                      value: template.name,
                                                    ),
                                                    _TemplateMetaRow(
                                                      label: '起始地址',
                                                      value: template.startUrl,
                                                    ),
                                                    _TemplateMetaRow(
                                                      label: '定时表达式',
                                                      value: template.cronExpr,
                                                    ),
                                                    _TemplateMetaRow(
                                                      label: '解析规则',
                                                      value: template
                                                              .parserRules ??
                                                          '使用可读性兜底解析',
                                                    ),
                                                    _TemplateMetaRow(
                                                      label: '使用情况',
                                                      value:
                                                          '已使用 ${template.usageCount} 次'
                                                          '${template.lastUsedAt == null ? '' : ' · 最近使用 ${template.lastUsedAt}'}',
                                                    ),
                                                    const SizedBox(height: 8),
                                                    Wrap(
                                                      spacing: 8,
                                                      runSpacing: 8,
                                                      children: [
                                                        if (runtimeStatus.canRetry &&
                                                            health?.task != null)
                                                          FilledButton.icon(
                                                            key: Key(
                                                              'source-template-retry-${template.id}',
                                                            ),
                                                            onPressed: busy
                                                                ? null
                                                                : () => _retryTask(
                                                                      template,
                                                                      health!.task!,
                                                                    ),
                                                            icon: retryingTask
                                                                ? const SizedBox.square(
                                                                    dimension: 18,
                                                                    child:
                                                                        CircularProgressIndicator(
                                                                      strokeWidth:
                                                                          2,
                                                                    ),
                                                                  )
                                                                : const Icon(
                                                                    Icons.refresh,
                                                                    size: 18,
                                                                  ),
                                                            label: Text(
                                                              retryingTask
                                                                  ? '正在重试'
                                                                  : '重试任务',
                                                            ),
                                                          ),
                                                        if (manualSourceIds
                                                            .contains(
                                                                template.id))
                                                          FilledButton.icon(
                                                            key: Key(
                                                              'source-template-collect-${template.id}',
                                                            ),
                                                            onPressed: busy
                                                                ? null
                                                                : () =>
                                                                    _collectManualSource(
                                                                      template,
                                                                    ),
                                                            icon:
                                                                collectingTemplate
                                                                    ? const SizedBox
                                                                        .square(
                                                                        dimension:
                                                                            18,
                                                                        child:
                                                                            CircularProgressIndicator(
                                                                          strokeWidth:
                                                                              2,
                                                                        ),
                                                                      )
                                                                    : const Icon(
                                                                        Icons
                                                                            .add_link,
                                                                        size:
                                                                            18,
                                                                      ),
                                                            label: Text(
                                                              collectingTemplate
                                                                  ? '正在登记'
                                                                  : '登记文章链接',
                                                            ),
                                                          ),
                                                        FilledButton.tonal(
                                                          key: Key(
                                                            'source-template-use-${template.id}',
                                                          ),
                                                          onPressed:
                                                              widget.onUseTemplate ==
                                                                          null ||
                                                                      busy
                                                                  ? null
                                                                  : () =>
                                                                      _useTemplate(
                                                                        template,
                                                                      ),
                                                          child: usingTemplate
                                                              ? const SizedBox
                                                                  .square(
                                                                  dimension: 18,
                                                                  child:
                                                                      CircularProgressIndicator(
                                                                    strokeWidth:
                                                                        2,
                                                                  ),
                                                                )
                                                              : const Text(
                                                                  '使用此模板'),
                                                        ),
                                                        OutlinedButton(
                                                          key: Key(
                                                            'source-template-edit-${template.id}',
                                                          ),
                                                          onPressed: busy
                                                              ? null
                                                              : () =>
                                                                  _openTemplateEditor(
                                                                    template,
                                                                  ),
                                                          child:
                                                              const Text('编辑'),
                                                        ),
                                                        OutlinedButton(
                                                          key: Key(
                                                            'source-template-delete-${template.id}',
                                                          ),
                                                          onPressed: busy
                                                              ? null
                                                              : () =>
                                                                  _deleteTemplate(
                                                                    template,
                                                                  ),
                                                          style: OutlinedButton
                                                              .styleFrom(
                                                            foregroundColor:
                                                                const Color(
                                                              0xFFB3261E,
                                                            ),
                                                          ),
                                                          child:
                                                              deletingTemplate
                                                                  ? const SizedBox
                                                                      .square(
                                                                      dimension:
                                                                          18,
                                                                      child:
                                                                          CircularProgressIndicator(
                                                                        strokeWidth:
                                                                            2,
                                                                      ),
                                                                    )
                                                                  : const Text(
                                                                      '删除'),
                                                        ),
                                                      ],
                                                    ),
                                                  ],
                                                ),
                                              ),
                                            ),
                                          ),
                                        ),
                                      ),
                                    );
                                  },
                                ),
                              ),
                      ),
                    ],
                  ),
          ),
        ],
      ),
    );
  }
}

String _formatLastSuccess(TaskListItemModel? task) {
  final lastSuccessAt = task?.lastSuccessAt;
  if (lastSuccessAt == null || lastSuccessAt.trim().isEmpty) {
    return '暂无成功记录';
  }
  return DateFormatter.formatDateTime(lastSuccessAt);
}

class _TaskHealthSnapshot {
  final TaskListItemModel? task;
  final TaskLogItemModel? latestLog;
  final TaskLogItemModel? latestSummaryLog;

  const _TaskHealthSnapshot({
    required this.task,
    required this.latestLog,
    required this.latestSummaryLog,
  });
}

class _TemplateFilterBar extends StatelessWidget {
  final TextEditingController searchController;
  final String sortKey;
  final bool sortAscending;
  final String? selectedTag;
  final ValueChanged<String> onSortKeyChanged;
  final VoidCallback onToggleAscending;
  final VoidCallback onClearSearch;
  final VoidCallback onClearTag;
  final int matchCount;
  final int totalCount;

  const _TemplateFilterBar({
    required this.searchController,
    required this.sortKey,
    required this.sortAscending,
    required this.selectedTag,
    required this.onSortKeyChanged,
    required this.onToggleAscending,
    required this.onClearSearch,
    required this.onClearTag,
    required this.matchCount,
    required this.totalCount,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        child: Wrap(
          spacing: 12,
          runSpacing: 12,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            SizedBox(
              width: 260,
              child: TextField(
                controller: searchController,
                decoration: const InputDecoration(
                  labelText: '搜索模板',
                  hintText: '名称、描述、URL、标签、ID',
                  prefixIcon: Icon(Icons.search),
                  isDense: true,
                  border: OutlineInputBorder(),
                ),
              ),
            ),
            SizedBox(
              width: 200,
              child: InputDecorator(
                decoration: const InputDecoration(
                  labelText: '排序',
                  isDense: true,
                  border: OutlineInputBorder(),
                  contentPadding:
                      EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                ),
                child: DropdownButtonHideUnderline(
                  child: DropdownButton<String>(
                    isExpanded: true,
                    value: sortKey,
                    items: const [
                      DropdownMenuItem(value: 'label', child: Text('按名称')),
                      DropdownMenuItem(value: 'usage', child: Text('按使用次数')),
                      DropdownMenuItem(
                        value: 'last_used',
                        child: Text('按最近使用'),
                      ),
                    ],
                    onChanged: (v) {
                      if (v != null) {
                        onSortKeyChanged(v);
                      }
                    },
                  ),
                ),
              ),
            ),
            IconButton.filledTonal(
              tooltip: sortAscending ? '当前升序，点击改为降序' : '当前降序，点击改为升序',
              onPressed: onToggleAscending,
              icon: Icon(
                sortAscending ? Icons.arrow_upward : Icons.arrow_downward,
              ),
            ),
            TextButton.icon(
              onPressed: onClearSearch,
              icon: const Icon(Icons.clear, size: 18),
              label: const Text('清空筛选'),
            ),
            if (selectedTag != null)
              InputChip(
                label: Text('筛选标签：$selectedTag'),
                tooltip: '清除标签筛选',
                onDeleted: onClearTag,
              ),
            Text(
              '显示 $matchCount / $totalCount',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }
}

class _SourceSitesPageHero extends StatelessWidget {
  final List<TaskTemplateModel> templates;
  final VoidCallback onCreate;
  final Future<void> Function() onRefresh;
  final bool refreshing;

  const _SourceSitesPageHero({
    required this.templates,
    required this.onCreate,
    required this.onRefresh,
    required this.refreshing,
  });

  @override
  Widget build(BuildContext context) {
    return AppPageHero(
      title: '来源站点模板',
      subtitle: '沉淀可复用的采集蓝图，减少重复配置，并把常用来源统一到同一套模板规范里。',
      primaryChips: const [
        AppPageHeroChipData.overlay('模板复用'),
        AppPageHeroChipData.overlay('一键套用'),
        AppPageHeroChipData.overlay('支持 CRUD'),
      ],
      secondaryChips: [
        AppPageHeroChipData.overlay('模板总数 · ${templates.length}'),
        const AppPageHeroChipData.overlay('同步任务蓝图'),
        const AppPageHeroChipData.overlay('记录使用统计'),
      ],
      actions: [
        FilledButton.tonalIcon(
          onPressed: onCreate,
          icon: const Icon(Icons.add),
          label: const Text('新建模板'),
        ),
        FilledButton.tonalIcon(
          onPressed: refreshing
              ? null
              : () {
                  onRefresh();
                },
          icon: refreshing
              ? const SizedBox.square(
                  dimension: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.refresh),
          label: Text(refreshing ? '刷新中' : '刷新'),
        ),
      ],
    );
  }
}

// ignore: unused_element
class _SourceSitesHero extends StatelessWidget {
  final List<TaskTemplateModel> templates;
  final VoidCallback onCreate;

  const _SourceSitesHero({
    required this.templates,
    required this.onCreate,
  });

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final isCompact = constraints.maxWidth < 760;

        final content = Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '来源站点模板',
              style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                    color: Colors.white,
                  ),
            ),
            const SizedBox(height: 8),
            Text(
              '为常见来源站点沉淀可复用的采集模板，减少重复配置工作。',
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: const Color(0xE6F3F8FF),
                  ),
            ),
            const SizedBox(height: 16),
            Wrap(
              spacing: 10,
              runSpacing: 10,
              children: [
                _HeroChip(label: '模板总数 ${templates.length}'),
                const _HeroChip(label: '一键套用任务蓝图'),
                const _HeroChip(label: '支持 CRUD 与使用统计'),
              ],
            ),
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
                    content,
                    const SizedBox(height: 16),
                    FilledButton.icon(
                      onPressed: onCreate,
                      icon: const Icon(Icons.add),
                      label: const Text('新建模板'),
                    ),
                  ],
                )
              : Row(
                  children: [
                    Expanded(child: content),
                    const SizedBox(width: 16),
                    FilledButton.icon(
                      onPressed: onCreate,
                      icon: const Icon(Icons.add),
                      label: const Text('新建模板'),
                    ),
                  ],
                ),
        );
      },
    );
  }
}

class _SourceSitesEmptyState extends StatelessWidget {
  final VoidCallback onCreate;

  const _SourceSitesEmptyState({required this.onCreate});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 56,
              height: 56,
              decoration: BoxDecoration(
                color: const Color(0xFFEAF3FF),
                borderRadius: BorderRadius.circular(18),
              ),
              child:
                  const Icon(Icons.language_outlined, color: Color(0xFF1E4F8A)),
            ),
            const SizedBox(height: 18),
            Text('还没有模板', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 10),
            Text(
              '先创建一个模板，再通过模板快速生成任务并沉淀来源站点配置。',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 18),
            FilledButton.icon(
              onPressed: onCreate,
              icon: const Icon(Icons.add),
              label: const Text('创建第一个模板'),
            ),
          ],
        ),
      ),
    );
  }
}

class _HeroChip extends StatelessWidget {
  final String label;

  const _HeroChip({required this.label});

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

class _TemplateMetaRow extends StatelessWidget {
  final String label;
  final String value;

  const _TemplateMetaRow({
    super.key,
    required this.label,
    required this.value,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: Theme.of(context).textTheme.labelLarge,
          ),
          const SizedBox(height: 4),
          SelectableText(value),
        ],
      ),
    );
  }
}

class _TemplateEditorDialog extends StatefulWidget {
  final TaskTemplateModel? template;
  final HttpTemplateRepository repository;

  const _TemplateEditorDialog({
    this.template,
    required this.repository,
  });

  @override
  State<_TemplateEditorDialog> createState() => _TemplateEditorDialogState();
}

class _TemplateEditorDialogState extends State<_TemplateEditorDialog> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _labelController;
  late final TextEditingController _nameController;
  late final TextEditingController _urlController;
  late final TextEditingController _cronController;
  late final TextEditingController _rulesController;
  late final TextEditingController _descriptionController;
  late final TextEditingController _tagsController;
  late bool _enabled;
  bool _submitting = false;
  String? _submitError;
  bool _testing = false;
  String? _testResult;

  @override
  void initState() {
    super.initState();
    final template = widget.template;
    _labelController = TextEditingController(text: template?.label ?? '');
    _nameController = TextEditingController(text: template?.name ?? '');
    _urlController = TextEditingController(text: template?.startUrl ?? '');
    _cronController =
        TextEditingController(text: template?.cronExpr ?? '0 */6 * * *');
    _rulesController = TextEditingController(text: template?.parserRules ?? '');
    _descriptionController =
        TextEditingController(text: template?.description ?? '');
    _tagsController =
        TextEditingController(text: template?.tags.join(', ') ?? '');
    _enabled = template?.enabled ?? true;
  }

  @override
  void dispose() {
    _labelController.dispose();
    _nameController.dispose();
    _urlController.dispose();
    _cronController.dispose();
    _rulesController.dispose();
    _descriptionController.dispose();
    _tagsController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_submitting || _testing) return;
    if (!_formKey.currentState!.validate()) {
      return;
    }

    setState(() {
      _submitting = true;
      _submitError = null;
      _testResult = null;
    });

    final template = TaskTemplateModel(
      id: widget.template?.id ??
          _labelController.text.trim().toLowerCase().replaceAll(' ', '_'),
      label: _labelController.text.trim(),
      name: _nameController.text.trim(),
      startUrl: _urlController.text.trim(),
      cronExpr: _cronController.text.trim(),
      parserRules: _nullableText(_rulesController.text),
      enabled: _enabled,
      description: _descriptionController.text.trim(),
      tags: _tagsController.text
          .split(',')
          .map((tag) => tag.trim())
          .where((tag) => tag.isNotEmpty)
          .toList(),
      usageCount: widget.template?.usageCount ?? 0,
      lastUsedAt: widget.template?.lastUsedAt,
    );

    try {
      if (widget.template == null) {
        await widget.repository.createTaskTemplate(template);
      } else {
        await widget.repository.updateTaskTemplate(template);
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

  Future<void> _testTemplate() async {
    if (_testing || _submitting) return;
    setState(() {
      _submitError = null;
      _testResult = null;
    });

    final startUrl = _urlController.text.trim();
    if (startUrl.isEmpty ||
        (!startUrl.startsWith('http://') && !startUrl.startsWith('https://'))) {
      setState(() {
        _submitError = '请先填写合法的起始地址';
      });
      return;
    }

    setState(() {
      _testing = true;
    });

    try {
      final req = TestTemplateRequest(
        startUrl: startUrl,
        parserRules: _nullableText(_rulesController.text),
      );
      final res = await widget.repository.testTaskTemplate(req);
      if (!mounted) return;

      setState(() {
        if (res.error != null) {
          final t = res.trace;
          final traceLines = t == null
              ? ''
              : '\n抓取：${t.fetch ?? '-'}\n'
                  '正文来源：${t.contentSource ?? '-'}\n'
                  '${t.notes.isEmpty ? '' : '说明：\n${t.notes.map((n) => '  · $n').join('\n')}\n'}';
          _testResult = '测试出错：$traceLines\n${res.error}';
        } else {
          final contentPreview = res.contentText != null
              ? (res.contentText!.length > 300
                  ? '${res.contentText!.substring(0, 300)}...\n[剩余内容已截断]'
                  : res.contentText!)
              : '无';
          final t = res.trace;
          final traceLines = t == null
              ? ''
              : '\n抓取：${t.fetch ?? '-'}\n'
                  '正文来源：${t.contentSource ?? '-'}\n'
                  '${t.notes.isEmpty ? '' : '说明：\n${t.notes.map((n) => '  · $n').join('\n')}\n'}';
          _testResult = '测试成功：\n'
              '标题：${res.title ?? '未提取到标题'}\n'
              '质量分：${res.qualityScore ?? 0}\n'
              '正文长度：${res.contentText?.length ?? 0} 字符\n'
              'HTML长度：${res.contentHtml?.length ?? 0} 字符\n'
              '$traceLines'
              '------------------------------\n'
              '正文预览：\n$contentPreview';
        }
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _testResult = '请求异常：${userFacingError(e)}';
      });
    } finally {
      if (mounted) {
        setState(() {
          _testing = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.template == null ? '新建模板' : '编辑模板'),
      content: SizedBox(
        width: 560,
        child: Form(
          key: _formKey,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
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
                  controller: _nameController,
                  decoration: const InputDecoration(
                    labelText: '建议任务名',
                  ),
                  validator: (value) =>
                      value == null || value.trim().isEmpty ? '必填项' : null,
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
                      return '必填项';
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
                  ),
                  validator: (value) =>
                      value == null || value.trim().isEmpty ? '必填项' : null,
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: _rulesController,
                  maxLines: 4,
                  decoration: const InputDecoration(
                    labelText: '解析规则 JSON',
                  ),
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
                const SizedBox(height: 12),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('默认启用'),
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
                if (_testing) ...[
                  const SizedBox(height: 16),
                  const Center(child: CircularProgressIndicator()),
                ] else if (_testResult != null) ...[
                  const SizedBox(height: 16),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: const Color(0xFFF0F5FF),
                      border: Border.all(
                          color:
                              const Color(0xFF1E4F8A).withValues(alpha: 0.2)),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: SelectableText(
                      _testResult!,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            fontFamily: 'Courier',
                            height: 1.5,
                          ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
      actions: [
        OutlinedButton.icon(
          onPressed: _testing || _submitting ? null : _testTemplate,
          icon: const Icon(Icons.bug_report, size: 18),
          label: const Text('在线测试'),
        ),
        TextButton(
          onPressed: _submitting || _testing
              ? null
              : () => Navigator.of(context).pop(false),
          child: const Text('取消'),
        ),
        FilledButton(
          onPressed: _submitting || _testing ? null : _submit,
          child: Text(_submitting ? '保存中...' : '保存'),
        ),
      ],
    );
  }
}
