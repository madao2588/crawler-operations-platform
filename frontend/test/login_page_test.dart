import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pharma_bid_monitor_frontend/features/auth/presentation/pages/login_page.dart';

void main() {
  testWidgets('LoginPage submits and calls onLogin with credentials',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(900, 1600));
    addTearDown(() async {
      await tester.binding.setSurfaceSize(null);
    });

    String? submittedUser;
    String? submittedPassword;
    Uint8List? submittedAvatar;

    await tester.pumpWidget(
      MaterialApp(
        home: LoginPage(
          onLogin: (user, password, avatar) async {
            submittedUser = user;
            submittedPassword = password;
            submittedAvatar = avatar;
          },
        ),
      ),
    );

    await tester.enterText(find.byType(TextFormField).first, 'tester');
    await tester.enterText(find.byType(TextFormField).at(1), 'secret1234');
    await tester.ensureVisible(find.text('\u8fdb\u5165\u7cfb\u7edf'));
    await tester.tap(find.text('\u8fdb\u5165\u7cfb\u7edf'));
    await tester.pumpAndSettle();

    expect(submittedUser, 'tester');
    expect(submittedPassword, 'secret1234');
    expect(submittedAvatar, isNull);
  });

  testWidgets('LoginPage hides backend bootstrap env names', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: LoginPage(
          onLogin: (_, __, ___) async {},
        ),
      ),
    );

    expect(
      find.textContaining('CRAWLER_BOOTSTRAP_ADMIN_USERNAME'),
      findsNothing,
    );
    expect(
      find.textContaining('CRAWLER_BOOTSTRAP_ADMIN_PASSWORD'),
      findsNothing,
    );
  });
}
