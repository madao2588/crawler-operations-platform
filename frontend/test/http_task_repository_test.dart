import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:pharma_bid_monitor_frontend/core/network/api_client.dart';
import 'package:pharma_bid_monitor_frontend/features/system_management/data/repositories/http_task_repository.dart';

void main() {
  test('HttpTaskRepository.fetchTasks parses envelope', () async {
    final mock = MockClient((request) async {
      expect(request.method, 'GET');
      expect(request.url.path, '/v1/tasks');
      expect(request.url.queryParameters['page'], '1');
      expect(request.url.queryParameters['sort_by'], 'name');
      return http.Response(
        jsonEncode({
          'code': 0,
          'message': 'success',
          'data': {
            'items': [
              {
                'id': 42,
                'name': 'Repo Task',
                'start_url': 'https://a.example',
                'parser_rules': null,
                'cron_expr': '0 * * * *',
                'status': 1,
                'last_run_status': 'success',
                'last_run_at': null,
                'last_success_at': null,
                'last_error_message': null,
                'created_at': '2024-06-01T00:00:00',
              },
            ],
            'total': 99,
            'page': 1,
            'page_size': 20,
          },
        }),
        200,
      );
    });
    final client = ApiClient(baseUrl: 'http://localhost', httpClient: mock);
    final repo = HttpTaskRepository(apiClient: client);
    final page = await repo.fetchTasks(
      page: 1,
      pageSize: 20,
      sortBy: 'name',
    );
    expect(page.total, 99);
    expect(page.items.single.id, 42);
    expect(page.items.single.name, 'Repo Task');
    client.dispose();
  });

  test('HttpTaskRepository.hasActiveOrQueuedTasksGlobally uses total',
      () async {
    final mock = MockClient((request) async {
      expect(request.url.queryParameters['last_run'], 'active');
      expect(request.url.queryParameters['page_size'], '1');
      return http.Response(
        jsonEncode({
          'code': 0,
          'message': 'success',
          'data': {
            'items': [],
            'total': 2,
            'page': 1,
            'page_size': 1,
          },
        }),
        200,
      );
    });
    final client = ApiClient(baseUrl: 'http://localhost', httpClient: mock);
    final repo = HttpTaskRepository(apiClient: client);
    expect(await repo.hasActiveOrQueuedTasksGlobally(), isTrue);
    client.dispose();
  });

  test('HttpTaskRepository.fetchTasksByNames paginates until all matches are found',
      () async {
    final mock = MockClient((request) async {
      expect(request.method, 'GET');
      expect(request.url.path, '/v1/tasks');
      expect(request.url.queryParameters['page_size'], '100');
      expect(request.url.queryParameters['sort_by'], 'name');
      final page = request.url.queryParameters['page'];
      if (page == '1') {
        return http.Response(
          jsonEncode({
            'code': 0,
            'message': 'success',
            'data': {
              'items': [
                {
                  'id': 1,
                  'name': 'Alpha Task',
                  'start_url': 'https://alpha.example',
                  'parser_rules': null,
                  'cron_expr': '0 * * * *',
                  'status': 1,
                  'last_run_status': 'success',
                  'last_run_at': null,
                  'last_success_at': null,
                  'last_error_message': null,
                  'created_at': '2024-06-01T00:00:00',
                },
              ],
              'total': 101,
              'page': 1,
              'page_size': 100,
            },
          }),
          200,
        );
      }
      expect(page, '2');
      return http.Response(
        jsonEncode({
          'code': 0,
          'message': 'success',
          'data': {
            'items': [
              {
                'id': 2,
                'name': 'Beta Task',
                'start_url': 'https://beta.example',
                'parser_rules': null,
                'cron_expr': '0 * * * *',
                'status': 1,
                'last_run_status': 'failed',
                'last_run_at': null,
                'last_success_at': null,
                'last_error_message': null,
                'created_at': '2024-06-01T00:00:00',
              },
            ],
            'total': 101,
            'page': 2,
            'page_size': 100,
          },
        }),
        200,
      );
    });
    final client = ApiClient(baseUrl: 'http://localhost', httpClient: mock);
    final repo = HttpTaskRepository(apiClient: client);
    final tasks = await repo.fetchTasksByNames(const ['Alpha Task', 'Beta Task']);
    expect(tasks.map((task) => task.name).toList(), ['Alpha Task', 'Beta Task']);
    client.dispose();
  });

  test('HttpTaskRepository.fetchTaskLogs parses run_summary payload', () async {
    final mock = MockClient((request) async {
      expect(request.method, 'GET');
      expect(request.url.path, '/v1/logs');
      expect(request.url.queryParameters['task_id'], '9');
      expect(request.url.queryParameters['only_summary'], isNull);
      return http.Response(
        jsonEncode({
          'code': 0,
          'message': 'success',
          'data': {
            'items': [
              {
                'id': 100,
                'task_id': 9,
                'level': 'INFO',
                'message': '[run=abc] list_follow summary: ...',
                'error_stack': null,
                'run_summary': {
                  'run_id': 'abc',
                  'mode': 'list_follow',
                  'metrics': {
                    'stored': 3,
                    'failed': 1,
                    'detail_limit_hit': true,
                  },
                },
                'created_at': '2024-06-01T01:00:00',
              },
            ],
            'total': 1,
            'page': 1,
            'page_size': 10,
          },
        }),
        200,
      );
    });
    final client = ApiClient(baseUrl: 'http://localhost', httpClient: mock);
    final repo = HttpTaskRepository(apiClient: client);
    final page = await repo.fetchTaskLogs(9);
    expect(page.items.length, 1);
    final first = page.items.first;
    expect(first.runSummary, isNotNull);
    expect(first.runSummary!['mode'], 'list_follow');
    expect((first.runSummary!['metrics'] as Map<String, dynamic>)['stored'], 3);
    client.dispose();
  });

  test('HttpTaskRepository.fetchTaskLogs supports onlySummary query', () async {
    final mock = MockClient((request) async {
      expect(request.method, 'GET');
      expect(request.url.path, '/v1/logs');
      expect(request.url.queryParameters['task_id'], '9');
      expect(request.url.queryParameters['only_summary'], 'true');
      return http.Response(
        jsonEncode({
          'code': 0,
          'message': 'success',
          'data': {
            'items': [],
            'total': 0,
            'page': 1,
            'page_size': 1,
          },
        }),
        200,
      );
    });
    final client = ApiClient(baseUrl: 'http://localhost', httpClient: mock);
    final repo = HttpTaskRepository(apiClient: client);
    final page = await repo.fetchTaskLogs(9, pageSize: 1, onlySummary: true);
    expect(page.items, isEmpty);
    client.dispose();
  });

  test('HttpTaskRepository.runAllEnabledTasks posts run-enabled', () async {
    final mock = MockClient((request) async {
      expect(request.method, 'POST');
      expect(request.url.path, '/v1/tasks/run-enabled');
      return http.Response(
        jsonEncode({
          'code': 0,
          'message': 'success',
          'data': {
            'queued_task_ids': [1, 2],
            'skipped_task_ids': [3],
            'recovered_task_ids': [2],
            'quarantined_task_ids': [5],
            'errors': [],
          },
        }),
        200,
      );
    });
    final client = ApiClient(baseUrl: 'http://localhost', httpClient: mock);
    final repo = HttpTaskRepository(apiClient: client);
    final result = await repo.runAllEnabledTasks();
    expect(result.queuedTaskIds, [1, 2]);
    expect(result.skippedTaskIds, [3]);
    expect(result.recoveredTaskIds, [2]);
    expect(result.quarantinedTaskIds, [5]);
    expect(result.errors, isEmpty);
    client.dispose();
  });

  test('HttpTaskRepository.runTask parses stale recovery flag', () async {
    final mock = MockClient((request) async {
      expect(request.method, 'POST');
      expect(request.url.path, '/v1/tasks/9/run');
      return http.Response(
        jsonEncode({
          'code': 0,
          'message': 'success',
          'data': {
            'task_id': 9,
            'status': 'queued',
            'recovered_stale_run': true,
          },
        }),
        200,
      );
    });
    final client = ApiClient(baseUrl: 'http://localhost', httpClient: mock);
    final repo = HttpTaskRepository(apiClient: client);
    final result = await repo.runTask(9);
    expect(result.taskId, 9);
    expect(result.status, 'queued');
    expect(result.recoveredStaleRun, isTrue);
    client.dispose();
  });
}
