import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/app_config.dart';

class ApiClient {
  static String? _authToken;
  static Future<void> Function()? _unauthorizedHandler;
  static bool _handlingUnauthorized = false;

  static void setAuthToken(String? token) {
    _authToken = token;
  }

  static void setUnauthorizedHandler(Future<void> Function()? handler) {
    _unauthorizedHandler = handler;
  }

  final String baseUrl;
  final http.Client _httpClient;
  final Duration requestTimeout;

  ApiClient({
    String? baseUrl,
    http.Client? httpClient,
    Duration? requestTimeout,
  })  : baseUrl = baseUrl ?? AppConfig.apiBaseUrl,
        _httpClient = httpClient ?? http.Client(),
        requestTimeout = requestTimeout ?? AppConfig.apiRequestTimeout;

  Future<List<int>> getBytes(
    String path, {
    Map<String, String>? queryParameters,
  }) async {
    final uri = Uri.parse('$baseUrl$path').replace(
      queryParameters: queryParameters,
    );
    final response = await _httpClient
        .get(uri, headers: _headers())
        .timeout(requestTimeout, onTimeout: _onTimeout);
    if (response.statusCode < 200 || response.statusCode >= 300) {
      await _maybeHandleUnauthorized(path, response.statusCode);
      var msg = 'Request failed (${response.statusCode})';
      try {
        final decoded = jsonDecode(response.body);
        if (decoded is Map && decoded['message'] != null) {
          msg = decoded['message'].toString();
        }
      } on FormatException {
        if (response.body.isNotEmpty && response.body.length < 240) {
          msg = response.body;
        }
      } catch (_) {
        if (response.body.isNotEmpty && response.body.length < 240) {
          msg = response.body;
        }
      }
      throw ApiException(msg, statusCode: response.statusCode);
    }
    return response.bodyBytes;
  }

  Future<Map<String, dynamic>> getJson(
    String path, {
    Map<String, String>? queryParameters,
  }) async {
    final uri = Uri.parse('$baseUrl$path').replace(
      queryParameters: queryParameters,
    );
    final response = await _httpClient
        .get(uri, headers: _headers())
        .timeout(requestTimeout, onTimeout: _onTimeout);
    return _decodeResponse(response, path: path);
  }

  Future<Map<String, dynamic>> postJson(
    String path, {
    Map<String, dynamic>? body,
  }) async {
    final uri = Uri.parse('$baseUrl$path');
    final response = await _httpClient
        .post(
          uri,
          headers: _headers(includeContentType: true),
          body: body == null ? null : jsonEncode(body),
        )
        .timeout(requestTimeout, onTimeout: _onTimeout);
    return _decodeResponse(response, path: path);
  }

  Future<Map<String, dynamic>> putJson(
    String path, {
    Map<String, dynamic>? body,
  }) async {
    final uri = Uri.parse('$baseUrl$path');
    final response = await _httpClient
        .put(
          uri,
          headers: _headers(includeContentType: true),
          body: body == null ? null : jsonEncode(body),
        )
        .timeout(requestTimeout, onTimeout: _onTimeout);
    return _decodeResponse(response, path: path);
  }

  Future<Map<String, dynamic>> patchJson(
    String path, {
    Map<String, dynamic>? body,
  }) async {
    final uri = Uri.parse('$baseUrl$path');
    final response = await _httpClient
        .patch(
          uri,
          headers: _headers(includeContentType: true),
          body: body == null ? null : jsonEncode(body),
        )
        .timeout(requestTimeout, onTimeout: _onTimeout);
    return _decodeResponse(response, path: path);
  }

  Future<Map<String, dynamic>> deleteJson(String path) async {
    final uri = Uri.parse('$baseUrl$path');
    final response = await _httpClient
        .delete(uri, headers: _headers())
        .timeout(requestTimeout, onTimeout: _onTimeout);
    return _decodeResponse(response, path: path);
  }

  Never _onTimeout() {
    throw const ApiException('Request timed out');
  }

  Map<String, String> _headers({bool includeContentType = false}) {
    final headers = <String, String>{};
    if (includeContentType) {
      headers['Content-Type'] = 'application/json';
    }
    final token = _authToken;
    if (token != null && token.isNotEmpty) {
      headers['Authorization'] = 'Bearer $token';
    }
    return headers;
  }

  Future<Map<String, dynamic>> _decodeResponse(
    http.Response response, {
    required String path,
  }) async {
    late final Map<String, dynamic> decoded;
    try {
      final raw = jsonDecode(response.body);
      if (raw is! Map<String, dynamic>) {
        throw ApiException(
          'Server returned an invalid response shape',
          statusCode: response.statusCode,
        );
      }
      decoded = raw;
    } on FormatException {
      throw ApiException(
        'Server returned invalid JSON',
        statusCode: response.statusCode,
      );
    }

    if (response.statusCode < 200 || response.statusCode >= 300) {
      await _maybeHandleUnauthorized(path, response.statusCode);
      throw ApiException(
        decoded['message']?.toString() ?? 'Request failed',
        statusCode: response.statusCode,
      );
    }

    return decoded;
  }

  Future<void> _maybeHandleUnauthorized(String path, int statusCode) async {
    if (statusCode != 401 || path == '/v1/auth/login') {
      return;
    }

    final token = _authToken;
    final handler = _unauthorizedHandler;
    if (token == null ||
        token.isEmpty ||
        handler == null ||
        _handlingUnauthorized) {
      return;
    }

    _handlingUnauthorized = true;
    try {
      await handler();
    } finally {
      _handlingUnauthorized = false;
    }
  }

  void dispose() {
    _httpClient.close();
  }
}

class ApiException implements Exception {
  final String message;
  final int? statusCode;

  const ApiException(
    this.message, {
    this.statusCode,
  });

  @override
  String toString() {
    if (statusCode == null) {
      return 'ApiException($message)';
    }
    return 'ApiException($statusCode, $message)';
  }
}
