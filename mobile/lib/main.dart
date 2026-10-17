import 'package:flutter/material.dart';
import 'services.dart';
import 'screens.dart';

late final AppStore store;
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  store = AppStore();
  await store.initialize();
  runApp(const NasconApp());
}

class NasconApp extends StatelessWidget {
  const NasconApp({super.key});
  @override
  Widget build(BuildContext context) => AnimatedBuilder(
      animation: store,
      builder: (_, __) => MaterialApp(
            debugShowCheckedModeBanner: false,
            title: 'NaSCon LeagueOS',
            theme: ThemeData(
                useMaterial3: true,
                brightness: Brightness.dark,
                scaffoldBackgroundColor: const Color(0xff091524),
                colorScheme: ColorScheme.fromSeed(
                    seedColor: const Color(0xff54e0cf),
                    brightness: Brightness.dark,
                    surface: const Color(0xff12253a)),
                appBarTheme: const AppBarTheme(
                    backgroundColor: Color(0xff091524),
                    centerTitle: false,
                    titleTextStyle: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w800,
                        color: Colors.white)),
                inputDecorationTheme: InputDecorationTheme(
                    border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12)),
                    contentPadding: const EdgeInsets.symmetric(
                        horizontal: 15, vertical: 16)),
                cardTheme: CardThemeData(
                    color: const Color(0xff12253a),
                    elevation: 0,
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(18))),
                elevatedButtonTheme: ElevatedButtonThemeData(
                    style: ElevatedButton.styleFrom(
                        minimumSize: const Size.fromHeight(50),
                        backgroundColor: const Color(0xff54e0cf),
                        foregroundColor: const Color(0xff06131e),
                        shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12)))),
                outlinedButtonTheme: OutlinedButtonThemeData(
                    style: OutlinedButton.styleFrom(
                        minimumSize: const Size.fromHeight(48)))),
            home: store.token.isEmpty ? const LoginScreen() : const MainShell(),
          ));
}

void toast(BuildContext context, String message) {
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
}

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final mail = TextEditingController(text: 'organizer@nascon.test');
  final password = TextEditingController(text: 'Nascon@26');
  bool busy = false;
  @override
  void dispose() {
    mail.dispose();
    password.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        body: SafeArea(
            child: Center(
                child: SingleChildScrollView(
                    padding: const EdgeInsets.all(24),
                    child: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 440),
                        child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              const Icon(Icons.sports_soccer,
                                  size: 68,
                                  color: Color(0xff54e0cf),
                                  semanticLabel: 'NaSCon LeagueOS'),
                              const SizedBox(height: 16),
                              const Text('LEAGUE OS',
                                  textAlign: TextAlign.center,
                                  style: TextStyle(
                                      fontSize: 32,
                                      fontWeight: FontWeight.w900,
                                      letterSpacing: 2)),
                              const SizedBox(height: 4),
                              const Text('NaSCon 2026  /  MATCHDAY',
                                  textAlign: TextAlign.center,
                                  style: TextStyle(
                                      color: Color(0xff54e0cf),
                                      fontSize: 12,
                                      letterSpacing: 2,
                                      fontWeight: FontWeight.bold)),
                              const SizedBox(height: 28),
                              const Text('Welcome back',
                                  style: TextStyle(
                                      fontSize: 25,
                                      fontWeight: FontWeight.bold)),
                              const SizedBox(height: 5),
                              const Text(
                                  'Sign in to follow the league and manage your club.',
                                  style: TextStyle(color: Colors.white70)),
                              const SizedBox(height: 22),
                              DropdownButtonFormField<String>(
                                  initialValue: mail.text,
                                  isExpanded: true,
                                  decoration: const InputDecoration(
                                      labelText: 'Demo account',
                                      prefixIcon: Icon(Icons.badge_outlined)),
                                  items: const [
                                    DropdownMenuItem(
                                        value: 'admin@nascon.test',
                                        child: Text('Platform admin')),
                                    DropdownMenuItem(
                                        value: 'organizer@nascon.test',
                                        child: Text('League organizer')),
                                    DropdownMenuItem(
                                        value: 'manager@nascon.test',
                                        child: Text('Club manager')),
                                    DropdownMenuItem(
                                        value: 'player@nascon.test',
                                        child: Text('Player')),
                                    DropdownMenuItem(
                                        value: 'viewer@nascon.test',
                                        child: Text('Viewer')),
                                  ],
                                  onChanged: (value) {
                                    if (value != null) mail.text = value;
                                  }),
                              const SizedBox(height: 14),
                              TextField(
                                  controller: password,
                                  obscureText: true,
                                  decoration: const InputDecoration(
                                      labelText: 'Password',
                                      prefixIcon: Icon(Icons.lock_outline))),
                              const SizedBox(height: 20),
                              ElevatedButton(
                                  onPressed: busy
                                      ? null
                                      : () async {
                                          setState(() => busy = true);
                                          try {
                                            await store.login(mail.text.trim(),
                                                password.text);
                                          } catch (e) {
                                            if (context.mounted)
                                              toast(context, e.toString());
                                          }
                                          if (mounted)
                                            setState(() => busy = false);
                                        },
                                  child:
                                      Text(busy ? 'Signing in…' : 'Sign in')),
                              const SizedBox(height: 18),
                              OutlinedButton.icon(
                                  onPressed: () => Navigator.push(
                                      context,
                                      MaterialPageRoute(
                                          builder: (_) =>
                                              const ServerSettings())),
                                  icon: const Icon(Icons.settings_ethernet),
                                  label:
                                      const Text('Configure server address')),
                              const SizedBox(height: 12),
                              const Text('Demo password: Nascon@26',
                                  textAlign: TextAlign.center,
                                  style: TextStyle(color: Colors.white70)),
                            ]))))),
      );
}
