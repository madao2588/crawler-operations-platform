import 'package:flutter/material.dart';

import '../../../../app/navigation/app_navigation_intent.dart';
import '../../../../core/network/api_client.dart';
import '../../../../core/utils/date_formatter.dart';
import '../../../../core/utils/user_facing_error.dart';
import '../../../../core/widgets/async_error_panel.dart';
import '../../../../core/widgets/interactive_surface.dart';
import '../../../../core/widgets/page_chrome.dart';
import '../../data/models/dashboard_models.dart';
import '../../data/repositories/dashboard_repository.dart';
import '../../data/repositories/http_dashboard_repository.dart';
import '../../../notices/data/models/notice_models.dart';
import '../../../system_management/data/repositories/http_task_repository.dart';
import '../../../system_management/data/repositories/task_repository.dart';

class DashboardPage extends StatefulWidget {
  final DashboardRepository? repository;
  final TaskRepository? taskRepository;
  final ValueChanged<AppNavigationIntent>? onNavigate;

  const DashboardPage({
    super.key,
    this.repository,
    this.taskRepository,
    this.onNavigate,
  });

  @override
  State<DashboardPage> createState() => _DashboardPageState();
}

class _DashboardPageState extends State<DashboardPage> {
  late final DashboardRepository _repository;
  late final TaskRepository _taskRepository;
  final ScrollController _pageScrollController = ScrollController();
  late Future<DashboardOverviewModel> _future;
  bool _isRefreshing = false;

  @override
  void initState() {
    super.initState();
    final client = ApiClient();
    _repository =
        widget.repository ?? HttpDashboardRepository(apiClient: client);
    _taskRepository =
        widget.taskRepository ?? HttpTaskRepository(apiClient: client);
    _future = _repository.fetchOverview();
  }

  @override
  void dispose() {
    _pageScrollController.dispose();
    super.dispose();
  }

  Future<void> _refresh() async {
    if (_isRefreshing) {
      return;
    }
    setState(() {
      _isRefreshing = true;
    });
    try {
      try {
        await _taskRepository.runAllEnabledTasks();
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('触发采集失败：${userFacingError(e)}')),
          );
        }
      }
      if (!mounted) {
        return;
      }
      setState(() {
        _future = _repository.fetchOverview();
      });
      await _future;
    } finally {
      if (mounted) {
        setState(() {
          _isRefreshing = false;
        });
      }
    }
  }

  VoidCallback? _navigationAction(AppNavigationIntent intent) {
    final onNavigate = widget.onNavigate;
    return onNavigate == null ? null : () => onNavigate(intent);
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<DashboardOverviewModel>(
      future: _future,
      builder: (context, snapshot) {
        return AppPageFrame(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _DashboardPageHero(
                lastUpdatedAt: snapshot.data?.lastUpdatedAt,
                runtime: snapshot.data?.runtime ??
                    DashboardRuntimeModel.fromJson(null),
                onRefresh: _isRefreshing ? null : _refresh,
                isRefreshing: _isRefreshing,
              ),
              const SizedBox(height: 16),
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
    AsyncSnapshot<DashboardOverviewModel> snapshot,
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
              Text('正在刷新首页看板...'),
            ],
          ),
        ),
      );
    }

    if (snapshot.hasError) {
      return AsyncErrorPanel(
        error: snapshot.error!,
        title: '加载首页看板失败',
        onRetry: _refresh,
      );
    }

    final data = snapshot.data;
    if (data == null) {
      return const Card(
        child: Padding(
          padding: EdgeInsets.all(20),
          child: Text('暂无首页数据'),
        ),
      );
    }

    String sourceLabelFor(String sourceSite) {
      final normalized = sourceSite.trim();
      if (normalized.isEmpty) {
        return '未知来源';
      }
      for (final item in data.sourceDistribution) {
        if (item.sourceSite == normalized && item.displayName.isNotEmpty) {
          return item.displayName;
        }
      }
      return normalized;
    }

    return LayoutBuilder(
      builder: (context, constraints) {
        final isWide = constraints.maxWidth >= 1100;
        final metrics = [
          _MetricCard(
            key: const Key('dashboard-metric-today'),
            title: '今日新增公告',
            value: '${data.metrics.todayNewNotices}',
            subtitle: '当前采集窗口内新增内容',
            icon: Icons.notifications_active_outlined,
            accentColor: const Color(0xFF1E4F8A),
            onTap: _navigationAction(
              const AppNavigationIntent.notices(
                query: NoticeQuery(capturedToday: true),
              ),
            ),
          ),
          _MetricCard(
            key: const Key('dashboard-metric-declaration'),
            title: '申报通知',
            value: '${data.metrics.projectDeclarationNotices}',
            subtitle: '命中申报、指南、组织申报等线索',
            icon: Icons.assignment_outlined,
            accentColor: const Color(0xFF117A65),
            onTap: _navigationAction(
              const AppNavigationIntent.notices(
                query: NoticeQuery(projectSignal: '申报通知'),
              ),
            ),
          ),
          _MetricCard(
            key: const Key('dashboard-metric-result'),
            title: '结果公示',
            value: '${data.metrics.resultPublicationNotices}',
            subtitle: '命中结果、公示、拟立项等线索',
            icon: Icons.fact_check_outlined,
            accentColor: const Color(0xFF7B4DBB),
            onTap: _navigationAction(
              const AppNavigationIntent.notices(
                query: NoticeQuery(projectSignal: '结果公示'),
              ),
            ),
          ),
          _MetricCard(
            key: const Key('dashboard-metric-sites'),
            title: '监测站点数',
            value: '${data.metrics.monitoringSiteCount}',
            subtitle: '当前纳入监控的站点',
            icon: Icons.language_outlined,
            accentColor: const Color(0xFF2D6CDF),
            onTap: _navigationAction(
              const AppNavigationIntent.sourceSites(),
            ),
          ),
          _MetricCard(
            key: const Key('dashboard-metric-keywords'),
            title: '关键词命中',
            value: '${data.metrics.keywordHitNotices}',
            subtitle: '检索命中的业务线索',
            icon: Icons.local_offer_outlined,
            accentColor: const Color(0xFFC45A1A),
            onTap: _navigationAction(
              const AppNavigationIntent.notices(
                query: NoticeQuery(keywordHit: true),
              ),
            ),
          ),
          _MetricCard(
            key: const Key('dashboard-metric-business-priority'),
            title: '业务优先',
            value: '${data.metrics.highPriorityNotices}',
            subtitle: '命中业务优先词，建议优先查看',
            icon: Icons.flag_outlined,
            accentColor: const Color(0xFFB42318),
            onTap: _navigationAction(
              const AppNavigationIntent.notices(
                query: NoticeQuery(highPriority: true),
              ),
            ),
          ),
          _MetricCard(
            key: const Key('dashboard-metric-high-quality'),
            title: '高质量内容',
            value: '${data.metrics.highQualityNotices}',
            subtitle: '内容质量分达到 60',
            icon: Icons.verified_outlined,
            accentColor: const Color(0xFF2D6CDF),
            onTap: _navigationAction(
              const AppNavigationIntent.notices(
                query: NoticeQuery(highQuality: true),
              ),
            ),
          ),
        ];

        return Scrollbar(
          controller: _pageScrollController,
          thumbVisibility: true,
          child: ListView(
            controller: _pageScrollController,
            children: [
              LayoutBuilder(
                builder: (context, metricsConstraints) {
                  final cardWidth = metricsConstraints.maxWidth >= 1200
                      ? (metricsConstraints.maxWidth - 64) / 5
                      : metricsConstraints.maxWidth >= 760
                          ? (metricsConstraints.maxWidth - 16) / 2
                          : metricsConstraints.maxWidth;
                  return Wrap(
                    spacing: 16,
                    runSpacing: 16,
                    children: metrics
                        .map(
                          (metric) => SizedBox(width: cardWidth, child: metric),
                        )
                        .toList(),
                  );
                },
              ),
              const SizedBox(height: 18),
              if (isWide)
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      flex: 3,
                      child: _SectionCard(
                        title: '业务优先公告',
                        action: TextButton.icon(
                          onPressed: _navigationAction(
                            const AppNavigationIntent.notices(
                              query: NoticeQuery(highPriority: true),
                            ),
                          ),
                          icon: const Icon(Icons.arrow_forward, size: 16),
                          label:
                              Text('共 ${data.metrics.highPriorityNotices} 条'),
                        ),
                        child: _NoticeList(
                          notices: data.highValueNotices,
                          sourceLabelFor: sourceLabelFor,
                          onOpen: (noticeId) => widget.onNavigate?.call(
                            AppNavigationIntent.notices(noticeId: noticeId),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 16),
                    Expanded(
                      flex: 2,
                      child: Column(
                        children: [
                          _SectionCard(
                            title: '关键词热度',
                            child: _KeywordHeatGrid(
                              items: data.keywordHeat,
                              onSelect: (keyword) => widget.onNavigate?.call(
                                AppNavigationIntent.notices(
                                  query: NoticeQuery(keyword: keyword),
                                ),
                              ),
                            ),
                          ),
                          const SizedBox(height: 16),
                          _SectionCard(
                            title: '最近公告',
                            child: _RecentNoticeList(
                              items: data.recentNotices,
                              sourceLabelFor: sourceLabelFor,
                              onOpen: (noticeId) => widget.onNavigate?.call(
                                AppNavigationIntent.notices(noticeId: noticeId),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                )
              else ...[
                _SectionCard(
                  title: '业务优先公告',
                  action: TextButton.icon(
                    onPressed: _navigationAction(
                      const AppNavigationIntent.notices(
                        query: NoticeQuery(highPriority: true),
                      ),
                    ),
                    icon: const Icon(Icons.arrow_forward, size: 16),
                    label: Text('共 ${data.metrics.highPriorityNotices} 条'),
                  ),
                  child: _NoticeList(
                    notices: data.highValueNotices,
                    sourceLabelFor: sourceLabelFor,
                    onOpen: (noticeId) => widget.onNavigate?.call(
                      AppNavigationIntent.notices(noticeId: noticeId),
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                _SectionCard(
                  title: '关键词热度',
                  child: _KeywordHeatGrid(
                    items: data.keywordHeat,
                    onSelect: (keyword) => widget.onNavigate?.call(
                      AppNavigationIntent.notices(
                        query: NoticeQuery(keyword: keyword),
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                _SectionCard(
                  title: '最近公告',
                  child: _RecentNoticeList(
                    items: data.recentNotices,
                    sourceLabelFor: sourceLabelFor,
                    onOpen: (noticeId) => widget.onNavigate?.call(
                      AppNavigationIntent.notices(noticeId: noticeId),
                    ),
                  ),
                ),
              ],
              const SizedBox(height: 16),
              LayoutBuilder(
                builder: (context, sectionConstraints) {
                  final sideBySide = sectionConstraints.maxWidth >= 980;
                  final projectCard = _SectionCard(
                    title: '项目申报检索输出',
                    child: Column(
                      children: data.projectSignalDistribution
                          .map(
                            (item) => Padding(
                              padding: const EdgeInsets.only(bottom: 12),
                              child: _ProjectSignalDistributionRow(
                                item: item,
                                onTap: _navigationAction(
                                  AppNavigationIntent.notices(
                                    query: NoticeQuery(
                                      projectSignal: item.label,
                                    ),
                                  ),
                                ),
                              ),
                            ),
                          )
                          .toList(),
                    ),
                  );

                  final sourceCard = _SectionCard(
                    title: '来源站点分布',
                    child: Column(
                      children: data.sourceDistribution
                          .map(
                            (item) => Padding(
                              padding: const EdgeInsets.only(bottom: 12),
                              child: _SourceDistributionRow(
                                item: item,
                                onTap: _navigationAction(
                                  AppNavigationIntent.notices(
                                    query: NoticeQuery(
                                      sourceSite: item.sourceSite,
                                    ),
                                  ),
                                ),
                              ),
                            ),
                          )
                          .toList(),
                    ),
                  );

                  final summaryCard = _SectionCard(
                    title: '运行摘要',
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '当前看板分别呈现业务优先线索、关键词命中、内容质量与站点覆盖，适合用于每日巡检和任务调度复盘。',
                          style: Theme.of(context).textTheme.bodyMedium,
                        ),
                        const SizedBox(height: 16),
                        const Wrap(
                          spacing: 10,
                          runSpacing: 10,
                          children: [
                            _InfoChip(
                              label: '业务优先',
                              color: Color(0xFFEAF3FF),
                              textColor: Color(0xFF1E4F8A),
                            ),
                            _InfoChip(
                              label: '关键词驱动',
                              color: Color(0xFFE7FBF5),
                              textColor: Color(0xFF117A65),
                            ),
                            _InfoChip(
                              label: '支持持续巡检',
                              color: Color(0xFFFFF4E8),
                              textColor: Color(0xFFC45A1A),
                            ),
                          ],
                        ),
                      ],
                    ),
                  );

                  if (!sideBySide) {
                    return Column(
                      children: [
                        projectCard,
                        const SizedBox(height: 16),
                        sourceCard,
                        const SizedBox(height: 16),
                        summaryCard,
                      ],
                    );
                  }

                  return Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(child: projectCard),
                      const SizedBox(width: 16),
                      Expanded(child: sourceCard),
                      const SizedBox(width: 16),
                      Expanded(child: summaryCard),
                    ],
                  );
                },
              ),
            ],
          ),
        );
      },
    );
  }
}

class _MetricCard extends StatelessWidget {
  final String title;
  final String value;
  final String subtitle;
  final IconData icon;
  final Color accentColor;
  final VoidCallback? onTap;

  const _MetricCard({
    super.key,
    required this.title,
    required this.value,
    required this.subtitle,
    required this.icon,
    required this.accentColor,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      clipBehavior: Clip.antiAlias,
      child: AppInteractiveSurface(
        onTap: onTap,
        semanticLabel: '$title，$value，点击查看',
        child: DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [
                accentColor.withValues(alpha: 0.08),
                Colors.white,
              ],
            ),
          ),
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      width: 42,
                      height: 42,
                      decoration: BoxDecoration(
                        color: accentColor.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(14),
                      ),
                      child: Icon(icon, color: accentColor),
                    ),
                    const Spacer(),
                    Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          '查看',
                          style:
                              Theme.of(context).textTheme.labelMedium?.copyWith(
                                    color: accentColor,
                                    fontWeight: FontWeight.w700,
                                  ),
                        ),
                        const SizedBox(width: 2),
                        Icon(
                          Icons.arrow_forward,
                          size: 16,
                          color: accentColor,
                        ),
                      ],
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                Text(
                  title,
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 10),
                Text(
                  value,
                  style: Theme.of(context).textTheme.displaySmall?.copyWith(
                        color: const Color(0xFF0F223D),
                      ),
                ),
                const SizedBox(height: 8),
                Text(
                  subtitle,
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _SectionCard extends StatelessWidget {
  final String title;
  final Widget child;
  final Widget? action;

  const _SectionCard({
    required this.title,
    required this.child,
    this.action,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    title,
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                ),
                if (action != null) action!,
              ],
            ),
            const SizedBox(height: 16),
            child,
          ],
        ),
      ),
    );
  }
}

class _DashboardPageHero extends StatelessWidget {
  final String? lastUpdatedAt;
  final DashboardRuntimeModel runtime;
  final Future<void> Function()? onRefresh;
  final bool isRefreshing;

  const _DashboardPageHero({
    required this.lastUpdatedAt,
    required this.runtime,
    required this.onRefresh,
    required this.isRefreshing,
  });

  @override
  Widget build(BuildContext context) {
    return AppPageHero(
      title: '首页看板',
      subtitle: '从新增公告、关键词命中、业务优先线索和来源分布，快速掌握今天的采集热度。',
      primaryChips: const [
        AppPageHeroChipData.overlay('实时巡检'),
        AppPageHeroChipData.overlay('模板驱动'),
        AppPageHeroChipData.overlay('任务闭环'),
      ],
      secondaryChips: [
        AppPageHeroChipData.overlay('数据库 · ${runtime.database}'),
        AppPageHeroChipData.overlay('调度器 · ${runtime.scheduler}'),
        AppPageHeroChipData.overlay('定时任务 · ${runtime.scheduledJobs}'),
      ],
      actions: [
        FilledButton.tonalIcon(
          onPressed: onRefresh,
          icon: isRefreshing
              ? const SizedBox.square(
                  dimension: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.refresh),
          label: Text(isRefreshing ? '刷新中...' : '刷新'),
        ),
        AppPill.overlay(
          label: lastUpdatedAt == null || lastUpdatedAt!.isEmpty
              ? '待更新'
              : '更新于 ${DateFormatter.formatDateTime(lastUpdatedAt!)}',
        ),
      ],
    );
  }
}

// ignore: unused_element
class _DashboardHero extends StatelessWidget {
  final String? lastUpdatedAt;
  final DashboardRuntimeModel runtime;
  final Future<void> Function() onRefresh;

  const _DashboardHero({
    required this.lastUpdatedAt,
    required this.runtime,
    required this.onRefresh,
  });

  @override
  Widget build(BuildContext context) {
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
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '首页看板',
                  style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                        color: Colors.white,
                      ),
                ),
                const SizedBox(height: 10),
                Text(
                  '从新增公告、关键词命中、业务优先线索和来源分布，快速掌握今天的采集热度。',
                  style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                        color: const Color(0xE6F3F8FF),
                      ),
                ),
                const SizedBox(height: 16),
                const Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: [
                    _InfoChip(
                      label: '实时巡检',
                      color: Color(0x1AFFFFFF),
                      textColor: Colors.white,
                      borderColor: Color(0x33FFFFFF),
                    ),
                    _InfoChip(
                      label: '模板驱动',
                      color: Color(0x1AFFFFFF),
                      textColor: Colors.white,
                      borderColor: Color(0x33FFFFFF),
                    ),
                    _InfoChip(
                      label: '任务闭环',
                      color: Color(0x1AFFFFFF),
                      textColor: Colors.white,
                      borderColor: Color(0x33FFFFFF),
                    ),
                  ],
                ),
                const SizedBox(height: 14),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    _InfoChip(
                      label: '数据库 · ${runtime.database}',
                      color: const Color(0x24FFFFFF),
                      textColor: Colors.white,
                      borderColor: const Color(0x44FFFFFF),
                    ),
                    _InfoChip(
                      label: '调度器 · ${runtime.scheduler}',
                      color: const Color(0x24FFFFFF),
                      textColor: Colors.white,
                      borderColor: const Color(0x44FFFFFF),
                    ),
                    _InfoChip(
                      label: '定时任务 · ${runtime.scheduledJobs}',
                      color: const Color(0x24FFFFFF),
                      textColor: Colors.white,
                      borderColor: const Color(0x44FFFFFF),
                    ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(width: 16),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              FilledButton.tonalIcon(
                onPressed: onRefresh,
                icon: const Icon(Icons.refresh),
                label: const Text('刷新'),
              ),
              const SizedBox(height: 12),
              _InfoChip(
                label: lastUpdatedAt == null || lastUpdatedAt!.isEmpty
                    ? '待更新'
                    : '更新于 ${DateFormatter.formatDateTime(lastUpdatedAt!)}',
                color: const Color(0x1AFFFFFF),
                textColor: Colors.white,
                borderColor: const Color(0x33FFFFFF),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _NoticeList extends StatelessWidget {
  final List<NoticeListItemModel> notices;
  final String Function(String sourceSite) sourceLabelFor;
  final ValueChanged<int>? onOpen;

  const _NoticeList({
    required this.notices,
    required this.sourceLabelFor,
    required this.onOpen,
  });

  @override
  Widget build(BuildContext context) {
    if (notices.isEmpty) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 8),
        child: Text('暂无业务优先公告。'),
      );
    }

    return Column(
      children: notices.map(
        (item) {
          final sourceLabel = sourceLabelFor(item.sourceSite);
          return Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: AppInteractiveSurface(
              key: Key('dashboard-notice-high-${item.id}'),
              onTap: onOpen == null ? null : () => onOpen!(item.id),
              semanticLabel:
                  '${item.title.isEmpty ? '未命名公告' : item.title}，点击查看公告详情',
              borderRadius: BorderRadius.circular(20),
              child: Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: const Color(0xFFF8FBFF),
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: const Color(0xFFE2EAF4)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(
                          child: Text(
                            item.title.isEmpty ? '未命名公告' : item.title,
                            style: Theme.of(context)
                                .textTheme
                                .titleMedium
                                ?.copyWith(height: 1.3),
                          ),
                        ),
                        const SizedBox(width: 12),
                        _InfoChip(
                          label: item.qualityScore >= 60
                              ? '内容质量 高 · ${item.qualityScore} 分'
                              : '内容待完善 · ${item.qualityScore} 分',
                          color: const Color(0xFFEAF3FF),
                          textColor: const Color(0xFF1E4F8A),
                        ),
                        const SizedBox(width: 8),
                        const Icon(
                          Icons.chevron_right,
                          color: Color(0xFF6B7E95),
                        ),
                      ],
                    ),
                    const SizedBox(height: 10),
                    Text(
                      item.summary.isEmpty ? '暂无摘要。' : item.summary,
                      style: Theme.of(context).textTheme.bodyMedium,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 12),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        _InfoChip(
                          label: sourceLabel,
                          color: const Color(0xFFF0F6FB),
                          textColor: const Color(0xFF2F425B),
                        ),
                        _InfoChip(
                          label: item.isHighPriority ? '业务优先' : '常规',
                          color: item.isHighPriority
                              ? const Color(0xFFFFF2E8)
                              : const Color(0xFFF0F6FB),
                          textColor: item.isHighPriority
                              ? const Color(0xFFC45A1A)
                              : const Color(0xFF2F425B),
                        ),
                        ...item.matchedKeywords.take(3).map(
                              (keyword) => _InfoChip(
                                label: keyword,
                                color: const Color(0xFFE7FBF5),
                                textColor: const Color(0xFF117A65),
                              ),
                            ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          );
        },
      ).toList(),
    );
  }
}

class _RecentNoticeList extends StatelessWidget {
  final List<NoticeListItemModel> items;
  final String Function(String sourceSite) sourceLabelFor;
  final ValueChanged<int>? onOpen;

  const _RecentNoticeList({
    required this.items,
    required this.sourceLabelFor,
    required this.onOpen,
  });

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 8),
        child: Text('暂无最近公告。'),
      );
    }

    return Column(
      children: items.take(5).map(
        (item) {
          final sourceLabel = sourceLabelFor(item.sourceSite);
          return Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: AppInteractiveSurface(
              key: Key('dashboard-notice-recent-${item.id}'),
              onTap: onOpen == null ? null : () => onOpen!(item.id),
              semanticLabel:
                  '${item.title.isEmpty ? '未命名公告' : item.title}，点击查看公告详情',
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      width: 40,
                      height: 40,
                      decoration: BoxDecoration(
                        color: const Color(0xFFEAF3FF),
                        borderRadius: BorderRadius.circular(14),
                      ),
                      child: const Icon(
                        Icons.article_outlined,
                        color: Color(0xFF1E4F8A),
                        size: 20,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            item.title.isEmpty ? '未命名公告' : item.title,
                            style: Theme.of(context).textTheme.titleMedium,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                          const SizedBox(height: 4),
                          Text(
                            sourceLabel == '未知来源'
                                ? '来源未知'
                                : '$sourceLabel · ${DateFormatter.formatShortDate(item.capturedAt)}',
                            style: Theme.of(context).textTheme.bodyMedium,
                          ),
                        ],
                      ),
                    ),
                    const Icon(
                      Icons.chevron_right,
                      color: Color(0xFF6B7E95),
                    ),
                  ],
                ),
              ),
            ),
          );
        },
      ).toList(),
    );
  }
}

class _KeywordHeatGrid extends StatelessWidget {
  final List<KeywordHeatItemModel> items;
  final ValueChanged<String>? onSelect;

  const _KeywordHeatGrid({
    required this.items,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 8),
        child: Text('暂无关键词热度。'),
      );
    }

    return Wrap(
      spacing: 10,
      runSpacing: 10,
      children: items
          .map(
            (item) => AppInteractiveSurface(
              key: Key('dashboard-keyword-${item.keyword}'),
              onTap: onSelect == null ? null : () => onSelect!(item.keyword),
              semanticLabel: '${item.keyword}，${item.count} 次命中，点击筛选公告',
              borderRadius: BorderRadius.circular(18),
              child: Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                decoration: BoxDecoration(
                  color: const Color(0xFFF3F8FF),
                  borderRadius: BorderRadius.circular(18),
                  border: Border.all(color: const Color(0xFFE2EAF4)),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          item.keyword,
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                        const SizedBox(height: 4),
                        Text(
                          '${item.count} 次命中',
                          style: Theme.of(context).textTheme.bodyMedium,
                        ),
                      ],
                    ),
                    const SizedBox(width: 10),
                    const Icon(
                      Icons.arrow_forward,
                      size: 16,
                      color: Color(0xFF6B7E95),
                    ),
                  ],
                ),
              ),
            ),
          )
          .toList(),
    );
  }
}

class _SourceDistributionRow extends StatelessWidget {
  final SourceDistributionItemModel item;
  final VoidCallback? onTap;

  const _SourceDistributionRow({
    required this.item,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final progress = (item.percentage / 100).clamp(0.0, 1.0);
    final sourceLabel = item.displayName.isNotEmpty
        ? item.displayName
        : (item.sourceSite.isEmpty ? '未知来源' : item.sourceSite);

    return AppInteractiveSurface(
      key: Key('dashboard-source-${item.sourceSite}'),
      onTap: onTap,
      semanticLabel: '$sourceLabel，${item.noticeCount} 条公告，点击筛选',
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    sourceLabel,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                Text(
                  '${item.noticeCount} 条',
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              ],
            ),
            const SizedBox(height: 8),
            ClipRRect(
              borderRadius: BorderRadius.circular(999),
              child: LinearProgressIndicator(
                value: progress,
                minHeight: 10,
                backgroundColor: const Color(0xFFE8EEF7),
                valueColor:
                    const AlwaysStoppedAnimation<Color>(Color(0xFF1E4F8A)),
              ),
            ),
            const SizedBox(height: 6),
            Text(
              '${item.percentage.toStringAsFixed(1)}%',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
          ],
        ),
      ),
    );
  }
}

class _ProjectSignalDistributionRow extends StatelessWidget {
  final ProjectSignalItemModel item;
  final VoidCallback? onTap;

  const _ProjectSignalDistributionRow({
    required this.item,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final progress = (item.percentage / 100).clamp(0.0, 1.0);
    final color = switch (item.label) {
      '申报通知' => const Color(0xFF117A65),
      '结果公示' => const Color(0xFF7B4DBB),
      _ => const Color(0xFF566A7F),
    };

    return AppInteractiveSurface(
      key: Key('dashboard-project-${item.label}'),
      onTap: onTap,
      semanticLabel:
          '${item.label.isEmpty ? '其他项目线索' : item.label}，${item.noticeCount} 条公告，点击筛选',
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    item.label.isEmpty ? '其他项目线索' : item.label,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                Text(
                  '${item.noticeCount} 条',
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              ],
            ),
            const SizedBox(height: 8),
            ClipRRect(
              borderRadius: BorderRadius.circular(999),
              child: LinearProgressIndicator(
                value: progress,
                minHeight: 10,
                backgroundColor: const Color(0xFFE8EEF7),
                valueColor: AlwaysStoppedAnimation<Color>(color),
              ),
            ),
            const SizedBox(height: 6),
            Text(
              '${item.percentage.toStringAsFixed(1)}%',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
          ],
        ),
      ),
    );
  }
}

class _InfoChip extends StatelessWidget {
  final String label;
  final Color color;
  final Color textColor;
  final Color? borderColor;

  const _InfoChip({
    required this.label,
    required this.color,
    required this.textColor,
    this.borderColor,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(999),
        border: Border.all(
          color: borderColor ?? color.withValues(alpha: 0.2),
        ),
      ),
      child: Text(
        label,
        style: Theme.of(context).textTheme.labelMedium?.copyWith(
              color: textColor,
              fontWeight: FontWeight.w700,
            ),
      ),
    );
  }
}
