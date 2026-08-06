class DateFormatter {
  static String lastUpdatedPlaceholder() {
    return '最后更新：待接入后端';
  }

  static String formatDateTime(String? value, {String fallback = '-'}) {
    final parsed = _parseBackendDateTime(value);
    if (parsed == null) {
      return value == null || value.trim().isEmpty ? fallback : value;
    }

    final local = parsed.toLocal();

    String twoDigits(int number) => number.toString().padLeft(2, '0');

    return '${local.year}-${twoDigits(local.month)}-${twoDigits(local.day)} '
        '${twoDigits(local.hour)}:${twoDigits(local.minute)}:${twoDigits(local.second)}';
  }

  static String formatShortDate(String? value, {String fallback = '-'}) {
    final parsed = _parseBackendDateTime(value);
    if (parsed == null) {
      return value == null || value.trim().isEmpty ? fallback : value;
    }

    final local = parsed.toLocal();

    String twoDigits(int number) => number.toString().padLeft(2, '0');

    return '${twoDigits(local.month)}-${twoDigits(local.day)}';
  }

  static DateTime? _parseBackendDateTime(String? value) {
    if (value == null || value.trim().isEmpty) {
      return null;
    }

    final normalized = value.trim();
    final direct = DateTime.tryParse(normalized);
    if (direct == null) {
      return null;
    }

    // API returns UTC with ``Z`` or ``+00:00``; naive strings are treated as UTC wall clock.
    final hasExplicitTimezone = normalized.endsWith('Z') ||
        RegExp(r'[+-]\d{2}:\d{2}(:\d{2})?$').hasMatch(normalized);

    if (hasExplicitTimezone || direct.isUtc) {
      return direct;
    }

    final utcCandidate =
        DateTime.tryParse('${normalized.replaceFirst(' ', 'T')}Z');
    return utcCandidate ?? direct;
  }
}
