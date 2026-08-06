import 'package:flutter/material.dart';

import '../core/theme/app_theme.dart';
import 'router/app_router.dart';

class PharmaBidMonitorApp extends StatelessWidget {
  const PharmaBidMonitorApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '网页采集运营平台',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      home: const AppRouter(),
    );
  }
}
