// The app's only door to the server: JSON in, JSON out, one Odoo session
// kept in a cookie. Every screen asks here; nothing else talks HTTP.
import 'dart:convert';

import 'package:flutter/foundation.dart' show kIsWeb;

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

class ApiError implements Exception {
  final String message;
  final bool signedOut;
  ApiError(this.message, {this.signedOut = false});
  @override
  String toString() => message;
}

class Api {
  Api._();
  static final Api instance = Api._();

  static const domain = 'miqyas.getmihwar.com';
  String? host; // alamana.miqyas.getmihwar.com
  String? _cookie;
  Map<String, dynamic>? me;

  // In a browser preview the app is served next to the server it talks to.
  String get base => kIsWeb ? Uri.base.origin : 'https://$host';
  Map<String, String> get imageHeaders => {if (_cookie != null) 'Cookie': _cookie!};

  static String hostFor(String code) {
    final c = code.trim().toLowerCase();
    if (c.contains('.')) return c.replaceAll(RegExp(r'^https?://'), '').split('/').first;
    return '$c.$domain';
  }

  Future<void> restore() async {
    final p = await SharedPreferences.getInstance();
    host = p.getString('host');
    _cookie = p.getString('cookie');
  }

  Future<void> _save() async {
    final p = await SharedPreferences.getInstance();
    if (host != null) await p.setString('host', host!);
    if (_cookie != null) {
      await p.setString('cookie', _cookie!);
    } else {
      await p.remove('cookie');
    }
  }

  Future<dynamic> _post(String path, Map<String, dynamic> params) async {
    final res = await http
        .post(Uri.parse('$base$path'),
            headers: {
              'Content-Type': 'application/json',
              if (_cookie != null) 'Cookie': _cookie!,
            },
            body: jsonEncode({'jsonrpc': '2.0', 'method': 'call', 'params': params}))
        .timeout(const Duration(seconds: 40));
    final setCookie = res.headers['set-cookie'];
    if (setCookie != null) {
      final m = RegExp(r'session_id=([^;]+)').firstMatch(setCookie);
      if (m != null) {
        _cookie = 'session_id=${m.group(1)}';
        await _save();
      }
    }
    if (res.statusCode != 200) throw ApiError('تعذّر الاتصال بالخادم (${res.statusCode}).');
    final body = jsonDecode(utf8.decode(res.bodyBytes));
    if (body['error'] != null) {
      final data = body['error']['data'] ?? {};
      final name = (data['name'] ?? '').toString();
      if (name.contains('SessionExpired')) {
        throw ApiError('انتهت الجلسة. سجّل الدخول مرة أخرى.', signedOut: true);
      }
      throw ApiError((data['message'] ?? body['error']['message'] ?? 'خطأ').toString());
    }
    return body['result'];
  }

  Future<bool> checkCompany(String code) async {
    if (kIsWeb) return true;
    final h = hostFor(code);
    try {
      final r = await http.get(Uri.parse('https://$h/web/login')).timeout(const Duration(seconds: 15));
      return r.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  Future<Map<String, dynamic>> login(String code, String login, String password) async {
    host = hostFor(code);
    _cookie = null;
    final r = await _post('/mizan/api/login', {'login': login.trim(), 'password': password});
    if (r['ok'] != true) {
      throw ApiError(r['error'] == 'wrong_login' ? 'البريد أو كلمة المرور غير صحيحة.' : 'تعذّر تسجيل الدخول.');
    }
    me = Map<String, dynamic>.from(r['me']);
    await _save();
    return me!;
  }

  Future<void> logout() async {
    try {
      await _post('/mizan/api/logout', {});
    } catch (_) {}
    _cookie = null;
    me = null;
    await _save();
  }

  bool get hasSession => host != null && _cookie != null;

  Future<dynamic> call(String method, [Map<String, dynamic> params = const {}]) async {
    final r = await _post('/mizan/api/$method', params);
    if (r is Map && r['ok'] == true) return r['data'];
    if (r is Map && r['message'] != null) throw ApiError(r['message'].toString());
    throw ApiError('تعذّر تنفيذ الطلب.');
  }

  String imageUrl(String path) => path.startsWith('http') ? path : '$base$path';
}
