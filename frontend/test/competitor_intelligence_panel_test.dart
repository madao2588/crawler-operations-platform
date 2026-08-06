import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pharma_bid_monitor_frontend/core/theme/app_theme.dart';
import 'package:pharma_bid_monitor_frontend/features/notices/presentation/widgets/competitor_intelligence_panel.dart';

void main() {
  const metadata = <String, dynamic>{
    'kind': 'competitor_intelligence',
    'source': 'PubMed',
    'topic': '脑胶质瘤',
    'external_id': '12345678',
    'doi': '10.1000/example.2026.001',
    'journal': 'Journal of Translational Medicine',
    'development_stage': '临床Ⅱ期',
    'evidence_level': '临床试验证据',
    'drugs': <String>['Examplemab', 'Temozolomide'],
    'organizations': <String>[
      'National Center for Translational Medicine',
      'University Hospital',
    ],
    'authors': <String>['Zhang San', 'Li Si'],
    'publication_types': <String>['Clinical Trial', 'Journal Article'],
    'keywords': <String>['glioblastoma', 'targeted therapy'],
  };

  const contentText = '''
研究方向：脑胶质瘤
PMID：12345678
DOI：10.1000/example.2026.001

摘要：
This phase II study evaluated Examplemab in recurrent glioblastoma.
The treatment showed a measurable response with a manageable safety profile.
''';

  testWidgets('renders competitor evidence in clear semantic sections',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: const Scaffold(
          body: SingleChildScrollView(
            child: CompetitorIntelligencePanel(
              metadata: metadata,
              contentText: contentText,
              publishedAtLabel: '2026-07-20',
            ),
          ),
        ),
      ),
    );

    expect(find.text('研究证据概览'), findsOneWidget);
    expect(find.text('研发阶段'), findsOneWidget);
    expect(find.text('临床Ⅱ期'), findsOneWidget);
    expect(find.text('证据等级'), findsOneWidget);
    expect(find.text('临床试验证据'), findsOneWidget);
    expect(find.text('药物与化学物质'), findsOneWidget);
    expect(find.text('Examplemab'), findsOneWidget);
    expect(find.text('研究摘要'), findsOneWidget);
    expect(
      find.textContaining('This phase II study evaluated Examplemab'),
      findsOneWidget,
    );
    expect(find.textContaining('研究方向：脑胶质瘤'), findsNothing);
    expect(find.text('正文内容'), findsNothing);
  });

  testWidgets('keeps long evidence content readable on a narrow viewport',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: const Scaffold(
          body: SingleChildScrollView(
            padding: EdgeInsets.all(16),
            child: CompetitorIntelligencePanel(
              metadata: metadata,
              contentText: contentText,
              publishedAtLabel: '2026-07-20',
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    expect(tester.takeException(), isNull);
    expect(
      tester.getTopLeft(find.text('研发阶段')).dy,
      tester.getTopLeft(find.text('证据等级')).dy,
    );
    expect(find.text('文献资料'), findsOneWidget);
    expect(find.text('研究团队'), findsOneWidget);
    expect(find.text('10.1000/example.2026.001'), findsOneWidget);
  });

  testWidgets('renders ClinicalTrials.gov records without PubMed-only labels',
      (tester) async {
    const clinicalMetadata = <String, dynamic>{
      'kind': 'competitor_intelligence',
      'source': 'ClinicalTrials.gov',
      'topic': '脑胶质瘤',
      'external_id': 'NCT87654321',
      'development_stage': 'Phase 2',
      'evidence_level': '临床试验注册证据',
      'trial_status': 'recruiting',
      'sponsor': 'Example Therapeutics',
      'drugs': <String>['EX-101'],
      'targets': <String>['EGFR'],
      'countries': <String>['China', 'United States'],
      'collaborators': <String>['Example University'],
      'trial_ids': <String>['NCT87654321'],
      'conditions': <String>['Glioblastoma'],
      'keywords': <String>['glioma'],
    };
    const clinicalContent = '''
研究方向：脑胶质瘤
试验编号：NCT87654321

研究摘要：
Recruiting phase 2 study of EX-101.
''';

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: const Scaffold(
          body: SingleChildScrollView(
            child: CompetitorIntelligencePanel(
              metadata: clinicalMetadata,
              contentText: clinicalContent,
              publishedAtLabel: '未提供',
            ),
          ),
        ),
      ),
    );

    expect(find.text('ClinicalTrials.gov'), findsWidgets);
    expect(find.text('试验编号'), findsOneWidget);
    expect(find.text('NCT87654321'), findsWidgets);
    expect(find.text('试验状态'), findsOneWidget);
    expect(find.text('recruiting'), findsOneWidget);
    expect(find.text('申办方'), findsWidgets);
    expect(find.text('Example Therapeutics'), findsWidgets);
    expect(find.text('靶点'), findsOneWidget);
    expect(find.text('EGFR'), findsOneWidget);
    expect(find.text('涉及国家/地区'), findsOneWidget);
    expect(find.textContaining('China'), findsOneWidget);
    expect(find.textContaining('PMID'), findsNothing);
    expect(
      find.textContaining('Recruiting phase 2 study of EX-101.'),
      findsOneWidget,
    );
  });
}
