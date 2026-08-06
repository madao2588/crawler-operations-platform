import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pharma_bid_monitor_frontend/core/theme/app_theme.dart';
import 'package:pharma_bid_monitor_frontend/features/notices/presentation/pages/notices_page.dart';

void main() {
  testWidgets('narrow notices page keeps secondary filters collapsed',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: const NoticesPage(),
      ),
    );

    expect(find.byTooltip('展开筛选'), findsOneWidget);
    expect(find.text('类别'), findsNothing);

    await tester.tap(find.byTooltip('展开筛选'));
    await tester.pump();

    expect(find.byTooltip('收起筛选'), findsOneWidget);
    expect(find.text('类别'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
