import 'package:flutter/material.dart';
import 'main.dart';
import 'screens.dart';

class RosterScreen extends StatefulWidget {
  const RosterScreen({super.key});
  @override State<RosterScreen> createState()=>_RosterScreenState();
}
class _RosterScreenState extends State<RosterScreen>{
  String player='player-demo-1';
  String action='transfer';
  final reason=TextEditingController(text:'Tactical squad adjustment');
  @override void dispose(){reason.dispose();super.dispose();}
  Future<void> submit() async{
    final ok=await showDialog<bool>(context:context,builder:(c)=>AlertDialog(
      title:const Text('Confirm roster change'),
      content:Text('Proceed with $action for $player? This will be recorded in the audit history.'),
      actions:[TextButton(onPressed:()=>Navigator.pop(c,false),child:const Text('Cancel')),
        FilledButton(onPressed:()=>Navigator.pop(c,true),child:const Text('Confirm'))]));
    if(ok!=true||!mounted)return;
    final now=DateTime.now();
    final day=now.toIso8601String().substring(0,10);
    final end=now.add(const Duration(days:7)).toIso8601String().substring(0,10);
    final request={
      'request_id':'mobile-tr-${now.microsecondsSinceEpoch}',
      'league_id':'demo-roster','player_id':player,
      'type':action,'from_squad_id':'sq-demo-alpha',
      'to_squad_id':action=='release'?null:'sq-demo-beta',
      'effective_date':day,
      'loan_end_date':action=='loan'?end:null,
      'reason':reason.text,'requested_by':store.email,
    };
    await store.queueAction('roster_transfer',request,0);
    if(mounted)toast(context,'Roster change queued. Check Sync status for results.');
  }
  @override Widget build(BuildContext context)=>Scaffold(
    appBar:AppBar(title:const Text('Roster management')),
    body:ListView(padding:const EdgeInsets.all(18),children:[
      header('Alpha Sports Club','Manage registrations and loans'),
      const Card(child:ListTile(leading:Icon(Icons.groups),
        title:Text('Active squad: Alpha'),
        subtitle:Text('Target squad: Beta Athletics • Demo scenario'))),
      const SizedBox(height:22),
      DropdownButtonFormField<String>(
        initialValue:player,decoration:const InputDecoration(labelText:'Player'),
        items:const [DropdownMenuItem(value:'player-demo-1',child:Text('Ayaan Khan')),
          DropdownMenuItem(value:'player-demo-2',child:Text('Zain Ahmed'))],
        onChanged:(v){if(v!=null)setState(()=>player=v);},
      ),
      const SizedBox(height:18),
      DropdownButtonFormField<String>(
        initialValue:action,decoration:const InputDecoration(labelText:'Action'),
        items:const [DropdownMenuItem(value:'transfer',child:Text('Transfer')),
          DropdownMenuItem(value:'loan',child:Text('Loan for 7 days')),
          DropdownMenuItem(value:'release',child:Text('Release'))],
        onChanged:(v){if(v!=null)setState(()=>action=v);},
      ),
      const SizedBox(height:18),
      TextField(controller:reason,maxLines:2,decoration:const InputDecoration(labelText:'Reason')),
      const SizedBox(height:20),
      ElevatedButton.icon(onPressed:submit,icon:const Icon(Icons.save_outlined),
        label:const Text('Save roster action')),
      const SizedBox(height:12),
      const Text('When offline, your change stays in SQLite until you sync. Rejected changes display the server reason.',
        style:TextStyle(color:Colors.white70)),
    ]),
  );
}
