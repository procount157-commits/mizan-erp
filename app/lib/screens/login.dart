// Sign in: the company's code once, then email and password.
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api.dart';
import '../theme.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _company = TextEditingController();
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _busy = false;
  bool _hide = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    SharedPreferences.getInstance().then((p) {
      final host = p.getString('host');
      if (host != null) _company.text = host.replaceAll('.${Api.domain}', '');
      _email.text = p.getString('email') ?? '';
      setState(() {});
    });
  }

  Future<void> _submit() async {
    if (_company.text.trim().isEmpty || _email.text.trim().isEmpty || _password.text.isEmpty) {
      setState(() => _error = 'اكتب رمز الشركة والبريد وكلمة المرور.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      if (!await Api.instance.checkCompany(_company.text)) {
        throw ApiError('لم نجد شركة بهذا الرمز. تأكد منه واتصالك بالإنترنت.');
      }
      await Api.instance.login(_company.text, _email.text, _password.text);
      final p = await SharedPreferences.getInstance();
      await p.setString('email', _email.text.trim());
      if (mounted) Navigator.of(context).pushNamedAndRemoveUntil('/home', (_) => false);
    } catch (e) {
      setState(() => _error = e is ApiError ? e.message : 'تعذّر الاتصال. تأكد من الإنترنت.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Brand.forest,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                Center(
                  child: Container(
                    decoration: BoxDecoration(borderRadius: BorderRadius.circular(26), boxShadow: [
                      BoxShadow(color: Brand.green.withValues(alpha: 0.35), blurRadius: 30, offset: const Offset(0, 10)),
                    ]),
                    child: Image.asset('assets/logo.png', width: 92, height: 92),
                  ),
                ),
                const SizedBox(height: 16),
                const Text('مقياس', textAlign: TextAlign.center, style: TextStyle(color: Colors.white, fontSize: 30, fontWeight: FontWeight.w800)),
                const Text('أرقام شركتك واعتماداتك في جيبك', textAlign: TextAlign.center, style: TextStyle(color: Color(0xFFA7C4B4))),
                const SizedBox(height: 28),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(20),
                    child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                      TextField(
                        controller: _company,
                        textDirection: TextDirection.ltr,
                        autocorrect: false,
                        decoration: const InputDecoration(labelText: 'رمز الشركة', hintText: 'alamana', prefixIcon: Icon(Icons.business_rounded)),
                      ),
                      const SizedBox(height: 12),
                      TextField(
                        controller: _email,
                        keyboardType: TextInputType.emailAddress,
                        textDirection: TextDirection.ltr,
                        autocorrect: false,
                        decoration: const InputDecoration(labelText: 'البريد الإلكتروني', prefixIcon: Icon(Icons.alternate_email_rounded)),
                      ),
                      const SizedBox(height: 12),
                      TextField(
                        controller: _password,
                        obscureText: _hide,
                        textDirection: TextDirection.ltr,
                        onSubmitted: (_) => _submit(),
                        decoration: InputDecoration(
                          labelText: 'كلمة المرور',
                          prefixIcon: const Icon(Icons.lock_rounded),
                          suffixIcon: IconButton(
                            icon: Icon(_hide ? Icons.visibility_rounded : Icons.visibility_off_rounded),
                            onPressed: () => setState(() => _hide = !_hide),
                          ),
                        ),
                      ),
                      if (_error != null) ...[
                        const SizedBox(height: 12),
                        Text(_error!, style: const TextStyle(color: Brand.bad, fontWeight: FontWeight.w600)),
                      ],
                      const SizedBox(height: 18),
                      FilledButton(
                        onPressed: _busy ? null : _submit,
                        child: _busy
                            ? const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2.5, color: Colors.white))
                            : const Text('دخول'),
                      ),
                    ]),
                  ),
                ),
              ]),
            ),
          ),
        ),
      ),
    );
  }
}
