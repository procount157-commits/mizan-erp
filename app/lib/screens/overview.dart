// The manager's first screen: one sentence on how the company is doing,
// the four figures that matter, the projects, the latest movements.
import 'package:flutter/material.dart';

import '../api.dart';
import '../theme.dart';
import '../widgets.dart';
import 'cashflow.dart';
import 'insights.dart';

class OverviewScreen extends StatelessWidget {
  const OverviewScreen({super.key});

  Color _tone(String? tone) {
    switch (tone) {
      case 'good':
        return Brand.good;
      case 'bad':
        return Brand.bad;
      case 'watch':
        return Brand.watch;
      default:
        return Brand.ink;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Loader<Map<String, dynamic>>(
      load: () async => Map<String, dynamic>.from(await Api.instance.call('manager_summary')),
      builder: (context, d, reload) {
        final cards = List<Map>.from(d['cards'] ?? []);
        final hero = cards.isNotEmpty ? cards.first : null;
        final rest = cards.length > 1 ? cards.sublist(1) : <Map>[];
        final mood = d['mood'];
        return ListView(padding: const EdgeInsets.fromLTRB(16, 4, 16, 24), children: [
          Text('مرحباً ${d['name'] ?? ''}', style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w800)),
          Text('${d['company'] ?? ''} · ${d['date'] ?? ''}', style: const TextStyle(color: Brand.muted)),
          const SizedBox(height: 14),
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: (mood == 'good' ? Brand.good : mood == 'bad' ? Brand.bad : Brand.watch).withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(14),
            ),
            child: Row(children: [
              Icon(mood == 'good' ? Icons.check_circle_rounded : Icons.error_rounded,
                  color: mood == 'good' ? Brand.good : mood == 'bad' ? Brand.bad : Brand.watch),
              const SizedBox(width: 10),
              Expanded(child: Text('${d['headline'] ?? ''}', style: const TextStyle(fontWeight: FontWeight.w700))),
            ]),
          ),
          if ((d['approvals'] ?? 0) > 0) ...[
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(color: Brand.forest, borderRadius: BorderRadius.circular(14)),
              child: Row(children: [
                const Icon(Icons.fact_check_rounded, color: Colors.white),
                const SizedBox(width: 10),
                Expanded(
                    child: Text('${d['approvals']} طلب ينتظر اعتمادك',
                        style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700))),
              ]),
            ),
          ],
          const SizedBox(height: 14),
          const InsightsCard(),
          const CashflowCard(),
          if (hero != null) ...[
            const SizedBox(height: 14),
            Container(
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(
                gradient: const LinearGradient(colors: [Brand.greenDark, Brand.forest], begin: Alignment.topRight, end: Alignment.bottomLeft),
                borderRadius: BorderRadius.circular(18),
              ),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('${hero['title']}', style: const TextStyle(color: Color(0xFFCDE9D9), fontWeight: FontWeight.w600)),
                const SizedBox(height: 4),
                Money('${hero['value']}', style: const TextStyle(color: Colors.white, fontSize: 30, fontWeight: FontWeight.w800)),
                const SizedBox(height: 8),
                ...List<String>.from(hero['lines'] ?? []).map((l) =>
                    Text(l, style: const TextStyle(color: Color(0xFFCDE9D9), fontSize: 13))),
              ]),
            ),
          ],
          const SizedBox(height: 12),
          ...rest.map((c) => Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text('${c['title']}', style: const TextStyle(color: Brand.muted, fontWeight: FontWeight.w600)),
                      // Money splits number from unit; a count of days or documents is a sentence.
                      ['safety', 'expiry'].contains(c['key'])
                          ? Text('${c['value']}', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: _tone(c['tone'])))
                          : Money('${c['value']}', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: _tone(c['tone']))),
                      const SizedBox(height: 4),
                      ...List<String>.from(c['lines'] ?? []).map((l) =>
                          Text(l, style: const TextStyle(color: Brand.muted, fontSize: 13))),
                    ]),
                  ),
                ),
              )),
          if (List.from(d['projects'] ?? []).isNotEmpty) ...[
            const SectionTitle('المشاريع'),
            ...List<Map>.from(d['projects']).map((p) => Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: Card(
                    child: Padding(
                      padding: const EdgeInsets.all(14),
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Row(children: [
                          Expanded(child: Text('${p['name']}', style: const TextStyle(fontWeight: FontWeight.w700))),
                          Pill('${p['progress']}%'),
                        ]),
                        const SizedBox(height: 8),
                        ClipRRect(
                          borderRadius: BorderRadius.circular(99),
                          child: LinearProgressIndicator(
                            value: ((p['progress'] ?? 0) as num) / 100,
                            minHeight: 7,
                            backgroundColor: Brand.line,
                            color: _tone(p['tone'] == 'good' ? 'good' : p['tone']),
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text('${p['line']}', style: TextStyle(color: _tone(p['tone']), fontSize: 13)),
                      ]),
                    ),
                  ),
                )),
          ],
          if (List.from(d['events'] ?? []).isNotEmpty) ...[
            const SectionTitle('آخر الحركات'),
            Card(
              child: Column(
                  children: List<Map>.from(d['events'])
                      .map((e) => ListTile(
                            leading: CircleAvatar(
                              backgroundColor: Brand.green.withValues(alpha: 0.12),
                              child: Icon(e['icon'] == 'fa-arrow-down' ? Icons.south_west_rounded : Icons.receipt_long_rounded,
                                  color: Brand.greenDark, size: 20),
                            ),
                            title: Text('${e['text']}', style: const TextStyle(fontSize: 14)),
                            trailing: Text('${e['date']}', style: const TextStyle(color: Brand.muted, fontSize: 12)),
                          ))
                      .toList()),
            ),
          ],
        ]);
      },
    );
  }
}
