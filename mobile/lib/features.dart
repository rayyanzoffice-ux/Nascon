import 'package:flutter/material.dart';
import 'main.dart';
import 'screens.dart';
import 'actions.dart';
export 'shop.dart' show StoreScreen;

class FixturesScreen extends StatefulWidget {
  const FixturesScreen({super.key});
  @override
  State<FixturesScreen> createState() => _FixturesScreenState();
}

class _FixturesScreenState extends State<FixturesScreen> {
  late Future<dynamic> future;
  @override
  void initState() {
    super.initState();
    refresh();
  }

  void refresh() {
    future = store.cached('fixtures', '/mobile/v1/fixtures');
  }

  @override
  Widget build(BuildContext context) => RefreshIndicator(
        onRefresh: () async {
          setState(refresh);
          await future;
        },
        child: FutureBuilder<dynamic>(
            future: future,
            builder: (context, snapshot) {
              final fixtures =
                  snapshot.data is List ? snapshot.data as List : [];
              return ListView(padding: const EdgeInsets.all(14), children: [
                header('Matchday', 'Fixtures, results and live scores'),
                if (snapshot.connectionState == ConnectionState.waiting)
                  const LinearProgressIndicator(),
                if (snapshot.hasError) Text(snapshot.error.toString()),
                if (fixtures.isEmpty)
                  const ListTile(
                      leading: Icon(Icons.event_busy),
                      title: Text('No fixtures yet'),
                      subtitle:
                          Text('Connect to your team server to load matches.')),
                ...fixtures.map((match) => Card(
                        child: InkWell(
                      borderRadius: BorderRadius.circular(18),
                      onTap: () => Navigator.push(
                          context,
                          MaterialPageRoute(
                              builder: (_) => MatchScreen(
                                  matchId: match['match_id'].toString()))),
                      child: Padding(
                          padding: const EdgeInsets.all(17),
                          child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(children: [
                                  const Icon(Icons.sports_score,
                                      size: 18, color: Color(0xff54e0cf)),
                                  const SizedBox(width: 8),
                                  Expanded(
                                      child: Text(
                                          '${match['sport_id']} • ${match['league_id']}',
                                          maxLines: 1,
                                          overflow: TextOverflow.ellipsis,
                                          style: const TextStyle(
                                              color: Colors.white70,
                                              fontSize: 12))),
                                  Container(
                                      padding: const EdgeInsets.symmetric(
                                          horizontal: 9, vertical: 5),
                                      decoration: BoxDecoration(
                                          color: const Color(0xff1d4251),
                                          borderRadius:
                                              BorderRadius.circular(12)),
                                      child: Text(
                                          match['status']
                                              .toString()
                                              .replaceAll('_', ' ')
                                              .toUpperCase(),
                                          style: const TextStyle(
                                              fontSize: 10,
                                              fontWeight: FontWeight.bold))),
                                ]),
                                const SizedBox(height: 16),
                                Row(children: [
                                  Expanded(
                                      child: Text('${match['home']}',
                                          maxLines: 2,
                                          overflow: TextOverflow.ellipsis,
                                          style: const TextStyle(
                                              fontWeight: FontWeight.bold,
                                              fontSize: 16))),
                                  Padding(
                                      padding: const EdgeInsets.symmetric(
                                          horizontal: 10),
                                      child: Text(
                                          '${match['home_score']}  :  ${match['away_score']}',
                                          style: const TextStyle(
                                              fontWeight: FontWeight.w900,
                                              fontSize: 23,
                                              color: Color(0xff54e0cf)))),
                                  Expanded(
                                      child: Text('${match['away']}',
                                          textAlign: TextAlign.end,
                                          maxLines: 2,
                                          overflow: TextOverflow.ellipsis,
                                          style: const TextStyle(
                                              fontWeight: FontWeight.bold,
                                              fontSize: 16))),
                                ]),
                                const SizedBox(height: 12),
                                Row(children: [
                                  Expanded(
                                      child: Text(
                                          match['start_time']?.toString() ??
                                              'Time to be announced',
                                          style: const TextStyle(
                                              fontSize: 12,
                                              color: Colors.white70))),
                                  const Text('VIEW MATCH  ›',
                                      style: TextStyle(
                                          fontSize: 11,
                                          fontWeight: FontWeight.bold,
                                          color: Color(0xff54e0cf)))
                                ]),
                              ])),
                    ))),
              ]);
            }),
      );
}

class StandingsScreen extends StatefulWidget {
  const StandingsScreen({super.key});
  @override
  State<StandingsScreen> createState() => _StandingsScreenState();
}

class _StandingsScreenState extends State<StandingsScreen> {
  late Future<dynamic> leaguesFuture;
  late Future<dynamic> fixturesFuture;
  late Future<dynamic> future;
  String leagueId = 'demo-league';
  @override
  void initState() {
    super.initState();
    refresh();
  }

  void refresh() {
    leaguesFuture = store.cached('leagues', '/mobile/v1/leagues');
    fixturesFuture = store.cached('fixtures', '/mobile/v1/fixtures');
    future =
        store.cached('standings_$leagueId', '/audit/v1/standings/$leagueId');
  }

  void chooseLeague(String id) {
    setState(() {
      leagueId = id;
      future = store.cached('standings_$id', '/audit/v1/standings/$id');
    });
  }

  @override
  Widget build(BuildContext context) => RefreshIndicator(
        onRefresh: () async {
          setState(refresh);
          await future;
        },
        child: FutureBuilder<dynamic>(
            future: future,
            builder: (context, snapshot) {
              final rows = (snapshot.data is Map
                      ? snapshot.data['table']
                      : null) as List? ??
                  [];
              return ListView(padding: const EdgeInsets.all(15), children: [
                header('Standings', 'Points, form and qualification'),
                FutureBuilder<dynamic>(
                    future: leaguesFuture,
                    builder: (context, leagueSnapshot) {
                      final leagues = leagueSnapshot.data is List
                          ? leagueSnapshot.data as List
                          : [];
                      if (leagues.isEmpty) return const SizedBox.shrink();
                      final ids = leagues
                          .map((e) => e['league_id'].toString())
                          .toList();
                      return DropdownButtonFormField<String>(
                          initialValue:
                              ids.contains(leagueId) ? leagueId : null,
                          isExpanded: true,
                          decoration: const InputDecoration(
                              labelText: 'League',
                              prefixIcon: Icon(Icons.emoji_events_outlined)),
                          items: ids
                              .map((id) => DropdownMenuItem(
                                  value: id,
                                  child: Text(id,
                                      overflow: TextOverflow.ellipsis)))
                              .toList(),
                          onChanged: (id) {
                            if (id != null) chooseLeague(id);
                          });
                    }),
                const SizedBox(height: 12),
                if (snapshot.connectionState == ConnectionState.waiting)
                  const LinearProgressIndicator(),
                if (snapshot.hasError) Text(snapshot.error.toString()),
                if (rows.isEmpty)
                  const ListTile(
                      title: Text('No standings available'),
                      subtitle:
                          Text('Pull to refresh after the league is set up.')),
                if (rows.isNotEmpty)
                  Card(
                      child: Padding(
                          padding: const EdgeInsets.all(14),
                          child: Row(children: [
                            const Expanded(
                                child: Text('TEAM',
                                    style: TextStyle(
                                        fontSize: 12,
                                        fontWeight: FontWeight.bold))),
                            Text('P   DIFF   PTS',
                                style: TextStyle(
                                    fontSize: 12,
                                    fontWeight: FontWeight.bold,
                                    color: Colors.white70)),
                          ]))),
                ...rows.map((r) => Card(
                        child: ListTile(
                      contentPadding: const EdgeInsets.symmetric(
                          horizontal: 12, vertical: 5),
                      leading:
                          CircleAvatar(radius: 19, child: Text('${r['rank']}')),
                      title: Text(r['team_id'].toString(),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontWeight: FontWeight.bold)),
                      subtitle: Text(
                          '${r['status'].toString().replaceAll('_', ' ')} • ${r['played']} played',
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis),
                      trailing: Text('${r['points']} PTS\n${r['diff']} DIFF',
                          textAlign: TextAlign.end,
                          style: const TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.bold,
                              color: Color(0xff54e0cf))),
                    ))),
                header('League matches', 'Open a match from the table'),
                FutureBuilder<dynamic>(
                    future: fixturesFuture,
                    builder: (context, matchSnapshot) {
                      final matches = matchSnapshot.data is List
                          ? matchSnapshot.data as List
                          : [];
                      final leagueMatches = matches
                          .where((m) => m['league_id'] == leagueId)
                          .toList();
                      if (leagueMatches.isEmpty)
                        return const ListTile(
                            title: Text('No cached matches for this league'));
                      return Column(
                          children: leagueMatches
                              .map((m) => Card(
                                      child: ListTile(
                                    title: Text('${m['home']} vs ${m['away']}',
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis),
                                    subtitle: Text(m['status']
                                        .toString()
                                        .replaceAll('_', ' ')),
                                    trailing: const Icon(Icons.chevron_right),
                                    onTap: () => Navigator.push(
                                        context,
                                        MaterialPageRoute(
                                            builder: (_) => MatchScreen(
                                                matchId:
                                                    m['match_id'].toString()))),
                                  )))
                              .toList());
                    }),
              ]);
            }),
      );
}

class ClubsScreen extends StatefulWidget {
  const ClubsScreen({super.key});
  @override
  State<ClubsScreen> createState() => _ClubsScreenState();
}

class _ClubsScreenState extends State<ClubsScreen> {
  late Future<dynamic> future;
  @override
  void initState() {
    super.initState();
    refresh();
  }

  void refresh() {
    future = store.clubsWithRosterCache();
  }

  @override
  Widget build(BuildContext context) => RefreshIndicator(
      onRefresh: () async {
        setState(refresh);
        await future;
      },
      child: FutureBuilder<dynamic>(
          future: future,
          builder: (context, snapshot) {
            final clubs = snapshot.data is List ? snapshot.data as List : [];
            return ListView(padding: const EdgeInsets.all(15), children: [
              header('Clubs', 'Staff, rosters and home venues'),
              if (snapshot.connectionState == ConnectionState.waiting)
                const LinearProgressIndicator(),
              if (snapshot.hasError) Text(snapshot.error.toString()),
              ...clubs.map((club) => Card(
                      child: ExpansionTile(
                    leading: CircleAvatar(
                        backgroundColor: const Color(0xff1a4855),
                        child: Text(
                            club['name']
                                .toString()
                                .substring(0, 1)
                                .toUpperCase(),
                            style: const TextStyle(color: Color(0xff54e0cf)))),
                    title: Text(club['name'].toString()),
                    subtitle: Text(club['tenant_id'] == store.tenantId
                        ? 'Your organization • ${club['tenant_id']}'
                        : club['tenant_id'].toString()),
                    children: [
                      ListTile(
                          leading: const Icon(Icons.stadium_outlined),
                          title: const Text('Home venue'),
                          subtitle: Text(club['home_venue'].toString())),
                      const ListTile(
                          title: Text('Club staff',
                              style: TextStyle(fontWeight: FontWeight.bold))),
                      ...((club['staff'] as List?) ?? []).map((person) =>
                          ListTile(
                              leading: const Icon(Icons.badge_outlined),
                              title: Text(person['name'].toString()),
                              subtitle: Text(person['role'].toString()))),
                      const ListTile(
                          title: Text('Roster',
                              style: TextStyle(fontWeight: FontWeight.bold))),
                      ...((club['roster'] as List?) ?? []).map((p) => ListTile(
                          leading: const Icon(Icons.person_outline),
                          title: Text(p['name'].toString()),
                          subtitle:
                              Text('${p['position']} • ${p['player_id']}'))),
                    ],
                  ))),
              if (clubs.isEmpty)
                const ListTile(title: Text('No club information cached')),
            ]);
          }));
}

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});
  @override
  Widget build(BuildContext context) =>
      ListView(padding: const EdgeInsets.all(16), children: [
        header('My profile', 'Role-based access and actions'),
        Card(
            child: ListTile(
                leading: const CircleAvatar(child: Icon(Icons.person)),
                title: Text(store.email),
                subtitle: Text(
                    'Role: ${store.role.replaceAll('_', ' ')}\nOrganization: ${store.tenantId}'))),
        if (store.role == 'club_manager' || store.role == 'super_admin')
          Card(
              child: ListTile(
                  leading: const Icon(Icons.groups),
                  title: const Text('Roster management'),
                  subtitle: const Text('Transfer, loan or release players'),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () => Navigator.push(
                      context,
                      MaterialPageRoute(
                          builder: (_) => const RosterScreen())))),
        if (store.role == 'league_organizer' || store.role == 'super_admin')
          Card(
              child: ListTile(
                  leading: const Icon(Icons.sports_score),
                  title: const Text('Live scoring'),
                  subtitle: const Text('Enter an event or reverse a score'),
                  onTap: () => Navigator.push(
                      context,
                      MaterialPageRoute(
                          builder: (_) =>
                              const MatchScreen(matchId: 'demo-match-1'))))),
        Card(
            child: ListTile(
                leading: const Icon(Icons.logout),
                title: const Text('Sign out'),
                onTap: () async {
                  await store.logout();
                })),
      ]);
}
