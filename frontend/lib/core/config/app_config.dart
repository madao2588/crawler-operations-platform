class AppConfig {
  static const appName = '网页采集运营平台';
  static const apiBaseUrl = 'http://127.0.0.1:8000';

  /// Single-request ceiling so the UI does not hang indefinitely on a dead host.
  static const Duration apiRequestTimeout = Duration(seconds: 60);
}
