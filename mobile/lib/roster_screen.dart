import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';
import 'main.dart';
import 'screens.dart';
import 'services.dart';

class RosterScreen extends StatefulWidget {
  const RosterScreen({super.key});
  @override
  State<RosterScreen> createState() => _RosterScreenState();
}

class _RosterScreenState extends State<RosterScreen> {
  late Future<dynamic> clubsFuture;
  Future<dynamic>? historyFuture;
  String? playerId;
  String action = 'transfer';
  final reason = TextEditingController(text: 'Tactical squad adjustment');
  final effective = TextEditingController(
      text: DateTime.now().toIso8601String().substring(0, 10));
  final loanEnd = TextEditingController(
      text: DateTime.now()
          .add(const Duration(days: 7))
          .toIso8601String()
          .substring(0, 10));
  final destination = TextEditingController(text: 'sq-demo-beta');
  bool busy = false;
  @override
  void initState() {
    super.initState();
    clubsFuture = store.clubsWithRosterCache();
  }

  @override
  void dispose() {
    reason.dispose();
    effective.dispose();
    loanEnd.dispose();
    destination.dispose();
    super.dispose();
  }

  void selectPlayer(String id) {
    setState(() {
      playerId = id;
      historyFuture =
          store.cached('roster_$id', '/audit/v1/roster/history/$id');
    });
  }

  Future<void> submit(Map<String, dynamic> history) async {
    if (busy || playerId == null) return;
    final selectedDate = DateTime.tryParse(effective.text.trim());
    final endDate = DateTime.tryParse(loanEnd.text.trim());
    if (selectedDate == null ||
        selectedDate.toIso8601String().substring(0, 10) !=
            effective.text.trim()) {
      toast(context, 'Enter an effective date as YYYY-MM-DD.');
      return;
    }
    if (action == 'loan' &&
        (endDate == null || !endDate.isAfter(selectedDate))) {
      toast(context, 'Loan end date must be after the effective date.');
      return;
    }
    final source = history['current_squad_id']?.toString() ?? '';
    if (source.isEmpty) {
      toast(context, 'This player has no active squad to move from.');
      return;
    }
    final target = action == 'release' ? null : destination.text.trim();
    if (target != null && (target.isEmpty || target == source)) {
      toast(context, 'Choose a different destination squad.');
      return;
    }
    final body = <String, dynamic>{
      'request_id': 'tr-${const Uuid().v4()}',
      'league_id': history['league_id'],
      'player_id': playerId,
      'type': action,
      'from_squad_id': source,
      'to_squad_id': target,
      'effective_date': effective.text.trim(),
      'loan_end_date': action == 'loan' ? loanEnd.text.trim() : null,
      'reason': reason.text.trim(),
      'requested_by': store.email,
    };
    final yes = await showDialog<bool>(
        context: context,
        builder: (c) => AlertDialog(
              title: Text('Confirm $action'),
              content: Text(
                  '${playerId!} • $source ${target == null ? '→ released' : '→ $target'}\nEffective ${effective.text.trim()}\n\nThis request may be queued for later sync.'),
              actions: [
                TextButton(
                    onPressed: () => Navigator.pop(c, false),
                    child: const Text('Cancel')),
                FilledButton(
                    onPressed: () => Navigator.pop(c, true),
                    child: const Text('Save request'))
              ],
            ));
    if (yes != true || !mounted) return;
    setState(() => busy = true);
    try {
      final id = await store.queueAction(
          'roster_transfer', body, (history['history'] as List).length);
      if (!mounted) return;
      final result =
          store.results.where((r) => r['action_id'] == id).firstOrNull;
      toast(
          context,
          result == null
              ? 'Roster request saved and pending sync.'
              : result['status'] == 'rejected'
                  ? readableError(result['error_code']?.toString(),
                      'The request was rejected. Review Sync status.')
                  : 'Roster request ${result['status']}. Refresh history to see the new squad.');
      if (result != null && result['status'] != 'rejected')
        selectPlayer(playerId!);
    } catch (e) {
      if (mounted) toast(context, e.toString());
    }
    if (mounted) setState(() => busy = false);
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Roster management')),
        body: Column(children: [
          const SyncBanner(),
          Expanded(
              child: FutureBuilder<dynamic>(
                  future: clubsFuture,
                  builder: (context, clubsSnapshot) {
                    final clubs = clubsSnapshot.data is List
                        ? clubsSnapshot.data as List
                        : [];
                    final players = <Map<String, dynamic>>[];
                    for (final club in clubs) {
                      if (club['tenant_id'] != store.tenantId) continue;
                      for (final raw in (club['roster'] as List? ?? [])) {
                        players.add(Map<String, dynamic>.from(raw));
                      }
                    }
                    final ids =
                        players.map((p) => p['player_id'].toString()).toList();
                    return ListView(
                        padding: const EdgeInsets.all(16),
                        children: [
                          header('Squad operations',
                              'Transfer, loan and release with an audit trail'),
                          if (clubsSnapshot.connectionState ==
                              ConnectionState.waiting)
                            const LinearProgressIndicator(),
                          if (clubsSnapshot.hasError)
                            Text(clubsSnapshot.error.toString()),
                          if (players.isEmpty)
                            const Card(
                                child: ListTile(
                                    title: Text('No roster players available'),
                                    subtitle: Text(
                                        'Connect to the server and open Clubs first.'))),
                          if (players.isNotEmpty)
                            DropdownButtonFormField<String>(
                                initialValue:
                                    ids.contains(playerId) ? playerId : null,
                                isExpanded: true,
                                decoration: const InputDecoration(
                                    labelText: 'Player',
                                    prefixIcon: Icon(Icons.person_outline)),
                                items: players
                                    .map((p) => DropdownMenuItem(
                                        value: p['player_id'].toString(),
                                        child: Text(
                                            '${p['name']} • ${p['position']}',
                                            overflow: TextOverflow.ellipsis)))
                                    .toList(),
                                onChanged: (id) {
                                  if (id != null) selectPlayer(id);
                                }),
                          if (historyFuture != null)
                            FutureBuilder<dynamic>(
                                future: historyFuture,
                                builder: (context, snapshot) {
                                  if (snapshot.connectionState ==
                                      ConnectionState.waiting)
                                    return const LinearProgressIndicator();
                                  if (snapshot.hasError)
                                    return Padding(
                                        padding: const EdgeInsets.all(12),
                                        child: Text(snapshot.error.toString()));
                                  if (snapshot.data is! Map)
                                    return const SizedBox.shrink();
                                  final history =
                                      Map<String, dynamic>.from(snapshot.data);
                                  return Column(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.stretch,
                                      children: [
                                        const SizedBox(height: 14),
                                        Card(
                                            child: ListTile(
                                                leading: const Icon(
                                                    Icons.groups,
                                                    color: Color(0xff54e0cf)),
                                                title: Text(
                                                    'Current squad: ${history['current_squad_id'] ?? 'None'}'),
                                                subtitle: Text(
                                                    'League ${history['league_id']} • ${(history['history'] as List).length} audit entries'))),
                                        const SizedBox(height: 14),
                                        DropdownButtonFormField<String>(
                                            initialValue: action,
                                            isExpanded: true,
                                            decoration: const InputDecoration(
                                                labelText: 'Action'),
                                            items: const [
                                              DropdownMenuItem(
                                                  value: 'transfer',
                                                  child: Text('Transfer')),
                                              DropdownMenuItem(
                                                  value: 'loan',
                                                  child: Text('Loan')),
                                              DropdownMenuItem(
                                                  value: 'release',
                                                  child: Text('Release'))
                                            ],
                                            onChanged: (v) {
                                              if (v != null)
                                                setState(() => action = v);
                                            }),
                                        if (action != 'release') ...[
                                          const SizedBox(height: 14),
                                          TextField(
                                              controller: destination,
                                              decoration: const InputDecoration(
                                                  labelText:
                                                      'Destination squad ID',
                                                  helperText:
                                                      'Demo: sq-demo-alpha or sq-demo-beta')),
                                        ],
                                        const SizedBox(height: 14),
                                        TextField(
                                            controller: effective,
                                            keyboardType:
                                                TextInputType.datetime,
                                            decoration: const InputDecoration(
                                                labelText:
                                                    'Effective date (YYYY-MM-DD)',
                                                helperText:
                                                    'Demo transfer window: 2026-10-01 to 2026-10-31')),
                                        if (action == 'loan') ...[
                                          const SizedBox(height: 14),
                                          TextField(
                                              controller: loanEnd,
                                              keyboardType:
                                                  TextInputType.datetime,
                                              decoration: const InputDecoration(
                                                  labelText:
                                                      'Loan end date (YYYY-MM-DD)')),
                                        ],
                                        const SizedBox(height: 14),
                                        TextField(
                                            controller: reason,
                                            maxLines: 2,
                                            decoration: const InputDecoration(
                                                labelText: 'Reason')),
                                        const SizedBox(height: 18),
                                        ElevatedButton.icon(
                                            onPressed: busy
                                                ? null
                                                : () => submit(history),
                                            icon:
                                                const Icon(Icons.save_outlined),
                                            label: Text(busy
                                                ? 'Saving…'
                                                : 'Review roster action')),
                                        header('Audit history',
                                            'Latest roster changes for this player'),
                                        if ((history['history'] as List)
                                            .isEmpty)
                                          const Card(
                                              child: ListTile(
                                                  title:
                                                      Text('No changes yet'))),
                                        ...((history['history'] as List)
                                                .reversed)
                                            .map((entry) => Card(
                                                    child: ListTile(
                                                  title: Text(entry['action']
                                                      .toString()
                                                      .replaceAll('_', ' ')),
                                                  subtitle: Text(
                                                      '${entry['from_squad_id']} → ${entry['to_squad_id'] ?? 'released'}\n${entry['effective_date']} • ${entry['state']}'),
                                                ))),
                                      ]);
                                }),
                        ]);
                  })),
        ]),
      );
}
