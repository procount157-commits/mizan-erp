// The projects as the manager reads them: progress, billed, cost, what the
// client owes and holds, and where the cost came from.
import 'package:flutter/material.dart';

import '../api.dart';
import '../theme.dart';
import '../widgets.dart';

class ProjectsScreen extends StatelessWidget {
  const ProjectsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Loader<List<Map>>(
      load: () async => List<Map>.from((await Api.instance.call('projects'))['projects']),
      builder: (context, projects, reload) {
        if (projects.isEmpty) {
          return ListView(children: const [EmptyState(icon: Icons.apartment_rounded, title: 'لا توجد مشاريع جارية')]);
        }
        return GridView.builder(
          padding: const EdgeInsets.all(16),
          gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
              maxCrossAxisExtent: 150, mainAxisSpacing: 18, crossAxisSpacing: 12, childAspectRatio: 0.78),
          itemCount: projects.length,
          itemBuilder: (context, i) {
            final p = projects[i];
            const colors = [Brand.green, Color(0xFF2563EB), Color(0xFFD97706), Color(0xFF7C3AED), Color(0xFFDC2626), Color(0xFF0891B2)];
            final color = colors[(p['id'] as int) % colors.length];
            return InkWell(
              borderRadius: BorderRadius.circular(16),
              onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => ProjectDetail(project: p, color: color))),
              child: Column(children: [
                Stack(clipBehavior: Clip.none, children: [
                  Container(
                    width: 76,
                    height: 76,
                    decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(20), boxShadow: [
                      BoxShadow(color: color.withValues(alpha: 0.35), blurRadius: 12, offset: const Offset(0, 5)),
                    ]),
                    child: const Icon(Icons.apartment_rounded, color: Colors.white, size: 38),
                  ),
                  Positioned(
                    bottom: -6,
                    left: -6,
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(99), boxShadow: const [
                        BoxShadow(color: Color(0x22000000), blurRadius: 4),
                      ]),
                      child: Text('${(p['percent'] as num).round()}%', style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w800)),
                    ),
                  ),
                ]),
                const SizedBox(height: 10),
                Text('${p['name']}', maxLines: 2, overflow: TextOverflow.ellipsis, textAlign: TextAlign.center,
                    style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13, height: 1.3)),
                Text('${p['code']}', style: const TextStyle(color: Brand.muted, fontSize: 11)),
              ]),
            );
          },
        );
      },
    );
  }
}

class ProjectDetail extends StatelessWidget {
  final Map project;
  final Color color;
  const ProjectDetail({super.key, required this.project, required this.color});

  @override
  Widget build(BuildContext context) {
    final p = project;
    final sources = List<Map>.from(p['sources'] ?? []);
    return Scaffold(
      appBar: AppBar(title: Text('${p['name']}', overflow: TextOverflow.ellipsis)),
      body: ListView(padding: const EdgeInsets.fromLTRB(16, 4, 16, 24), children: [
        Text('${p['code']} · ${p['client']}', style: const TextStyle(color: Brand.muted)),
        const SizedBox(height: 12),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                const Text('نسبة الإنجاز', style: TextStyle(fontWeight: FontWeight.w700)),
                const Spacer(),
                Text('${p['percent']}%', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 20, color: color)),
              ]),
              const SizedBox(height: 8),
              ClipRRect(
                borderRadius: BorderRadius.circular(99),
                child: LinearProgressIndicator(value: ((p['percent'] as num) / 100).clamp(0, 1).toDouble(), minHeight: 9, backgroundColor: Brand.line, color: color),
              ),
            ]),
          ),
        ),
        const SectionTitle('حساب العميل'),
        Card(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Column(children: [
              ValueRow('قيمة العقد', '${p['value']}'),
              ValueRow('المفوتر', '${p['billed']}'),
              ValueRow('المستحق على العميل', '${p['owed']}', color: Brand.watch),
              ValueRow('محتجز لدى العميل', '${p['retention']}'),
            ]),
          ),
        ),
        const SectionTitle('تكلفة المشروع'),
        Card(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Column(children: [
              ...sources.map((s) => ValueRow('${s['label']}', '${s['value']}')),
              const Divider(),
              ValueRow('التكلفة حتى تاريخه', '${p['cost']}', bold: true),
              if ((p['margin'] ?? '').toString().isNotEmpty) ValueRow('هامش الربح المعترف به', '${p['margin']}', color: Brand.good, bold: true),
            ]),
          ),
        ),
      ]),
    );
  }
}
