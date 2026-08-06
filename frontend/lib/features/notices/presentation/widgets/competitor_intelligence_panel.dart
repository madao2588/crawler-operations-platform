import 'package:flutter/material.dart';

class CompetitorIntelligencePanel extends StatelessWidget {
  final Map<String, dynamic> metadata;
  final String contentText;
  final String publishedAtLabel;

  const CompetitorIntelligencePanel({
    super.key,
    required this.metadata,
    required this.contentText,
    required this.publishedAtLabel,
  });

  String _text(String key, {String fallback = '未提供'}) {
    final value = metadata[key];
    if (value is List) {
      final items = _items(key);
      return items.isEmpty ? fallback : items.join('、');
    }
    final text = value?.toString().trim() ?? '';
    return text.isEmpty ? fallback : text;
  }

  List<String> _items(String key) {
    final value = metadata[key];
    if (value is! List) {
      final text = value?.toString().trim() ?? '';
      return text.isEmpty ? const [] : [text];
    }
    return value
        .map((item) => item.toString().trim())
        .where((item) => item.isNotEmpty)
        .toSet()
        .toList();
  }

  @override
  Widget build(BuildContext context) {
    final source = _text('source', fallback: 'PubMed');
    final isClinicalTrial = source == 'ClinicalTrials.gov';
    final topic = _text('topic');
    final externalId = _text('external_id');
    final abstractText = extractCompetitorAbstract(contentText);
    final drugs = _items('drugs');
    final organizations = _items('organizations');
    final authors = _items('authors');
    final publicationTypes = _items('publication_types');
    final keywords = _items('keywords');
    final targets = _items('targets');
    final countries = _items('countries');
    final collaborators = _items('collaborators');
    final conditions = _items('conditions');

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _EvidenceHeader(
          source: source,
          topic: topic,
          externalId: externalId,
          identifierLabel: isClinicalTrial ? '试验编号' : 'PMID',
        ),
        const SizedBox(height: 16),
        _EvidenceMetrics(
          stage: _text('development_stage'),
          evidenceLevel: _text('evidence_level'),
          publishedAt: publishedAtLabel,
          externalId: externalId,
          isClinicalTrial: isClinicalTrial,
          trialStatus: _text('trial_status'),
          sponsor: _text('sponsor'),
        ),
        const SizedBox(height: 20),
        LayoutBuilder(
          builder: (context, constraints) {
            final mainContent = _MainEvidenceContent(
              drugs: drugs,
              targets: targets,
              abstractText: abstractText,
            );
            final referenceContent = _ReferenceSidebar(
              source: source,
              journal: _text('journal'),
              doi: _text('doi'),
              publicationTypes: publicationTypes,
              organizations: organizations,
              authors: authors,
              keywords: keywords,
              isClinicalTrial: isClinicalTrial,
              sponsor: _text('sponsor'),
              collaborators: collaborators,
              countries: countries,
              conditions: conditions,
            );

            if (constraints.maxWidth >= 840) {
              return Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(flex: 5, child: mainContent),
                  const SizedBox(width: 16),
                  SizedBox(width: 320, child: referenceContent),
                ],
              );
            }

            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                mainContent,
                const SizedBox(height: 16),
                referenceContent,
              ],
            );
          },
        ),
      ],
    );
  }
}

String extractCompetitorAbstract(String contentText) {
  final normalized = contentText.replaceAll('\r\n', '\n').trim();
  if (normalized.isEmpty) {
    return '当前文献暂无可展示的摘要。';
  }

  const markers = [
    '\n摘要：\n',
    '\n摘要:\n',
    '\nAbstract:\n',
    '\nABSTRACT:\n',
    '\n研究摘要：\n',
  ];
  for (final marker in markers) {
    final index = normalized.indexOf(marker);
    if (index >= 0) {
      final abstractText = normalized.substring(index + marker.length).trim();
      if (abstractText.isNotEmpty) {
        return abstractText;
      }
    }
  }

  if (normalized.startsWith('摘要：') || normalized.startsWith('摘要:')) {
    return normalized.substring(3).trim();
  }
  return normalized;
}

class _EvidenceHeader extends StatelessWidget {
  final String source;
  final String topic;
  final String externalId;
  final String identifierLabel;

  const _EvidenceHeader({
    required this.source,
    required this.topic,
    required this.externalId,
    required this.identifierLabel,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: const Color(0xFFF3F7FD),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFDCE6F3)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: const Color(0xFFDCE9FA),
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Icon(
              Icons.biotech_outlined,
              color: Color(0xFF1E4F8A),
              size: 24,
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    Text(
                      '研究证据概览',
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                    _SourceBadge(label: source),
                  ],
                ),
                const SizedBox(height: 6),
                Text(
                  '$topic · $identifierLabel $externalId',
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: const Color(0xFF536780),
                        fontWeight: FontWeight.w500,
                      ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _SourceBadge extends StatelessWidget {
  final String label;

  const _SourceBadge({required this.label});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: const Color(0xFFCAD9EC)),
      ),
      child: Text(
        label,
        style: const TextStyle(
          color: Color(0xFF1E4F8A),
          fontSize: 12,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}

class _EvidenceMetrics extends StatelessWidget {
  final String stage;
  final String evidenceLevel;
  final String publishedAt;
  final String externalId;
  final bool isClinicalTrial;
  final String trialStatus;
  final String sponsor;

  const _EvidenceMetrics({
    required this.stage,
    required this.evidenceLevel,
    required this.publishedAt,
    required this.externalId,
    required this.isClinicalTrial,
    required this.trialStatus,
    required this.sponsor,
  });

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        const gap = 12.0;
        final columns = constraints.maxWidth >= 760
            ? 4
            : constraints.maxWidth >= 280
                ? 2
                : 1;
        final itemWidth =
            (constraints.maxWidth - gap * (columns - 1)) / columns;

        return Wrap(
          spacing: gap,
          runSpacing: gap,
          children: [
            _MetricCard(
              width: itemWidth,
              icon: Icons.timeline_outlined,
              label: '研发阶段',
              value: stage,
              accent: const Color(0xFF1E4F8A),
              tint: const Color(0xFFEAF2FC),
            ),
            _MetricCard(
              width: itemWidth,
              icon: isClinicalTrial
                  ? Icons.sync_alt_outlined
                  : Icons.verified_outlined,
              label: isClinicalTrial ? '试验状态' : '证据等级',
              value: isClinicalTrial ? trialStatus : evidenceLevel,
              accent: const Color(0xFF117A65),
              tint: const Color(0xFFE8F5F1),
            ),
            _MetricCard(
              width: itemWidth,
              icon: isClinicalTrial
                  ? Icons.apartment_outlined
                  : Icons.event_outlined,
              label: isClinicalTrial ? '申办方' : '发表日期',
              value: isClinicalTrial ? sponsor : publishedAt,
              accent: const Color(0xFF8A5A16),
              tint: const Color(0xFFFFF4DF),
            ),
            _MetricCard(
              width: itemWidth,
              icon: Icons.fingerprint,
              label: isClinicalTrial ? '试验编号' : 'PMID',
              value: externalId,
              accent: const Color(0xFF5A4A9C),
              tint: const Color(0xFFF0EDFA),
            ),
          ],
        );
      },
    );
  }
}

class _MetricCard extends StatelessWidget {
  final double width;
  final IconData icon;
  final String label;
  final String value;
  final Color accent;
  final Color tint;

  const _MetricCard({
    required this.width,
    required this.icon,
    required this.label,
    required this.value,
    required this.accent,
    required this.tint,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: width,
      child: Container(
        constraints: const BoxConstraints(minHeight: 104),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: const Color(0xFFE0E7F0)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 32,
                  height: 32,
                  decoration: BoxDecoration(
                    color: tint,
                    borderRadius: BorderRadius.circular(9),
                  ),
                  child: Icon(icon, size: 18, color: accent),
                ),
                const SizedBox(width: 9),
                Expanded(
                  child: Text(
                    label,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: const Color(0xFF62748B),
                          fontWeight: FontWeight.w600,
                        ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Text(
              value,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    color: const Color(0xFF172B47),
                    fontWeight: FontWeight.w700,
                  ),
            ),
          ],
        ),
      ),
    );
  }
}

class _MainEvidenceContent extends StatelessWidget {
  final List<String> drugs;
  final List<String> targets;
  final String abstractText;

  const _MainEvidenceContent({
    required this.drugs,
    required this.targets,
    required this.abstractText,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _SectionCard(
          icon: Icons.medication_outlined,
          title: '药物与化学物质',
          child: drugs.isEmpty
              ? const _EmptyValue(text: '当前文献未结构化标注药物或化学物质。')
              : Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children:
                      drugs.map((item) => _EvidenceChip(label: item)).toList(),
                ),
        ),
        if (targets.isNotEmpty) ...[
          const SizedBox(height: 16),
          _SectionCard(
            icon: Icons.track_changes_outlined,
            title: '靶点',
            child: Wrap(
              spacing: 8,
              runSpacing: 8,
              children:
                  targets.map((item) => _EvidenceChip(label: item)).toList(),
            ),
          ),
        ],
        const SizedBox(height: 16),
        _SectionCard(
          icon: Icons.article_outlined,
          title: '研究摘要',
          child: SelectableText(
            abstractText,
            style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                  color: const Color(0xFF2E4058),
                  height: 1.75,
                ),
          ),
        ),
      ],
    );
  }
}

class _ReferenceSidebar extends StatelessWidget {
  final String source;
  final String journal;
  final String doi;
  final List<String> publicationTypes;
  final List<String> organizations;
  final List<String> authors;
  final List<String> keywords;
  final bool isClinicalTrial;
  final String sponsor;
  final List<String> collaborators;
  final List<String> countries;
  final List<String> conditions;

  const _ReferenceSidebar({
    required this.source,
    required this.journal,
    required this.doi,
    required this.publicationTypes,
    required this.organizations,
    required this.authors,
    required this.keywords,
    required this.isClinicalTrial,
    required this.sponsor,
    required this.collaborators,
    required this.countries,
    required this.conditions,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (isClinicalTrial)
          _SectionCard(
            icon: Icons.science_outlined,
            title: '临床试验资料',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _InfoRow(label: '数据库', value: source),
                const SizedBox(height: 12),
                _InfoRow(label: '申办方', value: sponsor),
                const SizedBox(height: 14),
                _CompactTagGroup(
                  label: '涉及国家/地区',
                  items: countries,
                  emptyText: '未提供国家或地区信息',
                ),
                const SizedBox(height: 14),
                _CompactTagGroup(
                  label: '适应症',
                  items: conditions,
                  emptyText: '未提供适应症信息',
                ),
              ],
            ),
          )
        else
          _SectionCard(
            icon: Icons.library_books_outlined,
            title: '文献资料',
            child: Column(
              children: [
                _InfoRow(label: '数据库', value: source),
                const SizedBox(height: 12),
                _InfoRow(label: '期刊', value: journal),
                const SizedBox(height: 12),
                _InfoRow(label: 'DOI', value: doi, selectable: true),
                if (publicationTypes.isNotEmpty) ...[
                  const SizedBox(height: 14),
                  _CompactTagGroup(
                    label: '文献类型',
                    items: publicationTypes,
                  ),
                ],
              ],
            ),
          ),
        const SizedBox(height: 16),
        _SectionCard(
          icon: Icons.groups_2_outlined,
          title: isClinicalTrial ? '试验协作机构' : '研究团队',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _CompactTagGroup(
                label: isClinicalTrial ? '合作机构' : '研究机构',
                items: isClinicalTrial ? collaborators : organizations,
                emptyText: isClinicalTrial ? '未提供合作机构' : '未提供机构信息',
              ),
              if (!isClinicalTrial) ...[
                const SizedBox(height: 14),
                _CompactTagGroup(
                  label: '作者',
                  items: authors,
                  emptyText: '未提供作者信息',
                ),
              ],
            ],
          ),
        ),
        if (keywords.isNotEmpty) ...[
          const SizedBox(height: 16),
          _SectionCard(
            icon: Icons.sell_outlined,
            title: '检索标签',
            child: Wrap(
              spacing: 8,
              runSpacing: 8,
              children:
                  keywords.map((item) => _SubtleChip(label: item)).toList(),
            ),
          ),
        ],
      ],
    );
  }
}

class _SectionCard extends StatelessWidget {
  final IconData icon;
  final String title;
  final Widget child;

  const _SectionCard({
    required this.icon,
    required this.title,
    required this.child,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFE0E7F0)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: 19, color: const Color(0xFF1E4F8A)),
              const SizedBox(width: 9),
              Expanded(
                child: Text(
                  title,
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        color: const Color(0xFF1A3151),
                        fontWeight: FontWeight.w700,
                      ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          child,
        ],
      ),
    );
  }
}

class _EvidenceChip extends StatelessWidget {
  final String label;

  const _EvidenceChip({required this.label});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: const Color(0xFFEAF2FC),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: const Color(0xFFD1E1F4)),
      ),
      child: Text(
        label,
        style: const TextStyle(
          color: Color(0xFF1E4F8A),
          fontWeight: FontWeight.w700,
          fontSize: 13,
        ),
      ),
    );
  }
}

class _SubtleChip extends StatelessWidget {
  final String label;

  const _SubtleChip({required this.label});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
      decoration: BoxDecoration(
        color: const Color(0xFFF4F6F9),
        borderRadius: BorderRadius.circular(9),
      ),
      child: Text(
        label,
        style: Theme.of(context).textTheme.bodySmall?.copyWith(
              color: const Color(0xFF4F6279),
              fontWeight: FontWeight.w600,
            ),
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  final String label;
  final String value;
  final bool selectable;

  const _InfoRow({
    required this.label,
    required this.value,
    this.selectable = false,
  });

  @override
  Widget build(BuildContext context) {
    final valueStyle = Theme.of(context).textTheme.bodyMedium?.copyWith(
          color: const Color(0xFF263B56),
          fontWeight: FontWeight.w600,
        );

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 58,
          child: Text(
            label,
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: const Color(0xFF738297),
                  fontWeight: FontWeight.w600,
                ),
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: selectable
              ? SelectableText(value, style: valueStyle)
              : Text(value, style: valueStyle),
        ),
      ],
    );
  }
}

class _CompactTagGroup extends StatelessWidget {
  final String label;
  final List<String> items;
  final String emptyText;

  const _CompactTagGroup({
    required this.label,
    required this.items,
    this.emptyText = '未提供',
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: const Color(0xFF738297),
                fontWeight: FontWeight.w600,
              ),
        ),
        const SizedBox(height: 7),
        Text(
          items.isEmpty ? emptyText : items.join('、'),
          style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                color: const Color(0xFF2D425B),
                height: 1.55,
              ),
        ),
      ],
    );
  }
}

class _EmptyValue extends StatelessWidget {
  final String text;

  const _EmptyValue({required this.text});

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: Theme.of(context).textTheme.bodyMedium?.copyWith(
            color: const Color(0xFF738297),
          ),
    );
  }
}
