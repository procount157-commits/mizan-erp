// The next thirteen weeks of cash as bars: the manager sees at a glance the
// week it dips and whether it ever runs short.
import 'package:flutter/material.dart';

import '../api.dart';
import '../theme.dart';
import '../widgets.dart';

class CashflowCard extends StatefulWidget {
  const CashflowCard({super.key});
  @override
  State<CashflowCard> createState() => _CashflowCardState();
}

class _CashflowCardState extends State<CashflowCard> {
  Map<String, dynamic>? _d;
  int? _selected;

  @override
  void initState() {
    super.initState();
    Api.instance.call('cashflow').then((d) {
      if (mounted) setState(() => _d = Map<String, dynamic>.from(d));
    }).catchError((_) {});
  }

  @override
  Widget build(BuildContext context) {
    final d = _d;
    if (d == null || d['available'] != true) return const SizedBox.shrink();
    final weeks = List<Map>.from(d['weeks'] ?? []);
    // Scaled to the range, not from zero: three million moving by fifty
    // thousand must still show which week dips.
    final values = weeks.map((w) => (w['closing'] as num).toDouble()).toList();
    final hi = values.fold<double>(values.first, (m, v) => v > m ? v : m);
    final lo0 = values.fold<double>(values.first, (m, v) => v < m ? v : m);
    final lo = lo0 < 0 ? lo0 : lo0 - (hi - lo0 == 0 ? hi * 0.1 : (hi - lo0) * 0.25);
    final span = (hi - lo) == 0 ? 1.0 : hi - lo;
    final sel = _selected != null && _selected! < weeks.length ? weeks[_selected!] : null;
    return Container(
      margin: const EdgeInsets.only(top: 14),
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(18), border: Border.all(color: Brand.line)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Container(
            padding: const EdgeInsets.all(7),
            decoration: BoxDecoration(color: const Color(0xFF4338CA).withValues(alpha: 0.1), borderRadius: BorderRadius.circular(10)),
            child: const Icon(Icons.show_chart_rounded, color: Color(0xFF4338CA), size: 18),
          ),
          const SizedBox(width: 10),
          const Expanded(child: Text('النقد المتوقع — 13 أسبوعاً', style: TextStyle(fontSize: 17, fontWeight: FontWeight.w800))),
          if (d['short'] == true) const Pill('عجز متوقع', color: Brand.bad),
        ]),
        const SizedBox(height: 4),
        Row(children: [
          Text('أدنى رصيد (${d['low_week']}): ', style: const TextStyle(color: Brand.muted, fontSize: 13)),
          Money('${d['low']}', style: TextStyle(fontWeight: FontWeight.w800, color: d['short'] == true ? Brand.bad : Brand.ink)),
        ]),
        const SizedBox(height: 14),
        SizedBox(
          height: 110,
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            textDirection: TextDirection.ltr, // time runs left to right on a chart
            children: List.generate(weeks.length, (i) {
              final w = weeks[i];
              final v = (w['closing'] as num).toDouble();
              final h = ((v - lo) / span * 100).clamp(6, 100).toDouble();
              return Expanded(
                child: GestureDetector(
                  onTap: () => setState(() => _selected = i),
                  child: Container(
                    height: h,
                    margin: const EdgeInsets.symmetric(horizontal: 2),
                    decoration: BoxDecoration(
                      color: (w['short'] == true ? Brand.bad : const Color(0xFF4338CA)).withValues(alpha: _selected == i ? 1 : 0.55),
                      borderRadius: BorderRadius.circular(4),
                    ),
                  ),
                ),
              );
            }),
          ),
        ),
        const SizedBox(height: 8),
        if (sel != null)
          Text('أسبوع ${sel['name']}: يدخل ${sel['in']} · يخرج ${sel['out']} · يبقى ${sel['closing_label']}',
              style: const TextStyle(fontSize: 13, height: 1.5))
        else
          const Text('اضغط على أي أسبوع لترى ما يدخل وما يخرج.', style: TextStyle(color: Brand.muted, fontSize: 12)),
      ]),
    );
  }
}
