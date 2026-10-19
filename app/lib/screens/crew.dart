// The engineer's daily crew: pick the project, tap who worked and for how
// much of the day, save. The labour cards fill and the project is costed.
import 'package:flutter/material.dart';

import '../api.dart';
import '../theme.dart';
import '../widgets.dart';

const _fractions = [('1', 'يوم'), ('0.5', 'نصف'), ('1.5', 'إضافي'), ('', 'غائب')];

class CrewScreen extends StatefulWidget {
  const CrewScreen({super.key});
  @override
  State<CrewScreen> createState() => _CrewScreenState();
}

class _CrewScreenState extends State<CrewScreen> {
  Map<String, dynamic>? _data;
  final Map<int, String> _marks = {};
  int? _project;
  DateTime _date = DateTime.now();
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  String get _dateStr => '${_date.year}-${_date.month.toString().padLeft(2, '0')}-${_date.day.toString().padLeft(2, '0')}';

  Future<void> _load() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final d = Map<String, dynamic>.from(await Api.instance.call('crew', {'contract_id': _project, 'date': _dateStr}));
      _apply(d);
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _apply(Map<String, dynamic> d) {
    _marks.clear();
    for (final w in List<Map>.from(d['workers'] ?? [])) {
      _marks[w['card_id']] = '${w['fraction'] ?? ''}';
    }
    setState(() {
      _data = d;
      _project = d['project_id'] == false ? null : d['project_id'];
    });
  }

  Future<void> _save() async {
    if (_project == null) return;
    setState(() => _busy = true);
    try {
      final entries = _marks.entries.map((e) => {'card_id': e.key, 'fraction': e.value}).toList();
      final d = Map<String, dynamic>.from(await Api.instance.call('save_crew', {'contract_id': _project, 'date': _dateStr, 'entries': entries}));
      _apply(d);
      if (mounted) toast(context, 'حُفظت يومية العمّال');
    } catch (e) {
      if (mounted) toast(context, e.toString(), error: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_data == null) {
      if (_error != null) return ErrorState(message: _error!, onRetry: _load);
      return const Center(child: CircularProgressIndicator(color: Brand.green));
    }
    final d = _data!;
    final projects = List<Map>.from(d['projects'] ?? []);
    final workers = List<Map>.from(d['workers'] ?? []);
    final present = _marks.values.where((v) => v.isNotEmpty).length;
    return Column(children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
        child: Row(children: [
          Expanded(
            child: DropdownButtonFormField<int>(
              key: ValueKey(_project),
              initialValue: _project,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'المشروع'),
              items: projects.map((p) => DropdownMenuItem<int>(value: p['id'], child: Text('${p['name']}', overflow: TextOverflow.ellipsis))).toList(),
              onChanged: (v) {
                _project = v;
                _load();
              },
            ),
          ),
          const SizedBox(width: 10),
          OutlinedButton.icon(
            style: OutlinedButton.styleFrom(minimumSize: const Size(0, 52)),
            onPressed: () async {
              final picked = await showDatePicker(context: context, initialDate: _date, firstDate: DateTime(2024), lastDate: DateTime.now());
              if (picked != null) {
                _date = picked;
                _load();
              }
            },
            icon: const Icon(Icons.event_rounded),
            label: Text('${d['date_label']}'),
          ),
        ]),
      ),
      if (projects.isEmpty)
        const Expanded(child: EmptyState(icon: Icons.apartment_rounded, title: 'لا يوجد مشروع جارٍ', text: 'يبدأ المحاسب المشروع من تطبيق المقاولات.'))
      else if (workers.isEmpty)
        const Expanded(child: EmptyState(icon: Icons.badge_rounded, title: 'لا توجد كروت عمّال', text: 'يضيف المحاسب العمّال وأجورهم من «كروت العمال».'))
      else
        Expanded(
          child: ListView.separated(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 100),
            itemCount: workers.length,
            separatorBuilder: (_, __) => const SizedBox(height: 8),
            itemBuilder: (context, i) {
              final w = workers[i];
              final id = w['card_id'] as int;
              final posted = w['posted'] == true;
              return Card(
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Row(children: [
                      CircleAvatar(
                        backgroundColor: Brand.green.withValues(alpha: 0.12),
                        child: Text('${w['name']}'.characters.first, style: const TextStyle(color: Brand.greenDark, fontWeight: FontWeight.w800)),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Text('${w['name']}', style: const TextStyle(fontWeight: FontWeight.w700)),
                          Text('${w['trade']} · ${w['wage']} / يوم', style: const TextStyle(color: Brand.muted, fontSize: 12)),
                        ]),
                      ),
                      if (posted) const Pill('مرحّل', color: Brand.good),
                    ]),
                    const SizedBox(height: 10),
                    SegmentedButton<String>(
                      showSelectedIcon: false,
                      segments: _fractions.map((f) => ButtonSegment<String>(value: f.$1, label: Text(f.$2))).toList(),
                      selected: {_marks[id] ?? ''},
                      onSelectionChanged: posted ? null : (s) => setState(() => _marks[id] = s.first),
                      style: SegmentedButton.styleFrom(selectedBackgroundColor: Brand.green.withValues(alpha: 0.18), selectedForegroundColor: Brand.greenDark),
                    ),
                  ]),
                ),
              );
            },
          ),
        ),
      if (workers.isNotEmpty && projects.isNotEmpty)
        SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
            child: FilledButton.icon(
              onPressed: _busy ? null : _save,
              icon: const Icon(Icons.save_rounded),
              label: Text('حفظ يومية $present عامل · ${d['total']}'),
            ),
          ),
        ),
    ]);
  }
}
