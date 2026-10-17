import 'package:flutter/material.dart';
import 'main.dart';
import 'features.dart';
import 'services.dart';

class MainShell extends StatefulWidget {
  const MainShell({super.key});
  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  int current = 0;
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await store.ping();
      if (store.online) await store.sync();
    });
  }

  @override
  Widget build(BuildContext context) {
    final views = [
      const FixturesScreen(),
      const StandingsScreen(),
      const StoreScreen(),
      const ClubsScreen(),
      const ProfileScreen()
    ];
    return Scaffold(
      appBar: AppBar(
          title: const Text('NaSCon 26',
              style: TextStyle(fontSize: 17, fontWeight: FontWeight.bold)),
          actions: [
            IconButton(
                tooltip: 'Sync status',
                icon: Badge(
                    isLabelVisible: store.pending.isNotEmpty,
                    label: Text('${store.pending.length}'),
                    child: const Icon(Icons.sync)),
                onPressed: () => Navigator.push(context,
                    MaterialPageRoute(builder: (_) => const SyncScreen()))),
            IconButton(
                tooltip: 'Server address',
                icon: const Icon(Icons.settings_outlined),
                onPressed: () => Navigator.push(context,
                    MaterialPageRoute(builder: (_) => const ServerSettings()))),
          ]),
      body: Column(children: [
        const SyncBanner(),
        Expanded(child: IndexedStack(index: current, children: views)),
      ]),
      bottomNavigationBar: NavigationBar(
          selectedIndex: current,
          onDestinationSelected: (index) => setState(() => current = index),
          destinations: const [
            NavigationDestination(
                icon: Icon(Icons.calendar_month_outlined), label: 'Fixtures'),
            NavigationDestination(
                icon: Icon(Icons.emoji_events_outlined), label: 'Standings'),
            NavigationDestination(
                icon: Icon(Icons.shopping_bag_outlined), label: 'Store'),
            NavigationDestination(
                icon: Icon(Icons.shield_outlined), label: 'Clubs'),
            NavigationDestination(
                icon: Icon(Icons.person_outline), label: 'Profile'),
          ]),
    );
  }
}

class ServerSettings extends StatefulWidget {
  const ServerSettings({super.key});
  @override
  State<ServerSettings> createState() => _ServerSettingsState();
}

class _ServerSettingsState extends State<ServerSettings> {
  late final address = TextEditingController(text: store.server);
  @override
  void dispose() {
    address.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Server address')),
        body: ListView(padding: const EdgeInsets.all(20), children: [
          const Text('Connect to the team laptop',
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 20)),
          const SizedBox(height: 12),
          const Text(
              'Emulator: http://10.0.2.2:8080\nReal Android phone: http://YOUR-LAPTOP-LAN-IP:8080'),
          const SizedBox(height: 20),
          TextField(
              controller: address,
              decoration: const InputDecoration(labelText: 'API base URL')),
          const SizedBox(height: 20),
          ElevatedButton(
              onPressed: () async {
                try {
                  await store.configureServer(address.text);
                  if (context.mounted)
                    toast(
                        context,
                        store.online
                            ? 'Connected to backend'
                            : 'Saved. Backend currently unreachable.');
                } catch (e) {
                  if (context.mounted) toast(context, e.toString());
                }
              },
              child: const Text('Save and test connection')),
        ]),
      );
}

class SyncScreen extends StatelessWidget {
  const SyncScreen({super.key});
  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Offline & sync')),
        body: AnimatedBuilder(
            animation: store,
            builder: (_, __) =>
                ListView(padding: const EdgeInsets.all(16), children: [
                  const SyncBanner(),
                  Card(
                      child: ListTile(
                          leading: Icon(store.online
                              ? Icons.cloud_done
                              : Icons.cloud_off),
                          title: Text(store.online ? 'Online' : 'Offline'),
                          subtitle: Text(
                              '${store.pending.length} saved actions awaiting sync'))),
                  const SizedBox(height: 12),
                  ElevatedButton.icon(
                      onPressed: store.syncing
                          ? null
                          : () async {
                              await store.ping();
                              await store.sync(retryRejected: true);
                            },
                      icon: const Icon(Icons.sync),
                      label: Text(
                          store.syncing ? 'Syncing…' : 'Sync pending actions')),
                  if (store.lastError.isNotEmpty)
                    Padding(
                        padding: const EdgeInsets.all(12),
                        child: Text(store.lastError,
                            style:
                                const TextStyle(color: Colors.orangeAccent))),
                  const SizedBox(height: 20),
                  const Text('Pending actions',
                      style:
                          TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
                  if (store.pending.isEmpty)
                    const ListTile(title: Text('No pending actions')),
                  ...store.pending.map((a) {
                    final id = a['action_id'].toString();
                    final rejected = store.rejectedIds.contains(id);
                    final result = store.results
                        .where((r) => r['action_id'] == id)
                        .firstOrNull;
                    return Card(
                        child: ListTile(
                      leading:
                          Icon(rejected ? Icons.error_outline : Icons.schedule),
                      title: Text(
                          '${a['type'].toString().replaceAll('_', ' ')} • ${rejected ? 'Needs review' : 'Pending'}'),
                      subtitle: Text(rejected
                          ? readableError(result?['error_code']?.toString(),
                              'Review this action before retrying.')
                          : 'Saved ${a['queued_at']}'),
                      trailing: rejected
                          ? IconButton(
                              tooltip: 'Dismiss rejected action',
                              icon: const Icon(Icons.close),
                              onPressed: () async {
                                final yes = await showDialog<bool>(
                                    context: context,
                                    builder: (c) => AlertDialog(
                                            title: const Text(
                                                'Remove rejected action?'),
                                            content: const Text(
                                                'The server did not apply this action. Removing it only clears this saved request.'),
                                            actions: [
                                              TextButton(
                                                  onPressed: () =>
                                                      Navigator.pop(c, false),
                                                  child: const Text('Keep')),
                                              TextButton(
                                                  onPressed: () =>
                                                      Navigator.pop(c, true),
                                                  child: const Text('Remove'))
                                            ]));
                                if (yes == true)
                                  await store.discardRejected(id);
                              })
                          : null,
                    ));
                  }),
                  const SizedBox(height: 15),
                  const Text('Previous sync results',
                      style:
                          TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
                  ...store.results.take(20).map((r) => ListTile(
                        leading: Icon(r['status'] == 'applied'
                            ? Icons.check_circle_outline
                            : Icons.info_outline),
                        title: Text(
                            '${r['status']} • ${r['resolution'].toString().replaceAll('_', ' ')}'),
                        subtitle: Text(r['status'] == 'rejected'
                            ? readableError(r['error_code']?.toString(),
                                'The server rejected this action.')
                            : 'Action ${r['action_id']}'),
                      )),
                ])),
      );
}

Widget header(String title, String desc) => Padding(
      padding: const EdgeInsets.only(top: 12, bottom: 12),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(title,
            style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold)),
        const SizedBox(height: 4),
        Text(desc, style: const TextStyle(color: Colors.white70)),
      ]),
    );

class SyncBanner extends StatelessWidget {
  const SyncBanner({super.key});
  @override
  Widget build(BuildContext context) => InkWell(
      onTap: () => Navigator.push(
          context, MaterialPageRoute(builder: (_) => const SyncScreen())),
      child: Container(
          color: store.syncing
              ? const Color(0xff174960)
              : store.online
                  ? const Color(0xff10433e)
                  : const Color(0xff574025),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          child: Row(children: [
            Icon(
                store.syncing
                    ? Icons.sync
                    : store.online
                        ? Icons.wifi
                        : Icons.wifi_off,
                size: 18),
            const SizedBox(width: 10),
            Expanded(
                child: Text(
                    store.syncing
                        ? 'Syncing saved actions…'
                        : store.online
                            ? 'Online • ${store.role.replaceAll('_', ' ')}'
                            : 'Offline • cached data',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis)),
            Text('${store.pending.length} pending',
                style:
                    const TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
          ])));
}
