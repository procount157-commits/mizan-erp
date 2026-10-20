// Small pieces every screen shares: loading, errors, empty states, money
// rows, section titles, and the pull-to-refresh loader.
import 'package:flutter/material.dart';

import 'api.dart';
import 'theme.dart';

class Loader<T> extends StatefulWidget {
  final Future<T> Function() load;
  final Widget Function(BuildContext, T, Future<void> Function() reload) builder;
  const Loader({super.key, required this.load, required this.builder});
  @override
  State<Loader<T>> createState() => _LoaderState<T>();
}

class _LoaderState<T> extends State<Loader<T>> {
  T? data;
  Object? error;
  bool busy = true;

  @override
  void initState() {
    super.initState();
    reload();
  }

  Future<void> reload() async {
    setState(() => busy = data == null);
    try {
      final d = await widget.load();
      if (mounted) {
        setState(() {
          data = d;
          error = null;
          busy = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          error = e;
          busy = false;
        });
      }
      if (e is ApiError && e.signedOut && mounted) {
        Navigator.of(context).pushNamedAndRemoveUntil('/login', (_) => false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (busy && data == null) return const Center(child: CircularProgressIndicator(color: Brand.green));
    if (error != null && data == null) {
      return ErrorState(message: error.toString(), onRetry: reload);
    }
    return RefreshIndicator(color: Brand.green, onRefresh: reload, child: widget.builder(context, data as T, reload));
  }
}

class ErrorState extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;
  const ErrorState({super.key, required this.message, required this.onRetry});
  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            const Icon(Icons.wifi_off_rounded, size: 48, color: Brand.muted),
            const SizedBox(height: 12),
            Text(message, textAlign: TextAlign.center, style: const TextStyle(color: Brand.muted)),
            const SizedBox(height: 16),
            OutlinedButton(onPressed: onRetry, child: const Text('إعادة المحاولة')),
          ]),
        ),
      );
}

class EmptyState extends StatelessWidget {
  final IconData icon;
  final String title;
  final String? text;
  const EmptyState({super.key, required this.icon, required this.title, this.text});
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 48, horizontal: 24),
        child: Column(children: [
          Icon(icon, size: 52, color: Brand.green.withValues(alpha: 0.7)),
          const SizedBox(height: 12),
          Text(title, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
          if (text != null) ...[
            const SizedBox(height: 6),
            Text(text!, textAlign: TextAlign.center, style: const TextStyle(color: Brand.muted)),
          ],
        ]),
      );
}

class SectionTitle extends StatelessWidget {
  final String text;
  final Widget? trailing;
  const SectionTitle(this.text, {super.key, this.trailing});
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(4, 20, 4, 10),
        child: Row(children: [
          Expanded(child: Text(text, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800))),
          if (trailing != null) trailing!,
        ]),
      );
}

class ValueRow extends StatelessWidget {
  final String label;
  final String value;
  final Color? color;
  final bool bold;
  const ValueRow(this.label, this.value, {super.key, this.color, this.bold = false});
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 7),
        child: Row(children: [
          Expanded(child: Text(label, style: TextStyle(color: bold ? Brand.ink : Brand.muted, fontWeight: bold ? FontWeight.w700 : FontWeight.w500))),
          Money(value, style: TextStyle(fontWeight: FontWeight.w800, color: color ?? Brand.ink)),
        ]),
      );
}

/// "2,806,500 د.إ" drawn as number then unit, whatever the paragraph
/// direction, as the system's web pages show money.
class Money extends StatelessWidget {
  final String text;
  final TextStyle? style;
  final TextStyle? unitStyle;
  const Money(this.text, {super.key, this.style, this.unitStyle});
  @override
  Widget build(BuildContext context) {
    final t = text.trim();
    final cut = t.lastIndexOf(' ');
    final number = cut > 0 ? t.substring(0, cut) : t;
    final unit = cut > 0 ? t.substring(cut + 1) : '';
    final base = style ?? DefaultTextStyle.of(context).style;
    return Row(mainAxisSize: MainAxisSize.min, textDirection: TextDirection.ltr, crossAxisAlignment: CrossAxisAlignment.baseline,
        textBaseline: TextBaseline.alphabetic, children: [
      Text(number, textDirection: TextDirection.ltr, style: base.copyWith(fontFeatures: const [FontFeature.tabularFigures()])),
      if (unit.isNotEmpty) Text(' $unit', textDirection: TextDirection.rtl, style: unitStyle ?? base.copyWith(fontSize: (base.fontSize ?? 14) * 0.7)),
    ]);
  }
}

class Pill extends StatelessWidget {
  final String text;
  final Color color;
  const Pill(this.text, {super.key, this.color = Brand.green});
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
        decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(99)),
        child: Text(text, style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w700)),
      );
}

void toast(BuildContext context, String text, {bool error = false}) {
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
    content: Text(text),
    backgroundColor: error ? Brand.bad : Brand.forest,
    behavior: SnackBarBehavior.floating,
  ));
}

Color stateColor(String state) {
  switch (state) {
    case 'submit':
    case 'submitted':
    case 'to_approve':
    case 'in_progress':
      return Brand.watch;
    case 'approve':
    case 'approved':
    case 'post':
    case 'done':
    case 'paid':
    case 'settled':
      return Brand.good;
    case 'cancel':
    case 'rejected':
      return Brand.bad;
    default:
      return Brand.muted;
  }
}
