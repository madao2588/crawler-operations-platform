import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../../core/constants/navigation_items.dart';
import '../../core/network/api_client.dart';
import '../../core/widgets/async_error_panel.dart';
import '../../features/dashboard/data/repositories/dashboard_repository.dart';
import '../../features/dashboard/presentation/pages/dashboard_page.dart';
import '../../features/keyword_rules/presentation/pages/keyword_rules_page.dart';
import '../../features/notices/presentation/pages/notices_page.dart';
import '../../features/source_sites/presentation/pages/source_sites_page.dart';
import '../../features/system_management/data/models/task_template_models.dart';
import '../../features/system_management/data/repositories/http_template_repository.dart';
import '../../features/system_management/presentation/pages/system_management_page.dart';
import 'app_navigation_intent.dart';

class AppShell extends StatefulWidget {
  final String userName;
  final Uint8List? avatarBytes;
  final Future<void> Function() onLogout;
  final Future<List<TaskTemplateModel>>? templatesFuture;
  final DashboardRepository? dashboardRepository;

  const AppShell({
    super.key,
    required this.userName,
    required this.avatarBytes,
    required this.onLogout,
    this.templatesFuture,
    this.dashboardRepository,
  });

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  int _selectedIndex = 0;
  TaskTemplateModel? _pendingTemplate;
  late final HttpTemplateRepository _templateRepository;
  late Future<List<TaskTemplateModel>> _templatesFuture;
  NoticeQuery _noticeQuery = const NoticeQuery();
  int? _noticeId;
  SystemManagementTab _systemTab = SystemManagementTab.tasks;
  String? _systemTaskFilter;
  String? _systemLogLevel;
  int? _systemTaskId;
  int _contentVersion = 0;

  @override
  void initState() {
    super.initState();
    _templateRepository = HttpTemplateRepository(apiClient: ApiClient());
    _templatesFuture =
        widget.templatesFuture ?? _templateRepository.fetchTaskTemplates();
  }

  void _openTemplateInTaskManagement(TaskTemplateModel template) {
    setState(() {
      _pendingTemplate = template;
      _selectedIndex = 4;
      _systemTab = SystemManagementTab.tasks;
      _systemTaskFilter = null;
      _systemLogLevel = null;
      _systemTaskId = null;
      _contentVersion += 1;
    });
  }

  void _handleNavigationIntent(AppNavigationIntent intent) {
    setState(() {
      switch (intent.destination) {
        case AppDestination.notices:
          _selectedIndex = 1;
          _noticeQuery = intent.noticeQuery ?? const NoticeQuery();
          _noticeId = intent.noticeId;
        case AppDestination.sourceSites:
          _selectedIndex = 3;
        case AppDestination.systemManagement:
          _selectedIndex = 4;
          _systemTab = intent.systemTab ?? SystemManagementTab.tasks;
          _systemTaskFilter = intent.taskFilter;
          _systemLogLevel = intent.logLevel;
          _systemTaskId = intent.taskId;
      }
      _contentVersion += 1;
    });
  }

  void _selectNavigationIndex(int index) {
    setState(() {
      _selectedIndex = index;
      if (index == 1) {
        _noticeQuery = const NoticeQuery();
        _noticeId = null;
      } else if (index == 4) {
        _systemTab = SystemManagementTab.tasks;
        _systemTaskFilter = null;
        _systemLogLevel = null;
        _systemTaskId = null;
      }
      _contentVersion += 1;
    });
  }

  Future<void> _reloadTemplates() async {
    setState(() {
      _templatesFuture = _templateRepository.fetchTaskTemplates();
    });
    await _templatesFuture;
  }

  void _clearPendingTemplate() {
    setState(() {
      _pendingTemplate = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    final currentItem = navigationItems[_selectedIndex];

    return LayoutBuilder(
      builder: (context, constraints) {
        final isCompact = constraints.maxWidth < 1040;

        return Scaffold(
          backgroundColor: Colors.transparent,
          drawer: isCompact ? _buildDrawer() : null,
          appBar: isCompact
              ? AppBar(
                  title: Text(currentItem.label),
                  backgroundColor: Colors.white.withValues(alpha: 0.9),
                  surfaceTintColor: Colors.transparent,
                  foregroundColor: const Color(0xFF13294B),
                  elevation: 0,
                  actions: [
                    IconButton(
                      onPressed: () {
                        widget.onLogout();
                      },
                      icon: const Icon(Icons.logout),
                      tooltip: '退出登录',
                    ),
                    const SizedBox(width: 4),
                    Padding(
                      padding: const EdgeInsets.only(right: 14),
                      child: CircleAvatar(
                        radius: 16,
                        backgroundColor: const Color(0xFFEAF3FF),
                        backgroundImage: widget.avatarBytes == null
                            ? null
                            : MemoryImage(widget.avatarBytes!),
                        child: widget.avatarBytes == null
                            ? const Icon(
                                Icons.person,
                                size: 16,
                                color: Color(0xFF1E4F8A),
                              )
                            : null,
                      ),
                    ),
                  ],
                )
              : null,
          body: DecoratedBox(
            decoration: const BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [
                  Color(0xFFF6F9FE),
                  Color(0xFFE6EEF9),
                ],
              ),
            ),
            child: Stack(
              children: [
                const Positioned(
                  top: -90,
                  right: -70,
                  child: _AmbientBlob(
                    color: Color(0x1A62A2FF),
                    size: 260,
                  ),
                ),
                const Positioned(
                  bottom: -120,
                  left: -80,
                  child: _AmbientBlob(
                    color: Color(0x1A2ED3B7),
                    size: 300,
                  ),
                ),
                SafeArea(
                  top: !isCompact,
                  child: FutureBuilder<List<TaskTemplateModel>>(
                    future: _templatesFuture,
                    builder: (context, snapshot) {
                      if (snapshot.hasError) {
                        return Center(
                          child: ConstrainedBox(
                            constraints: const BoxConstraints(maxWidth: 520),
                            child: AsyncErrorPanel(
                              error: snapshot.error!,
                              title: '加载任务模板失败',
                              onRetry: () {
                                setState(() {
                                  _templatesFuture =
                                      _templateRepository.fetchTaskTemplates();
                                });
                              },
                            ),
                          ),
                        );
                      }
                      if (snapshot.connectionState == ConnectionState.waiting &&
                          !snapshot.hasData) {
                        return const Center(
                          child: CircularProgressIndicator(),
                        );
                      }
                      final templates =
                          snapshot.data ?? const <TaskTemplateModel>[];
                      return isCompact
                          ? Padding(
                              padding: const EdgeInsets.all(12),
                              child: Column(
                                children: [
                                  _ShellHeader(
                                    title: currentItem.label,
                                    subtitle: _sectionSubtitle(_selectedIndex),
                                    userName: widget.userName,
                                    avatarBytes: widget.avatarBytes,
                                    onLogout: widget.onLogout,
                                    compact: true,
                                  ),
                                  const SizedBox(height: 12),
                                  Expanded(
                                    child: _buildContentFrame(templates),
                                  ),
                                ],
                              ),
                            )
                          : Padding(
                              padding: const EdgeInsets.all(20),
                              child: Row(
                                children: [
                                  _buildSidebar(),
                                  const SizedBox(width: 20),
                                  Expanded(
                                    child: Column(
                                      children: [
                                        _ShellHeader(
                                          title: currentItem.label,
                                          subtitle:
                                              _sectionSubtitle(_selectedIndex),
                                          userName: widget.userName,
                                          avatarBytes: widget.avatarBytes,
                                          onLogout: widget.onLogout,
                                        ),
                                        const SizedBox(height: 18),
                                        Expanded(
                                          child: _buildContentFrame(templates),
                                        ),
                                      ],
                                    ),
                                  ),
                                ],
                              ),
                            );
                    },
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildContentFrame(List<TaskTemplateModel> templates) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xF9FCFEFF),
        borderRadius: BorderRadius.circular(32),
        border: Border.all(
          color: const Color(0xFFE2E9F3),
        ),
        boxShadow: const [
          BoxShadow(
            color: Color(0x1A0E2343),
            blurRadius: 36,
            offset: Offset(0, 18),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(32),
        child: AnimatedSwitcher(
          duration: const Duration(milliseconds: 240),
          child: KeyedSubtree(
            key: ValueKey('$_selectedIndex-$_contentVersion'),
            child: [
              DashboardPage(
                repository: widget.dashboardRepository,
                onNavigate: _handleNavigationIntent,
              ),
              NoticesPage(
                initialQuery: _noticeQuery,
                initialNoticeId: _noticeId,
              ),
              const KeywordRulesPage(),
              SourceSitesPage(
                templates: templates,
                templateRepository: _templateRepository,
                onTemplatesChanged: _reloadTemplates,
                onUseTemplate: _openTemplateInTaskManagement,
              ),
              SystemManagementPage(
                templates: templates,
                templateRepository: _templateRepository,
                onTemplatesChanged: _reloadTemplates,
                pendingTemplate: _pendingTemplate,
                onPendingTemplateHandled: _clearPendingTemplate,
                initialTab: _systemTab,
                initialTaskFilter: _systemTaskFilter,
                initialLogLevel: _systemLogLevel,
                initialTaskId: _systemTaskId,
              ),
            ][_selectedIndex],
          ),
        ),
      ),
    );
  }

  Widget _buildSidebar() {
    return Container(
      width: 296,
      padding: const EdgeInsets.fromLTRB(18, 24, 18, 18),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(30),
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            Color(0xFF183153),
            Color(0xFF0F223D),
          ],
        ),
        boxShadow: const [
          BoxShadow(
            color: Color(0x2412263F),
            blurRadius: 32,
            offset: Offset(0, 20),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(
              color: const Color(0x12FFFFFF),
              borderRadius: BorderRadius.circular(24),
              border: Border.all(color: const Color(0x1EFFFFFF)),
            ),
            child: const Row(
              children: [
                _BrandMark(),
                SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '制药招标监测系统',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 18,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      SizedBox(height: 4),
                      Text(
                        '采集运营控制台',
                        style: TextStyle(
                          color: Color(0xFFAEBDD5),
                          fontSize: 12,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            decoration: BoxDecoration(
              color: const Color(0x14FFFFFF),
              borderRadius: BorderRadius.circular(20),
              border: Border.all(color: const Color(0x18FFFFFF)),
            ),
            child: const Row(
              children: [
                Icon(Icons.bolt_outlined, color: Color(0xFF8AE0CF), size: 18),
                SizedBox(width: 10),
                Expanded(
                  child: Text(
                    '采集、解析、入库、模板协作统一调度',
                    style: TextStyle(
                      color: Color(0xFFE7EEF8),
                      fontSize: 12,
                      height: 1.35,
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 20),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 10),
            child: Text(
              '工作区',
              style: TextStyle(
                color: Color(0xFF9BB0CD),
                fontSize: 12,
                letterSpacing: 1.2,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          const SizedBox(height: 8),
          Expanded(
            child: NavigationRail(
              extended: true,
              selectedIndex: _selectedIndex,
              minExtendedWidth: 240,
              groupAlignment: -0.95,
              labelType: NavigationRailLabelType.none,
              onDestinationSelected: _selectNavigationIndex,
              destinations: navigationItems
                  .map(
                    (item) => NavigationRailDestination(
                      icon: Icon(item.icon),
                      label: Text(item.label),
                    ),
                  )
                  .toList(),
            ),
          ),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: const Color(0x12FFFFFF),
              borderRadius: BorderRadius.circular(24),
              border: Border.all(color: const Color(0x1EFFFFFF)),
            ),
            child: const Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(Icons.insights_outlined,
                        color: Color(0xFF8AE0CF), size: 18),
                    SizedBox(width: 8),
                    Text(
                      '设计升级 · 第一步',
                      style: TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                ),
                SizedBox(height: 8),
                Text(
                  '先统一视觉基础、导航秩序和信息层级，再逐页打磨仪表盘与运营页面。',
                  style: TextStyle(
                    color: Color(0xFFB3C1D8),
                    height: 1.5,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDrawer() {
    return Drawer(
      child: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [
                    Color(0xFF183153),
                    Color(0xFF0F223D),
                  ],
                ),
                borderRadius: BorderRadius.circular(24),
              ),
              child: Row(
                children: [
                  CircleAvatar(
                    radius: 22,
                    backgroundColor: const Color(0xFFEAF3FF),
                    backgroundImage: widget.avatarBytes == null
                        ? null
                        : MemoryImage(widget.avatarBytes!),
                    child: widget.avatarBytes == null
                        ? const Icon(
                            Icons.person,
                            color: Color(0xFF1E4F8A),
                          )
                        : null,
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          widget.userName,
                          style:
                              Theme.of(context).textTheme.titleMedium?.copyWith(
                                    color: Colors.white,
                                  ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          '当前登录',
                          style:
                              Theme.of(context).textTheme.bodySmall?.copyWith(
                                    color: const Color(0xFFB3C1D8),
                                  ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            ...navigationItems.asMap().entries.map(
              (entry) {
                final index = entry.key;
                final item = entry.value;
                return Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: ListTile(
                    selected: index == _selectedIndex,
                    selectedTileColor: const Color(0xFFEAF3FF),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(16),
                    ),
                    leading: Icon(item.icon),
                    title: Text(item.label),
                    onTap: () {
                      _selectNavigationIndex(index);
                      Navigator.of(context).pop();
                    },
                  ),
                );
              },
            ),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              onPressed: () {
                widget.onLogout();
              },
              icon: const Icon(Icons.logout),
              label: const Text('退出登录'),
            ),
          ],
        ),
      ),
    );
  }

  String _sectionSubtitle(int index) {
    return switch (index) {
      0 => '聚焦核心指标、来源分布与今日动态，先看到系统整体运行面貌。',
      1 => '把采集结果组织成可浏览的信息流，便于快速筛查业务优先公告。',
      2 => '沉淀触发条件与命中逻辑，让规则配置更清晰、更可维护。',
      3 => '用模板管理常见站点与采集蓝图，降低新任务配置门槛。',
      _ => '在一个控制台里完成任务调度、运行诊断、日志排障与模板协作。',
    };
  }
}

class _AmbientBlob extends StatelessWidget {
  final Color color;
  final double size;

  const _AmbientBlob({
    required this.color,
    required this.size,
  });

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: RadialGradient(
            colors: [color, color.withValues(alpha: 0.0)],
          ),
        ),
      ),
    );
  }
}

class _ShellHeader extends StatelessWidget {
  final String title;
  final String subtitle;
  final String userName;
  final Uint8List? avatarBytes;
  final VoidCallback onLogout;
  final bool compact;

  const _ShellHeader({
    required this.title,
    required this.subtitle,
    required this.userName,
    required this.avatarBytes,
    required this.onLogout,
    this.compact = false,
  });

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final isCompact = compact || constraints.maxWidth < 920;

        return Container(
          width: double.infinity,
          padding: EdgeInsets.symmetric(
            horizontal: isCompact ? 18 : 24,
            vertical: isCompact ? 18 : 22,
          ),
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.82),
            borderRadius: BorderRadius.circular(28),
            border: Border.all(color: const Color(0xFFE1E9F4)),
          ),
          child: isCompact
              ? Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: Theme.of(context).textTheme.headlineMedium,
                    ),
                    const SizedBox(height: 8),
                    Text(
                      subtitle,
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                    const SizedBox(height: 12),
                    Wrap(
                      spacing: 12,
                      runSpacing: 12,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: [
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 14,
                            vertical: 12,
                          ),
                          decoration: BoxDecoration(
                            color: const Color(0xFFF2F6FC),
                            borderRadius: BorderRadius.circular(18),
                          ),
                          child: const Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(
                                Icons.auto_awesome_outlined,
                                size: 18,
                                color: Color(0xFF1F4B99),
                              ),
                              SizedBox(width: 8),
                              Text(
                                '界面升级中',
                                style: TextStyle(
                                  color: Color(0xFF1D3557),
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ],
                          ),
                        ),
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 14,
                            vertical: 10,
                          ),
                          decoration: BoxDecoration(
                            color: Colors.white,
                            borderRadius: BorderRadius.circular(18),
                            border: Border.all(color: const Color(0xFFE1E9F4)),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              CircleAvatar(
                                radius: 16,
                                backgroundColor: const Color(0xFFEAF3FF),
                                backgroundImage: avatarBytes == null
                                    ? null
                                    : MemoryImage(avatarBytes!),
                                child: avatarBytes == null
                                    ? const Icon(
                                        Icons.person,
                                        size: 16,
                                        color: Color(0xFF1E4F8A),
                                      )
                                    : null,
                              ),
                              const SizedBox(width: 10),
                              Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Text(
                                    userName,
                                    style: Theme.of(context)
                                        .textTheme
                                        .labelLarge
                                        ?.copyWith(
                                          color: const Color(0xFF1D3557),
                                        ),
                                  ),
                                  Text(
                                    '当前登录',
                                    style:
                                        Theme.of(context).textTheme.bodySmall,
                                  ),
                                ],
                              ),
                            ],
                          ),
                        ),
                        TextButton.icon(
                          onPressed: onLogout,
                          icon: const Icon(Icons.logout, size: 18),
                          label: const Text('退出登录'),
                        ),
                      ],
                    ),
                  ],
                )
              : Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            title,
                            style: Theme.of(context).textTheme.headlineMedium,
                          ),
                          const SizedBox(height: 8),
                          Text(
                            subtitle,
                            style: Theme.of(context).textTheme.bodyMedium,
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 16),
                    Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 14,
                            vertical: 12,
                          ),
                          decoration: BoxDecoration(
                            color: const Color(0xFFF2F6FC),
                            borderRadius: BorderRadius.circular(18),
                          ),
                          child: const Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(
                                Icons.auto_awesome_outlined,
                                size: 18,
                                color: Color(0xFF1F4B99),
                              ),
                              SizedBox(width: 8),
                              Text(
                                '界面升级中',
                                style: TextStyle(
                                  color: Color(0xFF1D3557),
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(width: 12),
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 14,
                            vertical: 10,
                          ),
                          decoration: BoxDecoration(
                            color: Colors.white,
                            borderRadius: BorderRadius.circular(18),
                            border: Border.all(color: const Color(0xFFE1E9F4)),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              CircleAvatar(
                                radius: 16,
                                backgroundColor: const Color(0xFFEAF3FF),
                                backgroundImage: avatarBytes == null
                                    ? null
                                    : MemoryImage(avatarBytes!),
                                child: avatarBytes == null
                                    ? const Icon(
                                        Icons.person,
                                        size: 16,
                                        color: Color(0xFF1E4F8A),
                                      )
                                    : null,
                              ),
                              const SizedBox(width: 10),
                              Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Text(
                                    userName,
                                    style: Theme.of(context)
                                        .textTheme
                                        .labelLarge
                                        ?.copyWith(
                                          color: const Color(0xFF1D3557),
                                        ),
                                  ),
                                  Text(
                                    '当前登录',
                                    style:
                                        Theme.of(context).textTheme.bodySmall,
                                  ),
                                ],
                              ),
                              const SizedBox(width: 12),
                              TextButton.icon(
                                onPressed: onLogout,
                                icon: const Icon(Icons.logout, size: 18),
                                label: const Text('退出登录'),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
        );
      },
    );
  }
}

class _BrandMark extends StatelessWidget {
  const _BrandMark();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 48,
      height: 48,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            Color(0xFF6AA6FF),
            Color(0xFF2ED3B7),
          ],
        ),
      ),
      child: const Icon(
        Icons.monitor_heart_outlined,
        color: Colors.white,
      ),
    );
  }
}
