import 'dart:convert';

import 'package:flutter/material.dart';

import '../../system_management/data/models/task_models.dart';
import '../../system_management/data/models/task_template_models.dart';

const manualSourceIds = {
  'wechat_k_innovation',
  'wechat_hengqin_biomed',
  'wechat_competitor_intelligence',
};

const authorizationTemplateIds = {
  'pharnexcloud_drug_database',
};

class TemplateCollectionStatus {
  final String label;
  final String note;
  final IconData icon;
  final Color foregroundColor;
  final Color backgroundColor;
  final Color borderColor;

  const TemplateCollectionStatus({
    required this.label,
    required this.note,
    required this.icon,
    required this.foregroundColor,
    required this.backgroundColor,
    required this.borderColor,
  });
}

class SourceSiteRuntimeStatus {
  final String label;
  final String note;
  final String? latestLog;
  final bool canRetry;
  final IconData icon;
  final Color foregroundColor;
  final Color backgroundColor;
  final Color borderColor;

  const SourceSiteRuntimeStatus({
    required this.label,
    required this.note,
    required this.latestLog,
    required this.canRetry,
    required this.icon,
    required this.foregroundColor,
    required this.backgroundColor,
    required this.borderColor,
  });
}

Map<String, dynamic>? tryParseTemplateRules(String? parserRules) {
  final raw = parserRules?.trim();
  if (raw == null || raw.isEmpty) {
    return null;
  }
  try {
    final decoded = jsonDecode(raw);
    if (decoded is Map<String, dynamic>) {
      return decoded;
    }
    if (decoded is Map) {
      return Map<String, dynamic>.from(decoded);
    }
  } catch (_) {
    return null;
  }
  return null;
}

TemplateCollectionStatus resolveTemplateCollectionStatus(
  TaskTemplateModel template,
) {
  final parsedRules = tryParseTemplateRules(template.parserRules);
  final collectionMode =
      parsedRules?['collection_mode']?.toString().trim().toLowerCase();
  final description = template.description.toLowerCase();
  final needsAuthorization = authorizationTemplateIds.contains(template.id) ||
      description.contains('授权');

  if (collectionMode == 'blocked') {
    return const TemplateCollectionStatus(
      label: '访问受阻',
      note: '来源当前触发验证码或访问控制，自动任务已停用。',
      icon: Icons.shield_outlined,
      foregroundColor: Color(0xFF9B2C2C),
      backgroundColor: Color(0xFFFDE8E8),
      borderColor: Color(0xFFE9AAAA),
    );
  }

  if (collectionMode == 'intermittent') {
    return const TemplateCollectionStatus(
      label: '受限采集',
      note: '已配置自动采集，但来源可能间歇触发验证码并导致任务失败。',
      icon: Icons.sync_problem_outlined,
      foregroundColor: Color(0xFF8A4B08),
      backgroundColor: Color(0xFFFFF0DD),
      borderColor: Color(0xFFE8BF87),
    );
  }

  if (collectionMode == 'stale') {
    return const TemplateCollectionStatus(
      label: '已暂停',
      note: '解析规则已保留，但官方列表长期未更新，暂不自动运行。',
      icon: Icons.pause_circle_outline,
      foregroundColor: Color(0xFF6B5B12),
      backgroundColor: Color(0xFFFFF8D9),
      borderColor: Color(0xFFE8D88E),
    );
  }

  if (manualSourceIds.contains(template.id) || collectionMode == 'manual') {
    return const TemplateCollectionStatus(
      label: '人工登记',
      note: '当前不做自动抓取，只支持人工登记文章链接。',
      icon: Icons.edit_note_outlined,
      foregroundColor: Color(0xFF9A6700),
      backgroundColor: Color(0xFFFFF6D8),
      borderColor: Color(0xFFF0D999),
    );
  }

  if (needsAuthorization) {
    return const TemplateCollectionStatus(
      label: '需授权',
      note: '该来源依赖账号或平台授权，当前仅保留入口信息。',
      icon: Icons.lock_outline,
      foregroundColor: Color(0xFF7A4D12),
      backgroundColor: Color(0xFFFCEBD8),
      borderColor: Color(0xFFE9C89F),
    );
  }

  if (template.parserRules?.trim().isNotEmpty == true) {
    return const TemplateCollectionStatus(
      label: '自动采集',
      note: '已配置解析规则，可按定时任务自动采集。',
      icon: Icons.auto_awesome_outlined,
      foregroundColor: Color(0xFF0B6B58),
      backgroundColor: Color(0xFFE0F4ED),
      borderColor: Color(0xFF9FD9C5),
    );
  }

  return const TemplateCollectionStatus(
    label: '未实现',
    note: '当前仅登记来源信息，尚未配置解析规则或采集流程。',
    icon: Icons.pending_outlined,
    foregroundColor: Color(0xFF556A86),
    backgroundColor: Color(0xFFF3F6FA),
    borderColor: Color(0xFFD7E1EC),
  );
}

SourceSiteRuntimeStatus resolveSourceSiteRuntimeStatus({
  required TaskTemplateModel template,
  TaskListItemModel? task,
  TaskLogItemModel? latestLog,
  TaskLogItemModel? latestSummaryLog,
}) {
  final collectionStatus = resolveTemplateCollectionStatus(template);
  if (collectionStatus.label == '人工登记' || collectionStatus.label == '已暂停') {
    return SourceSiteRuntimeStatus(
      label: collectionStatus.label,
      note: collectionStatus.note,
      latestLog: null,
      canRetry: false,
      icon: collectionStatus.icon,
      foregroundColor: collectionStatus.foregroundColor,
      backgroundColor: collectionStatus.backgroundColor,
      borderColor: collectionStatus.borderColor,
    );
  }

  if (task == null) {
    return SourceSiteRuntimeStatus(
      label: collectionStatus.label,
      note: '尚未找到对应任务，当前先展示模板配置状态。',
      latestLog: null,
      canRetry: false,
      icon: collectionStatus.icon,
      foregroundColor: collectionStatus.foregroundColor,
      backgroundColor: collectionStatus.backgroundColor,
      borderColor: collectionStatus.borderColor,
    );
  }

  final status = (task.lastRunStatus ?? '').trim().toLowerCase();
  if (status == 'partial') {
    final summaryText = _buildSummaryText(latestSummaryLog);
    return const SourceSiteRuntimeStatus(
      label: '部分失败',
      note: '',
      latestLog: null,
      canRetry: true,
      icon: Icons.warning_amber_rounded,
      foregroundColor: Color(0xFF8A4B00),
      backgroundColor: Color(0xFFFFF4E5),
      borderColor: Color(0xFFE8BF87),
    ).copyWith(
      note: summaryText == null
          ? '最近一次运行有部分详情失败，建议查看摘要后重试。'
          : '最近一次运行已$summaryText，建议处理失败项后重试。',
      latestLog: summaryText == null ? null : '运行摘要：$summaryText',
    );
  }

  if (status == 'failed') {
    final failureText = _latestFailureText(task, latestLog);
    if (_looksLikeConnectionFailure(failureText)) {
      return SourceSiteRuntimeStatus(
        label: '连接失败',
        note: '最近一次抓取未连通源站或请求超时，建议检查网络、证书或访问限制后重试。',
        latestLog: failureText,
        canRetry: true,
        icon: Icons.wifi_off_rounded,
        foregroundColor: const Color(0xFF9B2C2C),
        backgroundColor: const Color(0xFFFDE8E8),
        borderColor: const Color(0xFFE9AAAA),
      );
    }
    if (_looksLikeParseFailure(failureText)) {
      return SourceSiteRuntimeStatus(
        label: '解析失败',
        note: '最近一次抓取拿到了页面，但解析规则未提取出有效内容，建议检查解析规则后重试。',
        latestLog: failureText,
        canRetry: true,
        icon: Icons.rule_folder_outlined,
        foregroundColor: const Color(0xFF9B2C2C),
        backgroundColor: const Color(0xFFFDE8E8),
        borderColor: const Color(0xFFE9AAAA),
      );
    }
    return SourceSiteRuntimeStatus(
      label: '运行失败',
      note: '最近一次任务执行失败，请结合最新日志排查后重试。',
      latestLog: failureText,
      canRetry: true,
      icon: Icons.error_outline,
      foregroundColor: const Color(0xFF9B2C2C),
      backgroundColor: const Color(0xFFFDE8E8),
      borderColor: const Color(0xFFE9AAAA),
    );
  }

  if (status == 'queued') {
    return const SourceSiteRuntimeStatus(
      label: '等待运行',
      note: '任务已进入队列，状态会在本页自动刷新。',
      latestLog: null,
      canRetry: false,
      icon: Icons.schedule_rounded,
      foregroundColor: Color(0xFF1E4F8A),
      backgroundColor: Color(0xFFEAF3FF),
      borderColor: Color(0xFFB8D2F2),
    );
  }

  if (status == 'running') {
    return const SourceSiteRuntimeStatus(
      label: '采集中',
      note: '任务正在执行中，稍后可在此处查看最终结果。',
      latestLog: null,
      canRetry: false,
      icon: Icons.autorenew_rounded,
      foregroundColor: Color(0xFF1E4F8A),
      backgroundColor: Color(0xFFEAF3FF),
      borderColor: Color(0xFFB8D2F2),
    );
  }

  if (status == 'success') {
    return const SourceSiteRuntimeStatus(
      label: '运行正常',
      note: '最近一次运行成功，当前展示的时间和状态来自实时任务记录。',
      latestLog: null,
      canRetry: false,
      icon: Icons.check_circle_outline,
      foregroundColor: Color(0xFF0B6B58),
      backgroundColor: Color(0xFFE0F4ED),
      borderColor: Color(0xFF9FD9C5),
    );
  }

  return SourceSiteRuntimeStatus(
    label: collectionStatus.label,
    note: task.lastSuccessAt == null
        ? '任务已创建，但还没有成功运行记录。'
        : '任务状态暂未明确，保留最近一次成功记录供排查。',
    latestLog: _latestFailureText(task, latestLog),
    canRetry: false,
    icon: collectionStatus.icon,
    foregroundColor: collectionStatus.foregroundColor,
    backgroundColor: collectionStatus.backgroundColor,
    borderColor: collectionStatus.borderColor,
  );
}

extension on SourceSiteRuntimeStatus {
  SourceSiteRuntimeStatus copyWith({
    String? label,
    String? note,
    String? latestLog,
    bool? canRetry,
    IconData? icon,
    Color? foregroundColor,
    Color? backgroundColor,
    Color? borderColor,
  }) {
    return SourceSiteRuntimeStatus(
      label: label ?? this.label,
      note: note ?? this.note,
      latestLog: latestLog ?? this.latestLog,
      canRetry: canRetry ?? this.canRetry,
      icon: icon ?? this.icon,
      foregroundColor: foregroundColor ?? this.foregroundColor,
      backgroundColor: backgroundColor ?? this.backgroundColor,
      borderColor: borderColor ?? this.borderColor,
    );
  }
}

String? _buildSummaryText(TaskLogItemModel? latestSummaryLog) {
  final metricsRaw = latestSummaryLog?.runSummary?['metrics'];
  if (metricsRaw is! Map) {
    return null;
  }
  final metrics = Map<String, dynamic>.from(metricsRaw);
  final stored = int.tryParse('${metrics['stored'] ?? 0}') ?? 0;
  final failed = int.tryParse('${metrics['failed'] ?? 0}') ?? 0;
  final parts = <String>[];
  if (stored > 0) {
    parts.add('入库 $stored 条');
  }
  if (failed > 0) {
    parts.add('失败 $failed 条');
  }
  if (parts.isEmpty) {
    return null;
  }
  return parts.join('，');
}

String? _latestFailureText(
  TaskListItemModel task,
  TaskLogItemModel? latestLog,
) {
  final candidates = <String?>[
    latestLog?.errorStack,
    task.lastErrorMessage,
    latestLog?.message,
  ];
  for (final candidate in candidates) {
    final text = candidate?.trim();
    if (text != null && text.isNotEmpty) {
      return text;
    }
  }
  return null;
}

bool _looksLikeConnectionFailure(String? text) {
  final normalized = text?.toLowerCase();
  if (normalized == null || normalized.isEmpty) {
    return false;
  }
  return [
    'connection',
    'timed out',
    'timeout',
    'reset by peer',
    'ssl',
    'network',
    'dns',
    'proxy',
    'refused',
    'unreachable',
    '502',
    '503',
    '504',
  ].any(normalized.contains);
}

bool _looksLikeParseFailure(String? text) {
  final normalized = text?.toLowerCase();
  if (normalized == null || normalized.isEmpty) {
    return false;
  }
  return [
    'parse',
    'parser',
    'selector',
    'xpath',
    'readability',
    'extract',
    'content',
    '解析',
    '提取',
    '选择器',
    '正文',
  ].any(normalized.contains);
}
