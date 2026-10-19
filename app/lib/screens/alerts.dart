// What the system told this person: new invoices, deposits, approvals.
import 'package:flutter/material.dart';

import '../api.dart';
import '../theme.dart';
import '../widgets.dart';

class AlertsScreen extends StatelessWidget {
  final Future<void> Function() onRead;
  const AlertsScreen({super.key, required this.onRead});

  @override
  Widget build(BuildContext context) {
    return Loader<List<Map>>(
      load: () async {
        final items = List<Map>.from((await Api.instance.call('alerts'))['items']);
        if (items.any((e) => e['unread'] == true)) {
          await Api.instance.call('alerts_read');
          onRead();
        }
        return items;
      },
      builder: (context, items, reload) {
        if (items.isEmpty) {
          return ListView(children: const [
            EmptyState(icon: Icons.notifications_none_rounded, title: 'لا توجد تنبيهات', text: 'الفواتير الجديدة والإيداعات والطلبات تظهر هنا.'),
          ]);
        }
        return ListView.separated(
          padding: const EdgeInsets.all(16),
          itemCount: items.length,
          separatorBuilder: (_, __) => const SizedBox(height: 10),
          itemBuilder: (context, i) {
            final a = items[i];
            return Card(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Container(
                    width: 10,
                    height: 10,
                    margin: const EdgeInsets.only(top: 7, left: 10),
                    decoration: BoxDecoration(color: a['unread'] == true ? Brand.green : Brand.line, shape: BoxShape.circle),
                  ),
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text('${a['title']}', style: const TextStyle(fontWeight: FontWeight.w700)),
                      if ((a['text'] ?? '').toString().isNotEmpty)
                        Padding(padding: const EdgeInsets.only(top: 4), child: Text('${a['text']}', style: const TextStyle(color: Brand.muted, fontSize: 14))),
                    ]),
                  ),
                  Text('${a['date']}', style: const TextStyle(color: Brand.muted, fontSize: 12)),
                ]),
              ),
            );
          },
        );
      },
    );
  }
}
