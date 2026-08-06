class AppConfig {
  static const appName = '\u5236\u836f\u62db\u6807\u76d1\u6d4b\u7cfb\u7edf';
  static const _defaultApiBaseUrl = 'http://127.0.0.1:8000';
  static const _configuredApiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: _defaultApiBaseUrl,
  );

  static String get apiBaseUrl {
    final configured = _configuredApiBaseUrl.trim();
    if (configured.isEmpty) {
      return _defaultApiBaseUrl;
    }
    if (configured.endsWith('/')) {
      return configured.substring(0, configured.length - 1);
    }
    return configured;
  }

  /// Single-request ceiling so the UI does not hang indefinitely on a dead host.
  static const Duration apiRequestTimeout = Duration(seconds: 60);
}
