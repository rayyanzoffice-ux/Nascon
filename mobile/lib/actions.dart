import 'dart:async';
import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';
import 'main.dart';
import 'screens.dart';
import 'services.dart';
import 'shop.dart';
export 'roster_screen.dart' show RosterScreen;

const scoreTypes = <String, List<String>>{
  'football': ['goal'],
  'basketball': ['free_throw', 'two_pointer', 'three_pointer'],
  'cricket': [
    'dot_ball',
    'single',
    'two',
    'four',
    'six',
    'wide',
    'no_ball',
    'wicket'
  ],
  'esports': ['round_win'],
};

class MatchScreen extends StatefulWidget {
  final String matchId;
  const MatchScreen({super.key, required this.matchId});
  @override
  State<MatchScreen> createState() => _MatchScreenState();
}

class _MatchScreenState extends State<MatchScreen> {
  late Future<dynamic> future;
  Map<String, dynamic>? current;
  Timer? poll;
  @override
  void initState() {
    super.initState();
    refresh();
    poll = Timer.periodic(const Duration(seconds: 5), (_) {
      if (mounted && store.online) setState(refresh);
    });
  }

  void refresh() {
    future = store.cached(
        'match_${widget.matchId}', '/audit/v1/score/${widget.matchId}');
  }

  @override
  void dispose() {
    poll?.cancel();
    super.dispose();
  }

  Future<void> score() async {
    final match = current;
    if (match == null) return;
    final types = scoreTypes[match['sport_id']] ?? [];
    if (types.isEmpty) {
      toast(context, 'This sport needs a scoring template from the server.');
      return;
    }
    String team = match['home']['team_id'].toString();
    String eventType = types.first;
    final chosen = await showDialog<Map<String, String>>(
        context: context,
        builder: (dialogContext) => StatefulBuilder(
            builder: (context, update) => AlertDialog(
                  title: const Text('Record score event'),
                  content: Column(mainAxisSize: MainAxisSize.min, children: [
                    DropdownButtonFormField<String>(
                        initialValue: team,
                        isExpanded: true,
                        decoration: const InputDecoration(labelText: 'Team'),
                        items: [
                          match['home']['team_id'].toString(),
                          match['away']['team_id'].toString()
                        ]
                            .map((id) => DropdownMenuItem(
                                value: id,
                                child:
                                    Text(id, overflow: TextOverflow.ellipsis)))
                            .toList(),
                        onChanged: (v) {
                          if (v != null) update(() => team = v);
                        }),
                    const SizedBox(height: 14),
                    DropdownButtonFormField<String>(
                        initialValue: eventType,
                        isExpanded: true,
                        decoration:
                            const InputDecoration(labelText: 'Event type'),
                        items: types
                            .map((type) => DropdownMenuItem(
                                value: type,
                                child: Text(type.replaceAll('_', ' '))))
                            .toList(),
                        onChanged: (v) {
                          if (v != null) update(() => eventType = v);
                        }),
                  ]),
                  actions: [
                    TextButton(
                        onPressed: () => Navigator.pop(dialogContext),
                        child: const Text('Cancel')),
                    FilledButton(
                        onPressed: () => Navigator.pop(dialogContext,
                            {'team_id': team, 'event_type': eventType}),
                        child: const Text('Save event')),
                  ],
                )));
    if (chosen == null || !mounted) return;
    await queueEvent('score', chosen);
  }

  Future<void> correct(Map<String, dynamic> target) async {
    final yes = await showDialog<bool>(
        context: context,
        builder: (c) => AlertDialog(
              title: const Text('Reverse this event?'),
              content: Text(
                  'A signed correction will reverse event #${target['sequence']}. The original remains in the audit timeline.'),
              actions: [
                TextButton(
                    onPressed: () => Navigator.pop(c, false),
                    child: const Text('Cancel')),
                FilledButton(
                    onPressed: () => Navigator.pop(c, true),
                    child: const Text('Reverse event'))
              ],
            ));
    if (yes != true || !mounted) return;
    await queueEvent('compensation', {
      'compensates': target['event_id'],
      'reason': 'Score corrected by organizer',
    });
  }

  Future<void> queueEvent(String kind, Map<String, dynamic> payload) async {
    final match = current;
    if (match == null) return;
    final event = <String, dynamic>{
      'event_id': 'evt-${const Uuid().v4()}',
      'match_id': widget.matchId,
      'type': kind,
      'payload': payload,
    };
    final id =
        await store.queueAction('score_event', event, match['version'] as int);
    if (!mounted) return;
    final result = store.results.where((r) => r['action_id'] == id).firstOrNull;
    final message = result == null
        ? 'Saved offline. This event is pending sync.'
        : result['status'] == 'rejected'
            ? readableError(result['error_code']?.toString(),
                'The event was rejected. Review Sync status.')
            : 'Event ${result['status']}. The match will refresh shortly.';
    toast(context, message);
    setState(refresh);
  }

  Future<void> cancelMatch() async {
    final yes = await showDialog<bool>(
        context: context,
        builder: (c) => AlertDialog(
              title: const Text('Cancel this match?'),
              content: const Text('The match will remain in the record as cancelled.'),
              actions: [
                TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Keep match')),
                FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('Cancel match')),
              ],
            ));
    if (yes != true || !mounted) return;
    try {
      await store.request('POST', '/mobile/v1/matches/${widget.matchId}/cancel');
      if (mounted) {
        toast(context, 'Match cancelled.');
        setState(refresh);
      }
    } catch (e) {
      if (mounted) toast(context, e.toString());
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Match centre'), actions: [
          IconButton(
              tooltip: 'Refresh match',
              onPressed: () => setState(refresh),
              icon: const Icon(Icons.refresh)),
        ]),
        body: Column(children: [
          const SyncBanner(),
          Expanded(
              child: FutureBuilder<dynamic>(
                  future: future,
                  builder: (context, snapshot) {
                    if (snapshot.data is Map)
                      current = Map<String, dynamic>.from(snapshot.data);
                    final match = current;
                    if (match == null)
                      return Center(
                          child: Padding(
                              padding: const EdgeInsets.all(24),
                              child: Text(snapshot.hasError
                                  ? snapshot.error.toString()
                                  : 'Loading match…')));
                    final home = match['home'], away = match['away'];
                    final canScore = store.role == 'league_organizer' ||
                        store.role == 'super_admin';
                    final events = (match['events'] as List).cast<Map>();
                    return RefreshIndicator(
                        onRefresh: () async {
                          setState(refresh);
                          await future;
                        },
                        child: ListView(
                            padding: const EdgeInsets.all(16),
                            children: [
                              header('Live match',
                                  '${match['sport_id']} • ${match['status'].toString().replaceAll('_', ' ')}'),
                              Card(
                                  child: Padding(
                                      padding: const EdgeInsets.symmetric(
                                          vertical: 28, horizontal: 14),
                                      child: Column(children: [
                                        const Text('MATCH SCORE',
                                            style: TextStyle(
                                                fontSize: 11,
                                                letterSpacing: 2,
                                                color: Color(0xff54e0cf),
                                                fontWeight: FontWeight.bold)),
                                        const SizedBox(height: 14),
                                        Row(children: [
                                          Expanded(
                                              child: Text(
                                                  home['team_id'].toString(),
                                                  textAlign: TextAlign.center,
                                                  maxLines: 2,
                                                  overflow:
                                                      TextOverflow.ellipsis,
                                                  style: const TextStyle(
                                                      fontWeight:
                                                          FontWeight.bold))),
                                          Text(
                                              '${home['score']}  :  ${away['score']}',
                                              style: const TextStyle(
                                                  fontSize: 31,
                                                  fontWeight: FontWeight.w900,
                                                  color: Color(0xff54e0cf))),
                                          Expanded(
                                              child: Text(
                                                  away['team_id'].toString(),
                                                  textAlign: TextAlign.center,
                                                  maxLines: 2,
                                                  overflow:
                                                      TextOverflow.ellipsis,
                                                  style: const TextStyle(
                                                      fontWeight:
                                                          FontWeight.bold))),
                                        ]),
                                      ]))),
                              if (canScore) ...[
                                if (match['status'] != 'completed' && match['status'] != 'cancelled')
                                  TextButton.icon(
                                      onPressed: cancelMatch,
                                      icon: const Icon(Icons.event_busy),
                                      label: const Text('Cancel match')),
                                const SizedBox(height: 12),
                                ElevatedButton.icon(
                                    onPressed: match['status'] == 'in_progress'
                                        ? score
                                        : null,
                                    icon: const Icon(Icons.add_circle_outline),
                                    label: const Text('Record score event')),
                                if (match['status'] != 'in_progress')
                                  const Padding(
                                      padding: EdgeInsets.all(8),
                                      child: Text(
                                          'Scoring is available only while the match is in progress.',
                                          style: TextStyle(
                                              color: Colors.white70))),
                              ],
                              header('Event timeline',
                                  'Signed match history • newest first'),
                              if (events.isEmpty)
                                const Card(
                                    child: ListTile(
                                        title: Text('No events recorded yet'))),
                              ...events.reversed.map((raw) {
                                final e = Map<String, dynamic>.from(raw);
                                final payload = e['payload'] as Map? ?? {};
                                final reversible = canScore &&
                                    e['type'] == 'score' &&
                                    e['compensated'] != true;
                                return Card(
                                    child: ListTile(
                                  leading: Icon(
                                      e['compensated'] == true
                                          ? Icons.undo
                                          : Icons.bolt,
                                      color: const Color(0xff54e0cf)),
                                  title: Text(
                                      '#${e['sequence']}  ${e['type'].toString().replaceAll('_', ' ')}',
                                      style: const TextStyle(
                                          fontWeight: FontWeight.bold)),
                                  subtitle: Text(
                                      '${payload['team_id'] ?? ''} ${payload['event_type'] ?? payload['reason'] ?? ''}\nSigned • ${e['signature']?.toString().substring(0, 10) ?? 'pending'}…',
                                      maxLines: 3,
                                      overflow: TextOverflow.ellipsis),
                                  trailing: reversible
                                      ? IconButton(
                                          tooltip: 'Reverse event',
                                          icon: const Icon(Icons.undo),
                                          onPressed: () => correct(e))
                                      : null,
                                ));
                              }),
                              header('Featured merchandise',
                                  'Official league kit'),
                              Card(
                                  child: ListTile(
                                leading: const Icon(Icons.checkroom,
                                    color: Color(0xff54e0cf)),
                                title: const Text('Official league jersey'),
                                subtitle: const Text(
                                    'Shop sizes and pay with the mock gateway'),
                                trailing: const Icon(Icons.chevron_right),
                                onTap: () => Navigator.push(
                                    context,
                                    MaterialPageRoute(
                                        builder: (_) => const StoreScreen())),
                              )),
                            ]));
                  })),
        ]),
      );
}
