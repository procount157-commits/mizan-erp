// Notifications: ask once, hand this phone's Firebase token to the server
// for whoever is signed in, and keep it current. On a phone without Firebase
// (or in the browser preview) it does nothing.
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';

import 'api.dart';

class Push {
  static bool _ready = false;

  static Future<void> init() async {
    if (kIsWeb || _ready) return;
    try {
      await Firebase.initializeApp();
      _ready = true;
      FirebaseMessaging.instance.onTokenRefresh.listen(_send);
    } catch (e) {
      debugPrint('Push unavailable: $e');
    }
  }

  /// Called after sign-in and on every start while signed in.
  static Future<void> register() async {
    if (!_ready) return;
    try {
      final settings = await FirebaseMessaging.instance.requestPermission();
      if (settings.authorizationStatus == AuthorizationStatus.denied) return;
      final token = await FirebaseMessaging.instance.getToken();
      if (token != null) await _send(token);
    } catch (e) {
      debugPrint('Push registration failed: $e');
    }
  }

  static Future<void> _send(String token) async {
    if (!Api.instance.hasSession) return;
    try {
      await Api.instance.post('/mizan/push/register',
          {'token': token, 'platform': defaultTargetPlatform == TargetPlatform.iOS ? 'ios' : 'android', 'app_id': 'ae.miqyas.app'});
    } catch (e) {
      debugPrint('Push token not sent: $e');
    }
  }

  /// A message that arrives while the app is open: refresh what is on screen.
  static void onForeground(void Function(RemoteMessage) handler) {
    if (_ready) FirebaseMessaging.onMessage.listen(handler);
  }

  /// A notification tapped — from the background, or the one that started
  /// the app: the handler gets the record's model to open the right tab.
  static Future<void> onOpen(void Function(String model) handler) async {
    if (!_ready) return;
    FirebaseMessaging.onMessageOpenedApp.listen((m) => handler('${m.data['model'] ?? ''}'));
    try {
      final first = await FirebaseMessaging.instance.getInitialMessage();
      if (first != null) handler('${first.data['model'] ?? ''}');
    } catch (_) {}
  }
}
