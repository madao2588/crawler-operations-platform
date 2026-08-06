import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:pharma_bid_monitor_frontend/core/network/api_client.dart';
import 'package:pharma_bid_monitor_frontend/core/theme/app_theme.dart';
import 'package:pharma_bid_monitor_frontend/features/keyword_rules/data/repositories/http_keyword_rule_repository.dart';
import 'package:pharma_bid_monitor_frontend/features/keyword_rules/presentation/pages/keyword_rules_page.dart';

void main() {
  late ApiClient apiClient;
  late HttpKeywordRuleRepository repository;
  Completer<http.Response>? pendingToggleResponse;
  Completer<http.Response>? pendingUpdateResponse;
  var toggleRequestCount = 0;
  var updateRequestCount = 0;

  setUp(() {
    pendingToggleResponse = null;
    pendingUpdateResponse = null;
    toggleRequestCount = 0;
    updateRequestCount = 0;
    final mock = MockClient((request) async {
      if (request.method == 'GET' && request.url.path == '/v1/keywords') {
        return http.Response(
          jsonEncode({
            'code': 0,
            'message': 'success',
            'data': {
              'items': [
                {
                  'id': 1,
                  'word': '启用高优词',
                  'is_high_priority': true,
                  'is_active': true,
                  'is_default': true,
                  'created_at': '',
                  'updated_at': '',
                },
                {
                  'id': 2,
                  'word': '启用普通词',
                  'is_high_priority': false,
                  'is_active': true,
                  'created_at': '',
                  'updated_at': '',
                },
                {
                  'id': 3,
                  'word': '停用高优词',
                  'is_high_priority': true,
                  'is_active': false,
                  'created_at': '',
                  'updated_at': '',
                },
              ],
              'total': 3,
            },
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      }

      if (request.method == 'POST' &&
          request.url.path == '/v1/keywords/1/toggle') {
        toggleRequestCount += 1;
        if (pendingToggleResponse != null) {
          return pendingToggleResponse!.future;
        }
        return http.Response(
          jsonEncode({
            'code': 0,
            'message': 'success',
            'data': {
              'id': 1,
              'word': '启用高优词',
              'is_high_priority': true,
              'is_active': false,
              'created_at': '',
              'updated_at': '',
            },
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (request.method == 'PUT' && request.url.path == '/v1/keywords/2') {
        updateRequestCount += 1;
        if (pendingUpdateResponse != null) {
          return pendingUpdateResponse!.future;
        }
        return http.Response(
          jsonEncode({
            'code': 0,
            'message': 'success',
            'data': {
              'id': 2,
              'word': '启用普通词',
              'is_high_priority': false,
              'is_active': true,
              'created_at': '',
              'updated_at': '',
            },
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      }

      return http.Response(
        jsonEncode({'code': 0, 'message': 'success', 'data': {}}),
        200,
        headers: {'content-type': 'application/json'},
      );
    });
    apiClient = ApiClient(baseUrl: 'http://localhost', httpClient: mock);
    repository = HttpKeywordRuleRepository(apiClient: apiClient);
  });

  tearDown(() {
    apiClient.dispose();
  });

  Future<void> pumpPage(WidgetTester tester) async {
    tester.view.physicalSize = const Size(1440, 1000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: Scaffold(
          body: KeywordRulesPage(repository: repository),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('metric cards filter all, enabled, and high priority rules',
      (tester) async {
    await pumpPage(tester);

    expect(find.text('启用高优词'), findsOneWidget);
    expect(find.text('启用普通词'), findsOneWidget);
    expect(find.text('停用高优词'), findsOneWidget);

    await tester.tap(find.byKey(const Key('keyword-rule-filter-enabled')));
    await tester.pumpAndSettle();

    expect(find.text('启用高优词'), findsOneWidget);
    expect(find.text('启用普通词'), findsOneWidget);
    expect(find.text('停用高优词'), findsNothing);

    await tester.tap(find.byKey(const Key('keyword-rule-filter-highPriority')));
    await tester.pumpAndSettle();

    expect(find.text('启用高优词'), findsOneWidget);
    expect(find.text('启用普通词'), findsNothing);
    expect(find.text('停用高优词'), findsOneWidget);

    await tester.tap(find.byKey(const Key('keyword-rule-filter-all')));
    await tester.pumpAndSettle();

    expect(find.text('启用普通词'), findsOneWidget);
    expect(find.text('停用高优词'), findsOneWidget);
    expect(
      tester.getSize(find.byKey(const Key('keyword-rule-filter-all'))).height,
      greaterThanOrEqualTo(44),
    );
  });

  testWidgets(
      'tapping a rule row opens edit while its switch stays independent',
      (tester) async {
    await pumpPage(tester);

    await tester.tap(find.text('启用普通词'));
    await tester.pumpAndSettle();

    expect(find.text('编辑关键字'), findsOneWidget);
    await tester.tap(find.text('取消'));
    await tester.pumpAndSettle();

    await tester.tap(find.byType(Switch).at(1));
    await tester.pump();

    expect(find.text('编辑关键字'), findsNothing);
  });

  testWidgets(
      'default rule is labeled and keeps only configurable fields editable',
      (tester) async {
    await pumpPage(tester);

    expect(find.text('系统默认'), findsOneWidget);
    await tester.tap(find.text('启用高优词'));
    await tester.pumpAndSettle();

    expect(tester.widget<TextFormField>(find.byType(TextFormField)).enabled,
        isFalse);
    expect(find.text('默认词不能改名或删除，可调整优先级和启用状态。'), findsOneWidget);
  });

  testWidgets(
      'pending rule toggle visibly disables the row and ignores a second tap',
      (tester) async {
    await pumpPage(tester);
    pendingToggleResponse = Completer<http.Response>();

    final switchFinder = find.byKey(const Key('keyword-rule-active-switch-1'));
    await tester.tap(switchFinder);
    await tester.pump();

    expect(toggleRequestCount, 1);
    expect(tester.widget<Switch>(switchFinder).onChanged, isNull);
    expect(
      find.byKey(const Key('keyword-rule-progress-1')),
      findsOneWidget,
    );

    await tester.tap(switchFinder);
    await tester.pump();
    expect(toggleRequestCount, 1);

    pendingToggleResponse!.complete(
      http.Response(
        jsonEncode({
          'code': 0,
          'message': 'success',
          'data': {
            'id': 1,
            'word': '启用高优词',
            'is_high_priority': true,
            'is_active': false,
            'created_at': '',
            'updated_at': '',
          },
        }),
        200,
        headers: {'content-type': 'application/json'},
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('keyword-rule-progress-1')), findsNothing);
  });

  testWidgets('pending rule save stays open, disables save, and shows progress',
      (tester) async {
    await pumpPage(tester);
    pendingUpdateResponse = Completer<http.Response>();

    await tester.tap(find.text('启用普通词'));
    await tester.pumpAndSettle();
    final saveButton = find.byKey(const Key('keyword-rule-dialog-save'));
    await tester.tap(saveButton);
    await tester.pump();

    expect(updateRequestCount, 1);
    expect(find.text('编辑关键字'), findsOneWidget);
    expect(tester.widget<FilledButton>(saveButton).onPressed, isNull);
    expect(
      find.descendant(
        of: saveButton,
        matching: find.byType(CircularProgressIndicator),
      ),
      findsOneWidget,
    );

    await tester.tap(saveButton);
    await tester.pump();
    expect(updateRequestCount, 1);

    pendingUpdateResponse!.complete(
      http.Response(
        jsonEncode({
          'code': 0,
          'message': 'success',
          'data': {
            'id': 2,
            'word': '启用普通词',
            'is_high_priority': false,
            'is_active': true,
            'created_at': '',
            'updated_at': '',
          },
        }),
        200,
        headers: {'content-type': 'application/json'},
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('编辑关键字'), findsNothing);
  });
}
