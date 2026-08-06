import 'package:flutter/material.dart';

class AppPageFrame extends StatelessWidget {
  final Widget child;
  final double? maxWidth;
  final EdgeInsetsGeometry padding;

  const AppPageFrame({
    super.key,
    required this.child,
    this.maxWidth,
    this.padding = const EdgeInsets.all(24),
  });

  @override
  Widget build(BuildContext context) {
    final content = Padding(
      padding: padding,
      child: SizedBox(
        width: double.infinity,
        child: child,
      ),
    );

    if (maxWidth == null) {
      return content;
    }

    return Align(
      alignment: Alignment.topCenter,
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: maxWidth!),
        child: content,
      ),
    );
  }
}

class AppPill extends StatelessWidget {
  final String label;
  final Color backgroundColor;
  final Color foregroundColor;
  final Color? borderColor;
  final EdgeInsetsGeometry padding;

  const AppPill({
    super.key,
    required this.label,
    required this.backgroundColor,
    required this.foregroundColor,
    this.borderColor,
    this.padding = const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
  });

  const AppPill.overlay({
    super.key,
    required this.label,
    this.padding = const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
  })  : backgroundColor = const Color(0x24FFFFFF),
        foregroundColor = Colors.white,
        borderColor = const Color(0x44FFFFFF);

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: padding,
      decoration: BoxDecoration(
        color: backgroundColor,
        borderRadius: BorderRadius.circular(999),
        border: Border.all(
          color: borderColor ?? backgroundColor.withValues(alpha: 0.2),
        ),
      ),
      child: Text(
        label,
        style: Theme.of(context).textTheme.labelMedium?.copyWith(
              color: foregroundColor,
              fontWeight: FontWeight.w700,
            ),
      ),
    );
  }
}

class AppPageHeroChipData {
  final String label;
  final Color backgroundColor;
  final Color foregroundColor;
  final Color? borderColor;

  const AppPageHeroChipData({
    required this.label,
    required this.backgroundColor,
    required this.foregroundColor,
    this.borderColor,
  });

  const AppPageHeroChipData.overlay(String label)
      : this(
          label: label,
          backgroundColor: const Color(0x24FFFFFF),
          foregroundColor: Colors.white,
          borderColor: const Color(0x44FFFFFF),
        );
}

class AppPageHero extends StatelessWidget {
  final String title;
  final String subtitle;
  final List<AppPageHeroChipData> primaryChips;
  final List<AppPageHeroChipData> secondaryChips;
  final List<Widget> actions;
  final double compactBreakpoint;

  const AppPageHero({
    super.key,
    required this.title,
    required this.subtitle,
    this.primaryChips = const [],
    this.secondaryChips = const [],
    this.actions = const [],
    this.compactBreakpoint = 820,
  });

  List<Widget> _separatedActions() {
    final widgets = <Widget>[];
    for (var i = 0; i < actions.length; i += 1) {
      if (i > 0) {
        widgets.add(const SizedBox(height: 10));
      }
      widgets.add(actions[i]);
    }
    return widgets;
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final isCompact = constraints.maxWidth < compactBreakpoint;

        final content = Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              title,
              style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                    color: Colors.white,
                  ),
            ),
            const SizedBox(height: 8),
            Text(
              subtitle,
              style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                    color: const Color(0xE6F3F8FF),
                  ),
            ),
            if (primaryChips.isNotEmpty) ...[
              const SizedBox(height: 16),
              Wrap(
                spacing: 10,
                runSpacing: 10,
                children: primaryChips
                    .map(
                      (chip) => AppPill(
                        label: chip.label,
                        backgroundColor: chip.backgroundColor,
                        foregroundColor: chip.foregroundColor,
                        borderColor: chip.borderColor,
                      ),
                    )
                    .toList(),
              ),
            ],
            if (secondaryChips.isNotEmpty) ...[
              const SizedBox(height: 14),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: secondaryChips
                    .map(
                      (chip) => AppPill(
                        label: chip.label,
                        backgroundColor: chip.backgroundColor,
                        foregroundColor: chip.foregroundColor,
                        borderColor: chip.borderColor,
                      ),
                    )
                    .toList(),
              ),
            ],
          ],
        );

        final actionBlock = actions.isEmpty
            ? null
            : isCompact
                ? Wrap(
                    spacing: 10,
                    runSpacing: 10,
                    children: actions,
                  )
                : Column(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    mainAxisSize: MainAxisSize.min,
                    children: _separatedActions(),
                  );

        return Container(
          width: double.infinity,
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [
                Color(0xFF1D4E89),
                Color(0xFF235F9B),
                Color(0xFF13786A),
              ],
            ),
            borderRadius: BorderRadius.circular(28),
            boxShadow: const [
              BoxShadow(
                color: Color(0x281D4E89),
                blurRadius: 30,
                offset: Offset(0, 16),
              ),
            ],
          ),
          child: isCompact
              ? Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    content,
                    if (actionBlock != null) ...[
                      const SizedBox(height: 16),
                      actionBlock,
                    ],
                  ],
                )
              : Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(child: content),
                    if (actionBlock != null) ...[
                      const SizedBox(width: 16),
                      actionBlock,
                    ],
                  ],
                ),
        );
      },
    );
  }
}
