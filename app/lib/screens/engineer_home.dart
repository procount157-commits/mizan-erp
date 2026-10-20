// The engineer's first screen: what is still to do today, his cash, his
// jobs (progress and days to the completion date), and the day's tips.
import 'package:flutter/material.dart';

import '../api.dart';
import '../theme.dart';
import '../widgets.dart';
import 'insights.dart';
import 'incident.dart';
import 'materials.dart';

class EngineerHome extends StatelessWidget {
  /// Opens another tab by its label (العمّال، التقرير اليومي، عهدتي).
  final void Function(String tab) open;
  const EngineerHome({super.key, required this.open});

  static const _taskTab = {'crew': 'العمّال', 'report': 'التقرير', 'cash': 'عهدتي', 'refused': 'عهدتي'};
  static const _taskIcon = {
    'crew': Icons.groups_rounded,
    'report': Icons.assignment_rounded,
    'cash': Icons.account_balance_wallet_rounded,
    'refused': Icons.receipt_long_rounded,
  };

  Widget _action(BuildContext context, IconData icon, String label, Color color, VoidCallback onTap) => Expanded(
        child: Material(
          color: Colors.white,
          borderRadius: BorderRadius.circular(16),
          child: InkWell(
            borderRadius: BorderRadius.circular(16),
            onTap: onTap,
            child: Container(
              padding: const EdgeInsets.symmetric(vertical: 14),
              decoration: BoxDecoration(borderRadius: BorderRadius.circular(16), border: Border.all(color: Brand.line)),
              child: Column(children: [
                CircleAvatar(radius: 20, backgroundColor: color.withValues(alpha: 0.1), child: Icon(icon, color: color)),
                const SizedBox(height: 6),
                Text(label, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13)),
              ]),
            ),
          ),
        ),
      );

  @override
  Widget build(BuildContext context) {
    return Loader<Map<String, dynamic>>(
      load: () async => Map<String, dynamic>.from(await Api.instance.call('engineer_home')),
      builder: (context, d, reload) {
        final todo = List<Map>.from(d['todo'] ?? []);
        final projects = List<Map>.from(d['projects'] ?? []);
        final done = d['done'] ?? 0, total = d['total'] ?? 0;
        final cash = Map<String, dynamic>.from(d['cash'] ?? {});
        return ListView(padding: const EdgeInsets.fromLTRB(16, 4, 16, 24), children: [
          Text('صباح الخير ${d['first_name'] ?? ''}', style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w800)),
          Text('${d['date'] ?? ''}', style: const TextStyle(color: Brand.muted)),
          const SizedBox(height: 14),
          // Today's progress: how many of the day's tasks are done.
          Container(
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(
              gradient: const LinearGradient(colors: [Brand.greenDark, Brand.forest], begin: Alignment.topRight, end: Alignment.bottomLeft),
              borderRadius: BorderRadius.circular(18),
            ),
            child: Row(children: [
              SizedBox(
                width: 64,
                height: 64,
                child: Stack(alignment: Alignment.center, children: [
                  CircularProgressIndicator(
                    value: total == 0 ? 1 : done / total,
                    strokeWidth: 7,
                    backgroundColor: Colors.white24,
                    color: Colors.white,
                  ),
                  Text('$done/$total', style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w800)),
                ]),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(done == total ? 'أنهيت مهام اليوم' : 'مهام اليوم',
                      style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w800)),
                  const SizedBox(height: 4),
                  Row(children: [
                    const Text('المتاح في عهدتك: ', style: TextStyle(color: Color(0xFFCDE9D9), fontSize: 13)),
                    Money('${cash['available'] ?? ''}',
                        style: TextStyle(
                            color: cash['low'] == true ? const Color(0xFFFCA5A5) : Colors.white, fontWeight: FontWeight.w800)),
                  ]),
                ]),
              ),
            ]),
          ),
          const SizedBox(height: 12),
          Row(children: [
            _action(context, Icons.inventory_2_rounded, 'اطلب مواد', Brand.greenDark,
                () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const MaterialsScreen()))),
            const SizedBox(width: 10),
            _action(context, Icons.photo_camera_rounded, 'صوّر إيصالاً', Brand.greenDark, () => open('عهدتي')),
            const SizedBox(width: 10),
            _action(context, Icons.health_and_safety_rounded, 'بلاغ سلامة', Brand.bad,
                () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const IncidentScreen()))),
          ]),
          const SectionTitle('مهام اليوم'),
          Card(
            child: Column(
              children: todo
                  .map((t) => ListTile(
                        onTap: () => open(_taskTab[t['key']] ?? 'عهدتي'),
                        leading: CircleAvatar(
                          backgroundColor: (t['done'] == true ? Brand.good : Brand.watch).withValues(alpha: 0.12),
                          child: Icon(t['done'] == true ? Icons.check_rounded : (_taskIcon[t['key']] ?? Icons.circle_outlined),
                              color: t['done'] == true ? Brand.good : Brand.watch),
                        ),
                        title: Text('${t['title']}', style: const TextStyle(fontWeight: FontWeight.w700)),
                        subtitle: Text('${t['text']}', style: const TextStyle(fontSize: 13)),
                        trailing: t['done'] == true ? null : const Icon(Icons.chevron_left_rounded, color: Brand.muted),
                      ))
                  .toList(),
            ),
          ),
          const SizedBox(height: 14),
          const InsightsCard(role: 'engineer'),
          if (projects.isNotEmpty) ...[
            const SectionTitle('مشاريعي'),
            ...projects.map((p) {
              final left = p['days_left'];
              final late = left is num && left < 0;
              return Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Card(
                  child: Padding(
                    padding: const EdgeInsets.all(14),
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Row(children: [
                        Expanded(child: Text('${p['name']}', style: const TextStyle(fontWeight: FontWeight.w700))),
                        Pill('${p['percent']}%'),
                      ]),
                      Text('${p['client']}', style: const TextStyle(color: Brand.muted, fontSize: 12)),
                      const SizedBox(height: 8),
                      ClipRRect(
                        borderRadius: BorderRadius.circular(99),
                        child: LinearProgressIndicator(
                          value: ((p['percent'] ?? 0) as num).clamp(0, 100) / 100,
                          minHeight: 7,
                          backgroundColor: Brand.line,
                          color: late ? Brand.bad : Brand.green,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Wrap(spacing: 8, runSpacing: 6, children: [
                        if (left != null)
                          Pill(late ? 'متأخر $left يوم'.replaceAll('-', '') : 'باقي $left يوم', color: late ? Brand.bad : Brand.muted),
                        Pill('${p['workers_today']} عامل اليوم', color: Brand.greenDark),
                        Pill(p['report_today'] == true ? 'التقرير مرسل' : 'التقرير لم يُرسل',
                            color: p['report_today'] == true ? Brand.good : Brand.watch),
                      ]),
                    ]),
                  ),
                ),
              );
            }),
          ],
        ]);
      },
    );
  }
}
