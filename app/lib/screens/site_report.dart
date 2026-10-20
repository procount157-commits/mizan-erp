// The daily site report from the phone: the project, the weather, what was
// built, what stopped and why, a photograph. The crew recorded for the day
// is counted in by trade on the server; the engineer does not type it twice.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../api.dart';
import '../theme.dart';
import '../widgets.dart';

class SiteReportScreen extends StatefulWidget {
  const SiteReportScreen({super.key});
  @override
  State<SiteReportScreen> createState() => _SiteReportScreenState();
}

class _SiteReportScreenState extends State<SiteReportScreen> {
  Map<String, dynamic>? _form;
  String? _error;
  int? _project;
  String _weather = 'clear';
  bool _stopped = false;
  String? _reason;
  final _hours = TextEditingController();
  final _work = TextEditingController();
  final _issues = TextEditingController();
  XFile? _photo;
  bool _busy = false;
  final Map<int, TextEditingController> _worked = {};
  final Map<int, TextEditingController> _idle = {};

  TextEditingController _ctl(Map<int, TextEditingController> m, int id) => m.putIfAbsent(id, () => TextEditingController());

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _error = null);
    try {
      final f = Map<String, dynamic>.from(await Api.instance.call('site_report_form'));
      final open = List<Map>.from(f['projects'] ?? []).where((p) => p['filed'] != true).toList();
      setState(() {
        _form = f;
        _project ??= open.isNotEmpty ? open.first['id'] : null;
      });
    } catch (e) {
      setState(() => _error = e.toString());
    }
  }

  Future<void> _take(ImageSource source) async {
    try {
      final f = await ImagePicker().pickImage(source: source, maxWidth: 1600, imageQuality: 70);
      if (f != null) setState(() => _photo = f);
    } catch (_) {
      if (mounted && source == ImageSource.camera) _take(ImageSource.gallery);
    }
  }

  Future<void> _send() async {
    if (_project == null) return toast(context, 'اختر المشروع.', error: true);
    if (_work.text.trim().isEmpty) return toast(context, 'اكتب ما أُنجز اليوم.', error: true);
    if (_stopped && _reason == null) return toast(context, 'اختر سبب التوقف.', error: true);
    setState(() => _busy = true);
    try {
      final r = Map<String, dynamic>.from(await Api.instance.call('submit_site_report', {
        'project_id': _project,
        'work_done': _work.text,
        'weather': _weather,
        'issues': _issues.text,
        'work_stopped': _stopped,
        'stop_reason': _reason,
        'stop_hours': double.tryParse(_hours.text) ?? 0,
        'plants': [
          for (final id in {..._worked.keys, ..._idle.keys})
            {'plant_id': id, 'hours': double.tryParse(_worked[id]?.text ?? '') ?? 0, 'idle': double.tryParse(_idle[id]?.text ?? '') ?? 0}
        ],
        if (_photo != null) 'photo': base64Encode(await _photo!.readAsBytes()),
      }));
      if (!mounted) return;
      toast(context, 'أُرسل التقرير ${r['name']} · ${r['men']} عامل');
      setState(() {
        _form = Map<String, dynamic>.from(r['form']);
        _work.clear();
        _issues.clear();
        _hours.clear();
        _photo = null;
        for (final c in [..._worked.values, ..._idle.values]) {
          c.clear();
        }
        _stopped = false;
        _reason = null;
        final open = List<Map>.from(_form!['projects'] ?? []).where((p) => p['filed'] != true).toList();
        _project = open.isNotEmpty ? open.first['id'] : null;
      });
    } catch (e) {
      if (mounted) toast(context, e.toString(), error: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_form == null) {
      if (_error != null) return ErrorState(message: _error!, onRetry: _load);
      return const Center(child: CircularProgressIndicator(color: Brand.green));
    }
    final f = _form!;
    final projects = List<Map>.from(f['projects'] ?? []);
    final recent = List<Map>.from(f['recent'] ?? []);
    final open = projects.where((p) => p['filed'] != true).toList();
    final chosen = projects.where((p) => p['id'] == _project).toList();
    return RefreshIndicator(
      color: Brand.green,
      onRefresh: _load,
      child: ListView(padding: const EdgeInsets.fromLTRB(16, 4, 16, 24), children: [
        Text('تقرير ${f['date']}', style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
        const Text('يُرسل للمكتب ولمدير المشروع، ويُحسب فيه العمّال الذين سجّلتهم اليوم.', style: TextStyle(color: Brand.muted)),
        const SizedBox(height: 12),
        if (projects.isEmpty)
          const EmptyState(icon: Icons.apartment_rounded, title: 'لا يوجد مشروع جارٍ')
        else if (open.isEmpty)
          const Card(
            child: ListTile(
              leading: Icon(Icons.check_circle_rounded, color: Brand.good),
              title: Text('أرسلت تقارير اليوم لكل مشاريعك', style: TextStyle(fontWeight: FontWeight.w700)),
            ),
          )
        else ...[
          DropdownButtonFormField<int>(
            key: ValueKey(_project),
            initialValue: _project,
            isExpanded: true,
            decoration: const InputDecoration(labelText: 'المشروع'),
            items: open
                .map((p) => DropdownMenuItem<int>(value: p['id'], child: Text('${p['name']}', overflow: TextOverflow.ellipsis)))
                .toList(),
            onChanged: (v) => setState(() => _project = v),
          ),
          if (chosen.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(
                chosen.first['workers'] == 0
                    ? 'لم تسجّل عمّالاً لهذا المشروع اليوم — سجّلهم من «العمّال» أولاً ليُحسبوا.'
                    : 'سيُحسب ${chosen.first['workers']} عامل من يومية اليوم.',
                style: TextStyle(color: chosen.first['workers'] == 0 ? Brand.watch : Brand.greenDark, fontSize: 13),
              ),
            ),
          const SectionTitle('الطقس'),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: List<Map>.from(f['weather'] ?? [])
                .map((w) => ChoiceChip(
                      label: Text('${w['label']}'),
                      selected: _weather == w['key'],
                      selectedColor: Brand.green.withValues(alpha: 0.18),
                      onSelected: (_) => setState(() => _weather = w['key']),
                    ))
                .toList(),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _work,
            minLines: 3,
            maxLines: 6,
            decoration: const InputDecoration(labelText: 'ما الذي أُنجز اليوم', hintText: 'صب سقف الطابق الثالث، تمديدات كهرباء الشقق 301-304…'),
          ),
          const SizedBox(height: 12),
          TextField(controller: _issues, maxLines: 3, decoration: const InputDecoration(labelText: 'مشاكل أو ملاحظات (اختياري)')),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            value: _stopped,
            activeThumbColor: Brand.bad,
            onChanged: (v) => setState(() => _stopped = v),
            title: const Text('توقف العمل اليوم'),
          ),
          if (_stopped) ...[
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: List<Map>.from(f['reasons'] ?? [])
                  .map((r) => ChoiceChip(
                        label: Text('${r['label']}'),
                        selected: _reason == r['key'],
                        selectedColor: Brand.bad.withValues(alpha: 0.15),
                        onSelected: (_) => setState(() => _reason = r['key']),
                      ))
                  .toList(),
            ),
            const SizedBox(height: 10),
            TextField(
              controller: _hours,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(labelText: 'الساعات الضائعة'),
            ),
          ],
          if (List.from(f['plants'] ?? []).isNotEmpty)
            Card(
              margin: const EdgeInsets.only(top: 8),
              child: ExpansionTile(
                leading: const Icon(Icons.precision_manufacturing_rounded, color: Brand.greenDark),
                title: const Text('المعدات في الموقع', style: TextStyle(fontWeight: FontWeight.w700)),
                subtitle: const Text('ساعات العمل والتوقف — تُحمّل على المشروع', style: TextStyle(fontSize: 12)),
                childrenPadding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
                children: List<Map>.from(f['plants']).map((p) {
                  final id = p['id'] as int;
                  return Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Row(children: [
                      Expanded(flex: 3, child: Text('${p['name']}', style: const TextStyle(fontSize: 13))),
                      const SizedBox(width: 8),
                      Expanded(
                        flex: 2,
                        child: TextField(
                          controller: _ctl(_worked, id),
                          keyboardType: const TextInputType.numberWithOptions(decimal: true),
                          decoration: const InputDecoration(labelText: 'عمل (س)', isDense: true),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        flex: 2,
                        child: TextField(
                          controller: _ctl(_idle, id),
                          keyboardType: const TextInputType.numberWithOptions(decimal: true),
                          decoration: const InputDecoration(labelText: 'توقف (س)', isDense: true),
                        ),
                      ),
                    ]),
                  );
                }).toList(),
              ),
            ),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: () => _take(ImageSource.camera),
            icon: Icon(_photo == null ? Icons.add_a_photo_rounded : Icons.check_circle_rounded),
            label: Text(_photo == null ? 'أضف صورة من الموقع' : 'أُرفقت صورة — اضغط لتغييرها'),
          ),
          const SizedBox(height: 12),
          FilledButton.icon(
            onPressed: _busy ? null : _send,
            icon: _busy
                ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2.5, color: Colors.white))
                : const Icon(Icons.send_rounded),
            label: const Text('إرسال التقرير'),
          ),
        ],
        if (recent.isNotEmpty) ...[
          const SectionTitle('تقاريري الأخيرة'),
          Card(
            child: Column(
              children: recent
                  .map((r) => ListTile(
                        leading: Icon(r['stopped'] == true ? Icons.pause_circle_rounded : Icons.assignment_turned_in_rounded,
                            color: r['stopped'] == true ? Brand.bad : Brand.greenDark),
                        title: Text('${r['project']}', maxLines: 1, overflow: TextOverflow.ellipsis),
                        subtitle: Text('${r['name']} · ${r['date']} · ${r['men']} عامل', style: const TextStyle(fontSize: 12)),
                        trailing: Pill('${r['state_label']}', color: r['state'] == 'acknowledged' ? Brand.good : Brand.watch),
                      ))
                  .toList(),
            ),
          ),
        ],
      ]),
    );
  }
}
