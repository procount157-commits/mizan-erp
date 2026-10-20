// A safety incident, raised the moment it happens: what kind, how serious,
// what happened, who was hurt, what was done, a photograph. The project's
// manager and the managers are told at once.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../api.dart';
import '../theme.dart';
import '../widgets.dart';

class IncidentScreen extends StatefulWidget {
  const IncidentScreen({super.key});
  @override
  State<IncidentScreen> createState() => _IncidentScreenState();
}

class _IncidentScreenState extends State<IncidentScreen> {
  Map<String, dynamic>? _form;
  String? _error;
  int? _project;
  String _kind = 'near_miss';
  String _severity = 'low';
  final _what = TextEditingController();
  final _where = TextEditingController();
  final _who = TextEditingController();
  final _done = TextEditingController();
  XFile? _photo;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _error = null);
    try {
      final f = Map<String, dynamic>.from(await Api.instance.call('incident_form'));
      setState(() {
        _form = f;
        final p = List<Map>.from(f['projects'] ?? []);
        _project ??= p.isNotEmpty ? p.first['id'] : null;
      });
    } catch (e) {
      setState(() => _error = e.toString());
    }
  }

  Future<void> _take() async {
    try {
      final f = await ImagePicker().pickImage(source: ImageSource.camera, maxWidth: 1600, imageQuality: 70);
      if (f != null) setState(() => _photo = f);
    } catch (_) {
      final f = await ImagePicker().pickImage(source: ImageSource.gallery, maxWidth: 1600, imageQuality: 70);
      if (f != null) setState(() => _photo = f);
    }
  }

  Future<void> _send() async {
    if (_project == null) return toast(context, 'اختر المشروع.', error: true);
    if (_what.text.trim().isEmpty) return toast(context, 'صف ما حدث.', error: true);
    setState(() => _busy = true);
    try {
      final r = Map<String, dynamic>.from(await Api.instance.call('submit_incident', {
        'project_id': _project,
        'kind': _kind,
        'severity': _severity,
        'description': _what.text,
        'location': _where.text,
        'injured_name': _who.text,
        'immediate_action': _done.text,
        if (_photo != null) 'photo': base64Encode(await _photo!.readAsBytes()),
      }));
      if (!mounted) return;
      toast(context, 'أُرسل البلاغ ${r['name']} — أُبلغ المدير فوراً');
      setState(() {
        _form = Map<String, dynamic>.from(r['form']);
        for (final c in [_what, _where, _who, _done]) {
          c.clear();
        }
        _photo = null;
        _kind = 'near_miss';
        _severity = 'low';
      });
    } catch (e) {
      if (mounted) toast(context, e.toString(), error: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Widget _chips(List<Map> options, String value, ValueChanged<String> onPick, {Color color = Brand.green}) => Wrap(
        spacing: 8,
        runSpacing: 8,
        children: options
            .map((o) => ChoiceChip(
                  label: Text('${o['label']}'),
                  selected: value == o['key'],
                  selectedColor: color.withValues(alpha: 0.18),
                  onSelected: (_) => onPick('${o['key']}'),
                ))
            .toList(),
      );

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('بلاغ سلامة')),
      body: Builder(builder: (context) {
        if (_form == null) {
          if (_error != null) return ErrorState(message: _error!, onRetry: _load);
          return const Center(child: CircularProgressIndicator(color: Brand.green));
        }
        final f = _form!;
        final projects = List<Map>.from(f['projects'] ?? []);
        final recent = List<Map>.from(f['recent'] ?? []);
        return ListView(padding: const EdgeInsets.fromLTRB(16, 8, 16, 24), children: [
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(color: Brand.good.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(14)),
              child: Row(children: [
                const Icon(Icons.health_and_safety_rounded, color: Brand.good, size: 30),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(f['days_safe'] == null ? 'لا إصابات مضيّعة للوقت مسجّلة' : '${f['days_safe']} يوم دون إصابة مضيّعة للوقت',
                      style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800, color: Brand.greenDark)),
                ),
              ]),
            ),
          const SizedBox(height: 12),
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
          const SectionTitle('نوع الحادث'),
          _chips(List<Map>.from(f['kinds'] ?? []), _kind, (v) => setState(() => _kind = v), color: Brand.bad),
          const SectionTitle('الخطورة'),
          _chips(List<Map>.from(f['severities'] ?? []), _severity, (v) => setState(() => _severity = v), color: Brand.watch),
          const SizedBox(height: 16),
          TextField(controller: _what, minLines: 3, maxLines: 6, decoration: const InputDecoration(labelText: 'ماذا حدث')),
          const SizedBox(height: 10),
          TextField(controller: _where, decoration: const InputDecoration(labelText: 'أين في الموقع', hintText: 'سقف الطابق الثالث، البوابة 2…')),
          const SizedBox(height: 10),
          TextField(controller: _who, decoration: const InputDecoration(labelText: 'من أُصيب (إن وُجد)')),
          const SizedBox(height: 10),
          TextField(controller: _done, maxLines: 2, decoration: const InputDecoration(labelText: 'ما الذي فُعل فوراً')),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: _take,
            icon: Icon(_photo == null ? Icons.add_a_photo_rounded : Icons.check_circle_rounded),
            label: Text(_photo == null ? 'أضف صورة' : 'أُرفقت صورة — اضغط لتغييرها'),
          ),
          const SizedBox(height: 12),
          FilledButton.icon(
            style: FilledButton.styleFrom(backgroundColor: Brand.bad),
            onPressed: _busy ? null : _send,
            icon: _busy
                ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2.5, color: Colors.white))
                : const Icon(Icons.campaign_rounded),
            label: const Text('أرسل البلاغ الآن'),
          ),
          if (recent.isNotEmpty) ...[
            const SectionTitle('بلاغاتي'),
            Card(
              child: Column(
                children: recent
                    .map((r) => ListTile(
                          leading: const Icon(Icons.report_rounded, color: Brand.bad),
                          title: Text('${r['kind']} — ${r['project']}', maxLines: 1, overflow: TextOverflow.ellipsis),
                          subtitle: Text('${r['name']} · ${r['date']}', style: const TextStyle(fontSize: 12)),
                          trailing: Pill('${r['state_label']}', color: r['state'] == 'closed' ? Brand.good : Brand.watch),
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
