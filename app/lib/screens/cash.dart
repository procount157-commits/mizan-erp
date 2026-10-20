// The engineer's petty cash: what is left, the receipts and their state,
// a camera button for the next receipt, and asking for a top-up.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../api.dart';
import '../theme.dart';
import '../widgets.dart';

class CashScreen extends StatefulWidget {
  const CashScreen({super.key});
  @override
  State<CashScreen> createState() => _CashScreenState();
}

class _CashScreenState extends State<CashScreen> {
  Key _loader = UniqueKey();
  void _refresh() => setState(() => _loader = UniqueKey());

  @override
  Widget build(BuildContext context) {
    return Loader<Map<String, dynamic>>(
      key: _loader,
      load: () async => Map<String, dynamic>.from(await Api.instance.call('my_cash')),
      builder: (context, d, reload) {
        if (d['linked'] != true) {
          return ListView(children: const [
            EmptyState(icon: Icons.person_off_rounded, title: 'حسابك غير مربوط بموظف', text: 'اطلب من المحاسب ربط حسابك بسجل الموظف.'),
          ]);
        }
        final receipts = List<Map>.from(d['receipts'] ?? []);
        final requests = List<Map>.from(d['requests'] ?? []);
        final low = (d['available_raw'] ?? 0) < 0;
        return Stack(children: [
          ListView(padding: const EdgeInsets.fromLTRB(16, 4, 16, 110), children: [
            Container(
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(
                gradient: const LinearGradient(colors: [Brand.greenDark, Brand.forest], begin: Alignment.topRight, end: Alignment.bottomLeft),
                borderRadius: BorderRadius.circular(18),
              ),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Text('المتاح في عهدتك', style: TextStyle(color: Color(0xFFCDE9D9), fontWeight: FontWeight.w600)),
                Money('${d['available']}', style: TextStyle(color: low ? const Color(0xFFFCA5A5) : Colors.white, fontSize: 32, fontWeight: FontWeight.w800)),
                const SizedBox(height: 8),
                Row(children: [
                  Expanded(child: _mini('في عهدتك', '${d['held']}')),
                  Expanded(child: _mini('إيصالات قيد الاعتماد', '${d['waiting']}')),
                ]),
              ]),
            ),
            const SizedBox(height: 12),
            OutlinedButton.icon(
              onPressed: () async {
                final ok = await Navigator.of(context).push<bool>(MaterialPageRoute(builder: (_) => TopupForm(projects: List<Map>.from(d['projects'] ?? []))));
                if (ok == true) _refresh();
              },
              icon: const Icon(Icons.add_card_rounded),
              label: const Text('اطلب تعويض العهدة'),
            ),
            const SectionTitle('إيصالاتي'),
            if (receipts.isEmpty)
              const EmptyState(icon: Icons.receipt_long_rounded, title: 'لا توجد إيصالات بعد', text: 'اضغط زر الكاميرا لتصوير أول إيصال.'),
            ...receipts.map((r) => Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: Card(
                    child: ListTile(
                      contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                      leading: ClipRRect(
                        borderRadius: BorderRadius.circular(8),
                        child: (r['photo'] ?? '').toString().isEmpty
                            ? Container(width: 48, height: 48, color: Brand.line, child: const Icon(Icons.receipt_rounded, color: Brand.muted))
                            : Image.network(Api.instance.imageUrl(r['photo']), headers: Api.instance.imageHeaders, width: 48, height: 48, fit: BoxFit.cover,
                                errorBuilder: (_, __, ___) => Container(width: 48, height: 48, color: Brand.line)),
                      ),
                      title: Text('${r['title']}', maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w700)),
                      subtitle: Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Row(children: [Pill('${r['state_label']}', color: stateColor('${r['state']}')), const SizedBox(width: 8), Text('${r['date']}', style: const TextStyle(fontSize: 12))]),
                      ),
                      trailing: Money('${r['amount']}', style: const TextStyle(fontWeight: FontWeight.w800)),
                    ),
                  ),
                )),
            if (requests.isNotEmpty) ...[
              const SectionTitle('طلبات التعويض'),
              ...requests.map((a) => Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Card(
                      child: ListTile(
                        title: Text('${a['title']}'),
                        subtitle: Align(alignment: AlignmentDirectional.centerStart, child: Pill('${a['state_label']}', color: stateColor('${a['state']}'))),
                        trailing: Money('${a['amount']}', style: const TextStyle(fontWeight: FontWeight.w800)),
                      ),
                    ),
                  )),
            ],
          ]),
          PositionedDirectional(
            start: 16,
            end: 16,
            bottom: 16,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(58)),
              onPressed: () async {
                final ok = await Navigator.of(context).push<bool>(MaterialPageRoute(
                    builder: (_) => ReceiptForm(projects: List<Map>.from(d['projects'] ?? []), kinds: List<Map>.from(d['kinds'] ?? []))));
                if (ok == true) _refresh();
              },
              icon: const Icon(Icons.photo_camera_rounded),
              label: const Text('صوّر إيصالاً'),
            ),
          ),
        ]);
      },
    );
  }

  Widget _mini(String label, String value) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label, style: const TextStyle(color: Color(0xFFA7C4B4), fontSize: 12)),
        Money(value, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700)),
      ]);
}

class ReceiptForm extends StatefulWidget {
  final List<Map> projects;
  final List<Map> kinds;
  const ReceiptForm({super.key, required this.projects, required this.kinds});
  @override
  State<ReceiptForm> createState() => _ReceiptFormState();
}

class _ReceiptFormState extends State<ReceiptForm> {
  XFile? _photo;
  final _amount = TextEditingController();
  final _desc = TextEditingController();
  int? _project;
  String? _kind;
  bool _vat = true;
  bool _busy = false;
  bool _reading = false;
  Map<String, dynamic>? _read; // what the AI read off the photo

  bool get _aiReady => Api.instance.me?['ai_ready'] == true;

  @override
  void initState() {
    super.initState();
    if (widget.projects.isNotEmpty) _project = widget.projects.first['id'];
    if (widget.kinds.isNotEmpty) _kind = widget.kinds.first['key'];
    WidgetsBinding.instance.addPostFrameCallback((_) => _take(ImageSource.camera));
  }

  Future<void> _take(ImageSource source) async {
    try {
      final f = await ImagePicker().pickImage(source: source, maxWidth: 1600, imageQuality: 70);
      if (f != null) {
        setState(() {
          _photo = f;
          _read = null;
        });
        _readPhoto();
      }
    } catch (_) {
      if (mounted && source == ImageSource.camera) _take(ImageSource.gallery);
    }
  }

  /// The AI reads the receipt; the engineer checks the figures, he does not
  /// type them. Nothing is sent until he presses the button.
  Future<void> _readPhoto() async {
    if (!_aiReady || _photo == null) return;
    setState(() => _reading = true);
    try {
      final bytes = await _photo!.readAsBytes();
      final r = Map<String, dynamic>.from(await Api.instance.call('read_receipt', {
        'photo': base64Encode(bytes),
        'mimetype': (_photo!.mimeType ?? '').isNotEmpty ? _photo!.mimeType : 'image/jpeg',
      }));
      if (!mounted || r['ok'] != true) return;
      setState(() {
        _read = r;
        if (r['amount'] != null) _amount.text = '${r['amount']}';
        final what = [r['vendor'], r['description']].where((x) => (x ?? '').toString().isNotEmpty).join(' — ');
        if (_desc.text.isEmpty && what.isNotEmpty) _desc.text = what;
        _vat = r['vat'] == true;
        if (r['kind'] != null && widget.kinds.any((k) => k['key'] == r['kind'])) _kind = r['kind'];
      });
    } catch (_) {
      // Reading is a help, not a step: the form still works by hand.
    } finally {
      if (mounted) setState(() => _reading = false);
    }
  }

  Future<void> _save() async {
    final amount = double.tryParse(_amount.text.replaceAll(',', '.'));
    if (_photo == null) return toast(context, 'صوّر الإيصال أولاً.', error: true);
    if (amount == null || amount <= 0) return toast(context, 'اكتب مبلغ الإيصال.', error: true);
    if (_project == null) return toast(context, 'اختر المشروع.', error: true);
    setState(() => _busy = true);
    try {
      final bytes = await _photo!.readAsBytes();
      await Api.instance.call('submit_receipt', {
        'photo': base64Encode(bytes), 'amount': amount, 'project_id': _project, 'kind': _kind,
        'description': _desc.text, 'vat': _vat,
      });
      if (mounted) {
        toast(context, 'أُرسل الإيصال للاعتماد');
        Navigator.of(context).pop(true);
      }
    } catch (e) {
      if (mounted) toast(context, e.toString(), error: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('إيصال من العهدة')),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        GestureDetector(
          onTap: () => _take(ImageSource.camera),
          child: Container(
            height: 220,
            decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(16), border: Border.all(color: Brand.line)),
            clipBehavior: Clip.antiAlias,
            child: _photo == null
                ? const Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                    Icon(Icons.photo_camera_rounded, size: 48, color: Brand.green),
                    SizedBox(height: 8),
                    Text('اضغط لتصوير الإيصال', style: TextStyle(fontWeight: FontWeight.w700)),
                  ])
                : FutureBuilder(
                    future: _photo!.readAsBytes(),
                    builder: (_, s) => s.hasData ? Image.memory(s.data!, fit: BoxFit.cover, width: double.infinity) : const SizedBox()),
          ),
        ),
        TextButton.icon(onPressed: () => _take(ImageSource.gallery), icon: const Icon(Icons.photo_library_rounded), label: const Text('من المعرض')),
        if (_reading)
          const Padding(
            padding: EdgeInsets.only(bottom: 8),
            child: Row(children: [
              SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Brand.green)),
              SizedBox(width: 10),
              Text('الذكاء الاصطناعي يقرأ الإيصال…', style: TextStyle(color: Brand.greenDark, fontWeight: FontWeight.w600)),
            ]),
          ),
        if (_read != null)
          Container(
            margin: const EdgeInsets.only(bottom: 10),
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: (_read!['checked'] == true ? Brand.good : Brand.watch).withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Icon(Icons.auto_awesome_rounded, color: _read!['checked'] == true ? Brand.good : Brand.watch, size: 20),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  [
                    'قرأ الذكاء الاصطناعي الإيصال — راجع المبلغ قبل الإرسال.',
                    ...List<String>.from(_read!['notes'] ?? []),
                  ].join('\n'),
                  style: const TextStyle(fontSize: 13, height: 1.5),
                ),
              ),
            ]),
          ),
        const SizedBox(height: 8),
        TextField(
          controller: _amount,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          textDirection: TextDirection.ltr,
          style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800),
          decoration: const InputDecoration(labelText: 'المبلغ المكتوب على الإيصال', suffixText: 'د.إ'),
        ),
        const SizedBox(height: 12),
        DropdownButtonFormField<int>(
          key: ValueKey(_project),
          initialValue: _project,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'المشروع'),
          items: widget.projects.map((p) => DropdownMenuItem<int>(value: p['id'], child: Text('${p['name']}', overflow: TextOverflow.ellipsis))).toList(),
          onChanged: (v) => setState(() => _project = v),
        ),
        const SizedBox(height: 12),
        if (widget.kinds.isNotEmpty)
          Wrap(spacing: 8, runSpacing: 8, children: widget.kinds.map((k) => ChoiceChip(
                label: Text('${k['label']}'),
                selected: _kind == k['key'],
                selectedColor: Brand.green.withValues(alpha: 0.18),
                onSelected: (_) => setState(() => _kind = k['key']),
              )).toList()),
        const SizedBox(height: 12),
        TextField(controller: _desc, decoration: const InputDecoration(labelText: 'الغرض منها (اختياري)', hintText: 'إسمنت، ديزل، مضخة مستأجرة…')),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          value: _vat,
          activeThumbColor: Brand.green,
          onChanged: (v) => setState(() => _vat = v),
          title: const Text('الإيصال عليه ضريبة 5%'),
        ),
        const SizedBox(height: 8),
        FilledButton(
          onPressed: _busy ? null : _save,
          child: _busy ? const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2.5, color: Colors.white)) : const Text('إرسال للاعتماد'),
        ),
      ]),
    );
  }
}

class TopupForm extends StatefulWidget {
  final List<Map> projects;
  const TopupForm({super.key, required this.projects});
  @override
  State<TopupForm> createState() => _TopupFormState();
}

class _TopupFormState extends State<TopupForm> {
  final _amount = TextEditingController();
  final _purpose = TextEditingController(text: 'تعويض العهدة');
  int? _project;
  bool _busy = false;

  Future<void> _send() async {
    final amount = double.tryParse(_amount.text.replaceAll(',', '.'));
    if (amount == null || amount <= 0) return toast(context, 'اكتب المبلغ المطلوب.', error: true);
    setState(() => _busy = true);
    try {
      await Api.instance.call('request_topup', {'amount': amount, 'purpose': _purpose.text, 'project_id': _project});
      if (mounted) {
        toast(context, 'أُرسل الطلب لمديرك');
        Navigator.of(context).pop(true);
      }
    } catch (e) {
      if (mounted) toast(context, e.toString(), error: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('طلب تعويض العهدة')),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        TextField(
          controller: _amount,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          textDirection: TextDirection.ltr,
          style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800),
          decoration: const InputDecoration(labelText: 'المبلغ المطلوب', suffixText: 'د.إ'),
        ),
        const SizedBox(height: 12),
        TextField(controller: _purpose, decoration: const InputDecoration(labelText: 'السبب')),
        const SizedBox(height: 12),
        DropdownButtonFormField<int>(
          key: ValueKey(_project),
          initialValue: _project,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'المشروع (اختياري)'),
          items: widget.projects.map((p) => DropdownMenuItem<int>(value: p['id'], child: Text('${p['name']}', overflow: TextOverflow.ellipsis))).toList(),
          onChanged: (v) => setState(() => _project = v),
        ),
        const SizedBox(height: 20),
        FilledButton(onPressed: _busy ? null : _send, child: const Text('إرسال لمديري')),
      ]),
    );
  }
}
