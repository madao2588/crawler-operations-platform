class TaskTemplateModel {
  final String id;
  final String label;
  final String name;
  final String startUrl;
  final String cronExpr;
  final String? parserRules;
  final bool enabled;
  final String description;
  final List<String> tags;
  final int usageCount;
  final String? lastUsedAt;

  const TaskTemplateModel({
    required this.id,
    required this.label,
    required this.name,
    required this.startUrl,
    required this.cronExpr,
    required this.parserRules,
    required this.enabled,
    required this.description,
    required this.tags,
    required this.usageCount,
    required this.lastUsedAt,
  });

  factory TaskTemplateModel.fromJson(Map<String, dynamic> json) {
    return TaskTemplateModel(
      id: json['id']?.toString() ?? '',
      label: json['label']?.toString() ?? '',
      name: json['name']?.toString() ?? '',
      startUrl: json['start_url']?.toString() ?? '',
      cronExpr: json['cron_expr']?.toString() ?? '',
      parserRules: json['parser_rules']?.toString(),
      enabled: json['enabled'] as bool? ?? true,
      description: json['description']?.toString() ?? '',
      tags: (json['tags'] as List<dynamic>? ?? [])
          .map((item) => item.toString())
          .toList(),
      usageCount: json['usage_count'] as int? ?? 0,
      lastUsedAt: json['last_used_at']?.toString(),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'label': label,
      'name': name,
      'start_url': startUrl,
      'cron_expr': cronExpr,
      'parser_rules': parserRules,
      'enabled': enabled,
      'description': description,
      'tags': tags,
      'usage_count': usageCount,
      'last_used_at': lastUsedAt,
    };
  }
}

class TestTemplateRequest {
  final String startUrl;
  final String? parserRules;

  const TestTemplateRequest({
    required this.startUrl,
    this.parserRules,
  });

  Map<String, dynamic> toJson() {
    return {
      'start_url': startUrl,
      if (parserRules != null) 'parser_rules': parserRules,
    };
  }
}

class TemplateTestTrace {
  final String? fetch;
  final String? contentSource;
  final List<String> notes;

  const TemplateTestTrace({
    this.fetch,
    this.contentSource,
    this.notes = const [],
  });

  factory TemplateTestTrace.fromJson(Object? raw) {
    if (raw == null || raw is! Map) {
      return const TemplateTestTrace();
    }
    final m = Map<String, dynamic>.from(raw);
    return TemplateTestTrace(
      fetch: m['fetch']?.toString(),
      contentSource: m['content_source']?.toString(),
      notes: (m['notes'] as List<dynamic>? ?? [])
          .map((e) => e.toString())
          .toList(),
    );
  }
}

class TestTemplateResponse {
  final String? title;
  final String? contentText;
  final String? contentHtml;
  final int? qualityScore;
  final String? error;
  final TemplateTestTrace? trace;

  const TestTemplateResponse({
    this.title,
    this.contentText,
    this.contentHtml,
    this.qualityScore,
    this.error,
    this.trace,
  });

  factory TestTemplateResponse.fromJson(Map<String, dynamic> json) {
    return TestTemplateResponse(
      title: json['title']?.toString(),
      contentText: json['content_text']?.toString(),
      contentHtml: json['content_html']?.toString(),
      qualityScore: json['quality_score'] as int?,
      error: json['error']?.toString(),
      trace: json['trace'] != null
          ? TemplateTestTrace.fromJson(json['trace'])
          : null,
    );
  }
}

class ManualCollectionResult {
  final String sourceId;
  final String sourceUrl;
  final String status;
  final int noticeId;

  const ManualCollectionResult({
    required this.sourceId,
    required this.sourceUrl,
    required this.status,
    required this.noticeId,
  });

  factory ManualCollectionResult.fromJson(Map<String, dynamic> json) {
    return ManualCollectionResult(
      sourceId: json['source_id']?.toString() ?? '',
      sourceUrl: json['source_url']?.toString() ?? '',
      status: json['status']?.toString() ?? '',
      noticeId: json['notice_id'] as int? ?? 0,
    );
  }
}
