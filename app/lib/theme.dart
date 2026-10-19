// One look for the whole app: the product's green, deep ink, Cairo.
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class Brand {
  static const green = Color(0xFF1BAE5A);
  static const greenDark = Color(0xFF0F7A3F);
  static const forest = Color(0xFF0F2A1C);
  static const ink = Color(0xFF1C2430);
  static const muted = Color(0xFF6B7686);
  static const line = Color(0xFFE4E9EF);
  static const ground = Color(0xFFF4F6FA);
  static const watch = Color(0xFFB45309);
  static const bad = Color(0xFFDC2626);
  static const good = Color(0xFF15803D);
}

ThemeData buildTheme() {
  final base = ThemeData(
    useMaterial3: true,
    colorScheme: ColorScheme.fromSeed(seedColor: Brand.green, primary: Brand.green, surface: Colors.white),
    scaffoldBackgroundColor: Brand.ground,
  );
  final text = GoogleFonts.cairoTextTheme(base.textTheme).apply(bodyColor: Brand.ink, displayColor: Brand.ink);
  return base.copyWith(
    textTheme: text,
    appBarTheme: AppBarTheme(
      backgroundColor: Brand.ground,
      foregroundColor: Brand.ink,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: false,
      titleTextStyle: GoogleFonts.cairo(fontSize: 20, fontWeight: FontWeight.w800, color: Brand.ink),
    ),
    cardTheme: CardThemeData(
      color: Colors.white,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16), side: const BorderSide(color: Brand.line)),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: Brand.green,
        minimumSize: const Size.fromHeight(52),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        textStyle: GoogleFonts.cairo(fontSize: 16, fontWeight: FontWeight.w700),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size.fromHeight(48),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        textStyle: GoogleFonts.cairo(fontSize: 15, fontWeight: FontWeight.w700),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: Colors.white,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: const BorderSide(color: Brand.line)),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: const BorderSide(color: Brand.line)),
      focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: const BorderSide(color: Brand.green, width: 2)),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: Colors.white,
      indicatorColor: Brand.green.withValues(alpha: 0.14),
      labelTextStyle: WidgetStatePropertyAll(GoogleFonts.cairo(fontSize: 12, fontWeight: FontWeight.w600)),
      iconTheme: WidgetStateProperty.resolveWith((s) =>
          IconThemeData(color: s.contains(WidgetState.selected) ? Brand.greenDark : Brand.muted)),
    ),
  );
}
