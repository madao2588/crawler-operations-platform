import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:pharma_bid_monitor_frontend/core/network/api_client.dart';
import 'package:pharma_bid_monitor_frontend/features/system_management/data/repositories/http_template_repository.dart';

void main() {
  test('collectManualSource posts article URL and parses notice result', () async {
    final mock = MockClient((request) async {
      expect(request.method, 'POST');
      expect(
        request.url.path,
        '/v1/templates/tasks/wechat_k_innovation/collect',
      );
      expect(
        jsonDecode(request.body),
        {'url': 'https://mp.weixin.qq.com/s/article'},
      );
      return http.Response(
        jsonEncode({
          'code': 0,
          'message': 'success',
          'data': {
            'source_id': 'wechat_k_innovation',
            'source_url': 'https://mp.weixin.qq.com/s/article',
            'status': 'stored',
            'notice_id': 88,
          },
        }),
        200,
      );
    });
    final client = ApiClient(baseUrl: 'http://localhost', httpClient: mock);
    final repository = HttpTemplateRepository(apiClient: client);

    final result = await repository.collectManualSource(
      'wechat_k_innovation',
      'https://mp.weixin.qq.com/s/article',
    );

    expect(result.noticeId, 88);
    expect(result.status, 'stored');
    expect(result.sourceUrl, 'https://mp.weixin.qq.com/s/article');
    client.dispose();
  });
}
