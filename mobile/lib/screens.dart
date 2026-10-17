import 'package:flutter/material.dart';
import 'main.dart';
import 'features.dart';

class MainShell extends StatefulWidget {
  const MainShell({super.key});
  @override State<MainShell> createState()=>_MainShellState();
}
class _MainShellState extends State<MainShell>{
  int current=0;
  @override void initState(){
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await store.ping();
      if(store.online) await store.sync();
    });
  }
  @override Widget build(BuildContext context){
    final views=[const FixturesScreen(),const StandingsScreen(),const StoreScreen(),const ClubsScreen(),const ProfileScreen()];
    return Scaffold(
      appBar:AppBar(title:const Text('NaSCon • LEAGUE OS',style:TextStyle(fontSize:17,fontWeight:FontWeight.bold)),
      actions:[
        IconButton(tooltip:'Sync status',icon:Badge(isLabelVisible:store.pending.isNotEmpty,
          label:Text('${store.pending.length}'),child:const Icon(Icons.sync)),
          onPressed:()=>Navigator.push(context,MaterialPageRoute(builder:(_)=>const SyncScreen()))),
        IconButton(tooltip:'Server address',icon:const Icon(Icons.settings_outlined),
          onPressed:()=>Navigator.push(context,MaterialPageRoute(builder:(_)=>const ServerSettings()))),
      ]),
      body:Column(children:[
        InkWell(onTap:()=>Navigator.push(context,MaterialPageRoute(builder:(_)=>const SyncScreen())),
          child:Container(color:store.online?const Color(0xff11433f):const Color(0xff55371f),
          padding:const EdgeInsets.all(10),child:Row(children:[
            Icon(store.online?Icons.wifi:Icons.wifi_off,size:18),
            const SizedBox(width:10),
            Expanded(child:Text(store.syncing?'Syncing…':store.online?'Online • ${store.role.replaceAll('_',' ')}':'Offline • showing cached data')),
            Text('${store.pending.length} pending',style:const TextStyle(fontSize:12))]))),
        Expanded(child:IndexedStack(index:current,children:views)),
      ]),
      bottomNavigationBar:NavigationBar(selectedIndex:current,onDestinationSelected:(index)=>setState(()=>current=index),
        destinations:const [
          NavigationDestination(icon:Icon(Icons.calendar_month_outlined),label:'Fixtures'),
          NavigationDestination(icon:Icon(Icons.emoji_events_outlined),label:'Standings'),
          NavigationDestination(icon:Icon(Icons.shopping_bag_outlined),label:'Store'),
          NavigationDestination(icon:Icon(Icons.shield_outlined),label:'Clubs'),
          NavigationDestination(icon:Icon(Icons.person_outline),label:'Profile'),
        ]),
    );
  }
}

class ServerSettings extends StatefulWidget {
  const ServerSettings({super.key});
  @override State<ServerSettings> createState()=>_ServerSettingsState();
}
class _ServerSettingsState extends State<ServerSettings>{
  late final address=TextEditingController(text:store.server);
  @override void dispose(){address.dispose();super.dispose();}
  @override Widget build(BuildContext context)=>Scaffold(
    appBar:AppBar(title:const Text('Server address')),
    body:Padding(padding:const EdgeInsets.all(20),child:Column(crossAxisAlignment:CrossAxisAlignment.stretch,children:[
      const Text('Connect to the team laptop',style:TextStyle(fontWeight:FontWeight.bold,fontSize:20)),
      const SizedBox(height:12),
      const Text('Emulator: http://10.0.2.2:8080\nReal Android phone: http://YOUR-LAPTOP-LAN-IP:8080'),
      const SizedBox(height:20),
      TextField(controller:address,decoration:const InputDecoration(labelText:'API base URL')),
      const SizedBox(height:20),
      ElevatedButton(onPressed:() async {
        await store.configureServer(address.text);
        if(context.mounted)toast(context,store.online?'Connected to backend':'Saved. Backend currently unreachable.');
      },child:const Text('Save and test connection')),
    ])),
  );
}

class SyncScreen extends StatelessWidget {
  const SyncScreen({super.key});
  @override Widget build(BuildContext context)=>Scaffold(
    appBar:AppBar(title:const Text('Offline & sync')),
    body:AnimatedBuilder(animation:store,builder:(_,__)=>ListView(padding:const EdgeInsets.all(16),children:[
      Card(child:ListTile(leading:Icon(store.online?Icons.cloud_done:Icons.cloud_off),
        title:Text(store.online?'Online':'Offline'),subtitle:Text('${store.pending.length} saved actions awaiting sync'))),
      const SizedBox(height:12),
      ElevatedButton.icon(onPressed:store.syncing?null:()=>store.sync(),
        icon:const Icon(Icons.sync),label:Text(store.syncing?'Syncing…':'Sync pending actions')),
      const SizedBox(height:20),const Text('Pending actions',style:TextStyle(fontSize:20,fontWeight:FontWeight.bold)),
      if(store.pending.isEmpty)const ListTile(title:Text('No pending actions')),
      ...store.pending.map((a)=>ListTile(
        leading:const Icon(Icons.schedule),
        title:Text(a['type'].toString().replaceAll('_',' ')),
        subtitle:Text('Queued: ${a['queued_at']}'),
      )),
      const SizedBox(height:15),
      const Text('Previous sync results',style:TextStyle(fontSize:20,fontWeight:FontWeight.bold)),
      ...store.results.map((r)=>ListTile(
        leading:Icon(r['status']=='applied'?Icons.check_circle_outline:Icons.info_outline),
        title:Text('${r['status']} — ${r['action_id']}'),
        subtitle:Text(r['error_code']?.toString().replaceAll('_',' ') ?? r['resolution'].toString()),
      )),
    ])),
  );
}

Widget header(String title,String desc)=>Padding(
  padding:const EdgeInsets.only(top:12,bottom:12),
  child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
    Text(title,style:const TextStyle(fontSize:24,fontWeight:FontWeight.bold)),
    const SizedBox(height:4),Text(desc,style:const TextStyle(color:Colors.white70)),
  ]),
);
