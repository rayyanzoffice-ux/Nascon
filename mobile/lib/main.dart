import 'package:flutter/material.dart';
import 'services.dart';
import 'screens.dart';

late final AppStore store;
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  store=AppStore();
  await store.initialize();
  runApp(const NasconApp());
}

class NasconApp extends StatelessWidget {
  const NasconApp({super.key});
  @override Widget build(BuildContext context)=>AnimatedBuilder(
    animation:store,
    builder:(_,__)=>MaterialApp(
      debugShowCheckedModeBanner:false,
      title:'NaSCon LeagueOS',
      theme:ThemeData(useMaterial3:true,brightness:Brightness.dark,
        scaffoldBackgroundColor:const Color(0xff0b1529),
        colorScheme:ColorScheme.fromSeed(seedColor:const Color(0xff3dddc9),brightness:Brightness.dark),
        appBarTheme:const AppBarTheme(backgroundColor:Color(0xff101e35)),
        inputDecorationTheme:const InputDecorationTheme(border:OutlineInputBorder()),
        cardTheme:CardThemeData(color:const Color(0xff152842),
          shape:RoundedRectangleBorder(borderRadius:BorderRadius.circular(16))),
        elevatedButtonTheme:ElevatedButtonThemeData(style:ElevatedButton.styleFrom(
          minimumSize:const Size.fromHeight(48),backgroundColor:const Color(0xff3dddc9),foregroundColor:Colors.black))),
      home:store.token.isEmpty?const LoginScreen():const MainShell(),
    ));
}

void toast(BuildContext context,String message){
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content:Text(message)));
}

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});
  @override State<LoginScreen> createState()=>_LoginScreenState();
}
class _LoginScreenState extends State<LoginScreen>{
  final mail=TextEditingController(text:'organizer@nascon.test');
  final password=TextEditingController(text:'Nascon@26');
  bool busy=false;
  @override void dispose(){mail.dispose();password.dispose();super.dispose();}
  @override Widget build(BuildContext context)=>Scaffold(
    body:SafeArea(child:Center(child:SingleChildScrollView(
      padding:const EdgeInsets.all(24),child:ConstrainedBox(constraints:const BoxConstraints(maxWidth:440),
      child:Column(crossAxisAlignment:CrossAxisAlignment.stretch,children:[
        const Icon(Icons.sports_soccer,size:64,color:Color(0xff3dddc9)),
        const SizedBox(height:18),
        const Text('LEAGUE OS',textAlign:TextAlign.center,style:TextStyle(fontSize:34,fontWeight:FontWeight.bold,letterSpacing:3)),
        const Text('NaSCon 2026 • Club Operations',textAlign:TextAlign.center),
        const SizedBox(height:30),
        TextField(controller:mail,decoration:const InputDecoration(labelText:'Email',prefixIcon:Icon(Icons.mail_outline))),
        const SizedBox(height:14),
        TextField(controller:password,obscureText:true,decoration:const InputDecoration(labelText:'Password',prefixIcon:Icon(Icons.lock_outline))),
        const SizedBox(height:20),
        ElevatedButton(onPressed:busy?null:() async {
          setState(()=>busy=true);
          try {await store.login(mail.text.trim(),password.text);}
          catch(e){if(context.mounted)toast(context,e.toString());}
          if(mounted)setState(()=>busy=false);
        },child:Text(busy?'Signing in…':'Sign in')),
        const SizedBox(height:18),
        OutlinedButton.icon(onPressed:()=>Navigator.push(context,MaterialPageRoute(builder:(_)=>const ServerSettings())),
          icon:const Icon(Icons.settings_ethernet),label:const Text('Configure server address')),
        const SizedBox(height:12),
        const Text('Demo: admin, organizer, manager, player or viewer @nascon.test',textAlign:TextAlign.center),
      ]))))),
  );
}
