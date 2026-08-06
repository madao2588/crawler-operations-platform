import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../../../../core/utils/user_facing_error.dart';

class LoginPage extends StatefulWidget {
  final Future<void> Function(
    String userName,
    String password,
    Uint8List? avatarBytes,
  ) onLogin;

  const LoginPage({
    super.key,
    required this.onLogin,
  });

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final _formKey = GlobalKey<FormState>();
  final _userNameController = TextEditingController();
  final _passwordController = TextEditingController();

  Uint8List? _avatarBytes;
  String? _avatarFileName;
  bool _isSubmitting = false;

  @override
  void dispose() {
    _userNameController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _pickAvatar() async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.image,
      withData: true,
      allowMultiple: false,
    );

    if (!mounted || result == null) {
      return;
    }

    final file = result.files.single;
    final bytes = file.bytes;
    if (bytes == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('未能读取头像文件，请重新选择。')),
      );
      return;
    }

    setState(() {
      _avatarBytes = bytes;
      _avatarFileName = file.name;
    });
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) {
      return;
    }

    setState(() {
      _isSubmitting = true;
    });

    try {
      await widget.onLogin(
        _userNameController.text.trim(),
        _passwordController.text,
        _avatarBytes,
      );
    } on Object catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('登录失败：${userFacingError(error)}')),
        );
      }
    } finally {
      if (mounted) {
        setState(() {
          _isSubmitting = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              Color(0xFFF6FAFF),
              Color(0xFFE7F0FB),
              Color(0xFFDDEDF4),
            ],
          ),
        ),
        child: Stack(
          children: [
            const Positioned(
              top: -100,
              right: -80,
              child: _LoginBlob(
                color: Color(0x1A1E4F8A),
                size: 260,
              ),
            ),
            const Positioned(
              bottom: -120,
              left: -70,
              child: _LoginBlob(
                color: Color(0x1A2ED3B7),
                size: 300,
              ),
            ),
            SafeArea(
              child: Center(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.all(24),
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 1160),
                    child: LayoutBuilder(
                      builder: (context, constraints) {
                        final isCompact = constraints.maxWidth < 960;

                        final introPanel = Container(
                          padding: const EdgeInsets.all(28),
                          decoration: BoxDecoration(
                            borderRadius: BorderRadius.circular(32),
                            gradient: const LinearGradient(
                              begin: Alignment.topLeft,
                              end: Alignment.bottomRight,
                              colors: [
                                Color(0xFF183153),
                                Color(0xFF0F223D),
                              ],
                            ),
                            boxShadow: const [
                              BoxShadow(
                                color: Color(0x2812263F),
                                blurRadius: 34,
                                offset: Offset(0, 20),
                              ),
                            ],
                          ),
                          child: const Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              _BrandMark(),
                              SizedBox(height: 20),
                              Text(
                                '制药招标监测系统',
                                style: TextStyle(
                                  color: Colors.white,
                                  fontSize: 32,
                                  fontWeight: FontWeight.w700,
                                  height: 1.1,
                                ),
                              ),
                              SizedBox(height: 14),
                              Text(
                                '登录后进入统一控制台，集中查看公告、规则、来源站点和任务调度情况。\n支持本地导入头像，方便区分不同使用者。',
                                style: TextStyle(
                                  color: Color(0xFFD7E2F3),
                                  fontSize: 15,
                                  height: 1.6,
                                ),
                              ),
                              SizedBox(height: 22),
                              Wrap(
                                spacing: 10,
                                runSpacing: 10,
                                children: [
                                  _FeatureChip(label: '统一看板'),
                                  _FeatureChip(label: '任务调度'),
                                  _FeatureChip(label: '头像导入'),
                                ],
                              ),
                            ],
                          ),
                        );

                        final formPanel = Container(
                          padding: const EdgeInsets.all(28),
                          decoration: BoxDecoration(
                            color: Colors.white.withValues(alpha: 0.96),
                            borderRadius: BorderRadius.circular(32),
                            border: Border.all(color: const Color(0xFFE0E8F4)),
                            boxShadow: const [
                              BoxShadow(
                                color: Color(0x160A2342),
                                blurRadius: 34,
                                offset: Offset(0, 18),
                              ),
                            ],
                          ),
                          child: Form(
                            key: _formKey,
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  '欢迎回来',
                                  style: Theme.of(context)
                                      .textTheme
                                      .headlineMedium,
                                ),
                                const SizedBox(height: 10),
                                Text(
                                  '输入账号信息并上传头像，进入系统。',
                                  style: Theme.of(context).textTheme.bodyMedium,
                                ),
                                const SizedBox(height: 24),
                                Center(
                                  child: Column(
                                    children: [
                                      InkWell(
                                        onTap: _pickAvatar,
                                        borderRadius:
                                            BorderRadius.circular(999),
                                        child: CircleAvatar(
                                          radius: 44,
                                          backgroundColor:
                                              const Color(0xFFEAF3FF),
                                          backgroundImage: _avatarBytes == null
                                              ? null
                                              : MemoryImage(_avatarBytes!),
                                          child: _avatarBytes == null
                                              ? const Icon(
                                                  Icons.person,
                                                  size: 40,
                                                  color: Color(0xFF1E4F8A),
                                                )
                                              : null,
                                        ),
                                      ),
                                      const SizedBox(height: 12),
                                      TextButton.icon(
                                        onPressed: _pickAvatar,
                                        icon: const Icon(Icons.upload_file),
                                        label: const Text('导入头像'),
                                      ),
                                      if (_avatarFileName != null) ...[
                                        const SizedBox(height: 6),
                                        Text(
                                          _avatarFileName!,
                                          style: Theme.of(context)
                                              .textTheme
                                              .bodySmall,
                                        ),
                                      ],
                                    ],
                                  ),
                                ),
                                const SizedBox(height: 24),
                                TextFormField(
                                  controller: _userNameController,
                                  decoration: const InputDecoration(
                                    labelText: '账号',
                                    prefixIcon: Icon(Icons.badge_outlined),
                                  ),
                                  validator: (value) {
                                    if (value == null || value.trim().isEmpty) {
                                      return '请输入账号';
                                    }
                                    return null;
                                  },
                                ),
                                const SizedBox(height: 16),
                                TextFormField(
                                  controller: _passwordController,
                                  obscureText: true,
                                  decoration: const InputDecoration(
                                    labelText: '密码',
                                    prefixIcon: Icon(Icons.lock_outline),
                                  ),
                                  validator: (value) {
                                    if (value == null || value.trim().isEmpty) {
                                      return '请输入密码';
                                    }
                                    if (value.trim().length < 4) {
                                      return '密码至少 4 位';
                                    }
                                    return null;
                                  },
                                ),
                                const SizedBox(height: 20),
                                SizedBox(
                                  width: double.infinity,
                                  child: FilledButton.icon(
                                    onPressed: _isSubmitting ? null : _submit,
                                    icon: _isSubmitting
                                        ? const SizedBox(
                                            width: 18,
                                            height: 18,
                                            child: CircularProgressIndicator(
                                              strokeWidth: 2,
                                              color: Colors.white,
                                            ),
                                          )
                                        : const Icon(Icons.login),
                                    label: Text(
                                      _isSubmitting ? '登录中...' : '进入系统',
                                    ),
                                  ),
                                ),
                                const SizedBox(height: 14),
                                Text(
                                  '头像会保存在当前会话中，后续可在右上角看到你的登录信息。',
                                  style: Theme.of(context).textTheme.bodySmall,
                                ),
                              ],
                            ),
                          ),
                        );

                        if (isCompact) {
                          return Column(
                            children: [
                              introPanel,
                              const SizedBox(height: 16),
                              formPanel,
                            ],
                          );
                        }

                        return IntrinsicHeight(
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              Expanded(flex: 5, child: introPanel),
                              const SizedBox(width: 16),
                              Expanded(flex: 4, child: formPanel),
                            ],
                          ),
                        );
                      },
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LoginBlob extends StatelessWidget {
  final Color color;
  final double size;

  const _LoginBlob({
    required this.color,
    required this.size,
  });

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: RadialGradient(
            colors: [color, color.withValues(alpha: 0.0)],
          ),
        ),
      ),
    );
  }
}

class _FeatureChip extends StatelessWidget {
  final String label;

  const _FeatureChip({required this.label});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(0x14FFFFFF),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: const Color(0x26FFFFFF)),
      ),
      child: Text(
        label,
        style: Theme.of(context).textTheme.labelLarge?.copyWith(
              color: Colors.white,
            ),
      ),
    );
  }
}

class _BrandMark extends StatelessWidget {
  const _BrandMark();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 56,
      height: 56,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(18),
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            Color(0xFF6AA6FF),
            Color(0xFF2ED3B7),
          ],
        ),
      ),
      child: const Icon(
        Icons.monitor_heart_outlined,
        color: Colors.white,
      ),
    );
  }
}
