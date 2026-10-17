import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nascon_mobile/main.dart' as app;
import 'package:nascon_mobile/services.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

class UiStore extends AppStore {
  final Map<String, dynamic> saved = {};
  Map<String, dynamic>? checkoutBody;
  @override
  Future<dynamic> local(String key) async => saved[key];
  @override
  Future<void> save(String key, dynamic value) async {
    saved[key] = value;
    notifyListeners();
  }

  @override
  Future<void> ping() async {
    online = true;
    notifyListeners();
  }

  @override
  Future<void> login(String mail, String password) async {
    if (password != 'Nascon@26') throw ApiError('Wrong password');
    email = mail;
    role = AppStore.demoRoles[mail.split('@').first] ?? 'viewer';
    tenantId = 'tenant-alpha';
    token = 'test-token';
    online = true;
    notifyListeners();
  }

  @override
  Future<void> logout() async {
    token = '';
    notifyListeners();
  }

  @override
  Future<dynamic> cached(String key, String path) async {
    if (key == 'fixtures') {
      final fixtures = [
        {
          'match_id': 'demo-match-1',
          'league_id': 'demo-league',
          'sport_id': 'football',
          'home': 'demo-team-a',
          'away': 'demo-team-b',
          'status': 'in_progress',
          'home_score': 0,
          'away_score': 0,
          'start_time': '2026-10-17T12:00:00Z'
        }
      ];
      saved[key] = fixtures;
      return fixtures;
    }
    if (key == 'leagues')
      return [
        {'league_id': 'demo-league', 'sport_id': 'football'}
      ];
    if (key.startsWith('standings_'))
      return {
        'league_id': 'demo-league',
        'sport_id': 'football',
        'table': [
          {
            'rank': 1,
            'team_id': 'demo-team-a',
            'status': 'still_possible',
            'played': 0,
            'points': 0,
            'diff': 0
          }
        ]
      };
    if (key == 'clubs') return [];
    if (key.startsWith('match_'))
      return {
        'sport_id': 'football',
        'status': 'in_progress',
        'version': 1,
        'home': {'team_id': 'demo-team-a', 'score': 0},
        'away': {'team_id': 'demo-team-b', 'score': 0},
        'events': []
      };
    if (key == 'catalogue')
      return [
        {
          'name': 'Official League Jersey',
          'category': 'apparel',
          'variants': [
            {
              'variant_id': 'var-jersey-001-M',
              'size': 'M',
              'stock': 1,
              'price_minor': 450000
            }
          ]
        }
      ];
    return {};
  }

  @override
  Future<dynamic> clubsWithRosterCache() => cached('clubs', '/mobile/v1/clubs');
  @override
  Future<dynamic> request(String method, String path, {dynamic data}) async {
    if (path == '/audit/v1/checkout') {
      checkoutBody = Map<String, dynamic>.from(data);
      return {
        'order_id': data['order_id'],
        'status': 'paid',
        'items': [
          {
            'variant_id': 'var-jersey-001-M',
            'quantity': 1,
            'unit_price_minor': 450000
          }
        ],
        'subtotal_minor': 450000,
        'discount_minor': 0,
        'total_minor': 450000,
        'payment': {'state': 'captured'},
        'receipt': {
          'payload': {'paid_at': '2026-10-17T12:00:00Z'},
          'signature': 'signed',
          'pdf_base64': 'JVBERi0='
        }
      };
    }
    throw ApiError('Unexpected request');
  }
}

class SyncStore extends AppStore {
  bool fail = false;
  bool duplicate = false;
  @override
  Future<dynamic> request(String method, String path, {dynamic data}) async {
    if (fail) throw ApiError('Server unreachable');
    final actions = (data['actions'] as List).cast<Map>();
    return {
      'results': actions.map((a) {
        final roster = a['type'] == 'roster_transfer';
        final status = duplicate
            ? 'duplicate'
            : roster
                ? 'rejected'
                : 'applied';
        return {
          'action_id': a['action_id'],
          'status': status,
          'resolution': status == 'rejected'
              ? 'server_wins'
              : status == 'duplicate'
                  ? 'skipped_duplicate'
                  : 'appended',
          'error_code': status == 'rejected' ? 'SQUAD_FULL' : null
        };
      }).toList()
    };
  }
}

void main() {
  final ui = UiStore();
  app.store = ui;

  testWidgets('360 × 640 login and standings to match navigation',
      (tester) async {
    tester.view.physicalSize = const Size(360, 640);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    ui.token = '';
    await tester.pumpWidget(const app.NasconApp());
    await tester.pumpAndSettle();
    expect(find.text('Platform admin'), findsNothing);
    await tester.tap(find.text('League organizer'));
    await tester.pumpAndSettle();
    expect(find.text('Platform admin'), findsOneWidget);
    await tester.tap(find.text('League organizer').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Sign in'));
    await tester.pumpAndSettle();
    expect(find.text('Matchday'), findsOneWidget);
    await tester.tap(find.text('Standings').last);
    await tester.pumpAndSettle();
    expect(find.text('League matches'), findsOneWidget);
    await tester.scrollUntilVisible(
        find.text('demo-team-a vs demo-team-b'), 160);
    await tester.tap(find.text('demo-team-a vs demo-team-b').last);
    await tester.pumpAndSettle();
    expect(find.text('Match centre'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('cart checkout shows PKR receipt at phone width', (tester) async {
    tester.view.physicalSize = const Size(360, 640);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    ui.token = '';
    ui.saved.clear();
    await tester.pumpWidget(const app.NasconApp());
    await tester.pumpAndSettle();
    await tester.tap(find.text('Sign in'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Store').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Add'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Checkout securely'), 180);
    await tester.tap(find.text('Checkout securely'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Pay now'));
    await tester.pumpAndSettle();
    expect(ui.checkoutBody?['items'][0]['variant_id'], 'var-jersey-001-M');
    expect(find.text('Payment successful'), findsOneWidget);
    expect(find.text('PKR 4500.00'), findsWidgets);
    expect(tester.takeException(), isNull);
  });

  test('queue survives restart; rejected stays; duplicate clears on retry',
      () async {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
    final temp = await Directory.systemTemp.createTemp('nascon-queue-test');
    addTearDown(() => temp.delete(recursive: true));
    final path = '${temp.path}/queue.db';
    final first = SyncStore();
    first.db = await openDatabase(path, version: 1, onCreate: (db, _) async {
      await db.execute(
          'CREATE TABLE cache (key TEXT PRIMARY KEY, value TEXT NOT NULL)');
      await db.execute(
          'CREATE TABLE queue (id TEXT PRIMARY KEY, data TEXT NOT NULL)');
    });
    first.deviceId = 'dev-test';
    await first.save('device_id', first.deviceId);
    first.online = false;
    await first.queueAction('score_event', {'event_id': 'evt-1'}, 3);
    await first.queueAction('roster_transfer', {'request_id': 'tr-1'}, 1);
    expect(first.pending.length, 2);
    first.online = true;
    first.fail = true;
    await first.sync();
    expect(first.pending.length, 2);
    first.fail = false;
    await first.sync();
    expect(first.pending.length, 1);
    expect(
        first.rejectedIds.contains(first.pending.single['action_id']), isTrue);
    await first.db!.close();

    final reopened = SyncStore();
    reopened.db = await openDatabase(path);
    reopened.deviceId = await reopened.local('device_id') as String;
    await reopened.loadQueue();
    expect(reopened.deviceId, 'dev-test');
    expect(reopened.pending.length, 1);
    expect(reopened.rejectedIds.contains(reopened.pending.single['action_id']),
        isTrue);
    reopened.duplicate = true;
    await reopened.sync(retryRejected: true);
    expect(reopened.pending, isEmpty);
    await reopened.db!.close();
  });
}
