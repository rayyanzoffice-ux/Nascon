import 'dart:async';
import 'package:flutter/material.dart';
import 'main.dart';
import 'screens.dart';
export 'roster_screen.dart' show RosterScreen;

class MatchScreen extends StatefulWidget{
  final String matchId;
  const MatchScreen({super.key,required this.matchId});
  @override State<MatchScreen> createState()=>_MatchScreenState();
}
class _MatchScreenState extends State<MatchScreen>{
  late Future<dynamic> future;
  dynamic current;
  Timer? poll;
  @override void initState(){
    super.initState();
    refresh();
    poll=Timer.periodic(const Duration(seconds:4),(_) {if(mounted && store.online)setState(refresh);});
  }
  void refresh(){future=store.cached('match_${widget.matchId}','/audit/v1/score/${widget.matchId}');}
  @override void dispose(){poll?.cancel();super.dispose();}

  Future<void> action(String kind) async{
    if(current==null)return;
    final events=(current['events'] as List);
    final id='mobile-${DateTime.now().microsecondsSinceEpoch}';
    Map<String,dynamic> payload;
    if(kind=='compensation'){
      final targets=events.where((e)=>e['type']=='score' && e['compensated']==false).toList();
      if(targets.isEmpty){toast(context,'No scoring event available to reverse');return;}
      payload={'compensates':targets.last['event_id'],'reason':'Score corrected by organizer'};
    }else{
      payload={'team_id':current['home']['team_id'],'event_type':'goal'};
    }
    final event={'event_id':id,'match_id':widget.matchId,'type':kind,'payload':payload};
    await store.queueAction('score_event',event,current['version'] as int);
    if(mounted){
      toast(context,store.online?'Score action submitted to sync':'Saved offline. It will sync when connected.');
      setState(refresh);
    }
  }

  @override Widget build(BuildContext context)=>Scaffold(
    appBar:AppBar(title:const Text('Match centre')),
    body:FutureBuilder<dynamic>(future:future,builder:(context,snapshot){
      if(snapshot.data is Map)current=snapshot.data;
      if(current==null)return Center(child:Text(snapshot.hasError?snapshot.error.toString():'Loading match…'));
      final h=current['home'],a=current['away'];
      return ListView(padding:const EdgeInsets.all(16),children:[
        header('Live match','${current['sport_id']} • ${current['status'].toString().replaceAll('_',' ')}'),
        Card(child:Padding(padding:const EdgeInsets.symmetric(vertical:35,horizontal:12),
          child:Row(mainAxisAlignment:MainAxisAlignment.spaceEvenly,children:[
            Expanded(child:Text(h['team_id'].toString(),textAlign:TextAlign.center)),
            Text('${h['score']}  :  ${a['score']}',
              style:const TextStyle(fontSize:34,fontWeight:FontWeight.w900,color:Color(0xff3dddc9))),
            Expanded(child:Text(a['team_id'].toString(),textAlign:TextAlign.center)),
          ]))),
        if(store.role=='league_organizer'||store.role=='super_admin')...[
          const SizedBox(height:14),
          ElevatedButton.icon(onPressed:()=>action('score'),icon:const Icon(Icons.add_circle),
            label:const Text('Record home-team goal')),
          const SizedBox(height:8),
          OutlinedButton.icon(onPressed:()=>action('compensation'),icon:const Icon(Icons.undo),
            label:const Text('Reverse latest score')),
        ],
        header('Event timeline','Signed append-only match history'),
        ...((current['events'] as List).reversed).map((e)=>Card(child:ListTile(
          leading:Icon(e['compensated']==true?Icons.undo:Icons.bolt),
          title:Text(e['type'].toString().replaceAll('_',' ')),
          subtitle:Text(e['payload'].toString()),
          trailing:Text('#${e['sequence']}'),
        ))),
        const Card(child:ListTile(leading:Icon(Icons.shopping_bag),
          title:Text('Official jersey'),subtitle:Text('Visit the Store tab to purchase club merchandise'))),
      ]);
    }),
  );
}
