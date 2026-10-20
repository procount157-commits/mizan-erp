// Today's insights for whoever is looking — the manager's company, the
// accountant's desk, the engineer's site — and a short report. The figures
// are the system's; the sentences are written from them (by the AI model
// when a key is set in Settings → AI, by fixed rules otherwise).
import 'package:flutter/material.dart';

import '../api.dart';
import '../theme.dart';
import '../widgets.dart';

class InsightsCard extends StatefulWidget {
  /// manager, accountant or engineer: each reads what concerns them.
  final String role;
  const InsightsCard({super.key, this.role = 'manager'});
  @override
  State<InsightsCard> createState() => _InsightsCardState();
}

class _InsightsCardState extends State<InsightsCard> {
  Map<String, dynamic>? _data;
  bool _busy = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load(false);
  }

  Future<void> _load(bool refresh) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final d = await Api.instance.call('role_insights', {'role': widget.role, 'refresh': refresh});
      if (mounted) setState(() => _data = Map<String, dynamic>.from(d));
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Color _tone(String? t) => t == 'bad' ? Brand.bad : t == 'watch' ? Brand.watch : Brand.good;
  IconData _icon(String? t) =>
      t == 'bad' ? Icons.trending_down_rounded : t == 'watch' ? Icons.visibility_rounded : Icons.trending_up_rounded;

  void _report() {
    final d = _data!;
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      backgroundColor: Colors.white,
      builder: (_) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.6,
        maxChildSize: 0.92,
        builder: (_, controller) => ListView(controller: controller, padding: const EdgeInsets.fromLTRB(20, 0, 20, 32), children: [
          const Text('تقرير اليوم', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800)),
          Text('${d['at'] ?? ''} · ${d['source'] == 'ai' ? 'كتبه الذكاء الاصطناعي من أرقام النظام' : 'تحليل تلقائي من أرقام النظام'}',
              style: const TextStyle(color: Brand.muted, fontSize: 13)),
          const SizedBox(height: 16),
          Text('${d['report'] ?? ''}', style: const TextStyle(fontSize: 16, height: 1.9)),
          const SizedBox(height: 20),
          ...List<Map>.from(d['insights'] ?? []).map((i) => Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Icon(_icon(i['tone']), color: _tone(i['tone']), size: 20),
                  const SizedBox(width: 10),
                  Expanded(child: Text('${i['title']}: ${i['text']}', style: const TextStyle(height: 1.6))),
                ]),
              )),
        ]),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final d = _data;
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: Brand.line),
      ),
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 12),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Container(
            padding: const EdgeInsets.all(7),
            decoration: BoxDecoration(color: Brand.green.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(10)),
            child: const Icon(Icons.auto_awesome_rounded, color: Brand.greenDark, size: 18),
          ),
          const SizedBox(width: 10),
          Expanded(child: Text(widget.role == 'engineer' ? 'نصائح اليوم' : widget.role == 'accountant' ? 'أولويات اليوم' : 'تحليلات اليوم',
              style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800))),
          if (d != null && d['source'] == 'ai') const Pill('ذكاء اصطناعي'),
          IconButton(
            visualDensity: VisualDensity.compact,
            onPressed: _busy ? null : () => _load(true),
            icon: _busy
                ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Brand.green))
                : const Icon(Icons.refresh_rounded, color: Brand.muted),
          ),
        ]),
        if (_error != null && d == null)
          Padding(padding: const EdgeInsets.symmetric(vertical: 8), child: Text(_error!, style: const TextStyle(color: Brand.muted))),
        if (d == null && _error == null)
          const Padding(padding: EdgeInsets.all(18), child: Center(child: CircularProgressIndicator(color: Brand.green))),
        if (d != null) ...[
          const SizedBox(height: 6),
          ...List<Map>.from(d['insights'] ?? []).take(5).map((i) => Container(
                margin: const EdgeInsets.only(bottom: 8),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: _tone(i['tone']).withValues(alpha: 0.07),
                  borderRadius: BorderRadius.circular(12),
                  border: BorderDirectional(start: BorderSide(color: _tone(i['tone']), width: 3)),
                ),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Icon(_icon(i['tone']), color: _tone(i['tone']), size: 20),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text('${i['title']}', style: const TextStyle(fontWeight: FontWeight.w800)),
                      const SizedBox(height: 2),
                      Text('${i['text']}', style: const TextStyle(color: Brand.ink, fontSize: 14, height: 1.5)),
                    ]),
                  ),
                ]),
              )),
          if ((d['report'] ?? '').toString().isNotEmpty)
            Align(
              alignment: AlignmentDirectional.centerStart,
              child: TextButton.icon(
                onPressed: _report,
                icon: const Icon(Icons.description_rounded, size: 18),
                label: const Text('اقرأ تقرير اليوم'),
              ),
            ),
        ],
      ]),
    );
  }
}
