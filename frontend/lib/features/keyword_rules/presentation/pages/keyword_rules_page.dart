import 'package:flutter/material.dart';

import '../../../../core/utils/user_facing_error.dart';
import '../../../../core/widgets/async_error_panel.dart';
import '../../../../core/widgets/page_chrome.dart';
import '../../../../shared/models/page_data.dart';
import '../../data/models/keyword_rule_model.dart';
import '../../data/repositories/http_keyword_rule_repository.dart';

enum _RuleFilter {
  all,
  enabled,
  highPriority,
}

class KeywordRulesPage extends StatefulWidget {
  final HttpKeywordRuleRepository? repository;

  const KeywordRulesPage({
    super.key,
    this.repository,
  });

  @override
  State<KeywordRulesPage> createState() => _KeywordRulesPageState();
}

class _KeywordRulesPageState extends State<KeywordRulesPage> {
  late final HttpKeywordRuleRepository _repository;
  final ScrollController _pageScrollController = ScrollController();
  late Future<PageData<KeywordRuleModel>> _rulesFuture;
  _RuleFilter _filter = _RuleFilter.all;
  final Set<int> _updatingRuleIds = {};

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? HttpKeywordRuleRepository();
    _refresh();
  }

  @override
  void dispose() {
    _pageScrollController.dispose();
    super.dispose();
  }

  void _refresh() {
    setState(() {
      _rulesFuture = _repository.getKeywordRules();
    });
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<PageData<KeywordRuleModel>>(
      future: _rulesFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(child: CircularProgressIndicator());
        } else if (snapshot.hasError) {
          return Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 520),
              child: AsyncErrorPanel(
                error: snapshot.error!,
                title: '加载关键字规则失败',
                onRetry: _refresh,
              ),
            ),
          );
        }

        final rules = snapshot.data?.items ?? [];
        final total = snapshot.data?.total ?? 0;
        final enabledCount = rules.where((r) => r.isActive).length;
        final highPriorityCount = rules.where((r) => r.isHighPriority).length;
        final visibleRules = switch (_filter) {
          _RuleFilter.all => rules,
          _RuleFilter.enabled => rules.where((r) => r.isActive).toList(),
          _RuleFilter.highPriority =>
            rules.where((r) => r.isHighPriority).toList(),
        };

        final cards = [
          _RuleMetricCard(
            key: const Key('keyword-rule-filter-all'),
            title: '规则总数',
            value: '$total',
            icon: Icons.rule_outlined,
            accentColor: const Color(0xFF1E4F8A),
            selected: _filter == _RuleFilter.all,
            onTap: () => _setFilter(_RuleFilter.all),
          ),
          _RuleMetricCard(
            key: const Key('keyword-rule-filter-enabled'),
            title: '已启用',
            value: '$enabledCount',
            icon: Icons.toggle_on_outlined,
            accentColor: const Color(0xFF117A65),
            selected: _filter == _RuleFilter.enabled,
            onTap: () => _setFilter(_RuleFilter.enabled),
          ),
          _RuleMetricCard(
            key: const Key('keyword-rule-filter-highPriority'),
            title: '业务优先规则',
            value: '$highPriorityCount',
            icon: Icons.flag_outlined,
            accentColor: const Color(0xFFC45A1A),
            selected: _filter == _RuleFilter.highPriority,
            onTap: () => _setFilter(_RuleFilter.highPriority),
          ),
        ];

        return AppPageFrame(
          child: LayoutBuilder(
            builder: (context, constraints) {
              final cardWidth = constraints.maxWidth >= 1200
                  ? (constraints.maxWidth - 32) / 3
                  : constraints.maxWidth >= 760
                      ? (constraints.maxWidth - 16) / 2
                      : constraints.maxWidth;

              return Scrollbar(
                controller: _pageScrollController,
                thumbVisibility: true,
                child: ListView(
                  controller: _pageScrollController,
                  children: [
                    _KeywordRulesPageHero(
                      total: total,
                      enabledCount: enabledCount,
                      highPriorityCount: highPriorityCount,
                      onCreateRule: () => _showRuleDialog(context),
                      onRefresh: _refresh,
                    ),
                    const SizedBox(height: 16),
                    Wrap(
                      spacing: 16,
                      runSpacing: 16,
                      children: cards
                          .map(
                              (card) => SizedBox(width: cardWidth, child: card))
                          .toList(),
                    ),
                    const SizedBox(height: 16),
                    _SectionCard(
                      title: '关键字规则列表',
                      child: Container(
                        width: double.infinity,
                        decoration: BoxDecoration(
                          color: Colors.white,
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(
                              color: Colors.grey.withValues(alpha: 0.2)),
                        ),
                        child: SingleChildScrollView(
                          scrollDirection: Axis.horizontal,
                          child: DataTable(
                            columns: const [
                              DataColumn(label: Text('关键词')),
                              DataColumn(label: Text('高优标注')),
                              DataColumn(label: Text('启用状态')),
                              DataColumn(label: Text('操作')),
                            ],
                            rows: visibleRules.map((r) {
                              final updating = _updatingRuleIds.contains(r.id);
                              return DataRow(
                                  mouseCursor: WidgetStatePropertyAll(
                                    updating
                                        ? SystemMouseCursors.basic
                                        : SystemMouseCursors.click,
                                  ),
                                  onSelectChanged: updating
                                      ? null
                                      : (_) =>
                                          _showRuleDialog(context, rule: r),
                                  cells: [
                                    DataCell(
                                      Row(
                                        mainAxisSize: MainAxisSize.min,
                                        children: [
                                          Text(
                                            r.word,
                                            style: const TextStyle(
                                              fontWeight: FontWeight.bold,
                                              color: Color(0xFF1E4F8A),
                                            ),
                                          ),
                                          if (r.isDefault) ...[
                                            const SizedBox(width: 8),
                                            Container(
                                              padding:
                                                  const EdgeInsets.symmetric(
                                                horizontal: 8,
                                                vertical: 4,
                                              ),
                                              decoration: BoxDecoration(
                                                color: const Color(0xFFEDF5FF),
                                                borderRadius:
                                                    BorderRadius.circular(999),
                                              ),
                                              child: const Text(
                                                '系统默认',
                                                style: TextStyle(
                                                  color: Color(0xFF315F91),
                                                  fontSize: 11,
                                                  fontWeight: FontWeight.w700,
                                                ),
                                              ),
                                            ),
                                          ],
                                        ],
                                      ),
                                    ),
                                    DataCell(
                                      Switch(
                                        key: Key(
                                          'keyword-rule-priority-switch-${r.id}',
                                        ),
                                        value: r.isHighPriority,
                                        onChanged: updating
                                            ? null
                                            : (v) => _toggleHighPriority(
                                                  context,
                                                  r,
                                                  v,
                                                ),
                                      ),
                                    ),
                                    DataCell(
                                      Switch(
                                        key: Key(
                                          'keyword-rule-active-switch-${r.id}',
                                        ),
                                        value: r.isActive,
                                        activeThumbColor:
                                            const Color(0xFF117A65),
                                        onChanged: updating
                                            ? null
                                            : (_) => _toggleActive(context, r),
                                      ),
                                    ),
                                    DataCell(
                                      Row(
                                        mainAxisSize: MainAxisSize.min,
                                        children: [
                                          if (updating) ...[
                                            SizedBox.square(
                                              key: Key(
                                                'keyword-rule-progress-${r.id}',
                                              ),
                                              dimension: 24,
                                              child:
                                                  const CircularProgressIndicator(
                                                strokeWidth: 2,
                                              ),
                                            ),
                                            const SizedBox(width: 8),
                                          ],
                                          IconButton(
                                            icon: const Icon(
                                                Icons.edit_outlined,
                                                size: 20),
                                            tooltip: '编辑',
                                            onPressed: updating
                                                ? null
                                                : () => _showRuleDialog(
                                                      context,
                                                      rule: r,
                                                    ),
                                          ),
                                          if (!r.isDefault)
                                            IconButton(
                                              icon: const Icon(
                                                  Icons.delete_outline,
                                                  size: 20,
                                                  color: Colors.red),
                                              tooltip: '删除',
                                              onPressed: updating
                                                  ? null
                                                  : () =>
                                                      _deleteRule(context, r),
                                            ),
                                        ],
                                      ),
                                    ),
                                  ]);
                            }).toList(),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              );
            },
          ),
        );
      },
    );
  }

  void _setFilter(_RuleFilter filter) {
    if (_filter == filter) return;
    setState(() {
      _filter = filter;
    });
  }

  void _showRuleDialog(BuildContext context, {KeywordRuleModel? rule}) {
    var word = rule?.word ?? '';
    var isHighPriority = rule?.isHighPriority ?? false;
    var isActive = rule?.isActive ?? true;
    var saving = false;
    String? saveError;

    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) {
        return StatefulBuilder(
          builder: (dialogContext, setDialogState) {
            return PopScope(
              canPop: !saving,
              child: AlertDialog(
                title: Text(rule == null ? '新建关键字' : '编辑关键字'),
                content: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    TextFormField(
                      initialValue: word,
                      enabled: !saving && !(rule?.isDefault ?? false),
                      decoration: const InputDecoration(labelText: '关键词'),
                      onChanged: (v) => word = v,
                    ),
                    if (rule?.isDefault ?? false) ...[
                      const SizedBox(height: 8),
                      const Align(
                        alignment: Alignment.centerLeft,
                        child: Text(
                          '默认词不能改名或删除，可调整优先级和启用状态。',
                          style: TextStyle(
                            color: Color(0xFF52657F),
                            fontSize: 12,
                          ),
                        ),
                      ),
                    ],
                    const SizedBox(height: 16),
                    SwitchListTile(
                      title: const Text('高优标注'),
                      value: isHighPriority,
                      onChanged: saving
                          ? null
                          : (v) => setDialogState(() => isHighPriority = v),
                    ),
                    SwitchListTile(
                      title: const Text('启用状态'),
                      value: isActive,
                      onChanged: saving
                          ? null
                          : (v) => setDialogState(() => isActive = v),
                    ),
                    if (saveError != null) ...[
                      const SizedBox(height: 8),
                      Text(
                        '保存失败：$saveError',
                        style: const TextStyle(color: Color(0xFFB3261E)),
                      ),
                    ],
                  ],
                ),
                actions: [
                  TextButton(
                    onPressed:
                        saving ? null : () => Navigator.pop(dialogContext),
                    child: const Text('取消'),
                  ),
                  FilledButton(
                    key: const Key('keyword-rule-dialog-save'),
                    onPressed: saving
                        ? null
                        : () async {
                            if (saving || word.trim().isEmpty) return;
                            setDialogState(() {
                              saving = true;
                              saveError = null;
                            });
                            final newRule = KeywordRuleModel(
                              id: rule?.id ?? 0,
                              word: word.trim(),
                              isHighPriority: isHighPriority,
                              isActive: isActive,
                              isDefault: rule?.isDefault ?? false,
                              createdAt: '',
                              updatedAt: '',
                            );

                            try {
                              if (rule == null) {
                                await _repository.createKeywordRule(newRule);
                              } else {
                                await _repository.updateKeywordRule(newRule);
                              }
                              if (!dialogContext.mounted) return;
                              Navigator.pop(dialogContext);
                              _refresh();
                              if (!context.mounted) return;
                              ScaffoldMessenger.of(context).showSnackBar(
                                SnackBar(
                                  content: Text(
                                    rule == null ? '关键字已创建。' : '关键字已更新。',
                                  ),
                                ),
                              );
                            } catch (error) {
                              if (!dialogContext.mounted) return;
                              setDialogState(() {
                                saveError = userFacingError(error);
                              });
                            } finally {
                              if (dialogContext.mounted) {
                                setDialogState(() {
                                  saving = false;
                                });
                              }
                            }
                          },
                    child: saving
                        ? const Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              SizedBox.square(
                                dimension: 18,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              ),
                              SizedBox(width: 8),
                              Text('保存中'),
                            ],
                          )
                        : const Text('保存'),
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }

  Future<void> _toggleHighPriority(
      BuildContext context, KeywordRuleModel rule, bool newValue) async {
    if (_updatingRuleIds.contains(rule.id)) return;
    _setRuleUpdating(rule.id, true);
    try {
      final updated = KeywordRuleModel(
        id: rule.id,
        word: rule.word,
        isHighPriority: newValue,
        isActive: rule.isActive,
        isDefault: rule.isDefault,
        createdAt: '',
        updatedAt: '',
      );
      await _repository.updateKeywordRule(updated);
      _refresh();
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('“${rule.word}”优先级已更新。')),
      );
    } catch (e) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('更新失败：${userFacingError(e)}')),
      );
    } finally {
      _setRuleUpdating(rule.id, false);
    }
  }

  Future<void> _toggleActive(
      BuildContext context, KeywordRuleModel rule) async {
    if (_updatingRuleIds.contains(rule.id)) return;
    _setRuleUpdating(rule.id, true);
    try {
      await _repository.toggleKeywordRuleActive(rule.id);
      _refresh();
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('“${rule.word}”状态已更新。')),
      );
    } catch (e) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('操作失败：${userFacingError(e)}')),
      );
    } finally {
      _setRuleUpdating(rule.id, false);
    }
  }

  void _setRuleUpdating(int id, bool updating) {
    if (!mounted) return;
    setState(() {
      if (updating) {
        _updatingRuleIds.add(id);
      } else {
        _updatingRuleIds.remove(id);
      }
    });
  }

  Future<void> _deleteRule(BuildContext context, KeywordRuleModel rule) async {
    if (rule.isDefault || _updatingRuleIds.contains(rule.id)) return;
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('确认删除'),
        content: Text('确定要删除关键字 "${rule.word}" 吗？此操作不可恢复。'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('取消')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Colors.red),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('删除'),
          ),
        ],
      ),
    );
    if (confirm != true) return;

    _setRuleUpdating(rule.id, true);
    try {
      await _repository.deleteKeywordRule(rule.id);
      _refresh();
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('“${rule.word}”已删除。')),
      );
    } catch (e) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('删除失败：${userFacingError(e)}')),
      );
    } finally {
      _setRuleUpdating(rule.id, false);
    }
  }
}

class _KeywordRulesPageHero extends StatelessWidget {
  final int total;
  final int enabledCount;
  final int highPriorityCount;
  final VoidCallback? onCreateRule;
  final VoidCallback onRefresh;

  const _KeywordRulesPageHero({
    required this.total,
    required this.enabledCount,
    required this.highPriorityCount,
    required this.onCreateRule,
    required this.onRefresh,
  });

  @override
  Widget build(BuildContext context) {
    return AppPageHero(
      title: '关键词规则',
      subtitle: '统一维护业务优先词和启用状态，保存后立即参与公告筛选与标记。',
      primaryChips: const [
        AppPageHeroChipData.overlay('实时生效'),
        AppPageHeroChipData.overlay('高优标记'),
        AppPageHeroChipData.overlay('支持启停'),
      ],
      secondaryChips: [
        AppPageHeroChipData.overlay('规则总数 · $total'),
        AppPageHeroChipData.overlay('已启用 · $enabledCount'),
        AppPageHeroChipData.overlay('业务优先 · $highPriorityCount'),
      ],
      actions: [
        FilledButton.tonalIcon(
          onPressed: onCreateRule,
          icon: const Icon(Icons.add),
          label: const Text('新建规则'),
        ),
        FilledButton.tonalIcon(
          onPressed: onRefresh,
          icon: const Icon(Icons.refresh),
          label: const Text('刷新'),
        ),
      ],
    );
  }
}

// ignore: unused_element
class _KeywordRulesHero extends StatelessWidget {
  final VoidCallback? onCreateRule;

  const _KeywordRulesHero({required this.onCreateRule});

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
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF1D4E89).withValues(alpha: 0.15),
            blurRadius: 30,
            offset: const Offset(0, 16),
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
                  '关键词规则',
                  style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                        color: Colors.white,
                      ),
                ),
                const SizedBox(height: 10),
                Text(
                  '支持动态配置业务优先关键词及启用状态，更新后即刻生效；内容质量由抓取完整度单独计算。',
                  style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                        color: const Color(0xE6F3F8FF),
                      ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 16),
          FilledButton.tonalIcon(
            onPressed: onCreateRule,
            icon: const Icon(Icons.add),
            label: const Text('新建规则'),
          ),
        ],
      ),
    );
  }
}

class _RuleMetricCard extends StatelessWidget {
  final String title;
  final String value;
  final IconData icon;
  final Color accentColor;
  final bool selected;
  final VoidCallback onTap;

  const _RuleMetricCard({
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
    const radius = BorderRadius.all(Radius.circular(12));
    return Semantics(
      button: true,
      selected: selected,
      label: '$title，$value 条，点击筛选',
      child: MouseRegion(
        cursor: SystemMouseCursors.click,
        child: Card(
          clipBehavior: Clip.antiAlias,
          child: InkWell(
            borderRadius: radius,
            onTap: onTap,
            focusColor: accentColor.withValues(alpha: 0.12),
            hoverColor: accentColor.withValues(alpha: 0.07),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 180),
              curve: Curves.easeOut,
              constraints: const BoxConstraints(minHeight: 148),
              decoration: BoxDecoration(
                borderRadius: radius,
                border: Border.all(
                  color: selected
                      ? accentColor.withValues(alpha: 0.7)
                      : Colors.transparent,
                  width: 2,
                ),
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [
                    accentColor.withValues(alpha: selected ? 0.11 : 0.05),
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
                          width: 44,
                          height: 44,
                          decoration: BoxDecoration(
                            color: accentColor.withValues(alpha: 0.12),
                            borderRadius: BorderRadius.circular(14),
                          ),
                          child: Icon(icon, color: accentColor),
                        ),
                        const Spacer(),
                        AnimatedContainer(
                          duration: const Duration(milliseconds: 180),
                          padding: const EdgeInsets.symmetric(
                            horizontal: 10,
                            vertical: 6,
                          ),
                          decoration: BoxDecoration(
                            color: selected
                                ? accentColor.withValues(alpha: 0.12)
                                : const Color(0xFFF2F6FC),
                            borderRadius: BorderRadius.circular(999),
                          ),
                          child: Text(
                            selected ? '当前筛选' : '点击筛选',
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
                    Text(title, style: Theme.of(context).textTheme.titleMedium),
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

class _SectionCard extends StatelessWidget {
  final String title;
  final Widget child;

  const _SectionCard({required this.title, required this.child});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 16),
            child,
          ],
        ),
      ),
    );
  }
}
