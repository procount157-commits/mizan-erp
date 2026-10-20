// Materials asked for from the site: what, how much, for which project and
// by when. The manager approves it on his phone; the office buys it.
import 'package:flutter/material.dart';

import '../api.dart';
import '../theme.dart';
import '../widgets.dart';

class _Row {
  final name = TextEditingController();
  final qty = TextEditingController();
  int? product;
  int? uom;
  bool hooked = false;
}

class MaterialsScreen extends StatefulWidget {
  const MaterialsScreen({super.key});
  @override
  State<MaterialsScreen> createState() => _MaterialsScreenState();
}

class _MaterialsScreenState extends State<MaterialsScreen> {
  Map<String, dynamic>? _form;
  String? _error;
  int? _project;
  DateTime _needed = DateTime.now().add(const Duration(days: 2));
  final _note = TextEditingController();
  final List<_Row> _rows = [_Row()];
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _error = null);
    try {
      final f = Map<String, dynamic>.from(await Api.instance.call('material_form'));
      setState(() {
        _form = f;
        final projects = List<Map>.from(f['projects'] ?? []);
        _project ??= projects.isNotEmpty ? projects.first['id'] : null;
      });
    } catch (e) {
      setState(() => _error = e.toString());
    }
  }

  String get _neededStr =>
      '${_needed.year}-${_needed.month.toString().padLeft(2, '0')}-${_needed.day.toString().padLeft(2, '0')}';

  Future<void> _send() async {
    if (_project == null) return toast(context, 'اختر المشروع.', error: true);
    final lines = _rows
        .where((r) => (r.name.text.trim().isNotEmpty || r.product != null) && (double.tryParse(r.qty.text) ?? 0) > 0)
        .map((r) => {'name': r.name.text.trim(), 'product_id': r.product, 'qty': double.parse(r.qty.text), 'uom_id': r.uom})
        .toList();
    if (lines.isEmpty) return toast(context, 'أضف صنفاً واحداً على الأقل مع كميته.', error: true);
    setState(() => _busy = true);
    try {
      final r = Map<String, dynamic>.from(await Api.instance.call('submit_material_request', {
        'contract_id': _project,
        'lines': lines,
        'needed_by': _neededStr,
        'note': _note.text,
      }));
      if (!mounted) return;
      toast(context, 'أُرسل الطلب ${r['name']} لاعتماد المدير');
      setState(() {
        _form = Map<String, dynamic>.from(r['form']);
        _rows
          ..clear()
          ..add(_Row());
        _note.clear();
      });
    } catch (e) {
      if (mounted) toast(context, e.toString(), error: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Widget _row(int i, List<Map> products, List<Map> uoms) {
    final r = _rows[i];
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(children: [
          Row(children: [
            Expanded(
              child: Autocomplete<Map>(
                displayStringForOption: (p) => '${p['name']}',
                optionsBuilder: (v) => v.text.isEmpty
                    ? const Iterable<Map>.empty()
                    : products.where((p) => '${p['name']}'.toLowerCase().contains(v.text.toLowerCase())),
                onSelected: (p) => setState(() {
                  r.product = p['id'];
                  r.name.text = '${p['name']}';
                  r.uom ??= p['uom_id'];
                }),
                fieldViewBuilder: (context, controller, focus, submit) {
                  if (!r.hooked) {
                    r.hooked = true;
                    controller.addListener(() {
                      if (controller.text != r.name.text) {
                        r.name.text = controller.text;
                        r.product = null;
                      }
                    });
                  }
                  return TextField(
                    controller: controller,
                    focusNode: focus,
                    decoration: InputDecoration(labelText: 'الصنف ${i + 1}', hintText: 'إسمنت، حديد 16 مم، بلوك 20…'),
                  );
                },
              ),
            ),
            if (_rows.length > 1)
              IconButton(
                onPressed: () => setState(() => _rows.removeAt(i)),
                icon: const Icon(Icons.delete_outline_rounded, color: Brand.bad),
              ),
          ]),
          const SizedBox(height: 10),
          Row(children: [
            Expanded(
              child: TextField(
                controller: r.qty,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                textDirection: TextDirection.ltr,
                decoration: const InputDecoration(labelText: 'الكمية'),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: DropdownButtonFormField<int>(
                key: ValueKey('u$i${r.uom}'),
                initialValue: r.uom ?? (uoms.isNotEmpty ? uoms.first['id'] : null),
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'الوحدة'),
                items: uoms.map((u) => DropdownMenuItem<int>(value: u['id'], child: Text('${u['name']}'))).toList(),
                onChanged: (v) => setState(() => r.uom = v),
              ),
            ),
          ]),
        ]),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('طلب مواد')),
      body: Builder(builder: (context) {
        if (_form == null) {
          if (_error != null) return ErrorState(message: _error!, onRetry: _load);
          return const Center(child: CircularProgressIndicator(color: Brand.green));
        }
        final f = _form!;
        final projects = List<Map>.from(f['projects'] ?? []);
        final products = List<Map>.from(f['products'] ?? []);
        final uoms = List<Map>.from(f['uoms'] ?? []);
        final recent = List<Map>.from(f['recent'] ?? []);
        if (projects.isEmpty) {
          return const EmptyState(icon: Icons.apartment_rounded, title: 'لا يوجد مشروع جارٍ');
        }
        return ListView(padding: const EdgeInsets.fromLTRB(16, 8, 16, 24), children: [
          DropdownButtonFormField<int>(
            key: ValueKey(_project),
            initialValue: _project,
            isExpanded: true,
            decoration: const InputDecoration(labelText: 'المشروع'),
            items: projects
                .map((p) => DropdownMenuItem<int>(value: p['id'], child: Text('${p['name']}', overflow: TextOverflow.ellipsis)))
                .toList(),
            onChanged: (v) => setState(() => _project = v),
          ),
          const SizedBox(height: 10),
          OutlinedButton.icon(
            onPressed: () async {
              final d = await showDatePicker(
                  context: context, initialDate: _needed, firstDate: DateTime.now(), lastDate: DateTime.now().add(const Duration(days: 180)));
              if (d != null) setState(() => _needed = d);
            },
            icon: const Icon(Icons.event_rounded),
            label: Text('مطلوبة بتاريخ ${_needed.day}/${_needed.month}/${_needed.year}'),
          ),
          const SectionTitle('الأصناف'),
          for (var i = 0; i < _rows.length; i++) Padding(padding: const EdgeInsets.only(bottom: 10), child: _row(i, products, uoms)),
          TextButton.icon(
            onPressed: () => setState(() => _rows.add(_Row())),
            icon: const Icon(Icons.add_circle_outline_rounded),
            label: const Text('أضف صنفاً'),
          ),
          const SizedBox(height: 6),
          TextField(controller: _note, maxLines: 2, decoration: const InputDecoration(labelText: 'ملاحظة (اختياري)', hintText: 'لصب سقف الطابق الرابع')),
          const SizedBox(height: 14),
          FilledButton.icon(
            onPressed: _busy ? null : _send,
            icon: _busy
                ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2.5, color: Colors.white))
                : const Icon(Icons.send_rounded),
            label: const Text('إرسال لاعتماد المدير'),
          ),
          if (recent.isNotEmpty) ...[
            const SectionTitle('طلباتي'),
            Card(
              child: Column(
                children: recent
                    .map((r) => ListTile(
                          leading: const Icon(Icons.inventory_2_rounded, color: Brand.greenDark),
                          title: Text('${r['what']}', maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 14)),
                          subtitle: Text('${r['name']} · ${r['project']}', style: const TextStyle(fontSize: 12)),
                          trailing: Pill('${r['state_label']}', color: stateColor('${r['state']}')),
                        ))
                    .toList(),
              ),
            ),
          ],
        ]);
      }),
    );
  }
}
