// مقياس: the manager's figures and approvals, the engineer's cash and crew.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'api.dart';
import 'push.dart';
import 'screens/login.dart';
import 'screens/shell.dart';
import 'theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
    statusBarColor: Colors.transparent,
    statusBarIconBrightness: Brightness.dark,
  ));
  // Nothing here may stop the first screen from appearing.
  try {
    await Api.instance.restore();
  } catch (_) {}
  Map<String, dynamic>? me;
  if (Api.instance.hasSession) {
    try {
      me = Map<String, dynamic>.from(await Api.instance.call('me'));
      Api.instance.me = me;
    } catch (_) {
      me = null;
    }
  }
  await Push.init();
  runApp(MiqyasApp(signedIn: me != null));
  if (me != null) Push.register();
}

class MiqyasApp extends StatelessWidget {
  final bool signedIn;
  const MiqyasApp({super.key, required this.signedIn});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'مقياس',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(),
      locale: const Locale('ar'),
      supportedLocales: const [Locale('ar'), Locale('en')],
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      initialRoute: signedIn ? '/home' : '/login',
      routes: {
        '/login': (_) => const LoginScreen(),
        '/home': (_) => const Shell(),
      },
    );
  }
}
