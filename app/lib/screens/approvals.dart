// Everything waiting for the manager, one card each, approve or refuse in
// one tap: petty cash receipts with the photo, top-ups, large supplier
// bills, payments to subcontractors, materials asked for from the site.
import 'package:flutter/material.dart';

import '../api.dart';
import '../theme.dart';
import '../widgets.dart';

const _kinds = {
  'receipt': ('إيصال عهدة', Icons.receipt_long_rounded),
  'topup': ('طلب تعويض عهدة', Icons.account_balance_wallet_rounded),
  'bill': ('فاتورة مورد', Icons.request_quote_rounded),
  'sc_payment': ('دفعة مقاول باطن', Icons.handshake_rounded),
  'material': ('طلب مواد من الموقع', Icons.inventory_2_rounded),
};

class ApprovalsScreen extends StatefulWidget {
  final Future<void> Function() onChanged;
  const ApprovalsScreen({super.key, required this.onChanged});
  @override
  State<ApprovalsScreen> createState() => _ApprovalsScreenState();
}

class _ApprovalsScreenState extends State<ApprovalsScreen> {
  final _key = GlobalKey();
  final Set<String> _busy = {};

  Future<void> _decide(Map item, bool approve, Future<void> Function() reload) async {
    final id = '${item['kind']}-${item['id']}';
    setState(() => _busy.add(id));
    try {
      await Api.instance.call('decide', {'kind': item['kind'], 'record_id': item['id'], 'approve': approve});
      if (mounted) toast(context, approve ? 'تم الاعتماد' : 'تم الرفض');
      await reload();
      await widget.onChanged();
    } catch (e) {
      if (mounted) toast(context, e.toString(), error: true);
    } finally {
      if (mounted) setState(() => _busy.remove(id));
    }
  }

  void _showPhoto(String url) {
    showDialog(
      context: context,
      builder: (_) => Dialog(
        insetPadding: const EdgeInsets.all(12),
        child: InteractiveViewer(
          child: Image.network(Api.instance.imageUrl(url), headers: Api.instance.imageHeaders, fit: BoxFit.contain),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Loader<List<Map>>(
      key: _key,
      load: () async => List<Map>.from((await Api.instance.call('approvals'))['items']),
      builder: (context, items, reload) {
        if (items.isEmpty) {
          return ListView(children: const [
            EmptyState(icon: Icons.task_alt_rounded, title: 'لا شيء ينتظرك', text: 'كل الطلبات معتمدة. سنخبرك حين يصل جديد.'),
          ]);
        }
        return ListView.separated(
          padding: const EdgeInsets.all(16),
          itemCount: items.length,
          separatorBuilder: (_, __) => const SizedBox(height: 12),
          itemBuilder: (context, i) {
            final it = items[i];
            final kind = _kinds[it['kind']] ?? ('طلب', Icons.inbox_rounded);
            final busy = _busy.contains('${it['kind']}-${it['id']}');
            final photo = (it['photo'] ?? '').toString();
            return Card(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Row(children: [
                    Icon(kind.$2, color: Brand.greenDark, size: 20),
                    const SizedBox(width: 6),
                    Text(kind.$1, style: const TextStyle(color: Brand.greenDark, fontWeight: FontWeight.w700, fontSize: 13)),
                    const Spacer(),
                    Text('${it['date'] ?? ''}', style: const TextStyle(color: Brand.muted, fontSize: 12)),
                  ]),
                  const SizedBox(height: 10),
                  Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    if (photo.isNotEmpty)
                      GestureDetector(
                        onTap: () => _showPhoto(photo),
                        child: ClipRRect(
                          borderRadius: BorderRadius.circular(10),
                          child: Image.network(Api.instance.imageUrl(photo),
                              headers: Api.instance.imageHeaders, width: 72, height: 72, fit: BoxFit.cover,
                              errorBuilder: (_, __, ___) => Container(
                                  width: 72, height: 72, color: Brand.line, child: const Icon(Icons.image_not_supported_outlined))),
                        ),
                      ),
                    if (photo.isNotEmpty) const SizedBox(width: 12),
                    Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text('${it['title'] ?? ''}', style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
                        Text('${it['who'] ?? ''}', style: const TextStyle(color: Brand.muted)),
                        if ((it['project'] ?? '').toString().isNotEmpty)
                          Text('${it['project']}', style: const TextStyle(color: Brand.muted, fontSize: 13)),
                        if ((it['note'] ?? '').toString().isNotEmpty)
                          Text('${it['note']}',
                              style: TextStyle(color: it['kind'] == 'material' ? Brand.ink : Brand.watch, fontSize: 13, height: 1.5)),
                        if ((it['amount'] ?? '').toString().isNotEmpty) ...[
                          const SizedBox(height: 4),
                          Money('${it['amount']}', style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800)),
                        ],
                      ]),
                    ),
                  ]),
                  const SizedBox(height: 12),
                  Row(children: [
                    Expanded(
                      child: FilledButton.icon(
                        onPressed: busy ? null : () => _decide(it, true, reload),
                        icon: const Icon(Icons.check_rounded),
                        label: const Text('اعتماد'),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: OutlinedButton.icon(
                        style: OutlinedButton.styleFrom(foregroundColor: Brand.bad, minimumSize: const Size.fromHeight(52)),
                        onPressed: busy ? null : () => _decide(it, false, reload),
                        icon: const Icon(Icons.close_rounded),
                        label: const Text('رفض'),
                      ),
                    ),
                  ]),
                ]),
              ),
            );
          },
        );
      },
    );
  }
}
