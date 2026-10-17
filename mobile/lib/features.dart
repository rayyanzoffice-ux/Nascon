import 'package:flutter/material.dart';
import 'main.dart';
import 'screens.dart';
import 'actions.dart';
import 'shop.dart';
export 'shop.dart' show StoreScreen;

class FixturesScreen extends StatefulWidget{
  const FixturesScreen({super.key});
  @override State<FixturesScreen> createState()=>_FixturesScreenState();
}
class _FixturesScreenState extends State<FixturesScreen>{
  late Future<dynamic> future;
  @override void initState(){super.initState();refresh();}
  void refresh(){future=store.cached('fixtures','/mobile/v1/fixtures');}
  @override Widget build(BuildContext context)=>RefreshIndicator(
    onRefresh:() async {setState(refresh);await future;},
    child:FutureBuilder<dynamic>(future:future,builder:(context,snapshot){
      final fixtures=snapshot.data is List?snapshot.data as List:[];
      return ListView(padding:const EdgeInsets.all(14),children:[
        header('Fixtures','Live scores and match schedules'),
        if(snapshot.connectionState==ConnectionState.waiting)const LinearProgressIndicator(),
        if(snapshot.hasError)Text(snapshot.error.toString()),
        if(fixtures.isEmpty)const ListTile(leading:Icon(Icons.event_busy),title:Text('No fixtures yet'),subtitle:Text('Connect to your team server to load matches.')),
        ...fixtures.map((match)=>Card(child:ListTile(
          contentPadding:const EdgeInsets.all(18),
          leading:const CircleAvatar(child:Icon(Icons.sports_soccer)),
          title:Text('${match['home']} vs ${match['away']}',style:const TextStyle(fontWeight:FontWeight.bold)),
          subtitle:Text('${match['sport_id']} • ${match['status']}'),
          trailing:Text('${match['home_score']} : ${match['away_score']}',style:const TextStyle(fontSize:19,fontWeight:FontWeight.bold)),
          onTap:()=>Navigator.push(context,MaterialPageRoute(builder:(_)=>MatchScreen(matchId:match['match_id'].toString()))),
        ))),
      ]);
    }),
  );
}

class StandingsScreen extends StatefulWidget{
  const StandingsScreen({super.key});
  @override State<StandingsScreen> createState()=>_StandingsScreenState();
}
class _StandingsScreenState extends State<StandingsScreen>{
  late Future<dynamic> future;
  @override void initState(){super.initState();refresh();}
  void refresh(){future=store.cached('standings','/audit/v1/standings/demo-league');}
  @override Widget build(BuildContext context)=>RefreshIndicator(
    onRefresh:()async{setState(refresh);await future;},
    child:FutureBuilder<dynamic>(future:future,builder:(context,snapshot){
      final rows=(snapshot.data is Map?snapshot.data['table']:null) as List? ?? [];
      return ListView(padding:const EdgeInsets.all(15),children:[
        header('Standings','Demo League • Football'),
        if(snapshot.connectionState==ConnectionState.waiting)const LinearProgressIndicator(),
        if(snapshot.hasError)Text(snapshot.error.toString()),
        if(rows.isEmpty)const ListTile(title:Text('No standings available')),
        const Card(child:Padding(padding:EdgeInsets.all(14),child:Text('TEAM                                    P    GD   PTS',style:TextStyle(fontSize:12,fontWeight:FontWeight.bold)))),
        ...rows.map((r)=>Card(child:ListTile(
          leading:CircleAvatar(child:Text('${r['rank']}')),
          title:Text(r['team_id'].toString(),maxLines:1,overflow:TextOverflow.ellipsis),
          subtitle:Text('${r['status'].toString().replaceAll('_',' ')} • W${r['won']} D${r['drawn']} L${r['lost']}'),
          trailing:Column(mainAxisAlignment:MainAxisAlignment.center,children:[
            Text('${r['points']} pts',style:const TextStyle(fontWeight:FontWeight.bold)),
            Text('GD ${r['diff']}',style:const TextStyle(fontSize:12)),
          ]),
        ))),
      ]);
    }),
  );
}

class ClubsScreen extends StatefulWidget{
  const ClubsScreen({super.key});
  @override State<ClubsScreen> createState()=>_ClubsScreenState();
}
class _ClubsScreenState extends State<ClubsScreen>{
  late Future<dynamic> future;
  @override void initState(){super.initState();future=store.cached('clubs','/mobile/v1/clubs');}
  @override Widget build(BuildContext context)=>FutureBuilder<dynamic>(future:future,builder:(context,snapshot){
    final clubs=snapshot.data is List?snapshot.data as List:[];
    return ListView(padding:const EdgeInsets.all(15),children:[
      header('Clubs','Staff, rosters and home venues'),
      if(snapshot.connectionState==ConnectionState.waiting)const LinearProgressIndicator(),
      if(snapshot.hasError)Text(snapshot.error.toString()),
      ...clubs.map((club)=>Card(child:ExpansionTile(
        leading:const Icon(Icons.shield,color:Color(0xff3dddc9)),
        title:Text(club['name'].toString()),
        subtitle:Text(club['tenant_id'].toString()),
        children:[ListTile(title:const Text('Home venue'),subtitle:Text(club['home_venue'].toString())),
          const ListTile(title:Text('Club staff'),subtitle:Text('Manager • Club Staff')),
          ...((club['roster'] as List?)??[]).map((p)=>ListTile(
            title:Text(p['name'].toString()),subtitle:Text(p['position'].toString()))),
        ],
      ))),
      if(clubs.isEmpty)const ListTile(title:Text('No club information cached')),
    ]);
  });
}

class ProfileScreen extends StatelessWidget{
  const ProfileScreen({super.key});
  @override Widget build(BuildContext context)=>ListView(padding:const EdgeInsets.all(16),children:[
    header('My profile','Role-based access and actions'),
    Card(child:ListTile(leading:const CircleAvatar(child:Icon(Icons.person)),
      title:Text(store.email),subtitle:Text('Role: ${store.role.replaceAll('_',' ')}'))),
    if(store.role=='club_manager'||store.role=='super_admin')
      Card(child:ListTile(leading:const Icon(Icons.groups),title:const Text('Roster management'),
        subtitle:const Text('Transfer, loan or release players'),
        trailing:const Icon(Icons.chevron_right),
        onTap:()=>Navigator.push(context,MaterialPageRoute(builder:(_)=>const RosterScreen())))),
    if(store.role=='league_organizer'||store.role=='super_admin')
      Card(child:ListTile(leading:const Icon(Icons.sports_score),title:const Text('Live scoring'),
        subtitle:const Text('Enter an event or reverse a score'),
        onTap:()=>Navigator.push(context,MaterialPageRoute(builder:(_)=>const MatchScreen(matchId:'demo-match-1'))))),
    Card(child:ListTile(leading:const Icon(Icons.logout),title:const Text('Sign out'),
      onTap:()async{await store.logout();})),
  ]);
}
