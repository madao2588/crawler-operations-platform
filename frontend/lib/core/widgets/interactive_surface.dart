import 'package:flutter/material.dart';

class AppInteractiveSurface extends StatefulWidget {
  final Widget child;
  final VoidCallback? onTap;
  final String semanticLabel;
  final BorderRadius borderRadius;

  const AppInteractiveSurface({
    super.key,
    required this.child,
    required this.onTap,
    required this.semanticLabel,
    this.borderRadius = const BorderRadius.all(Radius.circular(16)),
  });

  @override
  State<AppInteractiveSurface> createState() => _AppInteractiveSurfaceState();
}

class _AppInteractiveSurfaceState extends State<AppInteractiveSurface> {
  bool _pressed = false;

  void _handleHighlightChanged(bool value) {
    if (_pressed == value) {
      return;
    }
    setState(() {
      _pressed = value;
    });
  }

  @override
  Widget build(BuildContext context) {
    final enabled = widget.onTap != null;

    return Semantics(
      button: enabled,
      enabled: enabled,
      label: widget.semanticLabel,
      child: MouseRegion(
        cursor: enabled ? SystemMouseCursors.click : MouseCursor.defer,
        child: AnimatedScale(
          scale: _pressed ? 0.985 : 1,
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOutCubic,
          child: Material(
            color: Colors.transparent,
            child: InkWell(
              onTap: widget.onTap,
              onHighlightChanged: enabled ? _handleHighlightChanged : null,
              borderRadius: widget.borderRadius,
              hoverColor:
                  Theme.of(context).colorScheme.primary.withValues(alpha: 0.05),
              focusColor:
                  Theme.of(context).colorScheme.primary.withValues(alpha: 0.08),
              splashColor:
                  Theme.of(context).colorScheme.primary.withValues(alpha: 0.10),
              canRequestFocus: enabled,
              child: ConstrainedBox(
                constraints: const BoxConstraints(minHeight: 44, minWidth: 44),
                child: widget.child,
              ),
            ),
          ),
        ),
      ),
    );
  }
}
