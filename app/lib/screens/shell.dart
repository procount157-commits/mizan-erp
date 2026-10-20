// The tabs a person gets, by what they do. One app, a different app for each
// role: the manager's figures and approvals, the accountant's desk, the
// engineer's day on site, the staff member's petty cash. Nobody sees the
// whole system.
import 'package:flutter/material.dart';

import '../api.dart';
import '../push.dart';
import '../theme.dart';
import 'accountant.dart';
import 'alerts.dart';
import 'approvals.dart';
import 'cash.dart';
import 'crew.dart';
import 'engineer_home.dart';
import 'overview.dart';
import 'projects.dart';
import 'site_report.dart';

class _Tab {
  final String label;
  final IconData icon;
  final IconData selected;
  final Widget page;
  final String? badge;
  _Tab(this.label, this.icon, this.selected, this.page, {this.badge});
}

class Shell extends StatefulWidget {
  const Shell({super.key});
  @override
  State<Shell> createState() => _ShellState();
}

class _ShellState extends State<Shell> {
  int _index = 0;
  int _homeVersion = 0; // bumped to reload the home screen when it is shown again
  Map<String, dynamic> counts = {};

  List<String> get roles => List<String>.from(Api.instance.me?['roles'] ?? []);

  @override
  void initState() {
    super.initState();
    counts = Map<String, dynamic>.from(Api.instance.me?['counts'] ?? {});
    // A notification while the app is open: show it and refresh the badges.
    Push.onForeground((m) {
      refreshCounts();
      final n = m.notification;
      if (n != null && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          behavior: SnackBarBehavior.floating,
          content: Text('${n.title ?? ''}\n${n.body ?? ''}'.trim()),
        ));
      }
    });
    Push.onOpen(_openFor);
  }

  /// A tapped notification opens where its record is handled.
  void _openFor(String model) {
    final approver = roles.contains('manager') || roles.contains('approver');
    String tab;
    switch (model) {
      case 'account.move':
      case 'mizan.payment.request':
        tab = roles.contains('manager') ? 'الاعتمادات' : 'المحاسبة';
        break;
      case 'hr.expense.sheet':
      case 'mizan.employee.advance':
        tab = approver ? 'الاعتمادات' : roles.contains('accountant') ? 'المحاسبة' : 'عهدتي';
        break;
      case 'mizan.site.report':
        tab = roles.contains('engineer') ? 'التقرير' : 'التنبيهات';
        break;
      default:
        tab = 'التنبيهات';
    }
    open(tab);
  }

  /// Show a tab by its label, wherever it sits (or under «المزيد»).
  void open(String label) {
    final i = visibleTabs.indexWhere((t) => t.label == label);
    if (i >= 0) {
      setState(() => _index = i);
    } else {
      final t = tabs.where((t) => t.label == label).toList();
      if (t.isNotEmpty) {
        Navigator.of(context).push(MaterialPageRoute(builder: (_) => Scaffold(appBar: AppBar(title: Text(label)), body: t.first.page)));
      }
    }
    refreshCounts();
  }

  Future<void> refreshCounts() async {
    try {
      final c = await Api.instance.call('counts');
      if (mounted) setState(() => counts = Map<String, dynamic>.from(c));
    } catch (_) {}
  }

  List<_Tab> get tabs {
    final t = <_Tab>[];
    final manager = roles.contains('manager');
    final approver = manager || roles.contains('approver');
    final accountant = roles.contains('accountant');
    final engineer = roles.contains('engineer');
    final staff = roles.contains('staff');
    final approvals = _Tab('الاعتمادات', Icons.fact_check_outlined, Icons.fact_check_rounded,
        ApprovalsScreen(onChanged: refreshCounts), badge: '${counts['approvals'] ?? 0}');
    final accounts = _Tab('المحاسبة', Icons.receipt_long_outlined, Icons.receipt_long_rounded, const AccountantScreen());
    final projects = _Tab('المشاريع', Icons.apartment_outlined, Icons.apartment_rounded, const ProjectsScreen());
    final cash = _Tab('عهدتي', Icons.account_balance_wallet_outlined, Icons.account_balance_wallet_rounded, const CashScreen());

    if (manager) {
      // The owner: the company first, then what waits for him.
      t.add(_Tab('الرئيسية', Icons.space_dashboard_outlined, Icons.space_dashboard_rounded, const OverviewScreen()));
      t.add(approvals);
      t.add(projects);
      if (accountant) t.add(accounts);
    } else if (accountant) {
      // The accountant opens on today's desk.
      t.add(accounts);
      if (approver) t.add(approvals);
      t.add(projects);
    } else if (approver) {
      t.add(approvals);
    }
    if (engineer) {
      // The engineer's day: what is left to do, the crew, the report, the cash.
      t.add(_Tab('الرئيسية', Icons.home_outlined, Icons.home_rounded,
          EngineerHome(key: ValueKey('home$_homeVersion'), open: open)));
      t.add(_Tab('العمّال', Icons.groups_outlined, Icons.groups_rounded, const CrewScreen()));
      t.add(_Tab('التقرير', Icons.assignment_outlined, Icons.assignment_rounded, const SiteReportScreen()));
      t.add(cash);
    } else if (staff) {
      t.add(cash);
    }
    t.add(_Tab('التنبيهات', Icons.notifications_none_rounded, Icons.notifications_rounded,
        AlertsScreen(onRead: refreshCounts), badge: '${counts['alerts'] ?? 0}'));
    return t;
  }

  Future<void> _logout() async {
    await Api.instance.logout();
    if (mounted) Navigator.of(context).pushNamedAndRemoveUntil('/login', (_) => false);
  }

  /// Five fit at the bottom; beyond that the fifth opens the rest.
  List<_Tab> get visibleTabs {
    final all = tabs;
    if (all.length <= 5) return all;
    final rest = all.sublist(4);
    return [
      ...all.sublist(0, 4),
      _Tab('المزيد', Icons.apps_rounded, Icons.apps_rounded, _MoreTabs(tabs: rest)),
    ];
  }

  @override
  Widget build(BuildContext context) {
    final t = visibleTabs;
    if (_index >= t.length) _index = 0;
    final me = Api.instance.me ?? {};
    return Scaffold(
      appBar: AppBar(
        titleSpacing: 16,
        title: Row(children: [
          Image.asset('assets/logo.png', width: 30, height: 30),
          const SizedBox(width: 10),
          Text(t[_index].label),
        ]),
        actions: [
          PopupMenuButton<String>(
            icon: CircleAvatar(
              radius: 17,
              backgroundColor: Brand.green,
              child: Text((me['first_name'] ?? 'م').toString().characters.first,
                  style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w800)),
            ),
            itemBuilder: (_) => [
              PopupMenuItem(enabled: false, child: Text('${me['name'] ?? ''}\n${me['company'] ?? ''}')),
              const PopupMenuItem(value: 'logout', child: Text('تسجيل الخروج')),
            ],
            onSelected: (v) => v == 'logout' ? _logout() : null,
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: IndexedStack(index: _index, children: t.map((e) => e.page).toList()),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) {
          setState(() {
            if (t[i].label == 'الرئيسية' && i != _index) _homeVersion++;
            _index = i;
          });
          refreshCounts();
        },
        destinations: t
            .map((e) => NavigationDestination(
                  icon: Badge(isLabelVisible: (e.badge ?? '0') != '0', label: Text(e.badge ?? ''), child: Icon(e.icon)),
                  selectedIcon: Badge(isLabelVisible: (e.badge ?? '0') != '0', label: Text(e.badge ?? ''), child: Icon(e.selected)),
                  label: e.label,
                ))
            .toList(),
      ),
    );
  }
}

class _MoreTabs extends StatelessWidget {
  final List<_Tab> tabs;
  const _MoreTabs({required this.tabs});
  @override
  Widget build(BuildContext context) => ListView(padding: const EdgeInsets.all(16), children: [
        ...tabs.map((t) => Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Card(
                child: ListTile(
                  leading: CircleAvatar(backgroundColor: Brand.green.withValues(alpha: 0.12), child: Icon(t.selected, color: Brand.greenDark)),
                  title: Text(t.label, style: const TextStyle(fontWeight: FontWeight.w700)),
                  trailing: Badge(isLabelVisible: (t.badge ?? '0') != '0', label: Text(t.badge ?? ''), child: const Icon(Icons.chevron_left_rounded)),
                  onTap: () => Navigator.of(context).push(MaterialPageRoute(
                      builder: (_) => Scaffold(appBar: AppBar(title: Text(t.label)), body: t.page))),
                ),
              ),
            )),
      ]);
}
