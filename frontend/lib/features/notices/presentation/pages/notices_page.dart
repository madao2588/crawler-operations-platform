import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

import '../../../../app/navigation/app_navigation_intent.dart';
import '../../../../core/export_download.dart';
import '../../../../core/network/api_client.dart';
import '../../../../core/utils/date_formatter.dart';
import '../../../../core/utils/user_facing_error.dart';
import '../../../../core/widgets/async_error_panel.dart';
import '../../../../core/widgets/page_chrome.dart';
import '../../../../shared/models/page_data.dart';
import '../../data/models/notice_models.dart';
import '../../data/repositories/http_notice_repository.dart';
import '../../data/repositories/notice_repository.dart';
import '../../../system_management/data/models/task_models.dart';
import '../../../system_management/data/repositories/http_task_repository.dart';
import '../widgets/competitor_intelligence_panel.dart';
import 'package:url_launcher/url_launcher.dart';

class NoticesPage extends StatefulWidget {
  final NoticeQuery initialQuery;
  final int? initialNoticeId;
  final NoticeRepository? repository;

  const NoticesPage({
    super.key,
    this.initialQuery = const NoticeQuery(),
    this.initialNoticeId,
    this.repository,
  });

  @override
  State<NoticesPage> createState() => _NoticesPageState();
}

class _NoticesPageState extends State<NoticesPage> {
  late final NoticeRepository _repository;
  late final HttpTaskRepository _taskRepository;
  late Future<PageData<NoticeListItemModel>> _noticesFuture;
  List<NoticeSourceSiteOption> _sourceSiteOptions =
      const <NoticeSourceSiteOption>[];
  Future<NoticeDetailModel>? _detailFuture;
  int? _selectedNoticeId;
  Timer? _autoRefreshTimer;
  final ScrollController _listScrollController = ScrollController();
  final ScrollController _detailScrollController = ScrollController();
  final TextEditingController _searchController = TextEditingController();

  int _currentPage = 1;
  final int _pageSize = 20;
  String? _keyword;
  String? _categoryFilter;
  String? _reviewStatusFilter;
  bool? _archivedFilter;
  bool? _capturedTodayFilter;
  String? _sourceSiteFilter;
  bool? _keywordHitFilter;
  bool? _highPriorityFilter;
  bool? _highQualityFilter;
  String? _projectSignalFilter;
  bool _exportingCsv = false;
  bool _compactShowDetail = false;
  bool _isRecrawlInFlight = false;
  final Map<int, String> _reviewActionsInFlight = <int, String>{};

  static const Duration _taskPollInterval = Duration(seconds: 2);
  static const int _maxTaskPollAttempts = 30;

  @override
  void dispose() {
    _autoRefreshTimer?.cancel();
    _searchController.dispose();
    _listScrollController.dispose();
    _detailScrollController.dispose();
    super.dispose();
  }

  @override
  void initState() {
    super.initState();
    final client = ApiClient();
    _repository = widget.repository ?? HttpNoticeRepository(apiClient: client);
    _taskRepository = HttpTaskRepository(apiClient: client);
    final initialQuery = widget.initialQuery;
    _keyword = _normalizeText(initialQuery.keyword);
    _categoryFilter = _normalizeText(initialQuery.category);
    _reviewStatusFilter = _normalizeText(initialQuery.reviewStatus);
    _archivedFilter = initialQuery.archived;
    _capturedTodayFilter = initialQuery.capturedToday;
    _sourceSiteFilter = _normalizeText(initialQuery.sourceSite);
    _keywordHitFilter = initialQuery.keywordHit;
    _highPriorityFilter = initialQuery.highPriority;
    _highQualityFilter = initialQuery.highQuality;
    _projectSignalFilter = _normalizeText(initialQuery.projectSignal);
    _searchController.text = _keyword ?? '';
    _selectedNoticeId = widget.initialNoticeId;
    _compactShowDetail = _selectedNoticeId != null;
    if (_selectedNoticeId != null) {
      _detailFuture = _repository.fetchNoticeDetail(_selectedNoticeId!);
    }
    unawaited(_loadSourceSites());
    _noticesFuture = _fetchPage();
    _startAutoRefresh();
  }

  @override
  void didUpdateWidget(covariant NoticesPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.initialQuery == widget.initialQuery &&
        oldWidget.initialNoticeId == widget.initialNoticeId) {
      return;
    }

    final query = widget.initialQuery;
    _keyword = _normalizeText(query.keyword);
    _categoryFilter = _normalizeText(query.category);
    _reviewStatusFilter = _normalizeText(query.reviewStatus);
    _archivedFilter = query.archived;
    _capturedTodayFilter = query.capturedToday;
    _sourceSiteFilter = _normalizeText(query.sourceSite);
    _keywordHitFilter = query.keywordHit;
    _highPriorityFilter = query.highPriority;
    _highQualityFilter = query.highQuality;
    _projectSignalFilter = _normalizeText(query.projectSignal);
    _searchController.text = _keyword ?? '';
    _currentPage = 1;
    _selectedNoticeId = widget.initialNoticeId;
    _compactShowDetail = _selectedNoticeId != null;
    _detailFuture = _selectedNoticeId == null
        ? null
        : _repository.fetchNoticeDetail(_selectedNoticeId!);
    _noticesFuture = _fetchPage();
  }

  String? _normalizeText(String? value) {
    final normalized = value?.trim();
    return normalized == null || normalized.isEmpty ? null : normalized;
  }

  List<NoticeSourceSiteOption> _mergeSourceSites(
    List<NoticeListItemModel> items,
  ) {
    final options = <NoticeSourceSiteOption>[];
    final seen = <String>{};

    void add(NoticeSourceSiteOption option) {
      final sourceSite = _normalizeText(option.sourceSite);
      if (sourceSite != null && seen.add(sourceSite)) {
        final displayName = _normalizeText(option.displayName);
        options.add(
          NoticeSourceSiteOption(
            sourceSite: sourceSite,
            displayName: displayName ?? sourceSite,
          ),
        );
      }
    }

    for (final option in _sourceSiteOptions) {
      add(option);
    }
    for (final item in items) {
      add(
        NoticeSourceSiteOption(
          sourceSite: item.sourceSite,
          displayName: _sourceDisplayName(item.sourceSite),
        ),
      );
    }
    if (_sourceSiteFilter != null) {
      add(
        NoticeSourceSiteOption(
          sourceSite: _sourceSiteFilter!,
          displayName: _sourceDisplayName(_sourceSiteFilter!),
        ),
      );
    }
    return options;
  }

  String _sourceDisplayName(String sourceSite) {
    for (final option in _sourceSiteOptions) {
      if (option.sourceSite == sourceSite) {
        return option.displayName;
      }
    }
    return sourceSite.trim().isEmpty ? '未命名来源' : sourceSite;
  }

  Future<void> _loadSourceSites() async {
    try {
      final options = await _repository.fetchSourceSites();
      if (mounted) {
        setState(() {
          _sourceSiteOptions = options;
        });
      }
    } catch (_) {
      // 公告列表仍可使用；来源名称保持安全的业务回退文案。
    }
  }

  NoticeQuery get _currentQuery => NoticeQuery(
        keyword: _keyword,
        category: _categoryFilter,
        reviewStatus: _reviewStatusFilter,
        archived: _archivedFilter,
        capturedToday: _capturedTodayFilter,
        sourceSite: _sourceSiteFilter,
        keywordHit: _keywordHitFilter,
        highPriority: _highPriorityFilter,
        highQuality: _highQualityFilter,
        projectSignal: _projectSignalFilter,
      );

  Future<PageData<NoticeListItemModel>> _fetchPage() {
    return _repository.fetchNotices(
      page: _currentPage,
      pageSize: _pageSize,
      keyword: _keyword,
      category: _categoryFilter,
      reviewStatus: _reviewStatusFilter,
      archived: _archivedFilter,
      capturedToday: _capturedTodayFilter,
      sourceSite: _sourceSiteFilter,
      keywordHit: _keywordHitFilter,
      highPriority: _highPriorityFilter,
      highQuality: _highQualityFilter,
      projectSignal: _projectSignalFilter,
    );
  }

  void _onFiltersChanged({
    String? keyword,
    String? sourceSite,
    String? category,
    String? reviewStatus,
    bool? archived,
  }) {
    _applyQuery(
      NoticeQuery(
        keyword: keyword,
        category: category,
        reviewStatus: reviewStatus,
        archived: archived,
        capturedToday: _capturedTodayFilter,
        sourceSite: sourceSite,
        keywordHit: _keywordHitFilter,
        highPriority: _highPriorityFilter,
        highQuality: _highQualityFilter,
        projectSignal: _projectSignalFilter,
      ),
    );
  }

  void _applyQuery(NoticeQuery query) {
    setState(() {
      _keyword = _normalizeText(query.keyword);
      _categoryFilter = _normalizeText(query.category);
      _reviewStatusFilter = _normalizeText(query.reviewStatus);
      _archivedFilter = query.archived;
      _capturedTodayFilter = query.capturedToday;
      _sourceSiteFilter = _normalizeText(query.sourceSite);
      _keywordHitFilter = query.keywordHit;
      _highPriorityFilter = query.highPriority;
      _highQualityFilter = query.highQuality;
      _projectSignalFilter = _normalizeText(query.projectSignal);
      if (_searchController.text != (_keyword ?? '')) {
        _searchController.text = _keyword ?? '';
      }
      _currentPage = 1;
      _noticesFuture = _fetchPage();
    });
  }

  void _clearAllFilters() {
    _applyQuery(const NoticeQuery());
  }

  NoticeQuery _queryWithout({
    bool keyword = false,
    bool category = false,
    bool reviewStatus = false,
    bool archived = false,
    bool capturedToday = false,
    bool sourceSite = false,
    bool keywordHit = false,
    bool highPriority = false,
    bool highQuality = false,
    bool projectSignal = false,
  }) {
    return NoticeQuery(
      keyword: keyword ? null : _keyword,
      category: category ? null : _categoryFilter,
      reviewStatus: reviewStatus ? null : _reviewStatusFilter,
      archived: archived ? null : _archivedFilter,
      capturedToday: capturedToday ? null : _capturedTodayFilter,
      sourceSite: sourceSite ? null : _sourceSiteFilter,
      keywordHit: keywordHit ? null : _keywordHitFilter,
      highPriority: highPriority ? null : _highPriorityFilter,
      highQuality: highQuality ? null : _highQualityFilter,
      projectSignal: projectSignal ? null : _projectSignalFilter,
    );
  }

  void _removeFilter(String filterKey) {
    final query = switch (filterKey) {
      'keyword' => _queryWithout(keyword: true),
      'category' => _queryWithout(category: true),
      'reviewStatus' => _queryWithout(reviewStatus: true),
      'archived' => _queryWithout(archived: true),
      'capturedToday' => _queryWithout(capturedToday: true),
      'sourceSite' => _queryWithout(sourceSite: true),
      'keywordHit' => _queryWithout(keywordHit: true),
      'highPriority' => _queryWithout(highPriority: true),
      'highQuality' => _queryWithout(highQuality: true),
      'projectSignal' => _queryWithout(projectSignal: true),
      _ => _currentQuery,
    };
    _applyQuery(query);
  }

  void _applySavedView(String viewId) {
    final query = switch (viewId) {
      'today' => const NoticeQuery(capturedToday: true),
      'application' => const NoticeQuery(projectSignal: '申报通知'),
      'result-publication' => const NoticeQuery(projectSignal: '结果公示'),
      'meeting' => const NoticeQuery(category: '行业会议'),
      'focus' => const NoticeQuery(reviewStatus: '待关注'),
      _ => const NoticeQuery(),
    };
    _applyQuery(query);
  }

  String get _activeSavedView {
    if (_capturedTodayFilter == true) {
      return 'today';
    }
    if (_projectSignalFilter == '申报通知') {
      return 'application';
    }
    if (_projectSignalFilter == '结果公示') {
      return 'result-publication';
    }
    if (_categoryFilter == '行业会议') {
      return 'meeting';
    }
    if (_reviewStatusFilter == '待关注') {
      return 'focus';
    }
    return _currentQuery.isEmpty ? 'all' : 'custom';
  }

  void _filterByHighPriority() {
    _applyQuery(
      NoticeQuery(
        keyword: _keyword,
        category: _categoryFilter,
        reviewStatus: _reviewStatusFilter,
        archived: _archivedFilter,
        capturedToday: _capturedTodayFilter,
        sourceSite: _sourceSiteFilter,
        keywordHit: _keywordHitFilter,
        highPriority: true,
        highQuality: _highQualityFilter,
        projectSignal: _projectSignalFilter,
      ),
    );
  }

  void _filterByHighQuality() {
    _applyQuery(
      NoticeQuery(
        keyword: _keyword,
        category: _categoryFilter,
        reviewStatus: _reviewStatusFilter,
        archived: _archivedFilter,
        capturedToday: _capturedTodayFilter,
        sourceSite: _sourceSiteFilter,
        keywordHit: _keywordHitFilter,
        highPriority: _highPriorityFilter,
        highQuality: true,
        projectSignal: _projectSignalFilter,
      ),
    );
  }

  void _filterByKeywordHit() {
    _applyQuery(
      NoticeQuery(
        keyword: _keyword,
        category: _categoryFilter,
        reviewStatus: _reviewStatusFilter,
        archived: _archivedFilter,
        capturedToday: _capturedTodayFilter,
        sourceSite: _sourceSiteFilter,
        keywordHit: true,
        highPriority: _highPriorityFilter,
        highQuality: _highQualityFilter,
        projectSignal: _projectSignalFilter,
      ),
    );
  }

  void _filterBySource(String sourceSite) {
    _applyQuery(
      NoticeQuery(
        keyword: _keyword,
        category: _categoryFilter,
        reviewStatus: _reviewStatusFilter,
        archived: _archivedFilter,
        capturedToday: _capturedTodayFilter,
        sourceSite: sourceSite,
        keywordHit: _keywordHitFilter,
        highPriority: _highPriorityFilter,
        highQuality: _highQualityFilter,
        projectSignal: _projectSignalFilter,
      ),
    );
  }

  void _filterByCategory(String category) {
    _applyQuery(
      NoticeQuery(
        keyword: _keyword,
        category: category,
        reviewStatus: _reviewStatusFilter,
        archived: _archivedFilter,
        capturedToday: _capturedTodayFilter,
        sourceSite: _sourceSiteFilter,
        keywordHit: _keywordHitFilter,
        highPriority: _highPriorityFilter,
        highQuality: _highQualityFilter,
        projectSignal: _projectSignalFilter,
      ),
    );
  }

  void _filterByKeyword(String keyword) {
    _applyQuery(
      NoticeQuery(
        keyword: keyword,
        category: _categoryFilter,
        reviewStatus: _reviewStatusFilter,
        archived: _archivedFilter,
        capturedToday: _capturedTodayFilter,
        sourceSite: _sourceSiteFilter,
        keywordHit: _keywordHitFilter,
        highPriority: _highPriorityFilter,
        highQuality: _highQualityFilter,
        projectSignal: _projectSignalFilter,
      ),
    );
  }

  void _onPageChanged(int newPage) {
    setState(() {
      _currentPage = newPage;
      _noticesFuture = _fetchPage();
    });
  }

  void _showMessage(String message) {
    if (!mounted) {
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }

  void _showReCrawlFeedback(
    RunAllEnabledResultModel result, {
    required bool showFeedback,
  }) {
    if (!showFeedback || !mounted) {
      return;
    }

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
      _showMessage('$message，将继续等待并刷新列表。');
    } else if (result.quarantinedTaskIds.isNotEmpty) {
      _showMessage(
          '已隔离 ${result.quarantinedTaskIds.length} 个失败源，本次没有其余启用任务可触发采集。');
    } else {
      _showMessage('当前没有已启用任务可触发采集。');
    }

    if (result.errors.isNotEmpty) {
      _showMessage(result.errors.join('\n'));
    }
  }

  Future<void> _reloadPage({bool resetPage = false}) async {
    if (!mounted) {
      return;
    }
    setState(() {
      if (resetPage) {
        _currentPage = 1;
      }
      _noticesFuture = _fetchPage();
      if (_selectedNoticeId != null) {
        _detailFuture = _repository.fetchNoticeDetail(_selectedNoticeId!);
      }
    });
    await _noticesFuture;
  }

  Future<void> _waitForTasksToSettle({bool resetPage = false}) async {
    var firstReload = true;
    for (var attempt = 0; attempt < _maxTaskPollAttempts; attempt += 1) {
      if (!mounted) {
        return;
      }
      await _reloadPage(resetPage: firstReload && resetPage);
      firstReload = false;
      final stillActive =
          await _taskRepository.hasActiveOrQueuedTasksGlobally();
      if (!stillActive) {
        return;
      }
      await Future<void>.delayed(_taskPollInterval);
    }
    await _reloadPage();
  }

  Future<void> _triggerReCrawlAndRefresh({
    required bool resetPage,
    required bool showFeedback,
  }) async {
    if (_isRecrawlInFlight) {
      return;
    }
    if (!mounted) {
      return;
    }
    setState(() {
      _isRecrawlInFlight = true;
    });
    try {
      final result = await _taskRepository.runAllEnabledTasks();
      if (!mounted) {
        return;
      }
      _showReCrawlFeedback(result, showFeedback: showFeedback);
      final shouldPoll =
          result.queuedTaskIds.isNotEmpty || result.skippedTaskIds.isNotEmpty;
      if (shouldPoll) {
        await _waitForTasksToSettle(resetPage: resetPage);
      } else {
        await _reloadPage(resetPage: resetPage);
      }
    } catch (error) {
      if (showFeedback && mounted) {
        _showMessage('触发采集失败：${userFacingError(error)}');
      }
      await _reloadPage(resetPage: resetPage);
    } finally {
      if (mounted) {
        setState(() {
          _isRecrawlInFlight = false;
        });
      } else {
        _isRecrawlInFlight = false;
      }
    }
  }

  /// Manual pull-to-refresh: re-queue enabled tasks so DB can update; timer uses [_refreshCurrentPage] only.
  // ignore: unused_element
  Future<void> _requestReCrawlForEnabledTasks() async {
    try {
      final result = await _taskRepository.runAllEnabledTasks();
      if (!mounted) {
        return;
      }
      final q = result.queuedTaskIds.length;
      final messenger = ScaffoldMessenger.of(context);
      if (q > 0) {
        var message = '已为 $q 个已启用任务排队采集；完成后「采集时间」才会变，可稍后再下拉刷新。';
        if (result.quarantinedTaskIds.isNotEmpty) {
          message += ' 已隔离 ${result.quarantinedTaskIds.length} 个失败源。';
        }
        messenger.showSnackBar(
          SnackBar(
            content: Text(message),
          ),
        );
      } else if (result.skippedTaskIds.isNotEmpty) {
        var message = '没有新排队任务（均在运行或排队中），仅刷新列表。';
        if (result.quarantinedTaskIds.isNotEmpty) {
          message = '已隔离 ${result.quarantinedTaskIds.length} 个失败源；$message';
        }
        messenger.showSnackBar(
          SnackBar(
            content: Text(message),
          ),
        );
      } else if (result.quarantinedTaskIds.isNotEmpty) {
        messenger.showSnackBar(
          SnackBar(
            content: Text(
              '已隔离 ${result.quarantinedTaskIds.length} 个失败源，本次没有其余启用任务可排队。',
            ),
          ),
        );
      } else {
        messenger.showSnackBar(
          const SnackBar(
            content: Text('没有已启用的任务可排队；请先启用任务后再下拉刷新。'),
          ),
        );
      }
      if (result.errors.isNotEmpty) {
        messenger.showSnackBar(
          SnackBar(content: Text(result.errors.join('\n'))),
        );
      }
    } catch (e) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('触发采集失败：${userFacingError(e)}')),
      );
    }
  }

  Future<void> _refresh() async {
    await _triggerReCrawlAndRefresh(
      resetPage: true,
      showFeedback: true,
    );
    await _loadSourceSites();
  }

  Future<void> _exportInformationPool() async {
    if (_exportingCsv) {
      return;
    }
    setState(() {
      _exportingCsv = true;
    });
    final messenger = ScaffoldMessenger.of(context);
    try {
      final bytes = await _repository.downloadInformationPoolExcel(
        limit: 5000,
        category: _categoryFilter,
        reviewStatus: _reviewStatusFilter,
        archived: _archivedFilter,
      );
      final path = await triggerFileDownload(
        Uint8List.fromList(bytes),
        'information_pool_export.xls',
      );
      if (!mounted) {
        return;
      }
      if (path != null) {
        messenger.showSnackBar(
          SnackBar(content: Text('已写入临时文件：$path')),
        );
      } else {
        messenger.showSnackBar(
          const SnackBar(content: Text('已开始下载 information_pool_export.xls')),
        );
      }
    } catch (error) {
      if (mounted) {
        messenger.showSnackBar(
          SnackBar(content: Text('导出失败：${userFacingError(error)}')),
        );
      }
    } finally {
      if (mounted) {
        setState(() {
          _exportingCsv = false;
        });
      }
    }
  }

  // ignore: unused_element
  Future<void> _refreshCurrentPage() async {
    await _reloadPage();
  }

  void _startAutoRefresh() {
    _autoRefreshTimer?.cancel();
    _autoRefreshTimer = Timer.periodic(const Duration(minutes: 5), (_) async {
      if (!mounted || _isRecrawlInFlight) {
        return;
      }
      await _triggerReCrawlAndRefresh(
        resetPage: false,
        showFeedback: false,
      );
    });
  }

  void _selectNotice(int noticeId) {
    if (_selectedNoticeId == noticeId) {
      return;
    }
    setState(() {
      _selectedNoticeId = noticeId;
      _detailFuture = _repository.fetchNoticeDetail(noticeId);
    });
  }

  Future<void> _updateNoticeReview(
    int noticeId,
    NoticeReviewPayload payload,
  ) async {
    if (_reviewActionsInFlight.containsKey(noticeId)) {
      return;
    }
    final action =
        payload.reviewStatus ?? (payload.isArchived == null ? '更新' : '归档');
    setState(() {
      _reviewActionsInFlight[noticeId] = action;
    });
    try {
      final updated = await _repository.updateNoticeReview(noticeId, payload);
      if (!mounted) {
        return;
      }
      setState(() {
        if (_selectedNoticeId == noticeId) {
          _detailFuture = Future.value(updated);
        }
        _noticesFuture = _fetchPage();
      });
      _showMessage('标记已更新。');
    } catch (error) {
      if (!mounted) {
        return;
      }
      _showMessage('更新标记失败：${userFacingError(error)}');
    } finally {
      if (mounted) {
        setState(() {
          _reviewActionsInFlight.remove(noticeId);
        });
      }
    }
  }

  Future<void> _openSnapshot(
    BuildContext context,
    NoticeDetailModel detail, [
    String? keywordToHighlight,
  ]) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      final snapshot = await _repository.fetchSnapshot(detail.id);
      if (!context.mounted) {
        return;
      }
      await showDialog<void>(
        context: context,
        builder: (context) {
          return _SnapshotViewerDialog(
            content: snapshot.content,
            keywordToHighlight: keywordToHighlight,
          );
        },
      );
    } catch (error) {
      messenger.showSnackBar(
        SnackBar(content: Text('加载快照失败：${userFacingError(error)}')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<PageData<NoticeListItemModel>>(
      future: _noticesFuture,
      builder: (context, snapshot) {
        final rawItems = snapshot.data?.items ?? const <NoticeListItemModel>[];
        final items = List<NoticeListItemModel>.from(rawItems)
          ..sort((a, b) {
            final ah = a.matchedKeywords.isNotEmpty;
            final bh = b.matchedKeywords.isNotEmpty;
            if (ah == bh) {
              return 0;
            }
            return ah ? -1 : 1;
          });
        final compactDetailMode =
            MediaQuery.sizeOf(context).width < 600 && _compactShowDetail;
        return AppPageFrame(
          padding: EdgeInsets.all(
            MediaQuery.sizeOf(context).width < 600 ? 12 : 16,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (!compactDetailMode) ...[
                _NoticePageHero(
                  items: items,
                  total: snapshot.data?.total ?? 0,
                  activeSavedView: _activeSavedView,
                  highPrioritySelected: _highPriorityFilter == true,
                  highQualitySelected: _highQualityFilter == true,
                  keywordHitSelected: _keywordHitFilter == true,
                  onSelectSavedView: _applySavedView,
                  onShowAll: _clearAllFilters,
                  onShowHighPriority: _filterByHighPriority,
                  onShowHighQuality: _filterByHighQuality,
                  onShowKeywordHits: _filterByKeywordHit,
                  onRefresh: _refresh,
                  onExportCsv: _exportInformationPool,
                  isRefreshing: _isRecrawlInFlight,
                  isExportingCsv: _exportingCsv,
                ),
                const SizedBox(height: 10),
                _NoticeFilterBar(
                  searchController: _searchController,
                  sourceSite: _sourceSiteFilter,
                  sourceSites: _mergeSourceSites(items),
                  category: _categoryFilter,
                  reviewStatus: _reviewStatusFilter,
                  archived: _archivedFilter,
                  onChanged: _onFiltersChanged,
                ),
                if (!_currentQuery.isEmpty) ...[
                  const SizedBox(height: 8),
                  _ActiveNoticeFilters(
                    query: _currentQuery,
                    total: snapshot.data?.total ?? 0,
                    sourceDisplayName: _sourceSiteFilter == null
                        ? null
                        : _sourceDisplayName(_sourceSiteFilter!),
                    onRemove: _removeFilter,
                    onClear: _clearAllFilters,
                  ),
                ],
                const SizedBox(height: 10),
              ],
              Expanded(
                child: _buildBody(context, snapshot),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildBody(
    BuildContext context,
    AsyncSnapshot<PageData<NoticeListItemModel>> snapshot,
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
              Text('正在刷新公告列表...'),
            ],
          ),
        ),
      );
    }

    if (snapshot.hasError) {
      return AsyncErrorPanel(
        error: snapshot.error!,
        title: '加载公告列表失败',
        onRetry: _refresh,
      );
    }

    final items = snapshot.data?.items ?? const <NoticeListItemModel>[];
    if (items.isEmpty) {
      return _EmptyStateCard(
        icon: Icons.inbox_outlined,
        title: '暂无公告数据',
        description: '当前没有可展示的公告，等采集任务再次运行后这里会自动更新。',
        actionLabel: '刷新',
        onAction: _refresh,
      );
    }

    final selectedNoticeId = _syncSelection(items);

    final totalPages = (snapshot.data?.total ?? 0) / _pageSize;
    final maxPage = totalPages.ceil();
    final effectiveMaxPage = maxPage == 0 && items.isNotEmpty ? 1 : maxPage;

    final paginationRow = FittedBox(
      fit: BoxFit.scaleDown,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          IconButton(
            icon: const Icon(Icons.chevron_left),
            onPressed: _currentPage > 1
                ? () => _onPageChanged(_currentPage - 1)
                : null,
          ),
          Text('第 $_currentPage 页 / 共 $effectiveMaxPage 页'),
          IconButton(
            icon: const Icon(Icons.chevron_right),
            onPressed: _currentPage < effectiveMaxPage
                ? () => _onPageChanged(_currentPage + 1)
                : null,
          ),
        ],
      ),
    );

    final isCompact = MediaQuery.sizeOf(context).width < 900;

    Widget listPane({required bool openDetailAfterSelection}) {
      return KeyedSubtree(
        key: const Key('notice-list-pane'),
        child: KeyedSubtree(
          key: const Key('notice-results-pane'),
          child: _NoticeListOnly(
            items: items,
            selectedNoticeId: _selectedNoticeId,
            dense: !openDetailAfterSelection,
            showInlineActions: openDetailAfterSelection,
            onSelect: (noticeId) {
              _selectNotice(noticeId);
              if (openDetailAfterSelection) {
                setState(() {
                  _compactShowDetail = true;
                });
              }
            },
            onUpdateReview: _updateNoticeReview,
            reviewActionsInFlight: _reviewActionsInFlight,
            onFilterBySource: _filterBySource,
            sourceDisplayName: _sourceDisplayName,
            onFilterByCategory: _filterByCategory,
            onFilterByKeyword: _filterByKeyword,
            scrollController: _listScrollController,
          ),
        ),
      );
    }

    Widget detailPane() {
      return KeyedSubtree(
        key: const Key('notice-detail-pane'),
        child: _NoticeDetailPanel(
          noticeId: selectedNoticeId,
          detailFuture: _detailFuture!,
          sourceDisplayName: _sourceDisplayName,
          onOpenSnapshot: _openSnapshot,
          onUpdateReview: _updateNoticeReview,
          reviewActionInFlight: _reviewActionsInFlight[selectedNoticeId],
          scrollController: _detailScrollController,
          onRetry: () {
            setState(() {
              _detailFuture = _repository.fetchNoticeDetail(
                _selectedNoticeId!,
              );
            });
          },
        ),
      );
    }

    final isWideWorkspace = MediaQuery.sizeOf(context).width >= 1180;
    final workspace = isCompact
        ? Column(
            children: [
              SizedBox(
                width: double.infinity,
                child: SegmentedButton<bool>(
                  key: const Key('notice-compact-mode-switcher'),
                  segments: const [
                    ButtonSegment<bool>(
                      value: false,
                      icon: Icon(Icons.view_list_outlined),
                      label: Text('列表'),
                    ),
                    ButtonSegment<bool>(
                      value: true,
                      icon: Icon(Icons.article_outlined),
                      label: Text('详情'),
                    ),
                  ],
                  selected: {_compactShowDetail},
                  onSelectionChanged: (selected) {
                    setState(() {
                      _compactShowDetail = selected.first;
                    });
                  },
                ),
              ),
              const SizedBox(height: 10),
              Expanded(
                child: _compactShowDetail
                    ? detailPane()
                    : listPane(openDetailAfterSelection: true),
              ),
            ],
          )
        : Row(
            key: const Key('notice-master-detail'),
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (isWideWorkspace) ...[
                SizedBox(
                  width: 244,
                  child: _NoticeFacetPane(
                    items: items,
                    query: _currentQuery,
                    sourceDisplayName: _sourceDisplayName,
                    onClear: _clearAllFilters,
                    onSourceChanged: (sourceSite) {
                      if (sourceSite == null) {
                        _removeFilter('sourceSite');
                      } else {
                        _filterBySource(sourceSite);
                      }
                    },
                    onCategoryChanged: (category) {
                      if (category == null) {
                        _removeFilter('category');
                      } else {
                        _filterByCategory(category);
                      }
                    },
                    onReviewStatusChanged: (status) {
                      _applyQuery(
                        status == null
                            ? _queryWithout(reviewStatus: true)
                            : NoticeQuery(
                                keyword: _keyword,
                                category: _categoryFilter,
                                reviewStatus: status,
                                archived: _archivedFilter,
                                capturedToday: _capturedTodayFilter,
                                sourceSite: _sourceSiteFilter,
                                keywordHit: _keywordHitFilter,
                                highPriority: _highPriorityFilter,
                                highQuality: _highQualityFilter,
                                projectSignal: _projectSignalFilter,
                              ),
                      );
                    },
                    onShowHighPriority: _highPriorityFilter == true
                        ? () => _removeFilter('highPriority')
                        : _filterByHighPriority,
                    onShowHighQuality: _highQualityFilter == true
                        ? () => _removeFilter('highQuality')
                        : _filterByHighQuality,
                    onShowKeywordHits: _keywordHitFilter == true
                        ? () => _removeFilter('keywordHit')
                        : _filterByKeywordHit,
                  ),
                ),
                const SizedBox(width: 12),
              ],
              Expanded(
                flex: isWideWorkspace ? 7 : 6,
                child: listPane(openDetailAfterSelection: false),
              ),
              const SizedBox(width: 12),
              Expanded(
                flex: isWideWorkspace ? 6 : 7,
                child: detailPane(),
              ),
            ],
          );

    return Listener(
      behavior: HitTestBehavior.opaque,
      onPointerSignal: _handleBodyPointerSignal,
      child: Column(
        children: [
          Expanded(child: workspace),
          const SizedBox(height: 8),
          paginationRow,
        ],
      ),
    );
  }

  void _handleBodyPointerSignal(PointerSignalEvent event) {
    if (event is! PointerScrollEvent) {
      return;
    }
    final deltaY = event.scrollDelta.dy;
    if (deltaY == 0) {
      return;
    }
    if (_scrollByWheel(_listScrollController, deltaY)) {
      return;
    }
    _scrollByWheel(_detailScrollController, deltaY);
  }

  bool _scrollByWheel(ScrollController controller, double deltaY) {
    if (!controller.hasClients) {
      return false;
    }
    final position = controller.position;
    final next = (position.pixels + deltaY).clamp(
      position.minScrollExtent,
      position.maxScrollExtent,
    );
    if (next == position.pixels) {
      return false;
    }
    controller.jumpTo(next);
    return true;
  }

  int _syncSelection(List<NoticeListItemModel> items) {
    if (_selectedNoticeId != null && _detailFuture != null) {
      return _selectedNoticeId!;
    }

    final fallback = items.first;
    _selectedNoticeId = fallback.id;
    _detailFuture = _repository.fetchNoticeDetail(fallback.id);
    return fallback.id;
  }
}

class _NoticePageHero extends StatelessWidget {
  final List<NoticeListItemModel> items;
  final int total;
  final String activeSavedView;
  final bool highPrioritySelected;
  final bool highQualitySelected;
  final bool keywordHitSelected;
  final ValueChanged<String> onSelectSavedView;
  final VoidCallback onShowAll;
  final VoidCallback onShowHighPriority;
  final VoidCallback onShowHighQuality;
  final VoidCallback onShowKeywordHits;
  final Future<void> Function() onRefresh;
  final VoidCallback onExportCsv;
  final bool isRefreshing;
  final bool isExportingCsv;

  const _NoticePageHero({
    required this.items,
    required this.total,
    required this.activeSavedView,
    required this.highPrioritySelected,
    required this.highQualitySelected,
    required this.keywordHitSelected,
    required this.onSelectSavedView,
    required this.onShowAll,
    required this.onShowHighPriority,
    required this.onShowHighQuality,
    required this.onShowKeywordHits,
    required this.onRefresh,
    required this.onExportCsv,
    required this.isRefreshing,
    required this.isExportingCsv,
  });

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final isNarrow = constraints.maxWidth < 720;
        final titleBlock = Row(
          children: [
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: const Color(0xFFE8F1FC),
                borderRadius: BorderRadius.circular(10),
              ),
              child: const Icon(
                Icons.inbox_outlined,
                color: Color(0xFF1E4F8A),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    '公告中心',
                    style: Theme.of(context).textTheme.titleLarge?.copyWith(
                          fontWeight: FontWeight.w800,
                          color: const Color(0xFF18324E),
                        ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    '共 $total 条 · 当前页 ${items.length} 条',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: const Color(0xFF66778D),
                        ),
                  ),
                ],
              ),
            ),
          ],
        );

        const buttonStyle = ButtonStyle(
          minimumSize: WidgetStatePropertyAll(Size(0, 44)),
          padding: WidgetStatePropertyAll(
            EdgeInsets.symmetric(horizontal: 12),
          ),
        );
        final actions = Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            FilledButton.tonalIcon(
              key: const Key('notice-refresh-action'),
              onPressed: isRefreshing
                  ? null
                  : () {
                      onRefresh();
                    },
              style: buttonStyle,
              icon: isRefreshing
                  ? const SizedBox(
                      width: 17,
                      height: 17,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.refresh),
              label: Text(isRefreshing ? '刷新中' : '刷新'),
            ),
            const SizedBox(width: 8),
            OutlinedButton.icon(
              key: const Key('notice-export-action'),
              onPressed: isExportingCsv ? null : onExportCsv,
              style: buttonStyle,
              icon: isExportingCsv
                  ? const SizedBox(
                      width: 17,
                      height: 17,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.table_chart_outlined),
              label: Text(isExportingCsv ? '导出中' : '导出 Excel'),
            ),
          ],
        );

        final topRow = isNarrow
            ? Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  titleBlock,
                  const SizedBox(height: 10),
                  actions,
                ],
              )
            : Row(
                children: [
                  Expanded(child: titleBlock),
                  const SizedBox(width: 12),
                  actions,
                ],
              );

        return Container(
          key: const Key('notice-overview-toolbar'),
          width: double.infinity,
          padding: const EdgeInsets.fromLTRB(14, 12, 14, 10),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: const Color(0xFFDDE6F0)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              topRow,
              const SizedBox(height: 10),
              const Divider(height: 1),
              const SizedBox(height: 6),
              _NoticeSavedViewBar(
                activeView: activeSavedView,
                onSelected: onSelectSavedView,
              ),
              if (constraints.maxWidth < 1180) ...[
                const SizedBox(height: 8),
                _NoticeSummaryBar(
                  total: total,
                  items: items,
                  highPrioritySelected: highPrioritySelected,
                  highQualitySelected: highQualitySelected,
                  keywordHitSelected: keywordHitSelected,
                  onShowAll: onShowAll,
                  onShowHighPriority: onShowHighPriority,
                  onShowHighQuality: onShowHighQuality,
                  onShowKeywordHits: onShowKeywordHits,
                  compact: true,
                ),
              ],
            ],
          ),
        );
      },
    );
  }
}

class _NoticeSavedViewBar extends StatelessWidget {
  final String activeView;
  final ValueChanged<String> onSelected;

  const _NoticeSavedViewBar({
    required this.activeView,
    required this.onSelected,
  });

  @override
  Widget build(BuildContext context) {
    const views = <(String, String, IconData)>[
      ('all', '全部', Icons.apps_outlined),
      ('today', '今日新增', Icons.today_outlined),
      ('application', '项目申报', Icons.assignment_outlined),
      ('result-publication', '结果公示', Icons.fact_check_outlined),
      ('meeting', '行业会议', Icons.event_outlined),
      ('focus', '重点关注', Icons.star_outline),
    ];

    return SizedBox(
      height: 44,
      child: SingleChildScrollView(
        key: const Key('notice-saved-view-bar'),
        scrollDirection: Axis.horizontal,
        child: Row(
          children: [
            for (var index = 0; index < views.length; index++) ...[
              _SavedViewAction(
                key: Key('notice-saved-view-${views[index].$1}'),
                label: views[index].$2,
                icon: views[index].$3,
                selected: activeView == views[index].$1,
                onPressed: () => onSelected(views[index].$1),
              ),
              if (index != views.length - 1) const SizedBox(width: 6),
            ],
          ],
        ),
      ),
    );
  }
}

class _SavedViewAction extends StatelessWidget {
  final String label;
  final IconData icon;
  final bool selected;
  final VoidCallback onPressed;

  const _SavedViewAction({
    super.key,
    required this.label,
    required this.icon,
    required this.selected,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 40,
      child: selected
          ? FilledButton.tonalIcon(
              onPressed: onPressed,
              icon: Icon(icon, size: 17),
              label: Text(label),
            )
          : TextButton.icon(
              onPressed: onPressed,
              icon: Icon(icon, size: 17),
              label: Text(label),
            ),
    );
  }
}

// ignore: unused_element
class _NoticeHero extends StatelessWidget {
  final List<NoticeListItemModel> items;
  final Future<void> Function() onRefresh;
  final VoidCallback onExportCsv;
  final bool isExportingCsv;

  const _NoticeHero({
    required this.items,
    required this.onRefresh,
    required this.onExportCsv,
    required this.isExportingCsv,
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
              '公告中心',
              style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    color: Colors.white,
                  ),
            ),
            const SizedBox(height: 6),
            Text(
              '按来源、关键词、内容质量和业务优先级浏览采集结果。',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: const Color(0xE6F3F8FF),
                  ),
            ),
            const SizedBox(height: 12),
            _NoticeSummaryBar(
              total: items.length,
              items: items,
              highPrioritySelected: false,
              highQualitySelected: false,
              keywordHitSelected: false,
              onShowAll: () {},
              onShowHighPriority: () {},
              onShowHighQuality: () {},
              onShowKeywordHits: () {},
            ),
          ],
        );

        final actions = Column(
          crossAxisAlignment:
              isCompact ? CrossAxisAlignment.start : CrossAxisAlignment.end,
          children: [
            FilledButton.tonalIcon(
              onPressed: onRefresh,
              icon: const Icon(Icons.refresh),
              label: const Text('刷新'),
            ),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              onPressed: isExportingCsv ? null : onExportCsv,
              icon: isExportingCsv
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.white,
                      ),
                    )
                  : const Icon(Icons.table_chart_outlined),
              label: Text(isExportingCsv ? '导出中…' : '导出采集 CSV'),
              style: OutlinedButton.styleFrom(
                foregroundColor: Colors.white,
                side: const BorderSide(color: Color(0x66FFFFFF)),
              ),
            ),
            const SizedBox(height: 8),
            _InfoPill(
              label: '结果',
              value: '${items.length} 条',
            ),
          ],
        );

        return Container(
          width: double.infinity,
          padding: const EdgeInsets.all(14),
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
            borderRadius: BorderRadius.circular(20),
            boxShadow: const [
              BoxShadow(
                color: Color(0x281D4E89),
                blurRadius: 20,
                offset: Offset(0, 10),
              ),
            ],
          ),
          child: isCompact
              ? Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    content,
                    const SizedBox(height: 12),
                    actions,
                  ],
                )
              : Row(
                  children: [
                    Expanded(child: content),
                    const SizedBox(width: 12),
                    actions,
                  ],
                ),
        );
      },
    );
  }
}

class _NoticeSummaryBar extends StatelessWidget {
  final int total;
  final List<NoticeListItemModel> items;
  final bool highPrioritySelected;
  final bool highQualitySelected;
  final bool keywordHitSelected;
  final VoidCallback onShowAll;
  final VoidCallback onShowHighPriority;
  final VoidCallback onShowHighQuality;
  final VoidCallback onShowKeywordHits;
  final bool compact;

  const _NoticeSummaryBar({
    required this.total,
    required this.items,
    required this.highPrioritySelected,
    required this.highQualitySelected,
    required this.keywordHitSelected,
    required this.onShowAll,
    required this.onShowHighPriority,
    required this.onShowHighQuality,
    required this.onShowKeywordHits,
    this.compact = false,
  });

  @override
  Widget build(BuildContext context) {
    final highPriority = items.where((item) => item.isHighPriority).length;
    final highQuality = items.where((item) => item.qualityScore >= 60).length;
    final keywordHits =
        items.where((item) => item.matchedKeywords.isNotEmpty).length;
    final averageQuality = items.isEmpty
        ? 0
        : (items.fold<int>(0, (sum, item) => sum + item.qualityScore) /
                items.length)
            .round();

    if (compact) {
      final allMetric = _CompactNoticeMetricAction(
        key: const Key('notice-metric-all'),
        label: '全部 $total',
        icon: Icons.article_outlined,
        onPressed: onShowAll,
      );
      final priorityMetric = _CompactNoticeMetricAction(
        key: const Key('notice-metric-high-priority'),
        label: '业务优先 $highPriority',
        icon: Icons.flag_outlined,
        selected: highPrioritySelected,
        onPressed: onShowHighPriority,
      );
      final qualityMetric = _CompactNoticeMetricAction(
        key: const Key('notice-metric-high-quality'),
        label: '高质量 $highQuality',
        icon: Icons.verified_outlined,
        selected: highQualitySelected,
        onPressed: onShowHighQuality,
      );
      final keywordMetric = _CompactNoticeMetricAction(
        key: const Key('notice-metric-keyword-hit'),
        label: '关键词命中 $keywordHits',
        icon: Icons.local_offer_outlined,
        selected: keywordHitSelected,
        onPressed: onShowKeywordHits,
      );

      return Material(
        color: Colors.transparent,
        child: LayoutBuilder(
          builder: (context, constraints) {
            if (constraints.maxWidth < 520) {
              final gridAllMetric = _CompactNoticeMetricAction(
                key: const Key('notice-metric-all'),
                label: '全部 $total',
                icon: Icons.article_outlined,
                showIcon: false,
                onPressed: onShowAll,
              );
              final gridPriorityMetric = _CompactNoticeMetricAction(
                key: const Key('notice-metric-high-priority'),
                label: '本页优先 $highPriority',
                icon: Icons.flag_outlined,
                showIcon: false,
                selected: highPrioritySelected,
                onPressed: onShowHighPriority,
              );
              final gridQualityMetric = _CompactNoticeMetricAction(
                key: const Key('notice-metric-high-quality'),
                label: '本页优质 $highQuality',
                icon: Icons.verified_outlined,
                showIcon: false,
                selected: highQualitySelected,
                onPressed: onShowHighQuality,
              );
              final gridKeywordMetric = _CompactNoticeMetricAction(
                key: const Key('notice-metric-keyword-hit'),
                label: '本页命中 $keywordHits',
                icon: Icons.local_offer_outlined,
                showIcon: false,
                selected: keywordHitSelected,
                onPressed: onShowKeywordHits,
              );
              return SizedBox(
                key: const Key('notice-compact-metrics-grid'),
                height: 104,
                child: Column(
                  children: [
                    Row(
                      children: [
                        Expanded(child: gridAllMetric),
                        const SizedBox(width: 8),
                        Expanded(child: gridPriorityMetric),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        Expanded(child: gridQualityMetric),
                        const SizedBox(width: 8),
                        Expanded(child: gridKeywordMetric),
                      ],
                    ),
                  ],
                ),
              );
            }

            return SizedBox(
              height: 48,
              child: SingleChildScrollView(
                key: const Key('notice-compact-metrics-scroll'),
                scrollDirection: Axis.horizontal,
                child: Row(
                  children: [
                    allMetric,
                    const SizedBox(width: 8),
                    priorityMetric,
                    const SizedBox(width: 8),
                    qualityMetric,
                    const SizedBox(width: 8),
                    keywordMetric,
                  ],
                ),
              ),
            );
          },
        ),
      );
    }

    return Wrap(
      spacing: 10,
      runSpacing: 10,
      children: [
        _NoticeMetricCard(
          key: const Key('notice-metric-all'),
          title: '公告总数',
          value: '$total',
          icon: Icons.article_outlined,
          accentColor: const Color(0xFF1E4F8A),
          tooltip: '清除筛选并查看全部公告',
          onTap: onShowAll,
        ),
        _NoticeMetricCard(
          key: const Key('notice-metric-high-priority'),
          title: '本页业务优先',
          value: '$highPriority',
          icon: Icons.flag_outlined,
          accentColor: const Color(0xFFC45A1A),
          selected: highPrioritySelected,
          tooltip: '只看命中业务优先词的公告',
          onTap: onShowHighPriority,
        ),
        _NoticeMetricCard(
          key: const Key('notice-metric-high-quality'),
          title: '本页高质量内容',
          value: '$highQuality',
          icon: Icons.verified_outlined,
          accentColor: const Color(0xFF2D6CDF),
          selected: highQualitySelected,
          tooltip: '只看内容质量分达到 60 的公告',
          onTap: onShowHighQuality,
        ),
        _NoticeMetricCard(
          key: const Key('notice-metric-keyword-hit'),
          title: '本页关键词命中',
          value: '$keywordHits',
          icon: Icons.local_offer_outlined,
          accentColor: const Color(0xFF117A65),
          selected: keywordHitSelected,
          tooltip: '只看关键词命中公告',
          onTap: onShowKeywordHits,
        ),
        _NoticeMetricCard(
          title: '本页平均质量分',
          value: '$averageQuality',
          icon: Icons.assessment_outlined,
          accentColor: const Color(0xFF2D6CDF),
        ),
      ],
    );
  }
}

class _CompactNoticeMetricAction extends StatelessWidget {
  final String label;
  final IconData icon;
  final bool showIcon;
  final bool selected;
  final VoidCallback onPressed;

  const _CompactNoticeMetricAction({
    super.key,
    required this.label,
    required this.icon,
    this.showIcon = true,
    this.selected = false,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      selected: selected,
      child: FilterChip(
        avatar: showIcon ? Icon(icon, size: 17) : null,
        label: Text(
          label,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
        selected: selected,
        showCheckmark: false,
        padding: const EdgeInsets.symmetric(horizontal: 4),
        labelPadding: const EdgeInsets.only(left: 2, right: 4),
        visualDensity: VisualDensity.compact,
        onSelected: (_) => onPressed(),
        materialTapTargetSize: MaterialTapTargetSize.padded,
      ),
    );
  }
}

class _EmptyStateCard extends StatelessWidget {
  final IconData icon;
  final String title;
  final String description;
  final String actionLabel;
  final Future<void> Function() onAction;

  const _EmptyStateCard({
    required this.icon,
    required this.title,
    required this.description,
    required this.actionLabel,
    required this.onAction,
  });

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
              child: Icon(icon, color: const Color(0xFF1E4F8A)),
            ),
            const SizedBox(height: 18),
            Text(title, style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 10),
            Text(description, style: Theme.of(context).textTheme.bodyMedium),
            const SizedBox(height: 18),
            FilledButton.tonalIcon(
              onPressed: onAction,
              icon: const Icon(Icons.refresh),
              label: Text(actionLabel),
            ),
          ],
        ),
      ),
    );
  }
}

class _NoticeMetricCard extends StatelessWidget {
  final String title;
  final String value;
  final IconData icon;
  final Color accentColor;
  final bool selected;
  final String? tooltip;
  final VoidCallback? onTap;

  const _NoticeMetricCard({
    super.key,
    required this.title,
    required this.value,
    required this.icon,
    required this.accentColor,
    this.selected = false,
    this.tooltip,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final content = AnimatedContainer(
      duration: const Duration(milliseconds: 180),
      constraints: const BoxConstraints(minHeight: 108),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            accentColor.withValues(alpha: selected ? 0.16 : 0.08),
            Colors.white,
          ],
        ),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: selected
              ? accentColor.withValues(alpha: 0.55)
              : Colors.transparent,
          width: selected ? 1.5 : 1,
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 34,
                  height: 34,
                  decoration: BoxDecoration(
                    color: accentColor.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Icon(icon, color: accentColor, size: 18),
                ),
                const Spacer(),
                _MetricPill(accentColor: accentColor),
              ],
            ),
            const SizedBox(height: 10),
            Text(
              title,
              style: Theme.of(context).textTheme.titleSmall,
            ),
            const SizedBox(height: 6),
            Text(
              value,
              style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    color: const Color(0xFF0F223D),
                  ),
            ),
          ],
        ),
      ),
    );

    return SizedBox(
      width: 160,
      child: onTap == null
          ? content
          : Semantics(
              button: true,
              selected: selected,
              label: tooltip ?? title,
              child: Tooltip(
                message: tooltip ?? title,
                child: MouseRegion(
                  cursor: SystemMouseCursors.click,
                  child: Material(
                    color: Colors.transparent,
                    borderRadius: BorderRadius.circular(16),
                    clipBehavior: Clip.antiAlias,
                    child: InkWell(
                      borderRadius: BorderRadius.circular(16),
                      onTap: onTap,
                      child: content,
                    ),
                  ),
                ),
              ),
            ),
    );
  }
}

class _MetricPill extends StatelessWidget {
  final Color accentColor;

  const _MetricPill({required this.accentColor});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: const Color(0xFFF2F6FC),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        '实时',
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
              color: accentColor,
              fontWeight: FontWeight.w700,
            ),
      ),
    );
  }
}

class _ActiveNoticeFilters extends StatelessWidget {
  final NoticeQuery query;
  final int total;
  final String? sourceDisplayName;
  final ValueChanged<String> onRemove;
  final VoidCallback onClear;

  const _ActiveNoticeFilters({
    required this.query,
    required this.total,
    required this.sourceDisplayName,
    required this.onRemove,
    required this.onClear,
  });

  List<MapEntry<String, String>> _labels() {
    return [
      if (query.keyword != null) MapEntry('keyword', '关键词：${query.keyword}'),
      if (query.category != null) MapEntry('category', '类别：${query.category}'),
      if (query.reviewStatus != null)
        MapEntry('reviewStatus', '标记：${query.reviewStatus}'),
      if (query.archived != null)
        MapEntry('archived', query.archived! ? '已归档' : '未归档'),
      if (query.capturedToday != null)
        MapEntry(
          'capturedToday',
          query.capturedToday! ? '今日采集' : '非今日采集',
        ),
      if (query.sourceSite != null)
        MapEntry('sourceSite', '来源：${sourceDisplayName ?? '未命名来源'}'),
      if (query.keywordHit != null)
        MapEntry(
          'keywordHit',
          query.keywordHit! ? '关键词命中' : '关键词未命中',
        ),
      if (query.highPriority != null)
        MapEntry(
          'highPriority',
          query.highPriority! ? '业务优先' : '非业务优先',
        ),
      if (query.highQuality != null)
        MapEntry(
          'highQuality',
          query.highQuality! ? '高质量内容' : '待完善内容',
        ),
      if (query.projectSignal != null)
        MapEntry('projectSignal', '项目线索：${query.projectSignal}'),
    ];
  }

  @override
  Widget build(BuildContext context) {
    final filterChips = Wrap(
      spacing: 8,
      runSpacing: 8,
      children: _labels()
          .map(
            (entry) => InputChip(
              key: Key('active-notice-filter-${entry.key}'),
              visualDensity: VisualDensity.compact,
              label: Text(entry.value),
              deleteButtonTooltipMessage: '移除此筛选',
              onDeleted: () => onRemove(entry.key),
            ),
          )
          .toList(),
    );

    return Semantics(
      container: true,
      label: '当前联动筛选',
      child: Material(
        color: Colors.transparent,
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.fromLTRB(14, 10, 10, 10),
          decoration: BoxDecoration(
            color: const Color(0xFFEFF6FF),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: const Color(0xFFC9DDF8)),
          ),
          child: LayoutBuilder(
            builder: (context, constraints) {
              final title = Text(
                '当前联动筛选',
                style: Theme.of(context).textTheme.labelLarge?.copyWith(
                      color: const Color(0xFF1E4F8A),
                      fontWeight: FontWeight.w700,
                    ),
              );
              final clearButton = Tooltip(
                message: '清除全部联动筛选',
                child: TextButton.icon(
                  onPressed: onClear,
                  icon: const Icon(Icons.filter_alt_off_outlined, size: 18),
                  label: const Text('清除全部'),
                ),
              );
              final resultCount = Text(
                '共 $total 条',
                style: Theme.of(context).textTheme.labelMedium?.copyWith(
                      color: const Color(0xFF556A86),
                      fontWeight: FontWeight.w700,
                    ),
              );

              if (constraints.maxWidth < 520) {
                return Column(
                  key: const Key('active-notice-filters-compact'),
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        const Icon(
                          Icons.filter_alt_outlined,
                          size: 20,
                          color: Color(0xFF1E4F8A),
                        ),
                        const SizedBox(width: 8),
                        Expanded(child: title),
                        resultCount,
                        const SizedBox(width: 4),
                        clearButton,
                      ],
                    ),
                    const SizedBox(height: 4),
                    filterChips,
                  ],
                );
              }

              return Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  const Icon(
                    Icons.filter_alt_outlined,
                    size: 20,
                    color: Color(0xFF1E4F8A),
                  ),
                  const SizedBox(width: 8),
                  title,
                  const SizedBox(width: 12),
                  Expanded(child: filterChips),
                  const SizedBox(width: 8),
                  resultCount,
                  const SizedBox(width: 4),
                  clearButton,
                ],
              );
            },
          ),
        ),
      ),
    );
  }
}

class _NoticeFilterBar extends StatefulWidget {
  final TextEditingController searchController;
  final String? sourceSite;
  final List<NoticeSourceSiteOption> sourceSites;
  final String? category;
  final String? reviewStatus;
  final bool? archived;
  final void Function({
    String? keyword,
    String? sourceSite,
    String? category,
    String? reviewStatus,
    bool? archived,
  }) onChanged;

  const _NoticeFilterBar({
    required this.searchController,
    required this.sourceSite,
    required this.sourceSites,
    required this.category,
    required this.reviewStatus,
    required this.archived,
    required this.onChanged,
  });

  @override
  State<_NoticeFilterBar> createState() => _NoticeFilterBarState();
}

class _NoticeFilterBarState extends State<_NoticeFilterBar> {
  Timer? _debounceTimer;
  bool _filtersExpanded = false;

  void _onQueryChanged(String query) {
    if (_debounceTimer?.isActive ?? false) _debounceTimer!.cancel();
    _debounceTimer = Timer(const Duration(milliseconds: 500), () {
      _emit(keyword: query);
    });
  }

  void _emit({
    String? keyword,
    String? category,
    String? reviewStatus,
    bool? archived,
  }) {
    widget.onChanged(
      keyword: keyword ?? widget.searchController.text,
      sourceSite: widget.sourceSite,
      category: category ?? widget.category,
      reviewStatus: reviewStatus ?? widget.reviewStatus,
      archived: archived ?? widget.archived,
    );
  }

  @override
  void dispose() {
    _debounceTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final isCompact = constraints.maxWidth < 820;
        final isNarrow = constraints.maxWidth < 520;

        final searchField = TextField(
          controller: widget.searchController,
          onChanged: _onQueryChanged,
          decoration: InputDecoration(
            labelText: '搜索',
            hintText: '搜索标题、正文、机构',
            prefixIcon: const Icon(Icons.search),
            suffixIcon: widget.searchController.text.isNotEmpty
                ? IconButton(
                    icon: const Icon(Icons.clear),
                    onPressed: () {
                      widget.searchController.clear();
                      _onQueryChanged('');
                    },
                  )
                : null,
          ),
        );

        final filters = Wrap(
          spacing: 10,
          runSpacing: 10,
          children: [
            _SourceSiteMenu(
              value: widget.sourceSite,
              options: widget.sourceSites,
              onChanged: (value) => widget.onChanged(
                keyword: widget.searchController.text,
                sourceSite: value,
                category: widget.category,
                reviewStatus: widget.reviewStatus,
                archived: widget.archived,
              ),
            ),
            _FilterMenu<String>(
              label: '类别',
              value: widget.category ?? '',
              items: const {
                '': '全部类别',
                '项目申报': '项目申报',
                '行业会议': '行业会议',
                '竞品信息': '竞品信息',
                '未分类': '未分类',
              },
              onChanged: (value) => widget.onChanged(
                keyword: widget.searchController.text,
                sourceSite: widget.sourceSite,
                category: value.isEmpty ? null : value,
                reviewStatus: widget.reviewStatus,
                archived: widget.archived,
              ),
            ),
            _FilterMenu<String>(
              label: '标记',
              value: widget.reviewStatus ?? '',
              items: const {
                '': '全部标记',
                '待关注': '待关注',
                '有效': '有效',
                '无效': '无效',
              },
              onChanged: (value) => widget.onChanged(
                keyword: widget.searchController.text,
                sourceSite: widget.sourceSite,
                category: widget.category,
                reviewStatus: value.isEmpty ? null : value,
                archived: widget.archived,
              ),
            ),
            _FilterMenu<String>(
              label: '归档',
              value: widget.archived == null
                  ? ''
                  : widget.archived!
                      ? 'true'
                      : 'false',
              items: const {
                '': '全部',
                'false': '未归档',
                'true': '已归档',
              },
              onChanged: (value) => widget.onChanged(
                keyword: widget.searchController.text,
                sourceSite: widget.sourceSite,
                category: widget.category,
                reviewStatus: widget.reviewStatus,
                archived: value.isEmpty ? null : value == 'true',
              ),
            ),
          ],
        );

        if (isNarrow) {
          return Card(
            key: const Key('notice-filter-toolbar'),
            margin: EdgeInsets.zero,
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(child: searchField),
                      const SizedBox(width: 8),
                      IconButton.filledTonal(
                        onPressed: () {
                          setState(() {
                            _filtersExpanded = !_filtersExpanded;
                          });
                        },
                        tooltip: _filtersExpanded ? '收起筛选' : '展开筛选',
                        icon: Icon(
                          _filtersExpanded
                              ? Icons.filter_alt_off_outlined
                              : Icons.tune_outlined,
                        ),
                      ),
                    ],
                  ),
                  if (_filtersExpanded) ...[
                    const SizedBox(height: 12),
                    filters,
                  ],
                ],
              ),
            ),
          );
        }

        return Card(
          key: const Key('notice-filter-toolbar'),
          margin: EdgeInsets.zero,
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: isCompact
                ? Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      searchField,
                      const SizedBox(height: 12),
                      filters,
                    ],
                  )
                : Row(
                    children: [
                      Expanded(child: searchField),
                      const SizedBox(width: 12),
                      filters,
                    ],
                  ),
          ),
        );
      },
    );
  }
}

class _FilterMenu<T> extends StatelessWidget {
  final String label;
  final T value;
  final Map<T, String> items;
  final ValueChanged<T> onChanged;

  const _FilterMenu({
    required this.label,
    required this.value,
    required this.items,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 126,
      child: DropdownButtonFormField<T>(
        initialValue: value,
        decoration: InputDecoration(labelText: label),
        items: items.entries
            .map(
              (entry) => DropdownMenuItem<T>(
                value: entry.key,
                child: Text(entry.value),
              ),
            )
            .toList(),
        onChanged: (value) {
          if (value != null) {
            onChanged(value);
          }
        },
      ),
    );
  }
}

class _SourceSiteMenu extends StatelessWidget {
  final String? value;
  final List<NoticeSourceSiteOption> options;
  final ValueChanged<String?> onChanged;

  const _SourceSiteMenu({
    required this.value,
    required this.options,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      key: ValueKey('notice-source-site-${value ?? ''}-${options.length}'),
      width: 188,
      child: DropdownMenu<String>(
        key: const Key('notice-source-site-filter'),
        width: 188,
        menuHeight: 320,
        enableFilter: true,
        enableSearch: true,
        initialSelection: value ?? '',
        label: const Text('来源机构'),
        leadingIcon: const Icon(Icons.language_outlined),
        dropdownMenuEntries: [
          const DropdownMenuEntry<String>(
            value: '',
            label: '全部来源',
          ),
          ...options.map(
            (option) => DropdownMenuEntry<String>(
              value: option.sourceSite,
              label: option.displayName,
            ),
          ),
        ],
        onSelected: (selected) {
          if (selected != null) {
            onChanged(selected.isEmpty ? null : selected);
          }
        },
      ),
    );
  }
}

class _NoticeFacetPane extends StatelessWidget {
  final List<NoticeListItemModel> items;
  final NoticeQuery query;
  final String Function(String) sourceDisplayName;
  final VoidCallback onClear;
  final ValueChanged<String?> onSourceChanged;
  final ValueChanged<String?> onCategoryChanged;
  final ValueChanged<String?> onReviewStatusChanged;
  final VoidCallback onShowHighPriority;
  final VoidCallback onShowHighQuality;
  final VoidCallback onShowKeywordHits;

  const _NoticeFacetPane({
    required this.items,
    required this.query,
    required this.sourceDisplayName,
    required this.onClear,
    required this.onSourceChanged,
    required this.onCategoryChanged,
    required this.onReviewStatusChanged,
    required this.onShowHighPriority,
    required this.onShowHighQuality,
    required this.onShowKeywordHits,
  });

  Map<String, int> _countBy(String Function(NoticeListItemModel) selector) {
    final counts = <String, int>{};
    for (final item in items) {
      final value = selector(item).trim();
      if (value.isNotEmpty) {
        counts.update(value, (count) => count + 1, ifAbsent: () => 1);
      }
    }
    return counts;
  }

  @override
  Widget build(BuildContext context) {
    final sourceCounts = _countBy((item) => item.sourceSite);
    final categoryCounts = _countBy((item) => item.category);
    final statusCounts = _countBy((item) => item.reviewStatus);
    final highPriorityCount = items.where((item) => item.isHighPriority).length;
    final highQualityCount =
        items.where((item) => item.qualityScore >= 60).length;
    final keywordHitCount =
        items.where((item) => item.matchedKeywords.isNotEmpty).length;

    List<MapEntry<String, int>> sorted(Map<String, int> counts) {
      final entries = counts.entries.toList()
        ..sort((a, b) {
          final countOrder = b.value.compareTo(a.value);
          return countOrder == 0 ? a.key.compareTo(b.key) : countOrder;
        });
      return entries;
    }

    return Card(
      key: const Key('notice-facet-pane'),
      margin: EdgeInsets.zero,
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 10, 8, 8),
            child: Row(
              children: [
                const Icon(
                  Icons.tune_outlined,
                  size: 19,
                  color: Color(0xFF1E4F8A),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    '筛选条件',
                    style: Theme.of(context).textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.w800,
                        ),
                  ),
                ),
                IconButton(
                  onPressed: query.isEmpty ? null : onClear,
                  tooltip: '清除全部筛选',
                  icon: const Icon(Icons.filter_alt_off_outlined, size: 19),
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.fromLTRB(8, 8, 8, 12),
              children: [
                _FacetSection(
                  title: '快速筛选',
                  children: [
                    _FacetOption(
                      key: const Key('notice-metric-high-priority'),
                      label: '业务优先',
                      count: highPriorityCount,
                      selected: query.highPriority == true,
                      onTap: onShowHighPriority,
                    ),
                    _FacetOption(
                      key: const Key('notice-metric-high-quality'),
                      label: '高质量内容',
                      count: highQualityCount,
                      selected: query.highQuality == true,
                      onTap: onShowHighQuality,
                    ),
                    _FacetOption(
                      key: const Key('notice-metric-keyword-hit'),
                      label: '关键词命中',
                      count: keywordHitCount,
                      selected: query.keywordHit == true,
                      onTap: onShowKeywordHits,
                    ),
                  ],
                ),
                _FacetSection(
                  title: '来源机构 · 本页',
                  children: [
                    for (final entry in sorted(sourceCounts).take(6))
                      _FacetOption(
                        key: Key('notice-facet-source-${entry.key}'),
                        label: sourceDisplayName(entry.key),
                        count: entry.value,
                        selected: query.sourceSite == entry.key,
                        onTap: () => onSourceChanged(
                          query.sourceSite == entry.key ? null : entry.key,
                        ),
                      ),
                  ],
                ),
                _FacetSection(
                  title: '公告类型 · 本页',
                  children: [
                    for (final entry in sorted(categoryCounts))
                      _FacetOption(
                        key: Key('notice-facet-category-${entry.key}'),
                        label: entry.key,
                        count: entry.value,
                        selected: query.category == entry.key,
                        onTap: () => onCategoryChanged(
                          query.category == entry.key ? null : entry.key,
                        ),
                      ),
                  ],
                ),
                _FacetSection(
                  title: '处理状态 · 本页',
                  children: [
                    for (final entry in sorted(statusCounts))
                      _FacetOption(
                        key: Key('notice-facet-status-${entry.key}'),
                        label: entry.key,
                        count: entry.value,
                        selected: query.reviewStatus == entry.key,
                        onTap: () => onReviewStatusChanged(
                          query.reviewStatus == entry.key ? null : entry.key,
                        ),
                      ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _FacetSection extends StatelessWidget {
  final String title;
  final List<Widget> children;

  const _FacetSection({
    required this.title,
    required this.children,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(8, 7, 8, 4),
            child: Text(
              title,
              style: Theme.of(context).textTheme.labelMedium?.copyWith(
                    color: const Color(0xFF556A86),
                    fontWeight: FontWeight.w800,
                  ),
            ),
          ),
          ...children,
        ],
      ),
    );
  }
}

class _FacetOption extends StatelessWidget {
  final String label;
  final int count;
  final bool selected;
  final VoidCallback onTap;

  const _FacetOption({
    super.key,
    required this.label,
    required this.count,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      selected: selected,
      label: '$label，$count 条',
      child: Material(
        color: selected ? const Color(0xFFEAF2FF) : Colors.transparent,
        borderRadius: BorderRadius.circular(8),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(8),
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 44),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
              child: Row(
                children: [
                  Icon(
                    selected
                        ? Icons.check_box_outlined
                        : Icons.check_box_outline_blank,
                    size: 18,
                    color: selected
                        ? const Color(0xFF1E4F8A)
                        : const Color(0xFF708096),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      label,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            fontWeight:
                                selected ? FontWeight.w700 : FontWeight.w500,
                          ),
                    ),
                  ),
                  const SizedBox(width: 6),
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                    decoration: BoxDecoration(
                      color: selected
                          ? const Color(0xFFD8E8FF)
                          : const Color(0xFFF0F3F7),
                      borderRadius: BorderRadius.circular(999),
                    ),
                    child: Text(
                      '$count',
                      style: Theme.of(context).textTheme.labelSmall?.copyWith(
                            color: const Color(0xFF42566F),
                            fontWeight: FontWeight.w700,
                          ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _NoticeListOnly extends StatelessWidget {
  final List<NoticeListItemModel> items;
  final int? selectedNoticeId;
  final bool dense;
  final bool showInlineActions;
  final ValueChanged<int> onSelect;
  final Future<void> Function(int, NoticeReviewPayload) onUpdateReview;
  final Map<int, String> reviewActionsInFlight;
  final ValueChanged<String> onFilterBySource;
  final String Function(String) sourceDisplayName;
  final ValueChanged<String> onFilterByCategory;
  final ValueChanged<String> onFilterByKeyword;
  final ScrollController scrollController;

  const _NoticeListOnly({
    required this.items,
    required this.selectedNoticeId,
    required this.dense,
    required this.showInlineActions,
    required this.onSelect,
    required this.onUpdateReview,
    required this.reviewActionsInFlight,
    required this.onFilterBySource,
    required this.sourceDisplayName,
    required this.onFilterByCategory,
    required this.onFilterByKeyword,
    required this.scrollController,
  });

  @override
  Widget build(BuildContext context) {
    if (dense) {
      return _DenseNoticeList(
        items: items,
        selectedNoticeId: selectedNoticeId,
        onSelect: onSelect,
        onFilterBySource: onFilterBySource,
        sourceDisplayName: sourceDisplayName,
        onFilterByCategory: onFilterByCategory,
        onFilterByKeyword: onFilterByKeyword,
        scrollController: scrollController,
      );
    }

    return Card(
      margin: EdgeInsets.zero,
      child: ListView.separated(
        controller: scrollController,
        padding: const EdgeInsets.all(10),
        itemCount: items.length,
        separatorBuilder: (_, __) => const SizedBox(height: 8),
        itemBuilder: (context, index) {
          final item = items[index];
          final selected = item.id == selectedNoticeId;
          final reviewActionInFlight = reviewActionsInFlight[item.id];

          return AnimatedContainer(
            duration: const Duration(milliseconds: 180),
            decoration: BoxDecoration(
              color:
                  selected ? const Color(0xFFEAF2FF) : const Color(0xFFFDFEFF),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(
                color: selected
                    ? const Color(0xFFBFD3F8)
                    : const Color(0xFFE4EBF5),
              ),
            ),
            child: InkWell(
              borderRadius: BorderRadius.circular(16),
              onTap: () => onSelect(item.id),
              child: Padding(
                padding: EdgeInsets.all(dense ? 12 : 16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(
                          child: Text(
                            item.title.isEmpty ? '未命名公告' : item.title,
                            maxLines: dense ? 2 : null,
                            overflow: dense
                                ? TextOverflow.ellipsis
                                : TextOverflow.clip,
                            style: Theme.of(context).textTheme.titleMedium,
                          ),
                        ),
                        const SizedBox(width: 12),
                        _PriorityPill(isHighPriority: item.isHighPriority),
                      ],
                    ),
                    if (!dense && item.summary.isNotEmpty) ...[
                      const SizedBox(height: 10),
                      Text(
                        item.summary,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.bodyMedium,
                      ),
                    ],
                    SizedBox(height: dense ? 8 : 12),
                    Wrap(
                      spacing: 6,
                      runSpacing: 6,
                      children: [
                        SizedBox(
                          width: dense ? 180 : null,
                          child: _InfoPill(
                            key: Key('notice-source-${item.id}'),
                            label: '来源',
                            value: sourceDisplayName(item.sourceSite),
                            tooltip:
                                '只看来自 ${sourceDisplayName(item.sourceSite)} 的公告',
                            onTap: () => onFilterBySource(item.sourceSite),
                          ),
                        ),
                        _InfoPill(
                          key: Key('notice-category-${item.id}'),
                          label: '类别',
                          value: item.category,
                          tooltip: '只看 ${item.category}',
                          onTap: () => onFilterByCategory(item.category),
                        ),
                        if (!dense)
                          _InfoPill(label: '标记', value: item.reviewStatus),
                        if (!dense && item.isArchived)
                          const _InfoPill(label: '归档', value: '已归档'),
                        if (!dense)
                          _InfoPill(
                            label: '采集时间',
                            value:
                                DateFormatter.formatDateTime(item.capturedAt),
                          ),
                        if (!dense)
                          _InfoPill(
                            label: '内容质量',
                            value: item.qualityScore >= 60
                                ? '高 · ${item.qualityScore} 分'
                                : '待完善 · ${item.qualityScore} 分',
                          ),
                      ],
                    ),
                    if (item.matchedKeywords.isNotEmpty) ...[
                      SizedBox(height: dense ? 8 : 12),
                      Wrap(
                        spacing: 6,
                        runSpacing: 6,
                        children: [
                          ...item.matchedKeywords
                              .take(dense ? 2 : item.matchedKeywords.length)
                              .map(
                                (keyword) => ActionChip(
                                  key: Key(
                                    'notice-keyword-${item.id}-$keyword',
                                  ),
                                  avatar: const Icon(Icons.filter_alt_outlined,
                                      size: 16),
                                  label: Text(keyword),
                                  tooltip: '按关键词“$keyword”筛选',
                                  onPressed: () => onFilterByKeyword(keyword),
                                ),
                              ),
                          if (dense && item.matchedKeywords.length > 2)
                            Chip(
                              visualDensity: VisualDensity.compact,
                              label:
                                  Text('+${item.matchedKeywords.length - 2}'),
                            ),
                        ],
                      ),
                    ],
                    if (dense) ...[
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          const Icon(
                            Icons.schedule_outlined,
                            size: 15,
                            color: Color(0xFF708096),
                          ),
                          const SizedBox(width: 5),
                          Expanded(
                            child: Text(
                              '${item.reviewStatus} · ${item.qualityScore} 分 · '
                              '${DateFormatter.formatDateTime(item.capturedAt)}',
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: Theme.of(context)
                                  .textTheme
                                  .bodySmall
                                  ?.copyWith(
                                    color: const Color(0xFF708096),
                                  ),
                            ),
                          ),
                          const Icon(
                            Icons.chevron_right,
                            size: 18,
                            color: Color(0xFF55708E),
                          ),
                        ],
                      ),
                    ],
                    if (showInlineActions) ...[
                      const SizedBox(height: 12),
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: [
                          _ReviewActionButton(
                            key: Key('notice-review-${item.id}-有效'),
                            label: '有效',
                            selected: item.reviewStatus == '有效',
                            loading: reviewActionInFlight == '有效',
                            progressKey:
                                Key('notice-review-progress-${item.id}-有效'),
                            onPressed: reviewActionInFlight == null
                                ? () => onUpdateReview(
                                      item.id,
                                      const NoticeReviewPayload(
                                        reviewStatus: '有效',
                                      ),
                                    )
                                : null,
                          ),
                          _ReviewActionButton(
                            key: Key('notice-review-${item.id}-无效'),
                            label: '无效',
                            selected: item.reviewStatus == '无效',
                            loading: reviewActionInFlight == '无效',
                            progressKey:
                                Key('notice-review-progress-${item.id}-无效'),
                            onPressed: reviewActionInFlight == null
                                ? () => onUpdateReview(
                                      item.id,
                                      const NoticeReviewPayload(
                                        reviewStatus: '无效',
                                      ),
                                    )
                                : null,
                          ),
                          _ReviewActionButton(
                            key: Key('notice-review-${item.id}-归档'),
                            label: item.isArchived ? '取消归档' : '归档',
                            selected: item.isArchived,
                            loading: reviewActionInFlight == '归档',
                            progressKey:
                                Key('notice-review-progress-${item.id}-归档'),
                            onPressed: reviewActionInFlight == null
                                ? () => onUpdateReview(
                                      item.id,
                                      NoticeReviewPayload(
                                        isArchived: !item.isArchived,
                                      ),
                                    )
                                : null,
                          ),
                        ],
                      ),
                    ],
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}

class _DenseNoticeList extends StatelessWidget {
  final List<NoticeListItemModel> items;
  final int? selectedNoticeId;
  final ValueChanged<int> onSelect;
  final ValueChanged<String> onFilterBySource;
  final String Function(String) sourceDisplayName;
  final ValueChanged<String> onFilterByCategory;
  final ValueChanged<String> onFilterByKeyword;
  final ScrollController scrollController;

  const _DenseNoticeList({
    required this.items,
    required this.selectedNoticeId,
    required this.onSelect,
    required this.onFilterBySource,
    required this.sourceDisplayName,
    required this.onFilterByCategory,
    required this.onFilterByKeyword,
    required this.scrollController,
  });

  @override
  Widget build(BuildContext context) {
    const headerStyle = TextStyle(
      color: Color(0xFF556A86),
      fontSize: 12,
      fontWeight: FontWeight.w700,
    );

    return Card(
      margin: EdgeInsets.zero,
      clipBehavior: Clip.antiAlias,
      child: LayoutBuilder(
        builder: (context, constraints) {
          final showColumns = constraints.maxWidth >= 560;
          return Column(
            children: [
              if (showColumns) ...[
                Container(
                  height: 42,
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  color: const Color(0xFFF7F9FC),
                  child: const Row(
                    children: [
                      SizedBox(width: 24),
                      SizedBox(width: 8),
                      Expanded(child: Text('标题', style: headerStyle)),
                      SizedBox(width: 8),
                      SizedBox(
                          width: 96, child: Text('来源', style: headerStyle)),
                      SizedBox(
                          width: 76, child: Text('类型', style: headerStyle)),
                      SizedBox(
                          width: 96, child: Text('发布时间', style: headerStyle)),
                      SizedBox(
                          width: 60, child: Text('优先级', style: headerStyle)),
                    ],
                  ),
                ),
                const Divider(height: 1),
              ],
              Expanded(
                child: ListView.separated(
                  controller: scrollController,
                  padding: EdgeInsets.zero,
                  itemCount: items.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (context, index) {
                    final item = items[index];
                    final selected = item.id == selectedNoticeId;
                    final visibleKeyword = item.matchedKeywords.isEmpty
                        ? null
                        : item.matchedKeywords.first;

                    return Semantics(
                      button: true,
                      selected: selected,
                      label: '打开公告：${item.title}',
                      child: Material(
                        color: selected
                            ? const Color(0xFFEAF2FF)
                            : Colors.transparent,
                        child: InkWell(
                          onTap: () => onSelect(item.id),
                          child: Padding(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 12,
                              vertical: 8,
                            ),
                            child: showColumns
                                ? _buildColumnRow(
                                    context,
                                    item,
                                    visibleKeyword,
                                  )
                                : _buildCompactRow(
                                    context,
                                    item,
                                    visibleKeyword,
                                  ),
                          ),
                        ),
                      ),
                    );
                  },
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _buildColumnRow(
    BuildContext context,
    NoticeListItemModel item,
    String? visibleKeyword,
  ) {
    final publishedAt = item.publishedAt ?? item.capturedAt;
    return ConstrainedBox(
      constraints: const BoxConstraints(minHeight: 72),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          SizedBox(
            width: 24,
            child: _PriorityIcon(isHighPriority: item.isHighPriority),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _NoticeRowTitle(title: item.title),
                if (visibleKeyword != null)
                  _NoticeRowFilterButton(
                    key: Key(
                      'notice-keyword-${item.id}-$visibleKeyword',
                    ),
                    icon: Icons.search_outlined,
                    label: item.matchedKeywords.length > 1
                        ? '$visibleKeyword +${item.matchedKeywords.length - 1}'
                        : visibleKeyword,
                    onPressed: () => onFilterByKeyword(visibleKeyword),
                  ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          SizedBox(
            width: 96,
            child: _NoticeRowFilterButton(
              key: Key('notice-source-${item.id}'),
              label: sourceDisplayName(item.sourceSite),
              onPressed: () => onFilterBySource(item.sourceSite),
            ),
          ),
          SizedBox(
            width: 76,
            child: _NoticeRowFilterButton(
              key: Key('notice-category-${item.id}'),
              label: item.category,
              onPressed: () => onFilterByCategory(item.category),
            ),
          ),
          SizedBox(
            width: 96,
            child: Text(
              DateFormatter.formatDateTime(publishedAt),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: const Color(0xFF556A86),
                  ),
            ),
          ),
          SizedBox(
            width: 60,
            child: _CompactPriorityLabel(
              isHighPriority: item.isHighPriority,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCompactRow(
    BuildContext context,
    NoticeListItemModel item,
    String? visibleKeyword,
  ) {
    final publishedAt = item.publishedAt ?? item.capturedAt;
    return ConstrainedBox(
      constraints: const BoxConstraints(minHeight: 84),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 3),
            child: SizedBox(
              width: 24,
              child: _PriorityIcon(isHighPriority: item.isHighPriority),
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _NoticeRowTitle(title: item.title),
                const SizedBox(height: 4),
                Wrap(
                  spacing: 4,
                  runSpacing: 2,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    _NoticeRowFilterButton(
                      key: Key('notice-source-${item.id}'),
                      label: sourceDisplayName(item.sourceSite),
                      onPressed: () => onFilterBySource(item.sourceSite),
                    ),
                    _NoticeRowFilterButton(
                      key: Key('notice-category-${item.id}'),
                      label: item.category,
                      onPressed: () => onFilterByCategory(item.category),
                    ),
                    if (visibleKeyword != null)
                      _NoticeRowFilterButton(
                        key: Key(
                          'notice-keyword-${item.id}-$visibleKeyword',
                        ),
                        icon: Icons.search_outlined,
                        label: item.matchedKeywords.length > 1
                            ? '$visibleKeyword +${item.matchedKeywords.length - 1}'
                            : visibleKeyword,
                        onPressed: () => onFilterByKeyword(visibleKeyword),
                      ),
                    ConstrainedBox(
                      constraints: const BoxConstraints(minHeight: 44),
                      child: Align(
                        alignment: Alignment.centerLeft,
                        widthFactor: 1,
                        child: Text(
                          DateFormatter.formatDateTime(publishedAt),
                          style:
                              Theme.of(context).textTheme.bodySmall?.copyWith(
                                    color: const Color(0xFF66778D),
                                  ),
                        ),
                      ),
                    ),
                    SizedBox(
                      height: 44,
                      child: Center(
                        child: _CompactPriorityLabel(
                          isHighPriority: item.isHighPriority,
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _PriorityIcon extends StatelessWidget {
  final bool isHighPriority;

  const _PriorityIcon({required this.isHighPriority});

  @override
  Widget build(BuildContext context) {
    return Icon(
      isHighPriority ? Icons.star_rounded : Icons.star_border_rounded,
      size: 20,
      color: isHighPriority ? const Color(0xFFD97706) : const Color(0xFF8A9AAF),
    );
  }
}

class _NoticeRowTitle extends StatelessWidget {
  final String title;

  const _NoticeRowTitle({required this.title});

  @override
  Widget build(BuildContext context) {
    return Text(
      title.isEmpty ? '未命名公告' : title,
      maxLines: 2,
      overflow: TextOverflow.ellipsis,
      style: Theme.of(context).textTheme.bodyMedium?.copyWith(
            color: const Color(0xFF18324E),
            fontWeight: FontWeight.w700,
          ),
    );
  }
}

class _NoticeRowFilterButton extends StatelessWidget {
  final IconData? icon;
  final String label;
  final VoidCallback onPressed;

  const _NoticeRowFilterButton({
    super.key,
    this.icon,
    required this.label,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    final style = TextButton.styleFrom(
      alignment: Alignment.centerLeft,
      minimumSize: const Size(44, 44),
      padding: const EdgeInsets.symmetric(horizontal: 5),
      visualDensity: VisualDensity.compact,
    );
    if (icon == null) {
      return TextButton(
        onPressed: onPressed,
        style: style,
        child: Text(
          label,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
        ),
      );
    }
    return TextButton.icon(
      onPressed: onPressed,
      style: style,
      icon: Icon(icon, size: 14),
      label: Text(
        label,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
      ),
    );
  }
}

class _CompactPriorityLabel extends StatelessWidget {
  final bool isHighPriority;

  const _CompactPriorityLabel({required this.isHighPriority});

  @override
  Widget build(BuildContext context) {
    final foreground =
        isHighPriority ? const Color(0xFFB54708) : const Color(0xFF356859);
    final background =
        isHighPriority ? const Color(0xFFFFF0D5) : const Color(0xFFE7F4EF);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 5),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        isHighPriority ? '高' : '常规',
        maxLines: 1,
        textAlign: TextAlign.center,
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
              color: foreground,
              fontWeight: FontWeight.w800,
            ),
      ),
    );
  }
}

class _NoticeDetailPanel extends StatelessWidget {
  final int noticeId;
  final Future<NoticeDetailModel> detailFuture;
  final String Function(String) sourceDisplayName;
  final Future<void> Function(BuildContext, NoticeDetailModel, [String?])
      onOpenSnapshot;
  final Future<void> Function(int, NoticeReviewPayload) onUpdateReview;
  final String? reviewActionInFlight;
  final VoidCallback onRetry;
  final ScrollController scrollController;

  const _NoticeDetailPanel({
    required this.noticeId,
    required this.detailFuture,
    required this.sourceDisplayName,
    required this.onOpenSnapshot,
    required this.onUpdateReview,
    required this.reviewActionInFlight,
    required this.onRetry,
    required this.scrollController,
  });

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<NoticeDetailModel>(
      key: ValueKey(noticeId),
      future: detailFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Card(
            child: Center(child: CircularProgressIndicator()),
          );
        }

        if (snapshot.hasError) {
          return AsyncErrorPanel(
            error: snapshot.error!,
            title: '加载公告详情失败',
            onRetry: onRetry,
          );
        }

        final detail = snapshot.data;
        if (detail == null) {
          return const Card(
            child: Padding(
              padding: EdgeInsets.all(20),
              child: Text('暂无公告详情'),
            ),
          );
        }

        final isCompetitor =
            detail.metadata?['kind'] == 'competitor_intelligence';
        final hasMeetingMetadata = _hasMeetingMetadata(detail.metadata);
        final publishedAtLabel = detail.publishedAt == null
            ? '未提供'
            : DateFormatter.formatDateTime(
                detail.publishedAt,
                fallback: '未提供',
              );

        return Card(
          margin: EdgeInsets.zero,
          clipBehavior: Clip.antiAlias,
          child: Column(
            children: [
              Container(
                height: 52,
                padding: const EdgeInsets.symmetric(horizontal: 16),
                color: const Color(0xFFF7F9FC),
                child: Row(
                  children: [
                    const Icon(
                      Icons.article_outlined,
                      size: 19,
                      color: Color(0xFF1E4F8A),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      '公告详情',
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            color: const Color(0xFF18324E),
                            fontWeight: FontWeight.w800,
                          ),
                    ),
                    const Spacer(),
                    Text(
                      '#${detail.id}',
                      style: Theme.of(context).textTheme.labelMedium?.copyWith(
                            color: const Color(0xFF72839A),
                          ),
                    ),
                  ],
                ),
              ),
              const Divider(height: 1),
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: ListView(
                    controller: scrollController,
                    padding: EdgeInsets.zero,
                    children: [
                      Text(
                        detail.title.isEmpty ? '未命名公告' : detail.title,
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                      const SizedBox(height: 12),
                      Wrap(
                        spacing: 12,
                        runSpacing: 8,
                        children: isCompetitor
                            ? [
                                _MetaTag(
                                  label: '处理状态',
                                  value: detail.reviewStatus,
                                ),
                                _MetaTag(
                                  label: '归档',
                                  value: detail.isArchived ? '已归档' : '未归档',
                                ),
                                _MetaTag(
                                  label: '内容质量',
                                  value: detail.qualityScore >= 60
                                      ? '高 · ${detail.qualityScore} 分'
                                      : '待完善 · ${detail.qualityScore} 分',
                                ),
                                _MetaTag(
                                  label: '采集时间',
                                  value: DateFormatter.formatDateTime(
                                    detail.capturedAt,
                                  ),
                                ),
                              ]
                            : [
                                _MetaTag(
                                  label: '来源站点',
                                  value: sourceDisplayName(detail.sourceSite),
                                ),
                                _MetaTag(label: '类别', value: detail.category),
                                _MetaTag(
                                  label: '标记状态',
                                  value: detail.reviewStatus,
                                ),
                                _MetaTag(
                                  label: '归档',
                                  value: detail.isArchived ? '已归档' : '未归档',
                                ),
                                _MetaTag(
                                  label: '采集时间',
                                  value: DateFormatter.formatDateTime(
                                    detail.capturedAt,
                                  ),
                                ),
                                _MetaTag(
                                  label: '内容质量',
                                  value: detail.qualityScore >= 60
                                      ? '高 · ${detail.qualityScore} 分'
                                      : '待完善 · ${detail.qualityScore} 分',
                                ),
                                _MetaTag(
                                  label: '发布时间',
                                  value: publishedAtLabel,
                                ),
                              ],
                      ),
                      if (isCompetitor) ...[
                        const SizedBox(height: 18),
                        CompetitorIntelligencePanel(
                          metadata: detail.metadata!,
                          contentText: detail.contentText,
                          publishedAtLabel: publishedAtLabel,
                        ),
                      ] else ...[
                        const SizedBox(height: 14),
                        SelectableText(
                          detail.sourceUrl,
                          style: const TextStyle(
                            color: Color(0xFF1F4B99),
                            decoration: TextDecoration.underline,
                          ),
                        ),
                        if (hasMeetingMetadata) ...[
                          const SizedBox(height: 18),
                          _IndustryMeetingPanel(
                            noticeId: detail.id,
                            metadata: detail.metadata!,
                          ),
                        ],
                      ],
                      const SizedBox(height: 16),
                      _NoticeMatchReasonPanel(
                        detail: detail,
                        onKeywordPressed: (keyword) =>
                            onOpenSnapshot(context, detail, keyword),
                      ),
                      const SizedBox(height: 18),
                      Container(
                        width: double.infinity,
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: const Color(0xFFF8FAFD),
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(color: const Color(0xFFE0E7F0)),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                const Icon(
                                  Icons.task_alt_outlined,
                                  size: 19,
                                  color: Color(0xFF1E4F8A),
                                ),
                                const SizedBox(width: 9),
                                Text(
                                  '处理与查阅',
                                  style: Theme.of(context)
                                      .textTheme
                                      .titleMedium
                                      ?.copyWith(fontWeight: FontWeight.w700),
                                ),
                              ],
                            ),
                            const SizedBox(height: 14),
                            Wrap(
                              spacing: 8,
                              runSpacing: 8,
                              children: [
                                _ReviewActionButton(
                                  key: Key(
                                      'notice-detail-review-${detail.id}-有效'),
                                  label: '有效',
                                  selected: detail.reviewStatus == '有效',
                                  loading: reviewActionInFlight == '有效',
                                  progressKey: Key(
                                    'notice-detail-review-progress-${detail.id}-有效',
                                  ),
                                  onPressed: reviewActionInFlight == null
                                      ? () => onUpdateReview(
                                            detail.id,
                                            const NoticeReviewPayload(
                                              reviewStatus: '有效',
                                            ),
                                          )
                                      : null,
                                ),
                                _ReviewActionButton(
                                  key: Key(
                                      'notice-detail-review-${detail.id}-无效'),
                                  label: '无效',
                                  selected: detail.reviewStatus == '无效',
                                  loading: reviewActionInFlight == '无效',
                                  progressKey: Key(
                                    'notice-detail-review-progress-${detail.id}-无效',
                                  ),
                                  onPressed: reviewActionInFlight == null
                                      ? () => onUpdateReview(
                                            detail.id,
                                            const NoticeReviewPayload(
                                              reviewStatus: '无效',
                                            ),
                                          )
                                      : null,
                                ),
                                _ReviewActionButton(
                                  key: Key(
                                      'notice-detail-review-${detail.id}-待关注'),
                                  label: '待关注',
                                  selected: detail.reviewStatus == '待关注',
                                  loading: reviewActionInFlight == '待关注',
                                  progressKey: Key(
                                    'notice-detail-review-progress-'
                                    '${detail.id}-待关注',
                                  ),
                                  onPressed: reviewActionInFlight == null
                                      ? () => onUpdateReview(
                                            detail.id,
                                            const NoticeReviewPayload(
                                              reviewStatus: '待关注',
                                            ),
                                          )
                                      : null,
                                ),
                                _ReviewActionButton(
                                  key: Key(
                                      'notice-detail-review-${detail.id}-归档'),
                                  label: detail.isArchived ? '取消归档' : '加入归档',
                                  selected: detail.isArchived,
                                  loading: reviewActionInFlight == '归档',
                                  progressKey: Key(
                                    'notice-detail-review-progress-${detail.id}-归档',
                                  ),
                                  onPressed: reviewActionInFlight == null
                                      ? () => onUpdateReview(
                                            detail.id,
                                            NoticeReviewPayload(
                                              isArchived: !detail.isArchived,
                                            ),
                                          )
                                      : null,
                                ),
                              ],
                            ),
                            const SizedBox(height: 12),
                            Wrap(
                              spacing: 10,
                              runSpacing: 10,
                              children: [
                                FilledButton.tonalIcon(
                                  onPressed: () =>
                                      onOpenSnapshot(context, detail),
                                  icon: const Icon(Icons.history_edu_outlined),
                                  label: const Text('查看采集快照'),
                                ),
                                if (detail.sourceUrl.isNotEmpty)
                                  OutlinedButton.icon(
                                    onPressed: () async {
                                      final uri = Uri.parse(detail.sourceUrl);
                                      try {
                                        await launchUrl(
                                          uri,
                                          mode: LaunchMode.externalApplication,
                                        );
                                      } catch (e) {
                                        if (context.mounted) {
                                          ScaffoldMessenger.of(context)
                                              .showSnackBar(
                                            SnackBar(
                                              content: Text(
                                                '无法打开原文链接（$uri）：'
                                                '${userFacingError(e)}',
                                              ),
                                            ),
                                          );
                                        }
                                      }
                                    },
                                    icon: const Icon(
                                      Icons.open_in_new_outlined,
                                      size: 17,
                                    ),
                                    label: Text(
                                      isCompetitor ? '打开证据来源' : '查看原文',
                                    ),
                                  )
                                else
                                  const OutlinedButton(
                                    onPressed: null,
                                    child: Text('无原文链接'),
                                  ),
                              ],
                            ),
                          ],
                        ),
                      ),
                      if (!isCompetitor) ...[
                        const SizedBox(height: 18),
                        Text(
                          '正文内容',
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                        const SizedBox(height: 10),
                        Container(
                          width: double.infinity,
                          padding: const EdgeInsets.all(16),
                          decoration: BoxDecoration(
                            color: const Color(0xFFF7FAFD),
                            borderRadius: BorderRadius.circular(20),
                            border: Border.all(color: const Color(0xFFE3EAF5)),
                          ),
                          child: Text(
                            detail.contentText.isEmpty
                                ? '当前暂无正文内容。'
                                : detail.contentText,
                            style: Theme.of(context).textTheme.bodyMedium,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _NoticeMatchReasonPanel extends StatelessWidget {
  final NoticeDetailModel detail;
  final ValueChanged<String> onKeywordPressed;

  const _NoticeMatchReasonPanel({
    required this.detail,
    required this.onKeywordPressed,
  });

  @override
  Widget build(BuildContext context) {
    final keywordSummary = detail.matchedKeywords.isEmpty
        ? '未命中已启用关键词'
        : '命中 ${detail.matchedKeywords.length} 个已启用关键词';
    final prioritySummary = detail.isHighPriority ? '业务规则判定为高优先级' : '当前为常规优先级';

    return Container(
      key: const Key('notice-match-reason'),
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: detail.isHighPriority
            ? const Color(0xFFFFF8E8)
            : const Color(0xFFF3F7FC),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: detail.isHighPriority
              ? const Color(0xFFF3D394)
              : const Color(0xFFD9E5F2),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                detail.isHighPriority
                    ? Icons.priority_high_rounded
                    : Icons.rule_outlined,
                size: 19,
                color: detail.isHighPriority
                    ? const Color(0xFFB54708)
                    : const Color(0xFF1E4F8A),
              ),
              const SizedBox(width: 8),
              Text(
                '命中原因',
                style: Theme.of(context).textTheme.titleSmall?.copyWith(
                      color: const Color(0xFF18324E),
                      fontWeight: FontWeight.w800,
                    ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            '$keywordSummary；$prioritySummary；内容质量 ${detail.qualityScore} 分。',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: const Color(0xFF4D6078),
                  height: 1.5,
                ),
          ),
          if (detail.matchedKeywords.isNotEmpty) ...[
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: detail.matchedKeywords
                  .map(
                    (keyword) => ActionChip(
                      key: Key('notice-detail-keyword-$keyword'),
                      label: Text(keyword),
                      avatar: const Icon(Icons.search_outlined, size: 16),
                      onPressed: () => onKeywordPressed(keyword),
                      tooltip: '在快照中查找此关键词',
                      materialTapTargetSize: MaterialTapTargetSize.padded,
                    ),
                  )
                  .toList(),
            ),
          ],
        ],
      ),
    );
  }
}

bool _hasMeetingMetadata(Map<String, dynamic>? metadata) {
  if (metadata == null) {
    return false;
  }
  if (metadata['kind']?.toString() == 'industry_meeting') {
    return true;
  }
  return [
    'meeting_date',
    'location',
    'organizer',
    'registration_url',
    'registration_deadline',
  ].any((key) => _meetingMetadataText(metadata[key]).isNotEmpty);
}

String _meetingMetadataText(Object? raw) {
  if (raw == null) {
    return '';
  }
  if (raw is Iterable) {
    return raw
        .map((item) => item?.toString().trim() ?? '')
        .where((item) => item.isNotEmpty)
        .join('、');
  }
  final text = raw.toString().trim();
  if (text.isEmpty) {
    return '';
  }
  final parsed = DateTime.tryParse(text);
  if (parsed != null) {
    return DateFormatter.formatDateTime(
      parsed.toIso8601String(),
      fallback: text,
    );
  }
  return text;
}

class _IndustryMeetingPanel extends StatelessWidget {
  final int noticeId;
  final Map<String, dynamic> metadata;

  const _IndustryMeetingPanel({
    required this.noticeId,
    required this.metadata,
  });

  Future<void> _openExternalUrl(
    BuildContext context,
    String rawUrl, {
    required String failureLabel,
  }) async {
    final uri = Uri.tryParse(rawUrl);
    if (uri == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('$failureLabel：$rawUrl')),
      );
      return;
    }
    try {
      await launchUrl(
        uri,
        mode: LaunchMode.externalApplication,
      );
    } catch (error) {
      if (!context.mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('$failureLabel：${userFacingError(error)}'),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final meetingDate = _meetingMetadataText(metadata['meeting_date']);
    final location = _meetingMetadataText(metadata['location']);
    final organizer = _meetingMetadataText(metadata['organizer']);
    final registrationDeadline =
        _meetingMetadataText(metadata['registration_deadline']);
    final registrationUrl = _meetingMetadataText(metadata['registration_url']);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFFF7FAFD),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: const Color(0xFFE3EAF5)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(
                Icons.event_available_outlined,
                size: 19,
                color: Color(0xFF1E4F8A),
              ),
              const SizedBox(width: 8),
              Text(
                '会议信息',
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          Wrap(
            spacing: 16,
            runSpacing: 12,
            children: [
              if (meetingDate.isNotEmpty)
                _MeetingMetaItem(label: '会议时间', value: meetingDate),
              if (location.isNotEmpty)
                _MeetingMetaItem(label: '会议地点', value: location),
              if (organizer.isNotEmpty)
                _MeetingMetaItem(label: '主办方', value: organizer),
              if (registrationDeadline.isNotEmpty)
                _MeetingMetaItem(label: '报名截止', value: registrationDeadline),
            ],
          ),
          if (registrationUrl.isNotEmpty) ...[
            const SizedBox(height: 14),
            OutlinedButton.icon(
              key: Key('notice-meeting-registration-$noticeId'),
              onPressed: () => _openExternalUrl(
                context,
                registrationUrl,
                failureLabel: '无法打开报名入口',
              ),
              icon: const Icon(Icons.app_registration_outlined, size: 18),
              label: const Text('报名入口'),
            ),
          ],
        ],
      ),
    );
  }
}

class _MeetingMetaItem extends StatelessWidget {
  final String label;
  final String value;

  const _MeetingMetaItem({
    required this.label,
    required this.value,
  });

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
      constraints: const BoxConstraints(minWidth: 180, maxWidth: 320),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  color: const Color(0xFF556A86),
                  fontWeight: FontWeight.w700,
                ),
          ),
          const SizedBox(height: 4),
          Text(
            value,
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  fontWeight: FontWeight.w600,
                ),
          ),
        ],
      ),
    );
  }
}

class _PriorityPill extends StatelessWidget {
  final bool isHighPriority;

  const _PriorityPill({
    required this.isHighPriority,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color:
            isHighPriority ? const Color(0xFFFDEDED) : const Color(0xFFF3F6FA),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        isHighPriority ? '业务优先' : '常规',
        style: TextStyle(
          color: isHighPriority
              ? const Color(0xFFB42318)
              : const Color(0xFF556A86),
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}

class _ReviewActionButton extends StatelessWidget {
  final String label;
  final bool selected;
  final bool loading;
  final Key? progressKey;
  final VoidCallback? onPressed;

  const _ReviewActionButton({
    super.key,
    required this.label,
    required this.selected,
    this.loading = false,
    this.progressKey,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    final child = Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (loading) ...[
          SizedBox(
            key: progressKey,
            width: 16,
            height: 16,
            child: const CircularProgressIndicator(strokeWidth: 2),
          ),
          const SizedBox(width: 8),
        ],
        Text(label),
      ],
    );
    if (selected) {
      return FilledButton.tonal(
        onPressed: onPressed,
        child: child,
      );
    }
    return OutlinedButton(
      onPressed: onPressed,
      child: child,
    );
  }
}

class _InfoPill extends StatelessWidget {
  final String label;
  final String value;
  final String? tooltip;
  final VoidCallback? onTap;

  const _InfoPill({
    super.key,
    required this.label,
    required this.value,
    this.tooltip,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final content = Container(
      constraints: onTap == null
          ? null
          : const BoxConstraints(
              minHeight: 44,
            ),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: const Color(0xFFF5F8FC),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        '$label：$value',
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: Theme.of(context).textTheme.bodySmall,
      ),
    );

    if (onTap == null) {
      return content;
    }
    return Semantics(
      button: true,
      label: tooltip ?? '$label：$value',
      child: Tooltip(
        message: tooltip ?? '$label：$value',
        child: MouseRegion(
          cursor: SystemMouseCursors.click,
          child: Material(
            color: Colors.transparent,
            borderRadius: BorderRadius.circular(999),
            clipBehavior: Clip.antiAlias,
            child: InkWell(
              borderRadius: BorderRadius.circular(999),
              onTap: onTap,
              child: content,
            ),
          ),
        ),
      ),
    );
  }
}

class _MetaTag extends StatelessWidget {
  final String label;
  final String value;

  const _MetaTag({
    required this.label,
    required this.value,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: const Color(0xFFF3F6FA),
        borderRadius: BorderRadius.circular(12),
      ),
      child: RichText(
        text: TextSpan(
          style: DefaultTextStyle.of(context).style,
          children: [
            TextSpan(
              text: '$label：',
              style: const TextStyle(fontWeight: FontWeight.w600),
            ),
            TextSpan(text: value),
          ],
        ),
      ),
    );
  }
}

class _SnapshotViewerDialog extends StatefulWidget {
  final String content;
  final String? keywordToHighlight;

  const _SnapshotViewerDialog({
    required this.content,
    this.keywordToHighlight,
  });

  @override
  State<_SnapshotViewerDialog> createState() => _SnapshotViewerDialogState();
}

class _SnapshotViewerDialogState extends State<_SnapshotViewerDialog> {
  final GlobalKey _targetKey = GlobalKey();
  final ScrollController _scrollController = ScrollController();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (widget.keywordToHighlight != null &&
          widget.keywordToHighlight!.isNotEmpty &&
          _targetKey.currentContext != null) {
        Scrollable.ensureVisible(
          _targetKey.currentContext!,
          duration: const Duration(milliseconds: 300),
          alignment: 0.2,
        );
      }
    });
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  List<InlineSpan> _buildSpans(String text, String? keyword) {
    if (keyword == null || keyword.isEmpty) {
      return [TextSpan(text: text)];
    }
    final spans = <InlineSpan>[];
    final lowerText = text.toLowerCase();
    final lowerKeyword = keyword.toLowerCase();
    int start = 0;
    int indexOfMatch;
    bool isFirst = true;

    while ((indexOfMatch = lowerText.indexOf(lowerKeyword, start)) != -1) {
      if (indexOfMatch > start) {
        spans.add(TextSpan(text: text.substring(start, indexOfMatch)));
      }
      final kwText =
          text.substring(indexOfMatch, indexOfMatch + keyword.length);

      if (isFirst) {
        spans.add(
          WidgetSpan(
            alignment: PlaceholderAlignment.middle,
            child: Container(
              key: _targetKey,
              color: Colors.yellow,
              child: Text(
                kwText,
                style: const TextStyle(
                    color: Colors.red, fontWeight: FontWeight.bold),
              ),
            ),
          ),
        );
        isFirst = false;
      } else {
        spans.add(
          TextSpan(
            text: kwText,
            style: const TextStyle(
              backgroundColor: Colors.yellow,
              color: Colors.red,
              fontWeight: FontWeight.bold,
            ),
          ),
        );
      }
      start = indexOfMatch + keyword.length;
    }
    if (start < text.length) {
      spans.add(TextSpan(text: text.substring(start)));
    }
    return spans;
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('快照内容'),
      content: SizedBox(
        width: 720,
        child: Scrollbar(
          controller: _scrollController,
          interactive: true,
          thumbVisibility: true,
          child: SingleChildScrollView(
            controller: _scrollController,
            child: SelectableText.rich(
              TextSpan(
                children:
                    _buildSpans(widget.content, widget.keywordToHighlight),
              ),
            ),
          ),
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
