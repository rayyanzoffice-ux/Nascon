import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart';
import 'package:uuid/uuid.dart';

class ApiError implements Exception {
  final String message;
  final String? code;
  ApiError(this.message, [this.code]);
  @override
  String toString() => message;
}

String readableError(String? code, String fallback) {
  const messages = <String, String>{
    'TRANSFER_WINDOW_CLOSED':
        'Choose an effective date inside the transfer window.',
    'NOT_IN_SQUAD':
        'This player is no longer in the selected squad. Refresh the roster.',
    'PLAYER_ON_LOAN': 'This player is already on loan.',
    'SQUAD_FULL': 'The destination squad is full.',
    'INVALID_BASE_VERSION':
        'The server has newer changes. Refresh and review this action.',
    'MATCH_NOT_IN_PROGRESS':
        'This match is not live. Refresh the match before scoring.',
    'UNKNOWN_EVENT_TYPE':
        'This score type is not supported by the match sport.',
    'INVALID_COMPENSATION':
        'That event can no longer be reversed. Refresh the timeline.',
    'OUT_OF_STOCK': 'That size sold out. Choose another available size.',
  };
  return messages[code] ??
      (fallback.isNotEmpty
          ? fallback
          : 'The server could not complete this action.');
}

class AppStore extends ChangeNotifier {
  static const secure = FlutterSecureStorage();
  static const uuid = Uuid();
  static const demoRoles = <String, String>{
    'admin': 'super_admin',
    'organizer': 'league_organizer',
    'manager': 'club_manager',
    'player': 'player',
    'viewer': 'viewer',
  };
  Database? db;
  String server = 'http://10.0.2.2:8080';
  String role = 'viewer', email = '', token = '', tenantId = '', deviceId = '';
  bool online = false, syncing = false;
  String lastError = '';
  List<Map<String, dynamic>> pending = [];
  List<Map<String, dynamic>> results = [];
  Set<String> rejectedIds = {};

  Future<void> initialize() async {
    final base = await getDatabasesPath();
    db = await openDatabase(p.join(base, 'nascon_cache.db'), version: 1,
        onCreate: (database, version) async {
      await database.execute(
          'CREATE TABLE cache (key TEXT PRIMARY KEY, value TEXT NOT NULL)');
      await database.execute(
          'CREATE TABLE queue (id TEXT PRIMARY KEY, data TEXT NOT NULL)');
    });
    server = await local('server') as String? ?? server;
    deviceId = await local('device_id') as String? ?? '';
    if (deviceId.isEmpty) {
      deviceId = 'dev-${uuid.v4()}';
      await save('device_id', deviceId);
    }
    token = await secure.read(key: 'jwt') ?? '';
    role = await secure.read(key: 'role') ?? 'viewer';
    email = await secure.read(key: 'email') ?? '';
    tenantId = await secure.read(key: 'tenant_id') ?? '';
    await loadQueue();
    await ping();
  }

  Future<dynamic> local(String key) async {
    final rows =
        await db!.query('cache', where: 'key = ?', whereArgs: [key], limit: 1);
    return rows.isEmpty ? null : jsonDecode(rows.first['value'] as String);
  }

  Future<void> save(String key, dynamic value) async {
    await db!.insert('cache', {'key': key, 'value': jsonEncode(value)},
        conflictAlgorithm: ConflictAlgorithm.replace);
    notifyListeners();
  }

  Future<void> configureServer(String input) async {
    var next = input.trim().replaceAll(RegExp(r'/+$'), '');
    if (!next.startsWith('http://') && !next.startsWith('https://'))
      next = 'http://$next';
    final uri = Uri.tryParse(next);
    if (uri == null ||
        !uri.hasAuthority ||
        !['http', 'https'].contains(uri.scheme)) {
      throw ApiError(
          'Enter a valid server address, such as http://192.168.1.5:8080.');
    }
    server = next;
    await save('server', server);
    await ping();
  }

  Future<dynamic> request(String method, String path, {dynamic data}) async {
    http.Response response;
    try {
      final uri = Uri.parse('$server$path');
      final headers = <String, String>{'Content-Type': 'application/json'};
      if (token.isNotEmpty) headers['Authorization'] = 'Bearer $token';
      response = await (method == 'GET'
              ? http.get(uri, headers: headers)
              : http.post(uri, headers: headers, body: jsonEncode(data ?? {})))
          .timeout(const Duration(seconds: 6));
    } catch (_) {
      online = false;
      notifyListeners();
      throw ApiError(
          'Cannot reach the server. Saved information remains available offline.');
    }
    online = true;
    notifyListeners();
    dynamic parsed;
    try {
      parsed = jsonDecode(response.body);
    } catch (_) {
      throw ApiError('The server returned an unreadable response.');
    }
    if (response.statusCode >= 400) {
      final error = parsed is Map ? parsed['error'] : null;
      final code = error is Map ? error['code']?.toString() : null;
      final message = error is Map ? error['message']?.toString() ?? '' : '';
      throw ApiError(readableError(code, message), code);
    }
    return parsed;
  }

  Future<dynamic> cached(String key, String path) async {
    final scopedKey = '${email.isEmpty ? 'guest' : email}::$key';
    try {
      final value = await request('GET', path);
      await save(scopedKey, value);
      return value;
    } catch (_) {
      final previous = await local(scopedKey);
      if (previous != null) return previous;
      rethrow;
    }
  }

  Future<dynamic> clubsWithRosterCache() async {
    final clubs = await cached('clubs', '/mobile/v1/clubs');
    if (online && clubs is List) {
      for (final club in clubs) {
        if (club is! Map || club['tenant_id'] != tenantId) continue;
        for (final player in (club['roster'] as List? ?? [])) {
          if (player is! Map || player['player_id'] == null) continue;
          final id = player['player_id'].toString();
          try {
            await cached('roster_$id', '/audit/v1/roster/history/$id');
          } catch (_) {/* A missing history must not hide the club. */}
        }
      }
    }
    return clubs;
  }

  Future<void> ping() async {
    try {
      await request('GET', '/health');
      if (pending.any((a) => !rejectedIds.contains(a['action_id'])))
        await sync();
    } catch (_) {
      online = false;
      notifyListeners();
    }
  }

  Future<void> login(String mail, String password) async {
    dynamic data;
    try {
      data = await request('POST', '/mobile/v1/login',
          data: {'email': mail, 'password': password});
    } on ApiError {
      final prefix = mail.split('@').first;
      if (online ||
          !demoRoles.containsKey(prefix) ||
          mail != '$prefix@nascon.test' ||
          password != 'Nascon@26') rethrow;
      final cachedToken = await secure.read(key: 'demo_jwt_$prefix');
      if (cachedToken == null)
        throw ApiError(
            'Connect once to prepare this demo account for offline sign-in.');
      data = {
        'token': cachedToken,
        'role': demoRoles[prefix],
        'tenant_id': 'tenant-alpha'
      };
    }
    token = data['token'] as String;
    role = data['role'] as String;
    email = mail;
    tenantId = data['tenant_id']?.toString() ?? '';
    await secure.write(key: 'jwt', value: token);
    await secure.write(key: 'role', value: role);
    await secure.write(key: 'email', value: email);
    await secure.write(key: 'tenant_id', value: tenantId);
    if (online) {
      try {
        await request('POST', '/mobile/v1/demo-setup');
      } catch (_) {}
      await secure.write(key: 'demo_jwt_${mail.split('@').first}', value: token);
    }
    notifyListeners();
  }

  Future<void> logout() async {
    token = '';
    role = 'viewer';
    email = '';
    tenantId = '';
    await secure.delete(key: 'jwt');
    await secure.delete(key: 'role');
    await secure.delete(key: 'email');
    await secure.delete(key: 'tenant_id');
    notifyListeners();
  }

  Future<void> loadQueue() async {
    final rows = await db!.query('queue', orderBy: 'rowid ASC');
    pending = rows
        .map((r) => Map<String, dynamic>.from(jsonDecode(r['data'] as String)))
        .toList();
    results = (await local('sync_results') as List? ?? [])
        .map((x) => Map<String, dynamic>.from(x))
        .toList();
    rejectedIds = (await local('rejected_ids') as List? ?? [])
        .map((x) => x.toString())
        .toSet();
    notifyListeners();
  }

  Future<String> queueAction(
      String type, Map<String, dynamic> payload, int baseVersion) async {
    if (!['score_event', 'roster_transfer'].contains(type))
      throw ApiError('Unsupported offline action.');
    final id = uuid.v4();
    final entry = {
      'action_id': id,
      'type': type,
      'queued_at':
          DateTime.now().toUtc().toIso8601String().split('.').first + 'Z',
      'base_version': baseVersion,
      'payload': payload
    };
    await db!
        .insert('queue', {'id': entry['action_id'], 'data': jsonEncode(entry)});
    await loadQueue();
    if (online) await sync();
    return id;
  }

  Future<void> sync({bool retryRejected = false}) async {
    if (syncing) return;
    final actions = pending
        .where((a) => retryRejected || !rejectedIds.contains(a['action_id']))
        .take(100)
        .toList();
    if (actions.isEmpty) return;
    syncing = true;
    notifyListeners();
    try {
      final response = await request('POST', '/mobile/v1/offline-sync',
          data: {'device_id': deviceId, 'actions': actions});
      final received = (response['results'] as List)
          .map((x) => Map<String, dynamic>.from(x))
          .toList();
      final sentIds = actions.map((a) => a['action_id'].toString()).toSet();
      final confirmed = <String>{};
      for (final result in received) {
        final id = result['action_id']?.toString() ?? '';
        if (!sentIds.contains(id)) continue;
        if (['applied', 'duplicate'].contains(result['status']))
          confirmed.add(id);
        if (result['status'] == 'rejected') rejectedIds.add(id);
      }
      await db!.transaction((txn) async {
        for (final id in confirmed) {
          await txn.delete('queue', where: 'id = ?', whereArgs: [id]);
          rejectedIds.remove(id);
        }
      });
      results = [...received, ...results].take(100).toList();
      await save('sync_results', results);
      await save('rejected_ids', rejectedIds.toList());
      await loadQueue();
      lastError = '';
    } catch (e) {
      lastError = e.toString();
    }
    syncing = false;
    notifyListeners();
  }

  Future<void> discardRejected(String id) async {
    if (!rejectedIds.contains(id)) return;
    await db!.delete('queue', where: 'id = ?', whereArgs: [id]);
    rejectedIds.remove(id);
    await save('rejected_ids', rejectedIds.toList());
    await loadQueue();
  }
}
