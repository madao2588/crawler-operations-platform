class KeywordRuleModel {
  final int id;
  final String word;
  final bool isHighPriority;
  final bool isActive;
  final bool isDefault;
  final String createdAt;
  final String updatedAt;

  const KeywordRuleModel({
    required this.id,
    required this.word,
    required this.isHighPriority,
    required this.isActive,
    this.isDefault = false,
    required this.createdAt,
    required this.updatedAt,
  });

  factory KeywordRuleModel.fromJson(Map<String, dynamic> json) {
    return KeywordRuleModel(
      id: json['id'] as int? ?? 0,
      word: json['word']?.toString() ?? '',
      isHighPriority: json['is_high_priority'] as bool? ?? false,
      isActive: json['is_active'] as bool? ?? false,
      isDefault: json['is_default'] as bool? ?? false,
      createdAt: json['created_at']?.toString() ?? '',
      updatedAt: json['updated_at']?.toString() ?? '',
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'word': word,
      'is_high_priority': isHighPriority,
      'is_active': isActive,
    };
  }
}
