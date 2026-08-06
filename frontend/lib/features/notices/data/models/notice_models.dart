class NoticeSourceSiteOption {
  final String sourceSite;
  final String displayName;

  const NoticeSourceSiteOption({
    required this.sourceSite,
    required this.displayName,
  });

  factory NoticeSourceSiteOption.fromJson(Map<String, dynamic> json) {
    return NoticeSourceSiteOption(
      sourceSite: json['source_site']?.toString().trim() ?? '',
      displayName: json['display_name']?.toString().trim() ?? '',
    );
  }
}

class NoticeListItemModel {
  final int id;
  final String title;
  final String summary;
  final String sourceSite;
  final String sourceUrl;
  final String? publishedAt;
  final String capturedAt;
  final int qualityScore;
  final List<String> matchedKeywords;
  final bool isHighPriority;
  final String category;
  final String? aiSummary;
  final String reviewStatus;
  final bool isArchived;
  final String? remark;
  final int taskId;

  const NoticeListItemModel({
    required this.id,
    required this.title,
    required this.summary,
    required this.sourceSite,
    required this.sourceUrl,
    required this.publishedAt,
    required this.capturedAt,
    required this.qualityScore,
    required this.matchedKeywords,
    required this.isHighPriority,
    required this.category,
    required this.aiSummary,
    required this.reviewStatus,
    required this.isArchived,
    required this.remark,
    required this.taskId,
  });

  factory NoticeListItemModel.fromJson(Map<String, dynamic> json) {
    return NoticeListItemModel(
      id: json['id'] as int? ?? 0,
      title: json['title']?.toString() ?? '',
      summary: json['summary']?.toString() ?? '',
      sourceSite: json['source_site']?.toString() ?? '',
      sourceUrl: json['source_url']?.toString() ?? '',
      publishedAt: json['published_at']?.toString(),
      capturedAt: json['captured_at']?.toString() ?? '',
      qualityScore: json['quality_score'] as int? ?? 0,
      matchedKeywords: (json['matched_keywords'] as List<dynamic>? ?? [])
          .map((item) => item.toString())
          .toList(),
      isHighPriority: json['is_high_priority'] as bool? ?? false,
      category: json['category']?.toString() ?? '未分类',
      aiSummary: json['ai_summary']?.toString(),
      reviewStatus: json['review_status']?.toString() ?? '待关注',
      isArchived: json['is_archived'] as bool? ?? false,
      remark: json['remark']?.toString(),
      taskId: json['task_id'] as int? ?? 0,
    );
  }
}

class NoticeReviewPayload {
  final String? category;
  final String? reviewStatus;
  final bool? isArchived;
  final String? remark;

  const NoticeReviewPayload({
    this.category,
    this.reviewStatus,
    this.isArchived,
    this.remark,
  });

  Map<String, dynamic> toJson() {
    return {
      if (category != null) 'category': category,
      if (reviewStatus != null) 'review_status': reviewStatus,
      if (isArchived != null) 'is_archived': isArchived,
      if (remark != null) 'remark': remark,
    };
  }
}

class NoticeDetailModel extends NoticeListItemModel {
  final String contentText;
  final String contentHtml;
  final String? contentHash;
  final String? snapshotPath;
  final Map<String, dynamic>? metadata;

  const NoticeDetailModel({
    required super.id,
    required super.title,
    required super.summary,
    required super.sourceSite,
    required super.sourceUrl,
    required super.publishedAt,
    required super.capturedAt,
    required super.qualityScore,
    required super.matchedKeywords,
    required super.isHighPriority,
    required super.category,
    required super.aiSummary,
    required super.reviewStatus,
    required super.isArchived,
    required super.remark,
    required super.taskId,
    required this.contentText,
    required this.contentHtml,
    required this.contentHash,
    required this.snapshotPath,
    required this.metadata,
  });

  factory NoticeDetailModel.fromJson(Map<String, dynamic> json) {
    final rawMetadata = json['metadata'];
    return NoticeDetailModel(
      id: json['id'] as int? ?? 0,
      title: json['title']?.toString() ?? '',
      summary: json['summary']?.toString() ?? '',
      sourceSite: json['source_site']?.toString() ?? '',
      sourceUrl: json['source_url']?.toString() ?? '',
      publishedAt: json['published_at']?.toString(),
      capturedAt: json['captured_at']?.toString() ?? '',
      qualityScore: json['quality_score'] as int? ?? 0,
      matchedKeywords: (json['matched_keywords'] as List<dynamic>? ?? [])
          .map((item) => item.toString())
          .toList(),
      isHighPriority: json['is_high_priority'] as bool? ?? false,
      category: json['category']?.toString() ?? '未分类',
      aiSummary: json['ai_summary']?.toString(),
      reviewStatus: json['review_status']?.toString() ?? '待关注',
      isArchived: json['is_archived'] as bool? ?? false,
      remark: json['remark']?.toString(),
      taskId: json['task_id'] as int? ?? 0,
      contentText: json['content_text']?.toString() ?? '',
      contentHtml: json['content_html']?.toString() ?? '',
      contentHash: json['content_hash']?.toString(),
      snapshotPath: json['snapshot_path']?.toString(),
      metadata:
          rawMetadata is Map ? Map<String, dynamic>.from(rawMetadata) : null,
    );
  }
}

class NoticeSnapshotModel {
  final int id;
  final String sourceUrl;
  final String sourceSite;
  final String snapshotPath;
  final String content;

  const NoticeSnapshotModel({
    required this.id,
    required this.sourceUrl,
    required this.sourceSite,
    required this.snapshotPath,
    required this.content,
  });

  factory NoticeSnapshotModel.fromJson(Map<String, dynamic> json) {
    return NoticeSnapshotModel(
      id: json['id'] as int? ?? 0,
      sourceUrl: json['source_url']?.toString() ?? '',
      sourceSite: json['source_site']?.toString() ?? '',
      snapshotPath: json['snapshot_path']?.toString() ?? '',
      content: json['content']?.toString() ?? '',
    );
  }
}
