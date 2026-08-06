import 'package:flutter_test/flutter_test.dart';
import 'package:pharma_bid_monitor_frontend/features/notices/data/models/notice_models.dart';

void main() {
  test('notice detail parses competitor intelligence metadata', () {
    final model = NoticeDetailModel.fromJson({
      'id': 1,
      'title': 'Targeted therapy for glioblastoma',
      'summary': 'Abstract',
      'source_site': 'pubmed.ncbi.nlm.nih.gov',
      'source_url': 'https://pubmed.ncbi.nlm.nih.gov/12345678/',
      'published_at': '2026-07-20T00:00:00Z',
      'captured_at': '2026-07-28T00:00:00Z',
      'quality_score': 90,
      'matched_keywords': <String>[],
      'is_high_priority': false,
      'category': '竞品信息',
      'review_status': '待关注',
      'is_archived': false,
      'task_id': 1,
      'content_text': 'Abstract',
      'content_html': '<p>Abstract</p>',
      'metadata': {
        'kind': 'competitor_intelligence',
        'topic': '脑胶质瘤',
        'external_id': '12345678',
        'drugs': ['Examplemab'],
        'development_stage': '临床Ⅱ期',
        'evidence_level': '临床试验证据',
      },
    });

    expect(model.metadata?['kind'], 'competitor_intelligence');
    expect(model.metadata?['topic'], '脑胶质瘤');
    expect(model.metadata?['drugs'], ['Examplemab']);
  });
}
