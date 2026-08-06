import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/network/api_client.dart';
import '../../core/widgets/async_error_panel.dart';
import '../navigation/app_shell.dart';
import '../../features/auth/presentation/pages/login_page.dart';

class AppRouter extends StatefulWidget {
  const AppRouter({super.key});

  @override
  State<AppRouter> createState() => _AppRouterState();
}

class _AppRouterState extends State<AppRouter> {
  static const _prefAuthToken = 'app.authToken';
  static const _prefUserName = 'app.userName';
  static const _prefAvatarBase64 = 'app.avatarBase64';

  late Future<void> _bootstrapFuture;
  late final ApiClient _authClient;
  bool _isAuthenticated = false;
  String _userName = '\u8fd0\u8425\u7ba1\u7406\u5458';
  Uint8List? _avatarBytes;

  void _retryBootstrap() {
    setState(() {
      _bootstrapFuture = _loadSession();
    });
  }

  @override
  void initState() {
    super.initState();
    _authClient = ApiClient();
    ApiClient.setUnauthorizedHandler(_handleUnauthorizedSession);
    _bootstrapFuture = _loadSession();
  }

  @override
  void dispose() {
    ApiClient.setUnauthorizedHandler(null);
    _authClient.dispose();
    super.dispose();
  }

  Future<void> _loadSession() async {
    try {
      final preferences = await SharedPreferences.getInstance();
      final token = preferences.getString(_prefAuthToken);
      if (token == null || token.isEmpty) {
        return;
      }

      ApiClient.setAuthToken(token);

      final response = await _authClient.getJson('/v1/auth/me');
      final data = response['data'];
      if (data is! Map<String, dynamic>) {
        throw const ApiException('Invalid auth response format');
      }

      await _applySessionData(data, preferences: preferences);
    } catch (e, stack) {
      debugPrint('Session load error: $e\n$stack');
      await _resetSessionState();
      return;
    }
  }

  Future<void> _handleLogin(
    String userName,
    String password,
    Uint8List? avatarBytes,
  ) async {
    final response = await _authClient.postJson(
      '/v1/auth/login',
      body: {
        'username': userName,
        'password': password,
        'avatar_base64': avatarBytes == null ? null : base64Encode(avatarBytes),
      },
    );

    final data = response['data'];
    if (data is! Map<String, dynamic>) {
      throw const ApiException('Invalid auth response format');
    }

    final preferences = await SharedPreferences.getInstance();
    await _applySessionData(data, preferences: preferences);
  }

  Future<void> _handleLogout() async {
    final preferences = await SharedPreferences.getInstance();
    try {
      await _authClient.postJson('/v1/auth/logout');
    } catch (_) {
      // Logout should still clear local state even if the backend is unavailable.
    }

    await _resetSessionState(preferences: preferences);
  }

  Future<void> _applySessionData(
    Map<String, dynamic> data, {
    required SharedPreferences preferences,
  }) async {
    final token = data['access_token']?.toString();
    final user = data['user'];
    if (token == null || token.isEmpty || user is! Map<String, dynamic>) {
      throw const ApiException('Invalid auth response format');
    }

    final resolvedUserName = user['username']?.toString().trim();
    final avatarBase64 = user['avatar_base64']?.toString();

    await preferences.setString(_prefAuthToken, token);
    await preferences.setString(
      _prefUserName,
      resolvedUserName?.isNotEmpty == true ? resolvedUserName! : _userName,
    );
    if (avatarBase64 == null || avatarBase64.isEmpty) {
      await preferences.remove(_prefAvatarBase64);
    } else {
      await preferences.setString(_prefAvatarBase64, avatarBase64);
    }

    ApiClient.setAuthToken(token);

    if (!mounted) {
      return;
    }

    setState(() {
      _isAuthenticated = true;
      _userName =
          resolvedUserName?.isNotEmpty == true ? resolvedUserName! : _userName;
      _avatarBytes = avatarBase64 == null || avatarBase64.isEmpty
          ? null
          : base64Decode(avatarBase64);
    });
  }

  Future<void> _clearStoredSession(SharedPreferences preferences) async {
    await preferences.remove(_prefAuthToken);
    await preferences.remove(_prefUserName);
    await preferences.remove(_prefAvatarBase64);
  }

  Future<void> _handleUnauthorizedSession() async {
    final shouldNotify = _isAuthenticated;
    await _resetSessionState(notify: shouldNotify);
  }

  Future<void> _resetSessionState({
    SharedPreferences? preferences,
    bool notify = false,
  }) async {
    final prefs = preferences ?? await SharedPreferences.getInstance();
    await _clearStoredSession(prefs);
    ApiClient.setAuthToken(null);

    if (!mounted) {
      return;
    }

    setState(() {
      _isAuthenticated = false;
      _userName = '\u8fd0\u8425\u7ba1\u7406\u5458';
      _avatarBytes = null;
    });

    if (!notify) {
      return;
    }

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('\u767b\u5f55\u5df2\u5931\u6548\uff0c\u8bf7\u91cd\u65b0\u767b\u5f55\u3002'),
        ),
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<void>(
      future: _bootstrapFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Scaffold(
            body: Center(
              child: CircularProgressIndicator(),
            ),
          );
        }

        if (snapshot.hasError) {
          return Scaffold(
            body: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 480),
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: AsyncErrorPanel(
                    error: snapshot.error!,
                    title: '\u542f\u52a8\u5e94\u7528\u5931\u8d25',
                    retryLabel: '\u91cd\u65b0\u52a0\u8f7d',
                    onRetry: _retryBootstrap,
                  ),
                ),
              ),
            ),
          );
        }

        return AnimatedSwitcher(
          duration: const Duration(milliseconds: 260),
          child: _isAuthenticated
              ? AppShell(
                  key: const ValueKey('app-shell'),
                  userName: _userName,
                  avatarBytes: _avatarBytes,
                  onLogout: _handleLogout,
                )
              : LoginPage(
                  key: const ValueKey('login-page'),
                  onLogin: _handleLogin,
                ),
        );
      },
    );
  }
}
