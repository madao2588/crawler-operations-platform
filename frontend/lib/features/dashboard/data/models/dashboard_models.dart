import '../../../notices/data/models/notice_models.dart';

class DashboardRuntimeModel {
  final String status;
  final String database;
  final String scheduler;
  final int scheduledJobs;

  const DashboardRuntimeModel({
    required this.status,
    required this.database,
    required this.scheduler,
    required this.scheduledJobs,
  });

  factory DashboardRuntimeModel.fromJson(Map<String, dynamic>? json) {
    if (json == null || json.isEmpty) {
      return const DashboardRuntimeModel(
        status: 'unknown',
        database: 'unknown',
        scheduler: 'unknown',
        scheduledJobs: 0,
      );
    }
    return DashboardRuntimeModel(
      status: json['status']?.toString() ?? 'unknown',
      database: json['database']?.toString() ?? 'unknown',
      scheduler: json['scheduler']?.toString() ?? 'unknown',
      scheduledJobs: json['scheduled_jobs'] as int? ?? 0,
    );
  }
}

class DashboardMetricsModel {
  final int todayNewNotices;
  final int keywordHitNotices;
  final int monitoringSiteCount;
  final int highPriorityNotices;
  final int highQualityNotices;
  final int projectDeclarationNotices;
  final int resultPublicationNotices;

  const DashboardMetricsModel({
    required this.todayNewNotices,
    required this.keywordHitNotices,
    required this.monitoringSiteCount,
    required this.highPriorityNotices,
    this.highQualityNotices = 0,
    required this.projectDeclarationNotices,
    required this.resultPublicationNotices,
  });

  factory DashboardMetricsModel.fromJson(Map<String, dynamic> json) {
    return DashboardMetricsModel(
      todayNewNotices: json['today_new_notices'] as int? ?? 0,
      keywordHitNotices: json['keyword_hit_notices'] as int? ?? 0,
      monitoringSiteCount: json['monitoring_site_count'] as int? ?? 0,
      highPriorityNotices: json['high_priority_notices'] as int? ?? 0,
      highQualityNotices: json['high_quality_notices'] as int? ?? 0,
      projectDeclarationNotices:
          json['project_declaration_notices'] as int? ?? 0,
      resultPublicationNotices: json['result_publication_notices'] as int? ?? 0,
    );
  }
}

class KeywordHeatItemModel {
  final String keyword;
  final int count;

  const KeywordHeatItemModel({
    required this.keyword,
    required this.count,
  });

  factory KeywordHeatItemModel.fromJson(Map<String, dynamic> json) {
    return KeywordHeatItemModel(
      keyword: json['keyword']?.toString() ?? '',
      count: json['count'] as int? ?? 0,
    );
  }
}

class SourceDistributionItemModel {
  final String sourceSite;
  final String displayName;
  final int noticeCount;
  final double percentage;

  const SourceDistributionItemModel({
    required this.sourceSite,
    required this.displayName,
    required this.noticeCount,
    required this.percentage,
  });

  factory SourceDistributionItemModel.fromJson(Map<String, dynamic> json) {
    return SourceDistributionItemModel(
      sourceSite: json['source_site']?.toString() ?? '',
      displayName: json['display_name']?.toString() ?? '',
      noticeCount: json['notice_count'] as int? ?? 0,
      percentage: (json['percentage'] as num?)?.toDouble() ?? 0,
    );
  }
}

class ProjectSignalItemModel {
  final String label;
  final int noticeCount;
  final double percentage;

  const ProjectSignalItemModel({
    required this.label,
    required this.noticeCount,
    required this.percentage,
  });

  factory ProjectSignalItemModel.fromJson(Map<String, dynamic> json) {
    return ProjectSignalItemModel(
      label: json['label']?.toString() ?? '',
      noticeCount: json['notice_count'] as int? ?? 0,
      percentage: (json['percentage'] as num?)?.toDouble() ?? 0,
    );
  }
}

class DashboardOverviewModel {
  final DashboardMetricsModel metrics;
  final DashboardRuntimeModel runtime;
  final List<NoticeListItemModel> highValueNotices;
  final List<NoticeListItemModel> recentNotices;
  final List<KeywordHeatItemModel> keywordHeat;
  final List<SourceDistributionItemModel> sourceDistribution;
  final List<ProjectSignalItemModel> projectSignalDistribution;
  final String? lastUpdatedAt;

  const DashboardOverviewModel({
    required this.metrics,
    required this.runtime,
    required this.highValueNotices,
    required this.recentNotices,
    required this.keywordHeat,
    required this.sourceDistribution,
    required this.projectSignalDistribution,
    required this.lastUpdatedAt,
  });

  factory DashboardOverviewModel.fromJson(Map<String, dynamic> json) {
    return DashboardOverviewModel(
      metrics: DashboardMetricsModel.fromJson(
        json['metrics'] as Map<String, dynamic>? ?? {},
      ),
      runtime: DashboardRuntimeModel.fromJson(
        json['runtime'] as Map<String, dynamic>?,
      ),
      highValueNotices: (json['high_value_notices'] as List<dynamic>? ?? [])
          .whereType<Map<String, dynamic>>()
          .map(NoticeListItemModel.fromJson)
          .toList(),
      recentNotices: (json['recent_notices'] as List<dynamic>? ?? [])
          .whereType<Map<String, dynamic>>()
          .map(NoticeListItemModel.fromJson)
          .toList(),
      keywordHeat: (json['keyword_heat'] as List<dynamic>? ?? [])
          .whereType<Map<String, dynamic>>()
          .map(KeywordHeatItemModel.fromJson)
          .toList(),
      sourceDistribution: (json['source_distribution'] as List<dynamic>? ?? [])
          .whereType<Map<String, dynamic>>()
          .map(SourceDistributionItemModel.fromJson)
          .toList(),
      projectSignalDistribution:
          (json['project_signal_distribution'] as List<dynamic>? ?? [])
              .whereType<Map<String, dynamic>>()
              .map(ProjectSignalItemModel.fromJson)
              .toList(),
      lastUpdatedAt: json['last_updated_at']?.toString(),
    );
  }
}
