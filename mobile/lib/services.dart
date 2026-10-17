import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart';
import 'package:uuid/uuid.dart';

class ApiError implements Exception {
  final String message;
  ApiError(this.message);
  @override String toString() => message;
}

class AppStore extends ChangeNotifier {
  static const secure = FlutterSecureStorage();
  static const uuid = Uuid();
  Database? db;
  String server = 'http://10.0.2.2:8080';
  String role = 'viewer', email = '', token = '';
  bool online = false, syncing = false;
  String lastError = '';
  List<Map<String, dynamic>> pending = [];
  List<Map<String, dynamic>> results = [];

  Future<void> initialize() async {
    final base = await getDatabasesPath();
    db = await openDatabase(p.join(base, 'nascon_cache.db'), version: 1,
      onCreate: (database, version) async {
        await database.execute('CREATE TABLE cache (key TEXT PRIMARY KEY, value TEXT NOT NULL)');
        await database.execute('CREATE TABLE queue (id TEXT PRIMARY KEY, data TEXT NOT NULL)');
      });
    server = await local('server') as String? ?? server;
    token = await secure.read(key: 'jwt') ?? '';
    role = await secure.read(key: 'role') ?? 'viewer';
    email = await secure.read(key: 'email') ?? '';
    await loadQueue();
    await ping();
  }

  Future<dynamic> local(String key) async {
    final rows = await db!.query('cache', where: 'key = ?', whereArgs: [key], limit: 1);
    return rows.isEmpty ? null : jsonDecode(rows.first['value'] as String);
  }

  Future<void> save(String key, dynamic value) async {
    await db!.insert('cache', {'key': key, 'value': jsonEncode(value)},
      conflictAlgorithm: ConflictAlgorithm.replace);
    notifyListeners();
  }

  Future<void> configureServer(String input) async {
    server = input.trim().replaceAll(RegExp(r'/$'), '');
    if (!server.startsWith('http://') && !server.startsWith('https://')) server = 'http://$server';
    await save('server', server);
    await ping();
  }

  Future<dynamic> request(String method, String path, {dynamic data}) async {
    try {
      final uri = Uri.parse('$server$path');
      final headers = <String,String>{'Content-Type':'application/json'};
      if (token.isNotEmpty) headers['Authorization'] = 'Bearer $token';
      final response = await (method == 'GET'
        ? http.get(uri, headers: headers)
        : http.post(uri, headers: headers, body: jsonEncode(data ?? {})))
        .timeout(const Duration(seconds: 5));
      final parsed = jsonDecode(response.body);
      online = true;
      notifyListeners();
      if (response.statusCode >= 400) {
        final msg = parsed is Map ? (parsed['error']?['message'] ?? 'Request refused') : 'Request refused';
        throw ApiError(msg.toString());
      }
      return parsed;
    } on ApiError { rethrow; }
      catch (_) {
        online = false;
        notifyListeners();
        throw ApiError('Cannot reach the server. Saved information remains available offline.');
      }
  }

  Future<dynamic> cached(String key, String path) async {
    try {
      final value = await request('GET', path);
      await save(key, value);
      return value;
    } catch (_) {
      final previous = await local(key);
      if (previous != null) return previous;
      rethrow;
    }
  }

  Future<void> ping() async {
    try { await request('GET', '/health'); }
    catch (_) { online = false; notifyListeners(); }
  }

  Future<void> login(String mail,String password) async {
    final data = await request('POST','/mobile/v1/login',
        data: {'email':mail,'password':password});
    token = data['token'] as String;
    role = data['role'] as String;
    email = mail;
    await secure.write(key: 'jwt', value: token);
    await secure.write(key: 'role', value: role);
    await secure.write(key: 'email', value: email);
    try { await request('POST','/mobile/v1/demo-setup'); } catch (_) {}
    notifyListeners();
  }

  Future<void> logout() async {
    token = '';role='viewer';email='';
    await secure.deleteAll();
    notifyListeners();
  }

  Future<void> loadQueue() async {
    final rows = await db!.query('queue', orderBy: 'rowid ASC');
    pending = rows.map((r) => Map<String,dynamic>.from(jsonDecode(r['data'] as String))).toList();
    results = (await local('sync_results') as List? ?? [])
        .map((x) => Map<String,dynamic>.from(x)).toList();
    notifyListeners();
  }

  Future<void> queueAction(String type,Map<String,dynamic> payload,int baseVersion) async {
    final entry = {'action_id':uuid.v4(),'type':type,
      'queued_at':DateTime.now().toUtc().toIso8601String().split('.').first+'Z',
      'base_version':baseVersion,'payload':payload};
    await db!.insert('queue',{'id':entry['action_id'], 'data':jsonEncode(entry)});
    await loadQueue();
    if (online) await sync();
  }

  Future<void> sync() async {
    if (pending.isEmpty || syncing) return;
    syncing=true;notifyListeners();
    try {
      final response=await request('POST','/audit/v1/offline-sync',
        data:{'device_id':'nascon-android','actions':pending});
      results = List<Map<String,dynamic>>.from(
        (response['results'] as List).map((x) => Map<String,dynamic>.from(x)));
      await db!.delete('queue');
      await save('sync_results',results);
      await loadQueue();
      lastError='';
    } catch(e) {lastError=e.toString();}
    syncing=false;notifyListeners();
  }
}
