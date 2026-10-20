// The accountant's tab: receipts to post, customers past due, bills due
// this week, bank lines to match, and what still waits for the manager.
import 'package:flutter/material.dart';

import '../api.dart';
import '../theme.dart';
import '../widgets.dart';
import 'insights.dart';

class AccountantScreen extends StatefulWidget {
  const AccountantScreen({super.key});
  @override
  State<AccountantScreen> createState() => _AccountantScreenState();
}

class _AccountantScreenState extends State<AccountantScreen> {
  Key _k = UniqueKey();
  final Set<int> _posting = {};

  Future<void> _post(int id) async {
    setState(() => _posting.add(id));
    try {
      await Api.instance.call('post_receipts', {'ids': [id]});
      if (mounted) toast(context, 'رُحّل الإيصال وسُوّيت العهدة');
      setState(() => _k = UniqueKey());
    } catch (e) {
      if (mounted) toast(context, e.toString(), error: true);
    } finally {
      if (mounted) setState(() => _posting.remove(id));
    }
  }

  Widget _stat(String label, String value, IconData icon, Color color) => Expanded(
        child: Card(
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Icon(icon, color: color, size: 22),
              const SizedBox(height: 6),
              Text(value, style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: color)),
              Text(label, style: const TextStyle(color: Brand.muted, fontSize: 12)),
            ]),
          ),
        ),
      );

  @override
  Widget build(BuildContext context) {
    return Loader<Map<String, dynamic>>(
      key: _k,
      load: () async => Map<String, dynamic>.from(await Api.instance.call('accountant_summary')),
      builder: (context, d, reload) {
        final receipts = List<Map>.from(d['receipts'] ?? []);
        final overdue = List<Map>.from(d['overdue'] ?? []);
        final due = List<Map>.from(d['due'] ?? []);
        return ListView(padding: const EdgeInsets.fromLTRB(16, 4, 16, 24), children: [
          Row(children: [
            _stat('إيصالات للترحيل', '${receipts.length}', Icons.receipt_long_rounded, Brand.greenDark),
            const SizedBox(width: 10),
            _stat('حركات بنك للمطابقة', '${d['bank_count']}', Icons.account_balance_rounded, Brand.watch),
            const SizedBox(width: 10),
            _stat('بانتظار المدير', '${d['waiting_manager']}', Icons.hourglass_top_rounded, const Color(0xFF7C3AED)),
          ]),
          const SizedBox(height: 12),
          const InsightsCard(role: 'accountant'),
          const SectionTitle('إيصالات عهدة معتمدة تنتظر الترحيل'),
          if (receipts.isEmpty)
            const Card(child: Padding(padding: EdgeInsets.all(16), child: Text('لا شيء ينتظر الترحيل.', style: TextStyle(color: Brand.muted)))),
          ...receipts.map((r) => Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Card(
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Row(children: [
                      ClipRRect(
                        borderRadius: BorderRadius.circular(8),
                        child: (r['photo'] ?? '').toString().isEmpty
                            ? Container(width: 52, height: 52, color: Brand.line, child: const Icon(Icons.receipt_rounded, color: Brand.muted))
                            : Image.network(Api.instance.imageUrl(r['photo']), headers: Api.instance.imageHeaders, width: 52, height: 52, fit: BoxFit.cover,
                                errorBuilder: (_, __, ___) => Container(width: 52, height: 52, color: Brand.line)),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Text('${r['title']}', maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w700)),
                          Text('${r['who']} · ${r['date']}', style: const TextStyle(color: Brand.muted, fontSize: 12)),
                          Money('${r['amount']}', style: const TextStyle(fontWeight: FontWeight.w800)),
                        ]),
                      ),
                      FilledButton(
                        style: FilledButton.styleFrom(minimumSize: const Size(84, 44)),
                        onPressed: _posting.contains(r['id']) ? null : () => _post(r['id']),
                        child: const Text('ترحيل'),
                      ),
                    ]),
                  ),
                ),
              )),
          SectionTitle('فواتير عملاء متأخرة', trailing: Money('${d['overdue_total']}', style: const TextStyle(fontWeight: FontWeight.w800, color: Brand.bad))),
          Card(
            child: Column(children: [
              if (overdue.isEmpty) const ListTile(title: Text('لا توجد فواتير متأخرة.', style: TextStyle(color: Brand.muted))),
              ...overdue.map((m) => ListTile(
                    title: Text('${m['who']}', style: const TextStyle(fontWeight: FontWeight.w700)),
                    subtitle: Text('${m['name']} · ${m['late']}', style: const TextStyle(fontSize: 12)),
                    trailing: Money('${m['amount']}', style: const TextStyle(fontWeight: FontWeight.w800, color: Brand.bad)),
                  )),
            ]),
          ),
          SectionTitle('فواتير موردين مستحقة هذا الأسبوع', trailing: Money('${d['due_total']}', style: const TextStyle(fontWeight: FontWeight.w800))),
          Card(
            child: Column(children: [
              if (due.isEmpty) const ListTile(title: Text('لا شيء مستحق هذا الأسبوع.', style: TextStyle(color: Brand.muted))),
              ...due.map((m) => ListTile(
                    title: Text('${m['who']}', style: const TextStyle(fontWeight: FontWeight.w700)),
                    subtitle: Row(children: [
                      Text('${m['name']} · ${m['when']}', style: const TextStyle(fontSize: 12)),
                      if (m['waiting'] == true) ...[const SizedBox(width: 6), const Pill('بانتظار المدير', color: Brand.watch)],
                    ]),
                    trailing: Money('${m['amount']}', style: const TextStyle(fontWeight: FontWeight.w800)),
                  )),
            ]),
          ),
          const SectionTitle('البنك'),
          Card(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: Column(children: [
                ValueRow('حركات لم تُطابق', '${d['bank_count']}'),
                ValueRow('إيداعات غير مطابقة', '${d['bank_in']}', color: Brand.good),
                ValueRow('مسحوبات غير مطابقة', '${d['bank_out']}', color: Brand.bad),
              ]),
            ),
          ),
        ]);
      },
    );
  }
}
